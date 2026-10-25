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
# Dense instrument UI: subdued blue-gray telemetry, nested dial and grouped tiny readouts.
from PIL import ImageDraw
ui = Image.new('RGB', (768, 480), (5, 14, 23))
d = ImageDraw.Draw(ui)
CY, DIM, WHITE = (89, 163, 186), (28, 67, 84), (164, 187, 191)
d.rectangle((8, 8, 759, 471), outline=DIM, width=5)
d.rectangle((22, 20, 746, 49), fill=(21, 45, 59))
d.text((34, 27), 'POWER SYSTEM / CORE DIAGNOSTICS                     SYS. 01', fill=WHITE)
for x in range(38, 733, 24):
    d.line((x, 74, x, 414), fill=(12, 29, 40))
for y in range(74, 415, 24):
    d.line((36, y, 733, y), fill=(12, 29, 40))
for r in (112, 103, 82, 47):
    d.ellipse((221-r,226-r,221+r,226+r),outline=CY if r==103 else DIM,width=3)
for j in range(48):
    a=j*np.pi/24
    r=96 if j%4 else 90
    d.line((221+r*np.cos(a),226+r*np.sin(a),221+101*np.cos(a),226+101*np.sin(a)),fill=WHITE,width=2)
d.line((221,226,280,162),fill=CY,width=4)
d.text((194, 220),'87.4%',fill=WHITE)
for j in range(9):
    y=82+j*29
    d.text((374,y),f'{j+1:02d}  BUS',fill=WHITE)
    d.rectangle((438,y,693,y+10),fill=DIM)
    d.rectangle((438,y,438+int(rng.integers(70,240)),y+10),fill=CY if j%3 else (143,124,86))
for x in range(390,724,15):
    d.line((x,405,x,405-int(rng.integers(10,49))),fill=CY,width=5)
for j in range(5):
    d.text((42,364+j*17),f'CH-{j+1}  {int(rng.integers(100,990))}.0   STABLE',fill=WHITE)
d.text((383, 440),'OUTPUT  94.02    FLOW  17.53',fill=WHITE)
ui.save(OUT / 'screen_ui.png')
print('power textures ok')
