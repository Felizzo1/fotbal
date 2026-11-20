#!/usr/bin/env python3
"""Ergänzt data/europlan.json um den Untergrund jedes Stadions (Naturrasen, Kunstrasen, …) von der Stadionseite.

Selten von Hand ausführen (nach scripts/europlan.py), das Ergebnis wird eingecheckt:
  python3 scripts/europlan_untergrund.py data/europlan.json [zuerst.txt]

zuerst.txt (optional): Stadion-Links, eine pro Zeile, die zuerst geholt werden sollen.
Bewusst langsam, speichert zwischendurch und überspringt schon geholte Stadien (abbrechbar, fortsetzbar).
"""
import html, json, re, sys, time
sys.path.insert(0, __import__('os').path.dirname(__file__))
from europlan import BASE, get

DELAY = 1.5
RE = re.compile(r'Untergrund:\s*([^<\n]+)')

def main(path, first=None):
    d = json.load(open(path, encoding='utf-8'))
    pri = set(open(first, encoding='utf-8').read().split()) if first else set()
    todo = sorted((s for s in d['stadiums'] if 'untergrund' not in s), key=lambda s: s['href'] not in pri)
    print(len(todo), 'Stadien offen,', sum(s['href'] in pri for s in todo), 'davon zuerst')
    for i, s in enumerate(todo, 1):
        h = get(BASE + s['href'])
        if h is None: continue
        m = RE.search(h)
        s['untergrund'] = html.unescape(m.group(1)).strip() if m else ''
        if i % 50 == 0 or i == len(todo):
            json.dump(d, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
            print(i, 'gespeichert', flush=True)
        time.sleep(DELAY)

if __name__ == '__main__':
    main(*sys.argv[1:3])
