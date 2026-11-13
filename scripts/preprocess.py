#!/usr/bin/env python3
"""Bereitet den Rohabzug von fotbal.cz zu einem kompakten data.json für die Webseite auf.

Aufruf: python3 preprocess.py rohdaten.json[.gz] okresy.json kraje.json data.json
"""
import gzip, json, re, sys
from collections import Counter, defaultdict

raw_path, okresy_path, kraje_path, out_path = sys.argv[1:5]
op = gzip.open if raw_path.endswith('.gz') else open
with op(raw_path, 'rt', encoding='utf-8') as f:
    R = json.load(f)

subjects = {s['id']: s for s in R['subjects']}
clubs = R['clubs']  # uuid -> [name, lat, lon]

# ---------- Wettbewerbe vereinheitlichen ----------
comps = []   # dicts
matches = [] # (compIdx, round, homeName, homeClub, awayName, awayClub, score, dt, venue, spectators)
for c in R['comps']:
    comps.append({'id': c['id'], 'code': c.get('code') or '', 'name': c['name'], 'subj': c['subj']})
for m in R['matches']:
    ci, rnd, h, g, score, dt, v, spec, mid = m
    th, tg = R['teams'][h], R['teams'][g]
    matches.append((ci, rnd, th[0], th[1], tg[0], tg[1], score, dt, R['venues'][v] if v >= 0 else '', spec))
extra = R.get('extra') or {}
off = len(comps)
for c in extra.get('comps', []):
    name = re.sub(r'^90/100\s+', '', c['name'])
    comps.append({'id': c['id'], 'code': c.get('code') or '', 'name': name, 'subj': c['subj']})
for m in extra.get('matches', []):
    ci, rnd, hn, hc, an, ac, score, dt, venue, spec, mid = m
    matches.append((ci + off, rnd, hn, hc, an, ac, score, dt, venue, spec))

# ---------- Kategorie und Ligaebene ----------
CATS = ['Männer', 'Frauen', 'Dorost U19/U17', 'Žáci U15/U13', 'Přípravka U11 und jünger', 'Futsal/Sonstiges']

def classify(c):
    n = c['name'].lower()
    code = c['code'][:1]
    cup = bool(re.search(r'pohár|cup|baráž', n)) or code in ('Z', 'K')
    if re.search(r'futsal|malá kopaná|veterán|old ?boys|stará garda|gentleman|u-?40|\+3[05]', n):
        cat = 5
    elif re.search(r'přípravk|přípravek|bambin|u ?1[01]\b|u ?[6-9]\b|minižá|\d-\d+ let', n) or code in ('G', 'H', 'Ř'):
        cat = 4
    elif re.search(r'žák|žačk|u ?1[2-5]\b', n) or code in ('E', 'F', 'Ň', 'Š'):
        cat = 3
    elif re.search(r'doros|junior|u ?1[6-9]\b', n) or code in ('C', 'D', 'L'):
        cat = 2
    elif re.search(r'\bžen|ženy|žen\b|lyga', n) or code in ('J',):
        cat = 1
    elif code == 'Z':
        cat = 0
    else:
        cat = 0
    level = None
    m = re.search(r'(?<!\d)(\d{1,2})\s*\.?\s*(?:[^\d]{0,40}?)\b(?:liga|fl)\b', n)
    if 'chance liga' in n:
        level = 1
    elif 'národní liga' in n:
        level = 2
    elif m and 1 <= int(m.group(1)) <= 12:
        level = int(m.group(1))
    elif cat == 0 and not cup:
        if re.search(r'krajsk\w* přebor|přebor\b.*kraj', n): level = 5
        elif re.search(r'\bi\.?\s*a\b|1\.?\s*a\s*tř', n): level = 6
        elif re.search(r'\bi\.?\s*b\b|1\.?\s*b\s*tř', n): level = 7
        elif re.search(r'okresní přebor|^op\b', n): level = 8
        elif re.search(r'\bii\.?\s*tř|2\.?\s*tř', n): level = 8
        elif re.search(r'\biii\.?\s*tř|3\.?\s*tř', n): level = 9
        elif re.search(r'\biv\.?\s*tř|4\.?\s*tř', n): level = 10
    if cup:
        level = None
    return cat, level, cup

# Lesbarer Kurzname: Sponsorenzeug und Code-Präfixe entfernen
def short_name(c):
    n = c['name']
    n = re.sub(r'^\s*\d{1,2}\.\s*LIGA\s+[A-ZČŠŘŽÝÁÍÉÚŮ\s\-]*?-\s*[A-Z]\d[A-Z]\s+', '', n)  # "6.LIGA SELECT - A2A "
    n = re.sub(r'\s+', ' ', n).strip()
    return n

# ---------- Orte und Koordinaten ----------
def norm(s):
    s = s.lower()
    tr = str.maketrans('áčďéěíňóřšťúůýž', 'acdeeinorstuuyz')
    return re.sub(r'[^a-z0-9 ]', ' ', s.translate(tr)).strip()

club_by_norm = defaultdict(list)
for uid, (name, lat, lon) in clubs.items():
    club_by_norm[norm(name)].append(uid)

def coords_for(venue, home_club):
    if home_club and home_club in clubs:
        return clubs[home_club][1], clubs[home_club][2]
    if venue:
        nv = norm(venue)
        for n, uids in club_by_norm.items():
            if nv and nv in n:
                return clubs[uids[0]][1], clubs[uids[0]][2]
    return None

# Punkt-in-Polygon
def load_polys(path):
    G = json.load(open(path))
    out = []
    for f in G['features']:
        g = f['geometry']
        polys = g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]
        xs = [p[0] for poly in polys for p in poly[0]]; ys = [p[1] for poly in polys for p in poly[0]]
        out.append({'polys': polys, 'bbox': (min(xs), min(ys), max(xs), max(ys))})
    return out

def in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]; xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside

def locate(lat, lon, P):
    for k, p in enumerate(P):
        b = p['bbox']
        if not (b[0] <= lon <= b[2] and b[1] <= lat <= b[3]): continue
        for poly in p['polys']:
            if in_ring(lon, lat, poly[0]) and not any(in_ring(lon, lat, h) for h in poly[1:]):
                return k
    return -1

OK = load_polys(okresy_path)
KR = load_polys(kraje_path)

places = {}   # (venueName, lat, lon) -> idx
place_list = []
match_place = []
for m in matches:
    ci, rnd, hn, hc, an, ac, score, dt, venue, spec = m
    xy = coords_for(venue, hc)
    if not xy:
        match_place.append(-1); continue
    key = (venue or hn, round(xy[0], 4), round(xy[1], 4))
    if key not in places:
        places[key] = len(place_list)
        place_list.append({'name': key[0], 'lat': xy[0], 'lon': xy[1], 'ok': locate(xy[0], xy[1], OK), 'kr': locate(xy[0], xy[1], KR), 'home': Counter()})
    pi = places[key]
    place_list[pi]['home'][hn] += 1
    match_place.append(pi)

# Polygone benennen: Mehrheit der Wettbewerbs-Verbände, deren Heimspiele darin liegen
ok_votes = defaultdict(Counter); kr_votes = defaultdict(Counter)
for m, pi in zip(matches, match_place):
    if pi < 0: continue
    s = subjects.get(comps[m[0]]['subj'])
    if not s: continue
    p = place_list[pi]
    if s['type'] == 'OFS' and p['ok'] >= 0: ok_votes[p['ok']][s['name']] += 1
    if s['type'] in ('OFS', 'KFS') and p['kr'] >= 0: kr_votes[p['kr']][s['kraj']] += 1
    if s['type'] == 'KFS' and s['name'].startswith('Hl. město Praha') and p['ok'] >= 0: ok_votes[p['ok']]['Praha'] += 3
okres_names = {k: v.most_common(1)[0][0] for k, v in ok_votes.items()}
kraj_names = {k: v.most_common(1)[0][0] for k, v in kr_votes.items()}
KRAJE = sorted(set(kraj_names.values()))
OKRESY = sorted(set(okres_names.values()))

# Kraj eines Okres über die Kraj-Polygone seiner Orte
okres_kraj = defaultdict(Counter)
for p in place_list:
    if p['ok'] in okres_names and p['kr'] in kraj_names:
        okres_kraj[okres_names[p['ok']]][kraj_names[p['kr']]] += 1

# ---------- Ausgabe ----------
comp_out = []
for c in comps:
    cat, level, cup = classify(c)
    s = subjects.get(c['subj'], {})
    comp_out.append([short_name(c), cat, level, 1 if cup else 0, c['id'], s.get('name', ''), c['code']])

team_idx = {}; teams = []
def ti(n):
    if n not in team_idx: team_idx[n] = len(teams); teams.append(n)
    return team_idx[n]

M = []
for m, pi in zip(matches, match_place):
    ci, rnd, hn, hc, an, ac, score, dt, venue, spec = m
    if not dt: continue
    M.append([ci, dt, ti(hn), ti(an), score, pi, rnd or 0, spec if spec is not None else -1])
M.sort(key=lambda r: r[1])

P = []
for p in place_list:
    P.append([p['name'], round(p['lat'], 5), round(p['lon'], 5),
              OKRESY.index(okres_names[p['ok']]) if p['ok'] in okres_names else -1,
              KRAJE.index(kraj_names[p['kr']]) if p['kr'] in kraj_names else -1])

out = {
    'generated': R['generated'], 'season': R.get('season', ''),
    'cats': CATS, 'kraje': KRAJE,
    'okresy': [[o, KRAJE.index(okres_kraj[o].most_common(1)[0][0]) if okres_kraj[o] else -1] for o in OKRESY],
    'okresPoly': {str(k): OKRESY.index(v) for k, v in okres_names.items()},
    'comps': comp_out, 'places': P, 'teams': teams,
    'matchFields': ['comp', 'datetime', 'home', 'away', 'score', 'place', 'round', 'spectators'],
    'matches': M,
}
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

# Kurzbericht
cc = Counter(c[1] for c in comp_out)
lv = Counter(c[2] for c in comp_out if c[1] == 0 and not c[3])
print('Wettbewerbe', len(comp_out), {CATS[k]: v for k, v in sorted(cc.items())})
print('Männer-Ebenen', dict(sorted(lv.items(), key=lambda x: (x[0] is None, x[0] or 0))))
print('Spiele', len(M), 'ohne Ort', sum(1 for r in M if r[5] < 0))
print('Orte', len(P), 'Okresy', len(OKRESY), 'Kraje', len(KRAJE), 'Okres-Polygone benannt', len(okres_names), '/', len(OK))
print('Ohne Ebene (Männer, Liga):', [c[0] for c in comp_out if c[1] == 0 and not c[3] and c[2] is None][:25])
