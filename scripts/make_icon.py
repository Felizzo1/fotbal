"""Zeichnet das Icon des Klobása-Planers (Klobása auf Flaggenblau, weiß-roter Streifen).

Aufruf: python3 scripts/make_icon.py site   → icon-512.png, icon-192.png, apple-touch-icon.png, favicon-32.png
"""
import math, sys
from PIL import Image, ImageDraw, ImageFilter
S = 1024
BLUE, RED, WHITE = (17, 69, 126), (215, 20, 26), (255, 255, 255)
img = Image.new('RGB', (S, S), BLUE)
d = ImageDraw.Draw(img)
# Flaggenstreifen unten
d.rectangle([0, 790, S, 880], fill=WHITE)
d.rectangle([0, 880, S, S], fill=RED)
# Klobása auf eigener Ebene zeichnen, dann drehen
L = Image.new('RGBA', (S, S), (0, 0, 0, 0)); g = ImageDraw.Draw(L)
w, h = 660, 230; x0, y0 = (S - w) // 2, (S - h) // 2
g.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=h // 2, fill=(122, 52, 30, 255))            # Rand
g.rounded_rectangle([x0 + 14, y0 + 14, x0 + w - 14, y0 + h - 14], radius=h // 2 - 14, fill=(170, 78, 42, 255))  # Wurst
g.rounded_rectangle([x0 + 60, y0 + 38, x0 + w - 70, y0 + 78], radius=20, fill=(205, 112, 70, 255))  # Glanz
# Senf-Zickzack
pts = []
for k in range(0, 13):
    px = x0 + 95 + k * (w - 190) / 12
    py = y0 + h / 2 + 12 + (-26 if k % 2 else 26)
    pts.append((px, py))
g.line(pts, fill=(242, 194, 48, 255), width=22, joint='curve')
# Zipfel an den Enden
for ex, sgn in ((x0 - 6, -1), (x0 + w + 6, 1)):
    g.polygon([(ex, S / 2 - 18), (ex + sgn * 46, S / 2 - 34), (ex + sgn * 46, S / 2 + 34), (ex, S / 2 + 18)], fill=(122, 52, 30, 255))
L = L.rotate(18, resample=Image.BICUBIC, center=(S / 2, S / 2))
shadow = L.split()[3].point(lambda a: a * 0.35).filter(ImageFilter.GaussianBlur(14))
img.paste((5, 25, 55), (10, 22), shadow)
img.paste(L, (0, -40), L)
out = sys.argv[1]
for name, size in (('icon-512.png', 512), ('icon-192.png', 192), ('apple-touch-icon.png', 180), ('favicon-32.png', 32)):
    img.resize((size, size), Image.LANCZOS).save(f'{out}/{name}', optimize=True)
print('ok')
