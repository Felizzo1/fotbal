"""Erzeugt die Icons des Klobása-Planers aus der Vorlage data/icon_vorlage.png (Fußball-Nadel in CZ-Farben,
transparenter Hintergrund).

Aufruf: python3 scripts/make_icon.py site
  favicon-32.png                                  – transparent, eng zugeschnitten (Browser-Tab)
  icon-512.png, icon-192.png                      – transparent (Web-App, „any“)
  apple-touch-icon.png                            – auf dunklem Grund (iOS macht Transparentes sonst schwarz)
  icon-maskable-512.png, icon-maskable-192.png    – dunkler Grund mit Rand, damit Android beim runden Zuschnitt nichts abschneidet
"""
import os, sys
from PIL import Image

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'icon_vorlage.png')
BG = (32, 32, 32, 255)  # Dunkelgrau für deckende Varianten
out = sys.argv[1] if len(sys.argv) > 1 else 'site'
im = Image.open(SRC).convert('RGBA')
motif = im.crop(im.split()[3].point(lambda a: 255 if a > 20 else 0).getbbox())  # Umriss der Nadel

def framed(fill, bg=None, side=2000):
    """Motiv mittig, Motivhöhe = fill × Kantenlänge; bg=None → transparent."""
    m = motif.copy(); s = fill * side / max(m.size)
    m = m.resize((round(m.width * s), round(m.height * s)), Image.LANCZOS)
    c = Image.new('RGBA', (side, side), bg or (0, 0, 0, 0)); c.alpha_composite(m, ((side - m.width) // 2, (side - m.height) // 2)); return c

framed(0.96).resize((32, 32), Image.LANCZOS).save(f'{out}/favicon-32.png', optimize=True)
for size in (512, 192):
    framed(0.86).resize((size, size), Image.LANCZOS).save(f'{out}/icon-{size}.png', optimize=True)
    framed(0.72, BG).convert('RGB').resize((size, size), Image.LANCZOS).save(f'{out}/icon-maskable-{size}.png', optimize=True)
framed(0.84, BG).convert('RGB').resize((180, 180), Image.LANCZOS).save(f'{out}/apple-touch-icon.png', optimize=True)
print('ok, Motiv', motif.size)
