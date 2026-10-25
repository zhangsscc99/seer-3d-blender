"""生成赛尔机器人面部贴图：黑色圆形面窗 + 两只白眼 + 黑色瞳孔。"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).parent
N = 512
img = Image.new('RGB', (N, N), (9, 10, 14))
d = ImageDraw.Draw(img)

# 面窗内部的暗色渐变（中心略亮，边缘更黑）
for r in range(250, 0, -2):
    t = r / 250
    v = int(18 - 9 * t)
    d.ellipse((N / 2 - r, N / 2 - r, N / 2 + r, N / 2 + r), fill=(v, v + 1, v + 3))

# 两只大白眼球：略向内倾的椭圆，中间留一道细缝
eye = (243, 245, 235)
for cx in (178, 334):
    d.ellipse((cx - 74, 166, cx + 74, 402), fill=eye)
# 眼球高光：左上角一小团柔光（画在瞳孔之前，保证瞳孔不被提亮）
hl = Image.new('RGB', (N, N), (0, 0, 0))
hd = ImageDraw.Draw(hl)
for cx in (178, 334):
    hd.ellipse((cx - 58, 200, cx - 26, 244), fill=(120, 126, 132))
hl = hl.filter(ImageFilter.GaussianBlur(9))
img = Image.composite(hl, img, hl.convert('L').point(lambda x: min(255, int(x * 0.55))))
d = ImageDraw.Draw(img)
# 瞳孔：各自眼睛中央偏内的黑色竖椭圆，不碰眼球边缘，避免远看连成“W”
for cx, inner in ((178, +1), (334, -1)):
    px = cx + inner * 28
    d.rounded_rectangle((px - 16, 234, px + 16, 336), radius=16, fill=(6, 7, 9))

# 面窗外沿一圈极暗的密封槽，避免贴图边缘和金属框硬碰
for r in range(252, 242, -1):
    a = (r - 242) / 10
    d.ellipse((N / 2 - r, N / 2 - r, N / 2 + r, N / 2 + r),
              outline=(int(14 * (1 - a)), int(16 * (1 - a)), int(20 * (1 - a))), width=1)

img.save(OUT / 'seer_face.png')
print('seer face texture ok')
