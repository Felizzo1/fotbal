"""Erzeugt die Icons des Klobása-Planers aus der Vorlage data/icon_vorlage.jpg (Fußball-Nadel in CZ-Farben).

Aufruf: python3 scripts/make_icon.py site
  icon-512.png, icon-192.png, apple-touch-icon.png  – Vorlage unverändert
  favicon-32.png                                    – enger zugeschnitten (im Browser-Tab besser erkennbar)
  icon-maskable-512.png, icon-maskable-192.png      – mit mehr Rand, damit Android beim runden Zuschnitt nichts abschneidet
"""
import os, sys
from PIL import Image

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icon_vorlage.jpg')
out = sys.argv[1] if len(sys.argv) > 1 else 'site'
im = Image.open(SRC).convert('RGB')
W, H = im.size
bg = im.getpixel((5, 5))

# Umriss des Motivs (alles deutlich anders als der Hintergrund)
px = im.load(); xs, ys = [], []
for y in range(0, H, 4):
    for x in range(0, W, 4):
        r, g, b = px[x, y]
        if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) > 60: xs.append(x); ys.append(y)
box = (min(xs), min(ys), max(xs), max(ys))
motif = im.crop(box)

def framed(fill):
    """Motiv mittig auf quadratischem Hintergrund, Motivhöhe = fill × Kantenlänge."""
    side = 2000; m = motif.copy()
    s = fill * side / max(m.size); m = m.resize((round(m.width * s), round(m.height * s)), Image.LANCZOS)
    c = Image.new('RGB', (side, side), bg); c.paste(m, ((side - m.width) // 2, (side - m.height) // 2)); return c

for name, size in (('icon-512.png', 512), ('icon-192.png', 192), ('apple-touch-icon.png', 180)):
    im.resize((size, size), Image.LANCZOS).save(f'{out}/{name}', optimize=True)
framed(0.94).resize((32, 32), Image.LANCZOS).save(f'{out}/favicon-32.png', optimize=True)
for size in (512, 192):
    framed(0.72).resize((size, size), Image.LANCZOS).save(f'{out}/icon-maskable-{size}.png', optimize=True)
print('ok', box, 'Hintergrund', bg)
