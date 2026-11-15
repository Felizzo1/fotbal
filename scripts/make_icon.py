"""Zeichnet das Icon des Klobása-Planers: Fußball in den Farben der tschechischen Flagge auf Nachtblau.

Aufruf: python3 scripts/make_icon.py site   → icon-512.png, icon-192.png, apple-touch-icon.png, favicon-32.png
Der Ball bleibt im inneren Kreis (Android schneidet Icons rund oder abgerundet zu).
"""
import math, sys
from PIL import Image, ImageDraw, ImageFilter, ImageChops

S = 1024
BLUE, RED, WHITE, INK = (17, 69, 126), (215, 20, 26), (255, 255, 255), (20, 24, 32)
BG = (10, 27, 52)

img = Image.new('RGBA', (S, S), BG + (255,))
# leichter Lichthof hinter dem Ball
glow = Image.new('L', (S, S), 0); ImageDraw.Draw(glow).ellipse([132, 132, 892, 892], fill=90)
img.paste((40, 80, 140), (0, 0), glow.filter(ImageFilter.GaussianBlur(70)))

K = 4; R = 370 * K; D = 2 * R + 40 * K; C = (D // 2, D // 2)
ball = Image.new('RGBA', (D, D), (0, 0, 0, 0))
mask = Image.new('L', (D, D), 0); ImageDraw.Draw(mask).ellipse([C[0] - R, C[1] - R, C[0] + R, C[1] + R], fill=255)

# Grundfläche: Flagge (weiß oben, rot unten, blauer Keil von links bis zur Mitte)
flag = Image.new('RGBA', (D, D), WHITE + (255,)); f = ImageDraw.Draw(flag)
f.rectangle([0, C[1], D, D], fill=RED + (255,))
f.polygon([(C[0] - R, C[1] - R), (C[0] + R * 0.12, C[1]), (C[0] - R, C[1] + R)], fill=BLUE + (255,))
ball.paste(flag, (0, 0), mask)

# Muster: Fünfecke und Nähte
def pent(cx, cy, r, rot):
    return [(cx + r * math.cos(rot + k * 2 * math.pi / 5), cy + r * math.sin(rot + k * 2 * math.pi / 5)) for k in range(5)]
pat = Image.new('RGBA', (D, D), (0, 0, 0, 0)); q = ImageDraw.Draw(pat)        # Nähte (deckend)
pen = Image.new('RGBA', (D, D), (0, 0, 0, 0)); pq = ImageDraw.Draw(pen)       # Fünfecke (abdunkelnd)
core = pent(C[0], C[1], R * 0.30, -math.pi / 2)
pq.polygon(core, fill=INK + (255,))
outer = []
for k in range(5):
    a = -math.pi / 2 + k * 2 * math.pi / 5 + math.pi / 5
    pg = pent(C[0] + R * 0.86 * math.cos(a), C[1] + R * 0.86 * math.sin(a), R * 0.30, a + math.pi)
    outer.append(pg); pq.polygon(pg, fill=INK + (255,))
W = 8 * K
for k in range(5):
    a = -math.pi / 2 + k * 2 * math.pi / 5
    J = (C[0] + R * 0.56 * math.cos(a), C[1] + R * 0.56 * math.sin(a))
    q.line([core[k], J], fill=INK + (255,), width=W)
    for pg in (outer[k], outer[k - 1]):
        v = min(pg, key=lambda p: (p[0] - J[0]) ** 2 + (p[1] - J[1]) ** 2)
        q.line([J, v], fill=INK + (255,), width=W)
    q.ellipse([J[0] - W / 2, J[1] - W / 2, J[0] + W / 2, J[1] + W / 2], fill=INK + (255,))
pen.putalpha(ImageChops.multiply(pen.split()[3].point(lambda a: a * 0.55), mask))
ball.alpha_composite(pen)
for pg in [core] + outer:  # Kanten der Fünfecke
    q.line(pg + [pg[0]], fill=INK + (255,), width=W, joint='curve')
pat.putalpha(ImageChops.multiply(pat.split()[3], mask))
ball.alpha_composite(pat)

# Kugelform: Schatten unten rechts, Glanzlicht oben links
shade = Image.new('L', (D, D), 0)
ImageDraw.Draw(shade).ellipse([C[0] - R * 0.55, C[1] - R * 0.65, C[0] + R * 1.55, C[1] + R * 1.45], fill=0)
sh = Image.new('L', (D, D), 0); ImageDraw.Draw(sh).ellipse([C[0] - R, C[1] - R, C[0] + R, C[1] + R], fill=120)
ImageDraw.Draw(sh).ellipse([C[0] - R * 1.25, C[1] - R * 1.25, C[0] + R * 0.75, C[1] + R * 0.75], fill=0)
sh = ImageChops.multiply(sh.filter(ImageFilter.GaussianBlur(60 * K)), mask)
ball.paste((0, 0, 0), (0, 0), sh)
hl = Image.new('L', (D, D), 0); ImageDraw.Draw(hl).ellipse([C[0] - R * 0.85, C[1] - R * 0.85, C[0] + R * 0.1, C[1] - R * 0.1], fill=55)
ball.paste((255, 255, 255), (0, 0), ImageChops.multiply(hl.filter(ImageFilter.GaussianBlur(70 * K)), mask))
ImageDraw.Draw(ball).ellipse([C[0] - R, C[1] - R, C[0] + R, C[1] + R], outline=INK + (255,), width=12 * K)

ball = ball.resize((D // K, D // K), Image.LANCZOS)
cx = cy = S // 2
shadow = ball.split()[3].point(lambda a: a * 0.5).filter(ImageFilter.GaussianBlur(18))
img.paste((0, 0, 0), (cx - ball.width // 2 + 12, cy - ball.height // 2 + 22), shadow)
img.alpha_composite(ball, (cx - ball.width // 2, cy - ball.height // 2))
img = img.convert('RGB')

out = sys.argv[1] if len(sys.argv) > 1 else 'site'
for name, size in (('icon-512.png', 512), ('icon-192.png', 192), ('apple-touch-icon.png', 180), ('favicon-32.png', 32)):
    img.resize((size, size), Image.LANCZOS).save(f'{out}/{name}', optimize=True)
print('ok')
