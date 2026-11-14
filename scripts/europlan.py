#!/usr/bin/env python3
"""Sammelt alle tschechischen Stadien von europlan-online.de (Name, Verein, Koordinaten, Link).

Einmalig bzw. selten von Hand ausführen (z. B. einmal pro Saison), das Ergebnis wird eingecheckt:
  python3 scripts/europlan.py data/europlan.json

Bewusst langsam: eine Seite alle paar Sekunden, ca. 320 Ligaseiten.
preprocess.py ordnet die Stadien dann den Spielorten zu.
"""
import html, json, re, sys, time, urllib.request
from datetime import datetime, timezone

BASE = 'https://www.europlan-online.de/'
COUNTRY = 33  # Tschechien
DELAY = 4.0
UA = 'Mozilla/5.0 (X11; Linux aarch64) Spielfinder-Abgleich (einmaliger Abruf, langsam)'

def get(url):
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode('utf-8', errors='replace')
        except Exception as e:
            print('  Fehler', url, e, file=sys.stderr)
            time.sleep(15 * (i + 1))
    return None

MARKER = re.compile(
    r'fromLonLat\(\[\s*([\d.]+)\s*,\s*([\d.]+)\s*\]\s*\).*?'
    r'<strong>(.*?)<\\/strong><br\\/>(.*?)<br\\/><a href="([^"]*?stadion-(\d+)\.html)"', re.S)

def main(out):
    land = get(f'{BASE}index.php?s=land&id={COUNTRY}')
    if not land:
        raise SystemExit('Länderseite nicht erreichbar')
    ligen = sorted(set(int(x) for x in re.findall(r's=liga&(?:amp;)?id=(\d+)', land)))
    print(len(ligen), 'Ligen')
    stadien = {}
    for k, lid in enumerate(ligen, 1):
        time.sleep(DELAY)
        h = get(f'{BASE}index.php?s=liga&id={lid}')
        if not h:
            continue
        liga = html.unescape((re.search(r'<h1[^>]*>(.*?)<', h, re.S) or [None, ''])[1]).strip()
        n = 0
        for lon, lat, club, name, href, sid in MARKER.findall(h):
            s = stadien.setdefault(int(sid), {'id': int(sid), 'name': html.unescape(name).strip(),
                                              'lat': round(float(lat), 5), 'lon': round(float(lon), 5),
                                              'href': href, 'clubs': [], 'ligen': []})
            c = html.unescape(club).strip()
            if c and c not in s['clubs']:
                s['clubs'].append(c)
            if liga and liga not in s['ligen']:
                s['ligen'].append(liga)
            n += 1
        print(f'{k}/{len(ligen)} {liga}: {n} Stadien, gesamt {len(stadien)}', flush=True)
    data = {'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'source': BASE,
            'stadiums': sorted(stadien.values(), key=lambda s: s['id'])}
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=0)
    print('fertig:', len(stadien), 'Stadien ->', out)

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'data/europlan.json')
