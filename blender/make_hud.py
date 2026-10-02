import math
import random
from PIL import Image, ImageDraw, ImageFilter

random.seed(7)
SS = 2
W, H = 1536 * SS, 704 * SS
img = Image.new("RGB", (W, H), (3, 14, 28))
d = ImageDraw.Draw(img)

CY = (70, 215, 255)
CY_D = (24, 96, 130)
CY_B = (170, 245, 255)


def s(v):
    return int(v * SS)


for x in range(0, 1536, 48):
    d.line([(s(x), 0), (s(x), H)], fill=(6, 30, 52), width=SS)
for y in range(0, 704, 48):
    d.line([(0, s(y)), (W, s(y))], fill=(6, 30, 52), width=SS)

d.rectangle([s(10), s(10), s(1526), s(694)], outline=CY_D, width=s(3))
for (x, y, dx, dy) in [(10, 10, 1, 1), (1526, 10, -1, 1), (10, 694, 1, -1), (1526, 694, -1, -1)]:
    d.line([(s(x), s(y)), (s(x + dx * 60), s(y))], fill=CY, width=s(6))
    d.line([(s(x), s(y)), (s(x), s(y + dy * 60))], fill=CY, width=s(6))


def ring(cx, cy, r, w, col, start=0, end=360):
    d.arc([s(cx - r), s(cy - r), s(cx + r), s(cy + r)], start, end, fill=col, width=s(w))


cx, cy = 770, 350
for r, w, col, a0, a1 in [
    (250, 6, CY, 20, 330), (220, 3, CY_D, 0, 360), (190, 10, CY, 200, 500),
    (150, 3, CY_B, 0, 360), (110, 12, CY, 300, 600), (70, 4, CY_B, 0, 360),
]:
    ring(cx, cy, r, w, col, a0, a1)
for i in range(72):
    a = math.radians(i * 5)
    r0, r1 = 262, 280 if i % 6 == 0 else 270
    d.line([(s(cx + r0 * math.cos(a)), s(cy + r0 * math.sin(a))), (s(cx + r1 * math.cos(a)), s(cy + r1 * math.sin(a)))], fill=CY, width=s(3))
d.polygon([(s(cx), s(cy - 40)), (s(cx + 35), s(cy + 25)), (s(cx - 35), s(cy + 25))], outline=CY_B, width=s(4))
d.ellipse([s(cx - 10), s(cy - 6), s(cx + 10), s(cy + 14)], fill=CY_B)

for side, x0 in (("l", 40), ("r", 1130)):
    for k in range(7):
        y = 60 + k * 52
        d.rectangle([s(x0), s(y), s(x0 + 360), s(y + 36)], outline=CY_D, width=s(2))
        fill = random.randint(60, 340)
        d.rectangle([s(x0 + 4), s(y + 4), s(x0 + 4 + fill), s(y + 32)], fill=CY if k % 3 else CY_B)
    for k in range(5):
        y = 440 + k * 46
        for j in range(6):
            bw = random.randint(20, 120)
            d.rectangle([s(x0 + j * 62), s(y), s(x0 + j * 62 + 52), s(y + 30)], outline=CY_D, width=s(2))
            d.rectangle([s(x0 + j * 62 + 4), s(y + 30 - bw // 4), s(x0 + j * 62 + 48), s(y + 28)], fill=CY_D)

pts = []
for i in range(60):
    pts.append((s(430 + i * 11), s(640 - 36 * math.sin(i * 0.4) - random.randint(0, 22))))
d.line(pts, fill=CY, width=s(4))
for i in range(0, 60, 6):
    d.ellipse([pts[i][0] - s(5), pts[i][1] - s(5), pts[i][0] + s(5), pts[i][1] + s(5)], fill=CY_B)

glow = img.filter(ImageFilter.GaussianBlur(s(7)))
img = Image.blend(img, Image.composite(glow, img, glow.convert("L").point(lambda v: 255 if v > 20 else 0)), 0.55)
img = img.resize((1536, 704), Image.LANCZOS)
img.save("blender/hud.png")
print("hud ok")
