#!/usr/bin/env python3
"""Bereitet den Rohabzug von fotbal.cz zu einem kompakten data.json für die Webseite auf.

Aufruf: python3 preprocess.py rohdaten.json[.gz] okresy.json kraje.json data.json
"""
import gzip, json, os, re, sys
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
    matches.append((ci, rnd, th[0], th[1], tg[0], tg[1], score, dt, R['venues'][v] if v >= 0 else '', spec, mid))
extra = R.get('extra') or {}
off = len(comps)
for c in extra.get('comps', []):
    name = re.sub(r'^90/100\s+', '', c['name'])
    comps.append({'id': c['id'], 'code': c.get('code') or '', 'name': name, 'subj': c['subj']})
for m in extra.get('matches', []):
    ci, rnd, hn, hc, an, ac, score, dt, venue, spec, mid = m
    matches.append((ci + off, rnd, hn, hc, an, ac, score, dt, venue, spec, mid))

# ---------- Kategorie und Ligaebene ----------
# Auf der Seite nur Männer und Frauen; Jugend, Futsal und Alte Herren werden unten aussortiert
CATS = ['Männer', 'Frauen']

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

# Nur Wettbewerbe der Männer und Frauen behalten (Indizes neu durchnummerieren)
keep = [i for i, c in enumerate(comps) if classify(c)[0] < len(CATS)]
remap = {o: n for n, o in enumerate(keep)}
comps = [comps[i] for i in keep]
matches = [(remap[m[0]],) + tuple(m[1:]) for m in matches if m[0] in remap]

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
# Spiele ohne Spielort und ohne Verein in der Vereinskarte: Position aus der Zuordnungsliste (Eintrag mit leerem Spielort)
_man_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'zuordnung_manuell.json')
_ep_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'europlan.json')
NOVENUE = {}
if os.path.exists(_man_path):
    _ep_pos = {s['id']: (s['lat'], s['lon']) for s in json.load(open(_ep_path, encoding='utf-8'))['stadiums']} if os.path.exists(_ep_path) else {}
    for e in json.load(open(_man_path, encoding='utf-8'))['eintraege']:
        if e.get('spielort') in ('', '*') and e.get('verein'):
            pos = _ep_pos.get(e.get('europlan')) or ((e['lat'], e['lon']) if 'lat' in e else None)
            if pos: NOVENUE[e['verein']] = pos
# Verein fehlt in der fotbal.cz-Vereinskarte (z. B. Frýdek-Místek): Position über den Vereinsnamen bei Europlan
_GEN = {'tj', 'sk', 'fk', 'fc', 'afk', 'mfk', 'sfc', 'sokol', 'z', 's', 'a', 'b', 'c', 'd', 'as', 'zs', 'spolek'}
EP_CLUBPOS = []
if os.path.exists(_ep_path):
    for _s in json.load(open(_ep_path, encoding='utf-8'))['stadiums']:
        for _c in _s['clubs']:
            if not re.search(r'ehemals|diverse', _c, re.I):
                EP_CLUBPOS.append((set(norm(_c).split()), _s['lat'], _s['lon']))
def coords_by_name(team):
    ws = {w for w in norm(re.sub(r',.*$', '', team)).split() if w not in _GEN and len(w) > 1}
    hits = [(la, lo) for cw, la, lo in EP_CLUBPOS if ws and ws <= cw]
    return hits[0] if hits else None

for m in matches:
    ci, rnd, hn, hc, an, ac, score, dt, venue, spec, mid = m
    xy = coords_for(venue, hc)
    if not xy and hn in NOVENUE: xy = NOVENUE[hn]
    if not xy: xy = coords_by_name(hn)
    if not xy:
        match_place.append(-1); continue
    key = (venue or hn, round(xy[0], 4), round(xy[1], 4))
    if key not in places:
        places[key] = len(place_list)
        place_list.append({'name': key[0], 'lat': xy[0], 'lon': xy[1], 'ok': locate(xy[0], xy[1], OK), 'kr': locate(xy[0], xy[1], KR), 'home': Counter()})
    pi = places[key]
    place_list[pi]['home'][hn] += 1
    match_place.append(pi)

# ---------- Europlan-Stadien zuordnen (data/europlan.json, erzeugt von scripts/europlan.py) ----------
# Reihenfolge: 1. Liga bei Europlan + Heimverein, 2. Verein allein, 3. Entfernung, 4. Ortsname im Spielort-Text.
# Der Spielort-Text von fotbal.cz muss jeweils zum Stadion passen. Zugeordnete Orte bekommen die Stadion-Koordinaten.
import math, os
EP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'europlan.json')
EP_GENERIC = re.compile(r'^(tj|sk|fk|fc|afk|mfk|sfk|sc|ss|ofk|telovychovna|jednota|sportovni|fotbalovy|klub|football|club|sokol|zeny|zen|zs|as|os|sro|spolek|[a-dfosrz])$')

def club_key(n):
    n = re.sub(r'\b([nup])([A-ZÁ-Ž])', r'\1 \2', n)  # zusammengeklebte Abkürzung: „Štítná nVl“ = nad Vláří
    n = norm(re.sub(r',.*$', '', n.replace('"', ' ')))
    return ' '.join(w for w in n.split() if not EP_GENERIC.match(w) and not re.match(r'^\d{4}$', w))

# Ortsnamen-Wörter aus OpenStreetMap (data/osm.json): unterscheiden Orte von Straßen- und Personennamen
PLACEW = set(); CITYW = set()  # CITYW: Großstädte (Praha, Brno …) – als Ortsangabe im Spielort zu allgemein
PLACEPOS = defaultdict(list)    # Ortsnamen-Wort → Koordinaten der Orte (für „liegt der genannte Ort in der Nähe?“)
_osm_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'osm.json')
if os.path.exists(_osm_path):
    for _nm, _la, _lo, _typ in json.load(open(_osm_path, encoding='utf-8'))['places']:
        PLACEW.update(w for w in norm(_nm).split() if len(w) >= 4)
        for w in norm(_nm).split():
            if len(w) >= 4: PLACEPOS[w[:5]].append((w, _la, _lo))
        if _typ == 'city' and len(norm(_nm).split()) == 1: CITYW.add(norm(_nm))  # nur einwortige (Praha, Brno), nicht „Ústí nad Labem“

def street_words(venue):
    """Wörter direkt vor einer Hausnummer sind Straßennamen („B.Němcové 3178, Česká Lípa“, „Bruslařská 1132/10 Praha“),
    keine Ortsangabe. Ausnahme Dorfadresse („Bludovice 23-tráva“): ein Ortsname, nach dem kein weiterer Ort mehr folgt."""
    t = norm(venue).split(); out = set()
    for i in range(len(t) - 1):
        if t[i + 1].isdigit() and len(t[i + 1]) >= 2 and not t[i].isdigit():
            later_place = any(w in PLACEW for w in t[i + 2:])
            if t[i] not in PLACEW or later_place: out.add(t[i])
    return out

def km(a, b, c, d):
    r = math.pi / 180
    x = math.sin((c - a) * r / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))

# Von Hand geklärte Spielorte (data/zuordnung_manuell.json) haben Vorrang vor der Automatik
MANUAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'zuordnung_manuell.json')
MANUAL = json.load(open(MANUAL_PATH, encoding='utf-8'))['eintraege'] if os.path.exists(MANUAL_PATH) else []
def manual_for(p):
    for e in MANUAL:
        if e['spielort'] == p['name'] and (not e.get('verein') or e['verein'] in p['home']): return e
        # leerer Spielort: gilt für Spiele des Vereins ohne Spielortangabe (Ortsname = Vereinsname)
        if e['spielort'] == '' and e.get('verein') and p['name'] == e['verein']: return e
        # „*“: gilt für alle Heimspiele des Vereins, egal welcher Spielort angegeben ist
        if e['spielort'] == '*' and e.get('verein') and e['verein'] in p['home']: return e
    return None
manual_fixed = {}  # Ort-Index → Eintrag

ep_href = [''] * len(place_list)
ep_name = [''] * len(place_list)
ep_stats = Counter()
if os.path.exists(EP_PATH):
    EPD = json.load(open(EP_PATH, encoding='utf-8'))
    EP = EPD['stadiums']; EP_BY_ID = {s['id']: s for s in EP}
    ep_by_club = defaultdict(list)
    for s in EP:
        for c in s['clubs']:
            if c.lower().startswith('ehemals'): continue  # frühere Plätze eines Vereins nicht mehr verwenden
            k = club_key(c)
            if k and s not in ep_by_club[k]: ep_by_club[k].append(s)
    grid = defaultdict(list)  # grobes Raster für die Umkreissuche
    for s in EP:
        grid[(round(s['lat'], 1), round(s['lon'], 1))].append(s)
    def near(lat, lon, r=1):
        out = []
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                out += grid.get((round(lat + dy / 10, 1), round(lon + dx / 10, 1)), [])
        return out
    ART = re.compile(r'\b(umt|ut|umela|umelka|kunstrasen|artificial|ut3g|umt3g|3g)\b')
    STOP = {'hriste', 'stadion', 'stadium', 'arena', 'areal', 'sportovni', 'fotbalove', 'fotbalovy', 'mestsky', 'tj', 'sk', 'fk', 'sokol', 'ul', 'na', 'u', 'v'}
    SURF = {'trava', 'umt', 'ut', 'umela', 'umelka', 'zs', 'nad', 'pod', 'ul', 'tj', 'sk', 'fk', 'fc', 'ii', 'iii', 'uo', 'ut3g', 'umt3g', '3g'}
    def toks(s): return {w for w in norm(s).split() if len(w) > 1 and w not in STOP and not w.isdigit()}
    def nums(s): return set(re.findall(r'\b\d\b', norm(s)))
    # Ortswörterbuch: alle Wörter aus Europlan-Stadion- und Vereinsnamen. Wörter im Spielort-Text, die dort nie vorkommen
    # (meist Straßennamen wie „Blümlova“), zählen nicht als Ortsangabe.
    VOCAB = set(); VOCAB5 = set()
    for s in EP:
        for w in toks(s['name'] + ' ' + ' '.join(s['clubs'])):
            VOCAB.add(w)
            if len(w) >= 5: VOCAB5.add(w[:5])
    def known(w): return w in VOCAB or (len(w) >= 5 and w[:5] in VOCAB5)
    def place_words(venue): return {w for w in toks(venue) - street_words(venue) - CITYW if w not in SURF and len(w) > 2 and known(w)}
    # Vereinsname mit Abkürzungen: „Babice n. Svit.“ = „Babice nad Svitavou“, „A.F.C. Humpolec“ = „AFC Humpolec“
    # Wortzahl des Original-Vereinsnamens („AFK Tišnov“ = 2, „Plzeň“ = 1): reine Ortsnamen sind keine Vereine
    raw_words = defaultdict(int)
    for s in EP:
        for c in s['clubs']:
            raw_words[club_key(c)] = max(raw_words[club_key(c)], len(c.split()))
    club_keys_by_tok = defaultdict(set)
    for k in ep_by_club:
        for w in k.split():
            if len(w) >= 4: club_keys_by_tok[w[:4]].add(k)
    def abbr_match(short, long):
        lw = long.split()
        return all(any(b.startswith(a) or a.startswith(b) for b in lw) for a in short.split())
    _club_cache = {}
    def club_stadiums(team, variants=False):
        k = club_key(team)
        if (k, variants) in _club_cache: return _club_cache[(k, variants)]
        res = list(ep_by_club.get(k, []))
        if not res and k:  # Kürzel: „Slezský fotbalový club Opava“ = „SFC Opava“
            ws = norm(re.sub(r',.*$', '', team)).split()
            for n in (2, 3, 4):
                if len(ws) > n:
                    res = list(ep_by_club.get(club_key(''.join(w[0] for w in ws[:n]) + ' ' + ' '.join(ws[n:])), []))
                    if res: break
        if variants and k:  # im Spielort genannter Ort/Verein: alle passenden Vereine, die Entfernung entscheidet später
            cand = set().union(*(club_keys_by_tok.get(w[:4], set()) for w in k.split() if len(w) >= 4)) if any(len(w) >= 4 for w in k.split()) else set()
            fwd = [c for c in cand if abbr_match(k, c)]
            if 0 < len({re.sub(r'( (diverse|mladez|ii|iii))+$', '', c) for c in fwd}) <= 6:
                for c in fwd:
                    for s in ep_by_club[c]:
                        if s not in res: res.append(s)
        if variants:  # Ausweich- und Jugendplätze desselben Vereins
            for v in ('diverse', 'mladez', 'b'):
                for s in ep_by_club.get(k + ' ' + v, []):
                    if s not in res: res.append(s)
        if not res and k:
            cand = set().union(*(club_keys_by_tok.get(w[:4], set()) for w in k.split() if len(w) >= 4)) if any(len(w) >= 4 for w in k.split()) else set()
            # zuerst Vereine, die alle Wörter des fotbal.cz-Namens erklären („babice n svit“ → „babice nad svitavou“),
            # erst danach kürzere Namen („babice“)
            # rückwärts (Europlan-Name ist Teil des fotbal.cz-Namens) nur mit mindestens zwei Wörtern: „Plzeň“ allein ist kein Verein
            hits = [c for c in cand if abbr_match(k, c)] or [c for c in cand if (len(c.split()) >= 2 or raw_words[c] >= 2) and abbr_match(c, k)]
            # Varianten desselben Vereins („… diverse“, „… mladez“) zählen beim Limit nur einmal
            bases = {re.sub(r'( (diverse|mladez|ii|iii))+$', '', c) for c in hits}
            if 0 < len(bases) <= 3:  # mehr Treffer = zu allgemein (z. B. nur „Praha“)
                for c in hits:
                    for s in ep_by_club[c]:
                        if s not in res: res.append(s)
        if variants and res:
            for s in list(res):
                for c in s['clubs']:
                    for s2 in ep_by_club.get(club_key(c) + ' diverse', []):
                        if s2 not in res: res.append(s2)
        _club_cache[(k, variants)] = res
        return res
    def same(a, b):  # gleich bis auf Beugung: Prefix aus 5 Zeichen oder nur letzter Buchstabe anders (Opava/Opavě)
        return a == b or (len(a) >= 5 and len(b) >= 5 and (a[:5] == b[:5] or a[:-1] == b[:-1]))
    def consistent(venue, s, strict=False):
        """Nennt der Spielort-Text einen Ort, müssen alle Ortswörter im Stadion- oder Vereinsnamen vorkommen.
        strict: auch Wörter, die Europlan nicht kennt (ohne Vereinsbezug kann ein unbekannter Ort ein anderer Ort sein)."""
        vt = {w for w in toks(venue) - street_words(venue) if w not in SURF and len(w) > 2} if strict else place_words(venue)
        if not vt: return True  # z. B. nur „tráva“
        # Ein markantes Wort aus dem Spielort steht wörtlich im Stadionnamen („ShipEx Aréna, Srbská, Brno“ → ShipEx Aréna,
        # „MěFS M.Valenty“ → Stadion Miroslava Valenty, „Na Litavce, Příbram“ → Stadion Na Litavce): das reicht
        # Markant heißt: steht im Stadionnamen, aber nicht im Vereinsnamen (sonst ist es nur der Ort: Planá, Hradec)
        if not strict:
            sn, cn = toks(s['name']), toks(' '.join(s['clubs']))
            if any(len(w) >= 4 and w not in SURF and w not in CITYW and not any(same(w, c) for c in cn)
                   and any(w == b or (len(w) >= 5 and w[:-1] == b[:-1]) for b in sn) for w in toks(venue)):
                return True
        st = toks(s['name'] + ' ' + ' '.join(s['clubs']))
        return all(any(same(a, b) for b in st) for a in vt)  # Stará Paka ≠ Nová Paka
    def score(venue, s):
        """Wie gut passt der Spielort-Text zum Stadionnamen (bei Vereinen mit mehreren Plätzen)?"""
        v, n = norm(venue), norm(s['name'])
        sc = len(toks(venue) & toks(s['name']))
        ini = ''.join(w[0] for w in n.split() if w not in ('a', 'v', 'u', 'na', 'pod', 'nad'))
        if any(3 <= len(w) <= 6 and w.isalpha() and w in ini for w in v.split()): sc += 3  # Kürzel: SCUK = Sportovní Centrum Univerzity Karlovy
        if bool(ART.search(v)) == bool(ART.search(n)): sc += 4   # Kunstrasen ja/nein stimmt überein (stärkstes Signal)
        if nums(venue) and nums(venue) == nums(s['name']): sc += 3  # „hřiště 2“ / „tráva č.2“ schlägt die Ligaliste
        if not nums(venue) and nums(s['name']):                     # Nebenplatz („hřiště 2“) …
            sc += 2 if ART.search(v) else -1                         # … bei „UMT“ wahrscheinlich, sonst nur wenn genannt
        return sc

    # Wettbewerb -> Europlan-Liga über gemeinsame Vereine
    leagues = []
    for L in EPD.get('leagues', []):
        ent = {}
        for club, sid in L['entries']:
            k = club_key(club)
            if k and k not in ent: ent[k] = sid
        if ent: leagues.append(ent)
    lg_by_key = defaultdict(list)
    for j, ent in enumerate(leagues):
        for k in ent: lg_by_key[k].append(j)
    comp_keys = defaultdict(set)
    for m in matches:
        comp_keys[m[0]].update(k for k in (club_key(m[2]), club_key(m[4])) if k)
    comp_league = {}
    for ci, ks in comp_keys.items():
        cnt = Counter(j for k in ks for j in lg_by_key.get(k, ()))
        if cnt:
            j, ov = cnt.most_common(1)[0]
            if ov >= 3 and ov >= 0.5 * min(len(ks), len(leagues[j])): comp_league[ci] = j
    ep_stats['Wettbewerbe mit Europlan-Liga'] = len(comp_league)

    def home_ok(p, s):
        """Platz des Heimvereins passt, außer ein Wort aus dem Spielort zeigt auf einen ANDEREN Platz in der Nähe.
        Straßennamen wie „Brankovická“ zeigen auf keinen Platz und stören deshalb nicht; „Javorník“ schließt Vápenná aus."""
        if consistent(p['name'], s): return True
        own = toks(s['name'] + ' ' + ' '.join(s['clubs']))
        miss = [w for w in place_words(p['name']) if not any(same(w, b) for b in own)]
        # ein genannter echter Ort (bis 60 km), der nicht zum Platz passt (Vícenice, Deštná, Bezděkov): anderer Spielort.
        # Ausgenommen Personennamen nach einem Initial („B. Němcové“, „M.Horákové“) – das sind Straßen.
        t = norm(p['name']).split()
        person = {t[i + 1] for i in range(len(t) - 1) if len(t[i]) == 1 and t[i].isalpha()}
        for w in miss:
            if w in person: continue
            if any(same(w, pw) and km(p['lat'], p['lon'], la, lo) <= 60 for pw, la, lo in PLACEPOS.get(w[:5], ())):
                return False
        for o in near(p['lat'], p['lon']):
            if o['id'] != s['id'] and km(p['lat'], p['lon'], o['lat'], o['lon']) <= 15:
                ot = toks(o['name'] + ' ' + ' '.join(o['clubs']))
                if any(same(w, b) for w in miss for b in ot): return False
        return True

    def pick(p, team, prior):
        """Stadion für Heimverein `team` am Ort `p`; `prior` = Platz laut Europlan-Liga (oder None)."""
        cands = {s['id']: s for s in club_stadiums(team)
                 if km(p['lat'], p['lon'], s['lat'], s['lon']) <= 15 and consistent(p['name'], s)}
        if not cands:  # Rückfall: Ausweichplätze des Vereins („… diverse“), z. B. Areál Břízky bei FK Jablonec B
            cands = {s['id']: s for s in club_stadiums(team, True)
                     if km(p['lat'], p['lon'], s['lat'], s['lon']) <= 15 and consistent(p['name'], s)}
        if not cands:  # zweiter Rückfall: Plätze des Heimvereins, solange der Spielort nicht auf einen anderen Platz zeigt
            cands = {s['id']: s for s in club_stadiums(team, True)
                     if km(p['lat'], p['lon'], s['lat'], s['lon']) <= 15 and home_ok(p, s)}
        if prior and consistent(p['name'], prior) and km(p['lat'], p['lon'], prior['lat'], prior['lon']) <= 25:
            cands.setdefault(prior['id'], prior)
        # Nennt der Spielort-Text einen Verein (z. B. „FK Ústí n.L.- UMT.“ bei einem Heimspiel von SK Hostovice),
        # kommen dessen Stadien dazu; den Vorrang regelt unten der Ortsname im Stadionnamen
        # Nennt er nur den Ort des Heimvereins („Domažlice“ bei TJ Jiskra Domažlice), bleibt es bei dessen Plätzen;
        # bei Spielgemeinschaften („Černotín/Ústí“) zählt der passende Teil.
        vwords = [w for w in norm(p['name']).split() if w not in SURF and w not in STOP and len(w) > 2]
        if vwords:
            parts = [pt for pt in re.split(r'/', team) if pt.strip()]
            own = [pt for pt in parts if all(any(same(a, b) for b in norm(pt).split()) for a in vwords)]
            # für die Vereinssuche Abkürzungen behalten („Ústí n.L.“ = Ústí nad Labem, nicht TJ Sokol Ústí)
            vclub = ' '.join(w for w in norm(p['name']).split() if w not in SURF and w not in STOP)
            # fremder Verein/Ort im Spielort („UMT Brozany“ bei TJ Slavoj Úštěk): bis 40 km, inkl. Ausweichplätze („… diverse“)
            umt = bool(ART.search(norm(p['name'])))  # bei „UMT“ auch die Ausweichplätze des eigenen Vereins
            for src, radius, variants in ([(pt, 15, umt) for pt in own] if own else [(vclub, 40, True)]):
                for s in club_stadiums(src, variants):
                    if km(p['lat'], p['lon'], s['lat'], s['lon']) <= radius and consistent(p['name'], s):
                        cands.setdefault(s['id'], s)
        if not cands: return None
        # Nennt der Spielort einen Ort, haben Stadien mit diesem Ort im Namen Vorrang (Javorník ≠ Vápenná);
        # ein Kunstrasenplatz bleibt im Rennen, wenn der Spielort ausdrücklich Kunstrasen sagt (Ivančice ÚT → Němčice)
        vt = place_words(p['name'])
        if vt and len(cands) > 1:
            named = {k: s for k, s in cands.items() if all(any(same(a, b) for b in toks(s['name'])) for a in vt)
                     or (ART.search(norm(p['name'])) and ART.search(norm(s['name'])))}
            # Platz laut Europlan-Liga bleibt im Rennen, solange sein Name keinen anderen Ort nennt
            if prior and prior['id'] in cands and prior['id'] not in named:
                if not any(w in PLACEW and not any(same(w, a) for a in vt) for w in toks(prior['name'])):
                    named[prior['id']] = prior
            if named: cands = named
        if len(cands) == 1: return next(iter(cands.values()))
        bonus = lambda s: 2.5 if prior and s['id'] == prior['id'] else 0
        # Abzug für Entfernung: bei gleichnamigen Orten gewinnt der nähere (Dubice, Kostomlaty)
        ranked = sorted(((score(p['name'], s) + bonus(s) - km(p['lat'], p['lon'], s['lat'], s['lon']) / 10, s['id'], s)
                         for s in cands.values()), key=lambda x: -x[0])
        return ranked[0][2] if ranked[0][0] > ranked[1][0] else None

    # Stimmen je Ort aus allen Heimspielen
    votes = defaultdict(Counter); cache = {}
    for m, pi in zip(matches, match_place):
        if pi < 0: continue
        prior = None
        if m[0] in comp_league:
            sid = leagues[comp_league[m[0]]].get(club_key(m[2]))
            prior = EP_BY_ID.get(sid)
        key = (pi, m[2], prior['id'] if prior else 0)
        if key not in cache: cache[key] = pick(place_list[pi], m[2], prior)
        s = cache[key]
        votes[pi][s['id'] if s else 0] += 2 if prior else 1  # Liga-Angaben zählen doppelt
    for i, p in enumerate(place_list):
        best = None
        man = manual_for(p)
        if man:
            manual_fixed[i] = man; ep_stats['von Hand'] += 1
            if man.get('europlan') in EP_BY_ID: best = EP_BY_ID[man['europlan']]
            elif 'lat' in man:
                p['lat'], p['lon'] = man['lat'], man['lon']
                p['ok'], p['kr'] = locate(p['lat'], p['lon'], OK), locate(p['lat'], p['lon'], KR)
                ep_name[i] = man.get('name', ''); continue
            else: continue  # „weglassen“: bleibt unsicher
        nz = Counter({k: c for k, c in votes.get(i, {}).items() if k}) if not best else Counter()  # Spiele ohne Treffer zählen nicht mit
        if nz and not best:
            sid, n = nz.most_common(1)[0]
            tot = sum(nz.values())
            top = [EP_BY_ID[k] for k, c in nz.items() if c >= 0.25 * tot]
            if n >= 0.6 * tot: best = EP_BY_ID[sid]
            # A- und B-Team auf verschiedenen Plätzen derselben Anlage (Holice: Hauptplatz/hřiště 2): Hauptkandidat
            elif all(km(a['lat'], a['lon'], b['lat'], b['lon']) <= 0.5 for a in top for b in top): best = EP_BY_ID[sid]
            else:  # sonst der nächstgelegene Kandidat mit mindestens 40 % der Stimmen (Pěnčín u Jbc ≠ Pěnčín u Turnova)
                near40 = sorted((km(p['lat'], p['lon'], EP_BY_ID[k]['lat'], EP_BY_ID[k]['lon']), k) for k, c in nz.items() if c >= 0.4 * tot)
                if near40: best = EP_BY_ID[near40[0][1]]
            if best: ep_stats['über Verein/Liga'] += 1
            else: ep_stats['mehrdeutig'] += 1; continue
        # nächstes Stadion bis 1 km, wenn kein zweites in der Nähe liegt
        if not best:
            cs = sorted(((km(p['lat'], p['lon'], s['lat'], s['lon']), s['id'], s) for s in near(p['lat'], p['lon']) if consistent(p['name'], s, strict=True)), key=lambda x: x[0])
            if cs and cs[0][0] <= 1.0 and (len(cs) == 1 or cs[1][0] > 1.0): best = cs[0][2]; ep_stats['über Entfernung'] += 1
        # Spielort-Text nennt einen Ort: eindeutiges Stadion mit diesem Ort bis 15 km
        if not best and place_words(p['name']):
            cs = {s['id']: s for s in near(p['lat'], p['lon'], 2) if km(p['lat'], p['lon'], s['lat'], s['lon']) <= 15 and consistent(p['name'], s, strict=True)}
            if len(cs) == 1: best = next(iter(cs.values())); ep_stats['über Ortsnamen'] += 1
        if best:
            ep_href[i] = best['href']; ep_name[i] = best['name']
            p['lat'], p['lon'] = best['lat'], best['lon']  # genauer als der Vereinssitz
            p['ok'], p['kr'] = locate(p['lat'], p['lon'], OK), locate(p['lat'], p['lon'], KR)
    ep_stats['ohne'] = sum(1 for h in ep_href if not h)
    print('Europlan:', len(EP), 'Stadien;', dict(ep_stats))

# ---------- OpenStreetMap (data/osm.json, erzeugt von scripts/osm.py) ----------
# Spielorte ohne Europlan-Stadion: Kartenpunkt auf den echten Fußballplatz statt auf den Vereinssitz.
# Nennt der Spielort-Text einen Ort, wird dieser gesucht (bis 25 km vom Verein) und der nächste Platz dort genommen,
# sonst der nächste Platz am Vereinssitz (bis 2 km). Findet sich kein Platz, wenigstens die Ortsmitte.
OSM_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'osm.json')
osm_flag = [0] * len(place_list)  # 1 = OSM-Platz am genannten Ort, 2 = nur OSM-Ortsmitte, 3 = OSM-Platz geschätzt (mehrere möglich oder nur Vereinssitz)
if os.path.exists(OSM_PATH):
    O = json.load(open(OSM_PATH, encoding='utf-8'))
    o_stats = Counter()
    OSTOP = {'trava', 'umt', 'ut', 'uo', 'umela', 'umelka', 'hriste', 'stadion', 'stadiony', 'areal', 'sportovni', 'fotbalove',
             'fotbalovy', 'mestsky', 'mestske', 'tj', 'sk', 'fk', 'fc', 'afk', 'sokol', 'nad', 'pod', 'ul', 'ulice', 'nam',
             'namesti', 'skola', 'zs', 'muzi', 'dorost', 'zaci', 'zeny', 'hlavni', 'treninkove', 'treninkova', 'pristavek'}
    O_ART = re.compile(r'\b(umt|ut|umela|umelka|umt\d?|3g)\b')
    def owords(v): sw = street_words(v); return [w for w in norm(v).split() if len(w) > 2 and w not in OSTOP and not w.isdigit() and w not in sw]
    def osame(a, b): return a == b or (len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5])
    pgrid = defaultdict(list)
    for la, lo, nm, art, *rest in O['pitches']:
        diag = rest[0] if rest else 0
        if 0 < diag < 80: continue  # Kleinfeld- und Trainingsplätze (Normalfeld ≥ ca. 100 m Diagonale)
        pgrid[(round(la, 1), round(lo, 1))].append((la, lo, nm, art))
    def pitches_near(lat, lon, rad):
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for q in pgrid.get((round(lat + dy / 10, 1), round(lon + dx / 10, 1)), []):
                    d = km(lat, lon, q[0], q[1])
                    if d <= rad: out.append((d, q))
        return sorted(out, key=lambda x: x[0])
    pidx = defaultdict(list)
    for nm, la, lo, typ in O['places']:
        if typ == 'city': continue  # Großstädte sind für die Platzsuche zu groß (Praha 6, Juliska ≠ Innenstadt)
        ws = norm(nm).split()
        for w in set(ws):
            if len(w) > 2: pidx[w[:3]].append((ws, la, lo, typ))
    # Wort aus dem Spielort darf eine Abkürzung des Ortsnamens sein („Mor.“), aber nicht länger:
    # sonst würden Straßen wie „Sokolova“ oder „Kučerova“ zu Sokolov bzw. Kučerov
    def oabbr(a, b): return b.startswith(a)
    # Vereinsnamen-Wörter, die keine Orte sind
    CLUBW = {'slavia', 'sparta', 'spartak', 'banik', 'dynamo', 'viktoria', 'viktorie', 'lokomotiva', 'loko', 'tatran', 'jiskra',
             'slovan', 'meteor', 'union', 'olympia', 'sokol', 'orel', 'start', 'admira', 'bohemians', 'junior', 'juniorka',
             'zbrojovka', 'slavoj', 'cechie', 'hvezda', 'rapid', 'unie', 'agro', 'fotbal', 'football', 'club', 'klub', 'mladez',
             'praha', 'brno', 'ostrava', 'plzen', 'liberec', 'olomouc'}
    TYPRANK = {'town': 0, 'village': 1, 'suburb': 2, 'quarter': 2, 'hamlet': 3, 'neighbourhood': 3, 'locality': 4, 'isolated_dwelling': 5}
    def find_town(vt, lat, lon, maxd=12, initials=()):
        """Ort aus Wörtern: meiste passende Wörter, dann Entfernung (+3 km je zusätzliches Namenswort)."""
        best = None
        for w in vt:
            for ws, la, lo, typ in pidx.get(w[:3], []):
                d = km(lat, lon, la, lo)
                if d > maxd: continue
                # Abkürzungen wie „v O.h.“ oder „n.O.“ zählen als Anfangsbuchstaben (Deštné v Orlických horách)
                hit = sum(1 for a in list(vt) + list(initials) if any(oabbr(a, b) for b in ws))
                if not any(oabbr(w, b) for b in ws): continue
                extra = max(0, len(ws) - hit)
                # landesweit (falscher Vereinssitz möglich): exakter Name und größerer Ort vor Nähe
                # (Příbram, nicht Příbram na Moravě); in der Nähe: Entfernung, +3 km je zusätzliches Namenswort
                key = (-hit, extra, TYPRANK.get(typ, 9), d) if maxd > 12 else (-hit, d + 3 * extra)
                if best is None or key < best[0]: best = (key, la, lo)
        return (best[1], best[2]) if best else None
    for i, p in enumerate(place_list):
        if ep_href[i]: continue
        if i in manual_fixed:  # von Hand geklärt: Koordinaten gelten als sicher, „weglassen“ bleibt unsicher
            if 'lat' in manual_fixed[i]: osm_flag[i] = 1
            continue
        vt = owords(p['name'])
        tw = [w for w in owords(p['home'].most_common(1)[0][0]) if w not in CLUBW] if p['home'] else []
        center, rad = (p['lat'], p['lon']), 2.0
        # Der Vereinssitz aus fotbal.cz ist manchmal falsch (z. B. Liptaň in Ostrava). Nennt der Spielort denselben Ort
        # wie der Vereinsname oder gar keinen, wird der Ort aus dem Vereinsnamen landesweit gesucht.
        # Zuerst immer in der Nähe des Vereinssitzes suchen, landesweit nur, wenn dort nichts passt.
        words = vt or tw
        ini = [w for w in norm(p['name'] if vt else p['home'].most_common(1)[0][0]).split() if len(w) == 1 and w.isalpha()]
        town = find_town(words, p['lat'], p['lon'], 30 if vt else 12, initials=ini) if words else None
        if not town and words and (not vt or any(oabbr(a, b) or oabbr(b, a) for a in vt for b in tw)):
            town = find_town(words, p['lat'], p['lon'], 300, ini)
        if town: center, rad = town, 1.5
        cs = pitches_near(center[0], center[1], rad)
        n_cands = len(cs)
        if cs:
            if O_ART.search(norm(p['name'])):  # „UMT“: Kunstrasenplatz bevorzugen, wenn OSM einen kennt
                art = [c for c in cs if c[1][3]]
                if art: cs = art
            q = cs[0][1]
            # sicher nur, wenn am genannten Ort höchstens zwei Plätze infrage kommen (in Städten wie Děčín gibt es viele)
            p['lat'], p['lon'] = q[0], q[1]; ep_name[i] = q[2]; osm_flag[i] = 1 if town and n_cands <= 2 else 3
            o_stats['Platz über Ortsname' if town else 'Platz am Vereinssitz'] += 1
        elif town:
            p['lat'], p['lon'] = town; osm_flag[i] = 2; o_stats['nur Ortsmitte'] += 1
        else:
            o_stats['unverändert'] += 1; continue
        p['ok'], p['kr'] = locate(p['lat'], p['lon'], OK), locate(p['lat'], p['lon'], KR)
    print('OpenStreetMap:', len(O['pitches']), 'Plätze;', dict(o_stats))

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
    ci, rnd, hn, hc, an, ac, score, dt, venue, spec, mid = m
    if not dt: continue
    M.append([ci, dt, ti(hn), ti(an), score, pi, rnd or 0, spec if spec is not None else -1, (mid or '').replace('-', '')])
M.sort(key=lambda r: r[1])

P = []
for i, p in enumerate(place_list):
    P.append([p['name'], round(p['lat'], 5), round(p['lon'], 5),
              OKRESY.index(okres_names[p['ok']]) if p['ok'] in okres_names else -1,
              KRAJE.index(kraj_names[p['kr']]) if p['kr'] in kraj_names else -1,
              ep_href[i], ep_name[i], osm_flag[i]])

out = {
    'generated': R['generated'], 'season': R.get('season', ''),
    'cats': CATS, 'kraje': KRAJE,
    'okresy': [[o, KRAJE.index(okres_kraj[o].most_common(1)[0][0]) if okres_kraj[o] else -1] for o in OKRESY],
    'okresPoly': {str(k): OKRESY.index(v) for k, v in okres_names.items()},
    'comps': comp_out, 'places': P, 'teams': teams,
    'matchFields': ['comp', 'datetime', 'home', 'away', 'score', 'place', 'round', 'spectators', 'matchId (fotbal.cz, ohne Bindestriche)'],
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
