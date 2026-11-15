"""Zeichnet das Icon des Klobása-Planers: tschechische Flagge mit Fußball.

Aufruf: python3 scripts/make_icon.py site   → icon-512.png, icon-192.png, apple-touch-icon.png, favicon-32.png
Das Motiv bleibt im inneren Kreis (Android schneidet Icons rund oder abgerundet zu).
"""
import math, sys
from PIL import Image, ImageDraw, ImageFilter

S = 1024
BLUE, RED, WHITE, INK = (17, 69, 126), (215, 20, 26), (255, 255, 255), (22, 26, 34)

img = Image.new('RGB', (S, S), WHITE)
d = ImageDraw.Draw(img)
# Flagge: oben weiß, unten rot, blauer Keil von links bis zur Mitte
d.rectangle([0, S // 2, S, S], fill=RED)
d.polygon([(0, 0), (S * 0.56, S / 2), (0, S)], fill=BLUE)

# Fußball auf eigener Ebene (4-fach groß zeichnen, dann verkleinern = glatte Kanten)
K = 4; R = 255 * K; C = (R + 40 * K, R + 40 * K); B = Image.new('RGBA', (2 * C[0], 2 * C[1]), (0, 0, 0, 0))
g = ImageDraw.Draw(B)
g.ellipse([C[0] - R, C[1] - R, C[0] + R, C[1] + R], fill=WHITE + (255,))
def pent(cx, cy, r, rot):
    return [(cx + r * math.cos(rot + k * 2 * math.pi / 5), cy + r * math.sin(rot + k * 2 * math.pi / 5)) for k in range(5)]
core = pent(C[0], C[1], R * 0.30, -math.pi / 2)
mask = Image.new('L', B.size, 0); ImageDraw.Draw(mask).ellipse([C[0] - R, C[1] - R, C[0] + R, C[1] + R], fill=255)
P = Image.new('RGBA', B.size, (0, 0, 0, 0)); q = ImageDraw.Draw(P)
q.polygon(core, fill=INK + (255,))
outer = []
for k in range(5):
    a = -math.pi / 2 + k * 2 * math.pi / 5 + math.pi / 5
    ox, oy = C[0] + R * 0.86 * math.cos(a), C[1] + R * 0.86 * math.sin(a)
    pg = pent(ox, oy, R * 0.30, a + math.pi)  # eine Spitze zeigt zur Mitte
    outer.append(pg); q.polygon(pg, fill=INK + (255,))
# Nähte: von jeder Ecke des inneren Fünfecks zu einem Knoten, von dort zu den beiden nächsten äußeren Fünfecken
W = 9 * K
for k in range(5):
    a = -math.pi / 2 + k * 2 * math.pi / 5
    J = (C[0] + R * 0.56 * math.cos(a), C[1] + R * 0.56 * math.sin(a))
    q.line([core[k], J], fill=INK + (255,), width=W)
    for pg in (outer[k], outer[k - 1]):
        v = min(pg, key=lambda p: (p[0] - J[0]) ** 2 + (p[1] - J[1]) ** 2)
        q.line([J, v], fill=INK + (255,), width=W)
    q.ellipse([J[0] - W / 2, J[1] - W / 2, J[0] + W / 2, J[1] + W / 2], fill=INK + (255,))
P.putalpha(Image.composite(P.split()[3], Image.new('L', B.size, 0), mask))
B.alpha_composite(P)
g = ImageDraw.Draw(B)
g.ellipse([C[0] - R, C[1] - R, C[0] + R, C[1] + R], outline=INK + (255,), width=14 * K)
B = B.resize((B.width // K, B.height // K), Image.LANCZOS)

# Schatten und Ball setzen (rechts von der Mitte, über der Spitze des Keils)
cx, cy = 600, 512
shadow = B.split()[3].point(lambda a: a * 0.45).filter(ImageFilter.GaussianBlur(16))
img.paste((10, 20, 40), (cx - B.width // 2 + 10, cy - B.height // 2 + 18), shadow)
img.paste(B, (cx - B.width // 2, cy - B.height // 2), B)

out = sys.argv[1] if len(sys.argv) > 1 else 'site'
for name, size in (('icon-512.png', 512), ('icon-192.png', 192), ('apple-touch-icon.png', 180), ('favicon-32.png', 32)):
    img.resize((size, size), Image.LANCZOS).save(f'{out}/{name}', optimize=True)
print('ok')
