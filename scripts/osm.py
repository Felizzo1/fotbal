#!/usr/bin/env python3
"""Lädt aus OpenStreetMap alle Fußballplätze und Ortsnamen in Tschechien (zwei Overpass-Abfragen).

Selten von Hand ausführen (z. B. einmal pro Saison), das Ergebnis wird eingecheckt:
  python3 scripts/osm.py data/osm.json

preprocess.py nutzt die Daten für Spielorte ohne Europlan-Stadion: Kartenpunkt auf den echten Platz.
Daten © OpenStreetMap-Mitwirkende, ODbL.
"""
import json, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

URL = 'https://overpass-api.de/api/interpreter'
UA = 'Klobasa-Planer/1.0 (einmaliger Abruf fuer private Spielplan-Seite)'
AREA = 'area["ISO3166-1"="CZ"][admin_level=2]->.cz;'
Q_PITCH = f'''[out:json][timeout:600];{AREA}
(nwr["leisure"="pitch"]["sport"~"soccer|football"](area.cz);
 nwr["leisure"="stadium"]["sport"~"soccer|football"](area.cz););
out center tags qt;'''
Q_PLACE = f'''[out:json][timeout:600];{AREA}
node["place"~"^(city|town|village|hamlet|suburb|quarter|neighbourhood|locality|isolated_dwelling)$"]["name"](area.cz);
out qt;'''

def run(q):
    for i in range(3):
        try:
            req = urllib.request.Request(URL, data=urllib.parse.urlencode({'data': q}).encode(), headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=900) as r:
                return json.load(r)['elements']
        except Exception as e:
            print('Fehler, neuer Versuch:', e, file=sys.stderr)
            time.sleep(60 * (i + 1))
    raise SystemExit('Overpass nicht erreichbar')

def pos(e):
    c = e.get('center') or e
    return round(c['lat'], 5), round(c['lon'], 5)

def main(out):
    pitches = []
    for e in run(Q_PITCH):
        if 'lat' not in e and 'center' not in e: continue
        t = e.get('tags', {}); lat, lon = pos(e)
        art = 1 if t.get('surface') in ('artificial_turf', 'artificial_grass', 'synthetic') else 0
        pitches.append([lat, lon, t.get('name', ''), art])
    print(len(pitches), 'Plätze')
    time.sleep(10)
    places = [[e['tags']['name'], *pos(e), e['tags'].get('place', '')] for e in run(Q_PLACE)]
    print(len(places), 'Orte')
    data = {'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'source': 'OpenStreetMap (© OpenStreetMap-Mitwirkende, ODbL) via Overpass API',
            'pitchFields': ['lat', 'lon', 'name', 'kunstrasen'], 'pitches': pitches,
            'placeFields': ['name', 'lat', 'lon', 'typ'], 'places': places}
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    print('fertig ->', out)

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'data/osm.json')
