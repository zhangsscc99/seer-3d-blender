"""生成传送舱纹理：警示条、地面肋条、通风口、星云、跑灯环、终端环、拉丝金属。"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

OUT = Path(__file__).parent
N = 512
rng = np.random.default_rng(23)
yy, xx = np.mgrid[0:N, 0:N]


def fbm(stretch_y, power, seed, size=N):
    f = np.fft.fftfreq(size)
    fx, fy = np.meshgrid(f, f)
    k = np.sqrt(fx ** 2 + (fy * stretch_y) ** 2)
    k[0, 0] = 1
    r = np.random.default_rng(seed)
    spec = (r.normal(size=(size, size)) + 1j * r.normal(size=(size, size))) / k ** power
    spec[0, 0] = 0
    v = np.real(np.fft.ifft2(spec))
    return (v - v.min()) / (v.max() - v.min())


def ramp(v, stops, cols):
    cols = np.array(cols, float)
    return np.stack([np.interp(v, stops, cols[:, c]) for c in range(3)], -1).astype(np.uint8)


# 1. 黄黑斜警示条：更宽的旧金色条纹 + 磨损。
stripe = (((xx + yy) % 64) < 37).astype(np.uint8)
wear = (fbm(1.0, 1.2, 31) * 0.22 + 0.78)
hazard = np.where(stripe[..., None] == 1,
                  np.array([176, 146, 66], float),
                  np.array([24, 23, 24], float)) * wear[..., None]
edge = (np.clip(1.0 - np.abs(((xx + yy) % 64) - 18.5) / 18.5, 0, 1) * 0.05)[..., None]
hazard = np.clip(hazard + edge * 255, 0, 255).astype(np.uint8)
Image.fromarray(hazard).save(OUT / 'tele_hazard.png')

# 2. 地面肋条：深色凹槽 + 银灰叶片，对比度压低，避免像白色刻线。
ribs = np.zeros((N, N, 3), np.float64)
ribs[:] = (42, 46, 51)
bar = (yy % 64) < 16
bar_hi = (yy % 64) < 4
ribs[bar] = (92, 98, 104)
ribs[bar_hi] = (116, 122, 128)
# 横向断续的支撑筋，避免过于规则。
rib = (xx % 192) < 10
ribs[rib] = np.where(bar[rib][..., None], np.array([132, 138, 144]), np.array([64, 70, 76]))
noise = (fbm(0.5, 1.1, 37)[..., None] - 0.5) * 12
Image.fromarray(np.clip(ribs + noise, 0, 255).astype(np.uint8)).save(OUT / 'tele_ribs.png')

# 3. 通风口：更粗的深色横格栅 + 蓝色内光。
vent = np.zeros((N, N, 3), np.float64)
vent[:] = (14, 19, 25)
glow = np.clip(np.sin((yy / N) * np.pi * 24) * 0.5 + 0.5, 0, 1) ** 2
vent[..., 2] += glow * 110
vent[..., 1] += glow * 58
slat = (yy % 34) < 12
vent[slat] = (118, 126, 134)
vent[slat & ((yy % 34) < 3)] = (188, 196, 204)
Image.fromarray(np.clip(vent, 0, 255).astype(np.uint8)).save(OUT / 'tele_vent.png')

# 4. 星云：深海军蓝云气 + 两侧暖色气团 + 细小星点（整体压暗，玻璃下更通透）。
n1 = fbm(1.4, 1.6, 41)
n2 = fbm(0.8, 1.3, 43)
v = np.clip(0.62 * n1 + 0.38 * n2, 0, 1)
neb = ramp(v, [0.0, 0.28, 0.52, 0.74, 1.0],
           [(4, 7, 16), (12, 24, 48), (26, 50, 84), (56, 66, 104), (96, 84, 92)])
# 偏心暖色星云（参考图玻璃下沿左右各一团橙光）。
for cx0, cy0, rad in ((.30, .74, .24), (.74, .66, .20), (.58, .40, .14)):
    rr0 = np.hypot(xx / N - cx0, yy / N - cy0)
    blob = np.clip(1.0 - rr0 / rad, 0, 1) ** 2.6
    neb = np.clip(neb + blob[..., None] * np.array([130, 74, 28]), 0, 255)
img = Image.fromarray(neb.astype(np.uint8))
d = ImageDraw.Draw(img)
for _ in range(170):
    x, y = rng.integers(0, N, 2)
    b = int(rng.integers(45, 110))
    d.ellipse((x, y, x + 1, y + 1), fill=(b, min(255, b + 8), 255))
img.save(OUT / 'tele_nebula.png')

# 5. 跑灯环：U 方向 24 段，V 方向中部最亮；scrolling uOffset 即为跑灯。
seg = 24
phase = (xx.astype(float) / N * seg) % 1.0
seg_on = (phase < 0.62).astype(float)
pulse = np.clip(np.sin((phase / 0.62) * np.pi), 0, 1) ** 0.7 * seg_on
band = np.exp(-((yy / N - 0.5) ** 2) / 0.018)
chase = np.zeros((N, N, 3), float)
chase[..., 0] = pulse * band * 90
chase[..., 1] = pulse * band * 235
chase[..., 2] = pulse * band * 255
chase += np.array([2, 8, 12])
Image.fromarray(np.clip(chase, 0, 255).astype(np.uint8)).save(OUT / 'tele_chase.png')

# 6. 终端环：同心银环 + 青色刻度 + 深蓝底。
ring = Image.new('RGB', (N, N), (5, 8, 14))
d = ImageDraw.Draw(ring)
cx = cy = N // 2
for rad, col, w in [(238, (108, 116, 126), 5), (214, (42, 74, 92), 3),
                    (176, (158, 168, 178), 4), (150, (60, 150, 180), 3),
                    (118, (120, 132, 142), 3), (84, (44, 118, 150), 4),
                    (48, (170, 220, 235), 3)]:
    d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), outline=col, width=w)
for j in range(48):
    a = j * np.pi / 24
    r0, r1 = (196, 230) if j % 4 else (184, 232)
    col = (70, 200, 235) if j % 4 == 0 else (130, 140, 150)
    d.line((cx + r0 * np.cos(a), cy + r0 * np.sin(a),
            cx + r1 * np.cos(a), cy + r1 * np.sin(a)), fill=col, width=3)
d.ellipse((cx - 18, cy - 18, cx + 18, cy + 18), fill=(120, 220, 245))
ring.save(OUT / 'tele_ring.png')

# 7. 传送门发光盘：外圈 12 段亮青环 + 内部整片淡蓝发光玻璃（参考图中心的“蓝眼睛”）。
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


cx = cy = N // 2
rr = np.hypot(xx - cx, yy - cy) / (N / 2)
ang = np.arctan2(yy - cy, xx - cx)
# 环带位置：参考图的亮环位于外缘 0.66–0.93 半径处，中心大片区域被金属帽盖住。
r_band0, r_band1 = .700, .930
# 内盘（会被几何中心帽遮住）：深蓝灰金属，向外过渡到亮环内缘。
g = np.clip((rr - .42) / (r_band0 - .42), 0, 1)
stops = [0., .45, 1.]
cols = [(10, 16, 24), (22, 40, 60), (58, 82, 106)]
inner = np.stack([np.interp(g, stops, [c[k] for c in cols]) for k in range(3)], -1)
# 内盘上的细同心刻线（参考图里的蓝色同心圆）。
for rad, w, add in ((.50, .004, 18), (.565, .004, 20)):
    line = np.exp(-((rr - rad) / w) ** 2) * add
    inner += line[..., None] * np.array([.55, .85, 1.])
# 外圈：12 段淡青环，段缝是窄暗槽，段内保持明亮（参考图没有额外的中央刻线）。
phase = ((ang / (2 * np.pi)) * 12) % 1.0
seam = smoothstep(0, .055, phase) * smoothstep(0, .055, 1 - phase)
ring = np.stack([178 * (.42 + .58 * seam), 230 * (.42 + .58 * seam), 248 * (.42 + .58 * seam)], -1)
band = smoothstep(r_band0, r_band0 + .012, rr) * smoothstep(1.005, r_band1, rr)
dia = inner * (1 - band[..., None]) + ring * band[..., None]
# 环外沿留一圈深色过渡，避免和银色外框硬碰。
dia *= (1 - .55 * smoothstep(.965, 1.0, rr))[..., None]
dia = np.clip(dia, 0, 255).astype(np.uint8)
Image.fromarray(dia).save(OUT / 'tele_diaphragm.png')

# 8. 拉丝金属：横向细噪声。
brushed = fbm(0.08, 1.0, 53) * 32 + 172
brushed = np.clip(brushed + (rng.random((N, N)) - 0.5) * 8, 0, 255)
Image.fromarray(np.stack([brushed * 0.98, brushed, brushed * 1.02], -1).astype(np.uint8)).save(
    OUT / 'tele_brushed.png')

print('teleport textures ok')
