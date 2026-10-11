"""生成动力室纹理：反应堆火焰、地面格栅、玻璃管能量棒（均可平铺）。"""
from pathlib import Path
import numpy as np
from PIL import Image

OUT = Path(__file__).parent
N = 512
rng = np.random.default_rng(7)


def fbm(stretch_y, power, seed):
    # FFT 合成的分形噪声天然可平铺；纵向频率加权更高 -> 竖向拉长。
    f = np.fft.fftfreq(N)
    fx, fy = np.meshgrid(f, f)
    k = np.sqrt(fx ** 2 + (fy * stretch_y) ** 2)
    k[0, 0] = 1
    r = np.random.default_rng(seed)
    spec = (r.normal(size=(N, N)) + 1j * r.normal(size=(N, N))) / k ** power
    spec[0, 0] = 0
    v = np.real(np.fft.ifft2(spec))
    return (v - v.min()) / (v.max() - v.min())


def ramp(v, stops, cols):
    cols = np.array(cols, float)
    return np.stack([np.interp(v, stops, cols[:, c]) for c in range(3)], -1).astype(np.uint8)


# 反应堆火焰：中心黄白、边缘橙。
v = np.clip((fbm(2.6, 1.7, 7) - 0.25) / 0.6, 0, 1) ** 1.2
Image.fromarray(ramp(v, [0, 0.15, 0.55, 1.0],
                     [(230, 95, 10), (255, 175, 40), (255, 222, 105), (255, 246, 200)])).save(OUT / 'flame.png')

# 格栅：浅银横竖条 + 深色方孔，每张 32×32 孔；孔内亮度随机，模拟下层深浅。
G = 32
cell = N // G
img = np.zeros((N, N, 3), np.uint8)
img[:] = (150, 156, 162)
yy, xx = np.mgrid[0:N, 0:N]
hole = ((xx % cell) > 3) & ((yy % cell) > 3) & ((xx % cell) < cell - 1) & ((yy % cell) < cell - 1)
depth = (rng.random((G, G)) * 10).repeat(cell, 0).repeat(cell, 1)
img[hole] = np.stack([22 + depth, 24 + depth * .8, 28 + depth * .6], -1)[hole]
edge = (((xx % cell) == 3) | ((yy % cell) == 3)) & ~hole
img[edge] = (95, 100, 106)
Image.fromarray(img).save(OUT / 'grate.png')

# 能量棒：沿 U 方向（圆柱长度）的脉冲带 + 细噪声，网页端滚动 V/U 实现流动。
for name, cols in [('energy_blue', [(10, 40, 120), (40, 140, 255), (170, 225, 255), (240, 250, 255)]),
                   ('energy_orange', [(120, 35, 5), (255, 120, 20), (255, 200, 90), (255, 245, 210)])]:
    n = fbm(0.25, 1.4, 11 if 'blue' in name else 13)
    pulse = 0.5 + 0.5 * np.sin(yy / N * np.pi * 2 * 6)
    v = np.clip(0.55 * n + 0.45 * pulse ** 3, 0, 1)
    Image.fromarray(ramp(v, [0, 0.35, 0.75, 1.0], cols)).save(OUT / f'{name}.png')
# 控制台小屏：深蓝底 + 青色条形读数与波形。
from PIL import ImageDraw
ui = Image.new('RGB', (512, 320), (4, 22, 38))
d = ImageDraw.Draw(ui)
CY, DIM = (90, 215, 240), (25, 80, 105)
d.rounded_rectangle((8, 8, 503, 311), 18, outline=CY, width=5)
for i in range(6):
    w = int(rng.integers(90, 300))
    d.rectangle((30, 34 + i * 28, 30 + w, 48 + i * 28), fill=CY if i % 2 == 0 else DIM)
for gx in range(5):
    for gy in range(3):
        d.rectangle((350 + gx * 28, 34 + gy * 34, 370 + gx * 28, 58 + gy * 34),
                    fill=CY if (gx + gy) % 3 else (230, 120, 60))
d.line([(30 + j * 7, 260 + 26 * np.sin(j * .35)) for j in range(66)], fill=CY, width=4)
ui.save(OUT / 'screen_ui.png')
print('power textures ok')
