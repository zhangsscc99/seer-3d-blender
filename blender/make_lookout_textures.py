"""Rebuild the lookout's sky-only plate and reproducible material textures.

The reference is used only as a source of *visible sky pixels*.  The title,
window assembly, capsule, platform, deck and all equipment are conservatively
masked before inpainting.  No architectural part of the reference is used as a
scene texture.  The binary sky mask is white for untouched reference sky and
black for reconstructed pixels.

Run with the existing Python environment (Pillow, NumPy and SciPy):
    python3 blender/make_lookout_textures.py
"""
from __future__ import annotations

from pathlib import Path
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REFERENCE = ROOT / "refs" / "lookout_deck.png"
RESAMPLE = Image.Resampling.LANCZOS


def _save(image: Image.Image, name: str) -> Path:
    path = HERE / name
    image.save(path, format="PNG", compress_level=6)
    return path


def _smoothstep(t: np.ndarray) -> np.ndarray:
    return t * t * (3.0 - 2.0 * t)


def _value_noise(w: int, h: int, cells_x: int, cells_y: int,
                 seed: int) -> np.ndarray:
    """Periodic, smoothly interpolated value noise; no external noise module."""
    rng = np.random.default_rng(seed)
    grid = rng.random((cells_y, cells_x), dtype=np.float32)
    x = np.arange(w, dtype=np.float32) * (cells_x / float(w))
    y = np.arange(h, dtype=np.float32) * (cells_y / float(h))
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    tx = _smoothstep(x - x0)
    ty = _smoothstep(y - y0)
    x1 = (x0 + 1) % cells_x
    # Interpolate x while the intermediate is still short, then interpolate y.
    row = grid[:, x0] * (1.0 - tx)[None, :] + grid[:, x1] * tx[None, :]
    y1 = (y0 + 1) % cells_y
    return row[y0, :] * (1.0 - ty)[:, None] + row[y1, :] * ty[:, None]


def _fbm(w: int, h: int, seed: int,
         octaves=((5, 3, 0.46), (11, 6, 0.27), (23, 13, 0.14),
                  (47, 27, 0.075), (97, 55, 0.035),
                  (193, 109, 0.01))) -> np.ndarray:
    out = np.zeros((h, w), dtype=np.float32)
    weight_sum = 0.0
    for i, (cx, cy, weight) in enumerate(octaves):
        out += _value_noise(w, h, cx, cy, seed + i * 37) * weight
        weight_sum += weight
    return out / weight_sum


def _add_stars(image: np.ndarray, count: int, seed: int,
               allowed: np.ndarray | None = None,
               brightness=(28.0, 155.0),
               sigma_range=(0.38, 0.92)) -> None:
    """Add restrained antialiased stars, optionally only inside a mask."""
    h, w = image.shape[:2]
    rng = np.random.default_rng(seed)
    permitted = np.zeros((h, w), dtype=bool) if allowed is None else allowed
    made = 0
    attempts = 0
    while made < count and attempts < count * 12:
        attempts += 1
        x = int(rng.integers(0, w))
        y = int(rng.integers(0, h))
        if allowed is not None and not permitted[y, x]:
            continue
        sigma = float(rng.uniform(*sigma_range))
        if rng.random() < 0.09:
            sigma *= 1.45
        amp = float(rng.uniform(*brightness))
        if rng.random() < 0.035:
            amp *= 1.35
        color = rng.choice(3)
        tint = ((1.0, 0.94, 0.84), (0.79, 0.88, 1.0),
                (0.94, 0.97, 1.0))[color]
        radius = max(2, int(math.ceil(sigma * 3.2)))
        yy, xx = np.mgrid[-radius:radius + 1, -radius:radius + 1]
        rr = (xx * xx + yy * yy).astype(np.float32)
        core = np.exp(-rr / (2.0 * sigma * sigma)) * amp
        halo = np.exp(-rr / (2.0 * (sigma * 2.2) ** 2)) * (amp * 0.075)
        star = core + halo
        for oy in range(-radius, radius + 1):
            py = (y + oy) % h
            if allowed is not None and not permitted[py, x]:
                continue
            for ox in range(-radius, radius + 1):
                px = (x + ox) % w
                if allowed is not None and not permitted[py, px]:
                    continue
                value = float(star[oy + radius, ox + radius])
                image[py, px, 0] += value * tint[0]
                image[py, px, 1] += value * tint[1]
                image[py, px, 2] += value * tint[2]
        made += 1


def _sky_mask(size: tuple[int, int]) -> np.ndarray:
    """Return the conservative removal mask in the 2263x1272 crop."""
    w, h = size
    assert (w, h) == (2263, 1272)
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)

    # Title plus its glow and JPEG halo.  This is deliberately over-sized.
    title_box = (176, 100, 676, 250)
    draw.rectangle(title_box, fill=255)

    # Entire outer window/frame assembly and its interior.  Although the dark
    # clouds inside could be retained, conservatively rebuilding this opening
    # prevents an octagonal cloud island, dark mullion or capsule ghost from
    # surviving in the camera-ray sky plate.
    arch_outer = [
        (1055, 134), (1248, 134), (1272, 153), (1340, 153),
        (1380, 180), (1438, 218), (1492, 284), (1520, 365),
        (1522, 455), (1495, 535), (1445, 600), (1372, 637),
        (952, 637), (878, 596), (828, 535), (798, 455),
        (798, 367), (826, 288), (878, 218), (936, 177),
        (953, 146), (1040, 146),
    ]
    draw.polygon(arch_outer, fill=255)

    # Capsule, its cap, robot, arms and pedestal; overlaps the deck mask.
    capsule = [
        (1090, 389), (1222, 389), (1258, 425), (1270, 532),
        (1300, 566), (1310, 688), (1003, 688), (1010, 578),
        (1048, 538), (1054, 430),
    ]
    draw.polygon(capsule, fill=255)

    # A conservative upper envelope above *every* deck/equipment silhouette.
    # Everything below it is reconstructed, including the side turrets.
    deck_envelope = [
        (-12, 918), (95, 780), (195, 674), (295, 574),
        (405, 526), (520, 498), (635, 490), (755, 496),
        (875, 492), (1000, 492), (1130, 490), (1270, 493),
        (1390, 492), (1510, 493), (1630, 488), (1740, 500),
        (1840, 535), (1940, 585), (2050, 638), (2160, 684),
        (2275, 708), (2275, 1285), (-12, 1285),
    ]
    draw.polygon(deck_envelope, fill=255)

    remove = np.asarray(mask, dtype=np.uint8) > 0
    # Four extra pixels remove antialiasing, emissive fringes and JPEG ghosts.
    return ndimage.binary_dilation(remove, iterations=4)


def _diffuse_sky(source: np.ndarray, remove: np.ndarray) -> np.ndarray:
    """Multiscale constraint diffusion using only pixels marked as clean sky."""
    known = ~remove
    sky_values = source[known]
    initial = np.median(sky_values, axis=0).astype(np.float32)
    estimate = np.empty(source.shape, dtype=np.float32)
    estimate[:] = initial
    estimate[known] = source[known]
    # Coarse stages cross large holes; progressively finer stages seat the
    # result against the original sky without modifying any known pixel.
    for sigma in (180.0, 120.0, 78.0, 48.0, 29.0, 17.0, 9.0, 4.5, 2.0):
        for channel in range(3):
            blurred = ndimage.gaussian_filter(
                estimate[..., channel], sigma=sigma, mode="nearest", truncate=3.0
            )
            estimate[..., channel][remove] = blurred[remove]
        estimate[known] = source[known]
    return estimate


def sky_plate() -> list[Path]:
    # The file has a JPEG payload despite its .png suffix.  Crop exactly the
    # effective picture, excluding both dark side bars (x=270..2532 inclusive).
    reference = Image.open(REFERENCE).convert("RGB")
    if reference.size != (2800, 1272):
        raise ValueError(f"Unexpected lookout reference size: {reference.size}")
    reference = reference.crop((270, 0, 2533, 1272))
    source = np.asarray(reference, dtype=np.uint8)
    h, w = source.shape[:2]
    remove = _sky_mask((w, h))
    known = ~remove

    fill = _diffuse_sky(source, remove)

    # Coherent, restrained cloud/filament detail prevents the reconstructed
    # areas from becoming large blurred gradients.  This is added only inside
    # the mask, fading to zero at its boundary.
    # All synthesized structure is procedural.  Apart from the explicitly
    # retained clean-sky pixels, no reference patch is tiled or warped, so a
    # missed bright pixel can never replicate a window light or piece of deck.
    cloud = _warped_cloud(w, h, 7201)
    for i, (cx, cy, weight) in enumerate(
            ((192, 96, 0.25), (384, 192, 0.13), (768, 384, 0.06))):
        cloud += (_value_noise(w, h, cx, cy, 7219 + i * 41) - 0.5) * weight
    fiber = _fbm(
        w, h, 7333,
        octaves=((7, 19, 0.42), (15, 43, 0.28), (31, 89, 0.17),
                 (67, 181, 0.09), (137, 367, 0.04)),
    )
    fine = _value_noise(w, h, 383, 211, 7411)
    gate_noise = _value_noise(w, h, 9, 5, 7191)
    gate = _smoothstep(np.clip((gate_noise - 0.28) * 2.0, 0.0, 1.0))
    distance = ndimage.distance_transform_edt(remove).astype(np.float32)
    fade = _smoothstep(np.clip(distance / 38.0, 0.0, 1.0))

    xx = np.arange(w, dtype=np.float32)[None, :]
    red = np.clip((1250.0 - xx) / 1000.0, 0.0, 1.0)
    blue = np.clip((xx - 950.0) / 1000.0, 0.0, 1.0)
    purple = np.sqrt(red * blue)
    density = np.clip((cloud - 0.44) * 3.2, 0.0, 1.0) * gate
    filament = np.clip((fiber - 0.50) * 3.0, 0.0, 1.0) ** 1.4 * gate
    body = density * (0.24 + 0.76 * filament) * fade
    fill += body[..., None] * (
        red[..., None] * np.array([55.0, 19.0, 24.0], dtype=np.float32)
        + blue[..., None] * np.array([16.0, 29.0, 47.0], dtype=np.float32)
        + purple[..., None] * np.array([18.0, 8.0, 22.0], dtype=np.float32)
    )
    hot = np.clip((fiber - 0.58) * 3.5, 0.0, 1.0) ** 2
    hot *= gate * (0.30 + 0.70 * density) * fade
    fill += hot[..., None] * (
        red[..., None] * np.array([45.0, 28.0, 24.0], dtype=np.float32)
        + blue[..., None] * np.array([22.0, 32.0, 45.0], dtype=np.float32)
    )
    detail = ((cloud - 0.5) * 5.0 + (fine - 0.5) * 1.8) * fade
    fill += detail[..., None] * np.array([1.10, 0.86, 1.18], dtype=np.float32)
    dark_lane = np.clip((0.48 - fiber) * 2.0, 0.0, 1.0) * gate * fade
    fill *= (1.0 - dark_lane[..., None] * 0.15)

    # Reintroduce a sparse star field only well inside reconstructed regions.
    star_allowed = ndimage.binary_erosion(remove, iterations=4)
    _add_stars(fill, 760, seed=7501, allowed=star_allowed,
               brightness=(24.0, 142.0))

    output = np.clip(fill, 0.0, 255.0).astype(np.uint8)
    # A hard final guarantee: every retained sky pixel is bit-for-bit original;
    # no star, noise, colour transform or smoothing can leak outside the mask.
    output[known] = source[known]
    assert np.array_equal(output[known], source[known])

    debug_mask = np.where(remove, 0, 255).astype(np.uint8)
    plate_path = _save(Image.fromarray(output, "RGB"), "lookout_sky_plate.png")
    mask_path = _save(Image.fromarray(debug_mask, "L"), "lookout_sky_mask.png")
    print(f"sky plate: {100.0 * known.mean():.1f}% original sky, "
          f"{100.0 * remove.mean():.1f}% reconstructed")
    return [plate_path, mask_path]


def _warped_cloud(w: int, h: int, seed: int) -> np.ndarray:
    """Warp a periodic random lattice into non-blobby, curling cloud structure."""
    rng = np.random.default_rng(seed)
    cells_x, cells_y = 96, 48
    grid = rng.random((cells_y, cells_x), dtype=np.float32)
    warp_x = (_value_noise(w, h, 7, 4, seed + 11) - 0.5) * 5.2
    warp_y = (_value_noise(w, h, 6, 5, seed + 23) - 0.5) * 4.0
    x = np.arange(w, dtype=np.float32)[None, :] * (cells_x / float(w))
    y = np.arange(h, dtype=np.float32)[:, None] * (cells_y / float(h))
    coordinates = np.array([y + warp_y, x + warp_x], dtype=np.float32)
    return ndimage.map_coordinates(
        grid, coordinates, order=1, mode="grid-wrap", prefilter=False
    ).astype(np.float32)


def _add_galaxy(image: np.ndarray, x: int, y: int, radius: float,
                angle: float, tint: tuple[float, float, float],
                intensity: float) -> None:
    h, w = image.shape[:2]
    reach = int(math.ceil(radius * 3.0))
    yy, xx = np.mgrid[-reach:reach + 1, -reach:reach + 1].astype(np.float32)
    ca, sa = math.cos(angle), math.sin(angle)
    xr = xx * ca + yy * sa
    yr = -xx * sa + yy * ca
    ex = xr / radius
    ey = yr / (radius * 0.31)
    rr = np.sqrt(ex * ex + ey * ey)
    theta = np.arctan2(ey, ex)
    disk = np.exp(-rr * rr * 1.7)
    core = np.exp(-rr * rr * 9.0)
    arms = (0.5 + 0.5 * np.cos(theta * 2.0 - rr * 8.5)) ** 7
    glow = disk * (0.18 + 0.82 * arms) + core * 1.3
    glow *= np.clip(1.0 - rr / 3.0, 0.0, 1.0) * intensity
    for oy in range(-reach, reach + 1):
        py = (y + oy) % h
        for ox in range(-reach, reach + 1):
            px = (x + ox) % w
            value = float(glow[oy + reach, ox + reach])
            if value > 0.01:
                image[py, px] += value * np.asarray(tint, dtype=np.float32)


def nebula() -> Path:
    """4096px dark red/purple + blue nebula with fine filaments and stars."""
    w, h = 4096, 2048
    cloud = _warped_cloud(w, h, 8101)
    # Successive octaves supply actual small-scale structure, rather than a
    # handful of large Gaussian blobs as in the old texture.
    for i, (cx, cy, weight) in enumerate(
            ((192, 96, 0.29), (384, 192, 0.15),
             (768, 384, 0.075), (1536, 768, 0.035))):
        cloud += (_value_noise(w, h, cx, cy, 8119 + i * 41) - 0.5) * weight
    fiber = _fbm(
        w, h, 8231,
        octaves=((13, 37, 0.38), (29, 83, 0.29), (61, 173, 0.18),
                 (127, 353, 0.10), (257, 719, 0.05)),
    )
    fine = _value_noise(w, h, 1024, 512, 8293)
    gate_noise = _value_noise(w, h, 9, 5, 8201)
    gate = _smoothstep(np.clip((gate_noise - 0.29) * 2.1, 0.0, 1.0))
    density = np.clip((cloud - 0.46) * 3.4, 0.0, 1.0) * gate
    filaments = np.clip((fiber - 0.50) * 3.0, 0.0, 1.0) ** 1.45 * gate

    u = np.arange(w, dtype=np.float32)[None, :] / w
    v = np.arange(h, dtype=np.float32)[:, None] / h
    # Periodic colour regions make the horizontal sphere seam continuous.
    red_region = (0.5 + 0.5 * np.cos(2.0 * np.pi * (u - 0.20))) ** 1.5
    blue_region = (0.5 + 0.5 * np.cos(2.0 * np.pi * (u - 0.70))) ** 1.5

    def wrapped_dx(center):
        return (u - center + 0.5) % 1.0 - 0.5

    # Localized complexes leave genuinely dark sky between the detailed wisps.
    red_zone = np.exp(-((wrapped_dx(0.17) / 0.23) ** 2
                        + ((v - 0.27) / 0.31) ** 2) * 1.35)
    red_zone += 0.72 * np.exp(-((wrapped_dx(0.29) / 0.25) ** 2
                               + ((v - 0.76) / 0.28) ** 2) * 1.5)
    blue_zone = np.exp(-((wrapped_dx(0.71) / 0.26) ** 2
                         + ((v - 0.30) / 0.34) ** 2) * 1.3)
    blue_zone += 0.70 * np.exp(-((wrapped_dx(0.84) / 0.23) ** 2
                                + ((v - 0.79) / 0.29) ** 2) * 1.45)
    red = red_region * (0.09 + 0.91 * np.clip(red_zone, 0.0, 1.0))
    blue = blue_region * (0.09 + 0.91 * np.clip(blue_zone, 0.0, 1.0))
    purple = np.sqrt(red * blue)

    image = np.empty((h, w, 3), dtype=np.float32)
    image[:] = np.array([3.5, 5.0, 11.0], dtype=np.float32)
    red_mass = density * (0.25 + 0.60 * filaments) * 2.15
    blue_mass = density * (0.28 + 0.58 * filaments) * 2.15
    image += red_mass[..., None] * red[..., None] * np.array(
        [105.0, 36.0, 43.0], dtype=np.float32)
    image += blue_mass[..., None] * blue[..., None] * np.array(
        [30.0, 55.0, 88.0], dtype=np.float32)
    image += density[..., None] * purple[..., None] * 2.1 * np.array(
        [42.0, 18.0, 51.0], dtype=np.float32)

    hot_fiber = np.clip((fiber - 0.58) * 3.6, 0.0, 1.0) ** 2
    hot_fiber *= gate * (0.30 + 0.70 * density) * 3.8
    image += hot_fiber[..., None] * red[..., None] * np.array(
        [78.0, 46.0, 38.0], dtype=np.float32)
    image += hot_fiber[..., None] * blue[..., None] * np.array(
        [35.0, 48.0, 65.0], dtype=np.float32)
    dark_lane = np.clip((0.49 - fiber) * 2.1, 0.0, 1.0) * (0.25 + 0.75 * gate)
    image *= (1.0 - dark_lane[..., None] * 0.22)
    image += (fine[..., None] - 0.5) * np.array(
        [1.8, 1.6, 2.3], dtype=np.float32)

    rng = np.random.default_rng(8377)
    for i in range(10):
        _add_galaxy(
            image,
            int(rng.integers(80, w - 80)), int(rng.integers(90, h - 90)),
            radius=float(rng.uniform(10.0, 23.0)),
            angle=float(rng.uniform(0.0, math.pi)),
            tint=((0.80, 0.88, 1.0) if i % 3 else (1.0, 0.91, 0.76)),
            intensity=float(rng.uniform(24.0, 46.0)),
        )
    _add_stars(image, 4000, seed=8429, brightness=(30.0, 172.0),
               sigma_range=(0.50, 1.18))
    _add_stars(image, 85, seed=8441, brightness=(85.0, 185.0),
               sigma_range=(1.0, 1.62))
    return _save(Image.fromarray(np.clip(image, 0, 255).astype(np.uint8), "RGB"),
                 "lookout_nebula.png")


def _catmull_rom(points: list[tuple[float, float]], samples: int = 12,
                 closed: bool = True) -> list[tuple[float, float]]:
    pts = [np.array(p, dtype=np.float64) for p in points]
    result = []
    count = len(pts) if closed else len(pts) - 1
    for i in range(count):
        p0 = pts[(i - 1) % len(pts)] if closed or i else pts[0]
        p1 = pts[i]
        p2 = pts[(i + 1) % len(pts)]
        p3 = pts[(i + 2) % len(pts)] if closed or i + 2 < len(pts) else pts[-1]
        for j in range(samples):
            t = j / samples
            value = 0.5 * ((2.0 * p1) + (-p0 + p2) * t
                           + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t * t
                           + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t * t * t)
            result.append((float(value[0]), float(value[1])))
    if not closed:
        result.append(points[-1])
    return result


def badge() -> Path:
    """Redraw only the small olive/blue/rust helmet emblem, without its hex frame."""
    size = 1024
    scale = 3
    canvas_size = (size * scale, size * scale)
    # Transparent dark RGB is intentional: it also looks correct in a material
    # that reads RGB but has not connected the image's alpha socket.
    image = Image.new("RGBA", canvas_size, (3, 8, 12, 0))
    draw = ImageDraw.Draw(image, "RGBA")

    def sc(v):
        return int(round(v * scale))

    def box(coords):
        return tuple(sc(v) for v in coords)

    def polygon(points, fill, outline=None, width=1, smooth=False):
        pts = _catmull_rom(points, 10) if smooth else points
        scaled = [(sc(x), sc(y)) for x, y in pts]
        draw.polygon(scaled, fill=fill)
        if outline:
            draw.line(scaled + [scaled[0]], fill=outline,
                      width=sc(width), joint="curve")

    def rounded(coords, radius, fill, outline=None, width=1):
        draw.rounded_rectangle(box(coords), radius=sc(radius), fill=fill,
                               outline=outline, width=sc(width))

    def ellipse(coords, fill, outline=None, width=1):
        draw.ellipse(box(coords), fill=fill, outline=outline, width=sc(width))

    def line(points, fill, width):
        draw.line([(sc(x), sc(y)) for x, y in points], fill=fill,
                  width=sc(width), joint="curve")

    def gradient_rounded(coords, radius, top, bottom, outline, width):
        x0, y0, x1, y1 = box(coords)
        mask = Image.new("L", canvas_size, 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle((x0, y0, x1, y1), radius=sc(radius), fill=255)
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        gradient = Image.new("RGBA", (bw, bh))
        gd = ImageDraw.Draw(gradient)
        for yy in range(bh):
            t = yy / max(1, bh - 1)
            color = tuple(round(top[c] * (1.0 - t) + bottom[c] * t)
                          for c in range(3)) + (255,)
            gd.line((0, yy, bw, yy), fill=color)
        image.paste(gradient, (x0, y0), mask.crop((x0, y0, x1 + 1, y1 + 1)))
        draw.rounded_rectangle((x0, y0, x1, y1), radius=sc(radius),
                               outline=outline, width=sc(width))

    outer = [
        (455, 82), (582, 82), (675, 119), (733, 205), (754, 330),
        (795, 407), (824, 480), (819, 605), (779, 674), (742, 692),
        (728, 817), (674, 892), (583, 934), (415, 934), (330, 902),
        (282, 835), (263, 716), (236, 620), (226, 434), (247, 294),
        (294, 194), (360, 120),
    ]
    polygon(outer, (37, 48, 44, 255), (177, 181, 132, 255), 25, True)
    inner = [
        (452, 113), (573, 111), (647, 144), (698, 222), (712, 383),
        (697, 602), (708, 770), (650, 858), (571, 900), (423, 900),
        (349, 859), (314, 777), (296, 582), (286, 395), (306, 252),
        (353, 163),
    ]
    polygon(inner, (105, 112, 86, 255), (211, 202, 145, 255), 12, True)

    # Muted olive crown panels and the tiny warm-yellow mark in the reference.
    polygon([(350, 167), (449, 125), (570, 124), (650, 163),
             (681, 230), (625, 258), (380, 254), (315, 229)],
            (126, 131, 99, 255), (153, 156, 115, 255), 7, True)
    line([(408, 146), (398, 213), (423, 247)], (77, 85, 71, 255), 8)
    line([(578, 142), (603, 204), (593, 248)], (77, 85, 71, 255), 8)
    rounded((486, 130, 548, 184), 15, (156, 153, 94, 255),
            (188, 181, 119, 255), 5)
    line([(518, 139), (518, 174)], (98, 105, 77, 255), 5)

    gradient_rounded((316, 277, 705, 682), 126,
                     (75, 103, 119), (39, 66, 84),
                     (119, 139, 133, 255), 11)
    # Soft visor reflection and lower blue panel; no text or frame capture.
    polygon([(354, 314), (464, 290), (424, 597), (344, 608)],
            (151, 177, 179, 28))
    rounded((365, 399, 617, 614), 82, (48, 78, 99, 110))
    line([(382, 627), (568, 627)], (31, 57, 74, 180), 8)

    gradient_rounded((337, 616, 687, 873), 84,
                     (158, 76, 57), (105, 45, 39),
                     (211, 132, 88, 255), 12)
    polygon([(369, 654), (425, 635), (407, 827), (365, 806)],
            (214, 119, 78, 42))
    line([(399, 846), (617, 846)], (76, 39, 36, 190), 7)

    # Asymmetric teal side fitting and its two small fasteners.
    side = [(689, 351), (753, 383), (796, 462), (793, 576),
            (758, 655), (710, 688), (677, 628), (690, 509)]
    polygon(side, (38, 83, 94, 255), (115, 151, 139, 255), 11, True)
    polygon([(732, 391), (768, 445), (766, 572), (735, 622)],
            (64, 112, 118, 210), smooth=True)
    ellipse((704, 424, 758, 478), (32, 67, 78, 255),
            (124, 161, 148, 255), 7)
    ellipse((719, 438, 743, 462), (112, 153, 146, 255))
    ellipse((718, 532, 768, 582), (34, 69, 78, 255),
            (107, 147, 137, 255), 7)
    ellipse((733, 545, 754, 566), (106, 147, 137, 255))

    # Cream edge glints and the bottom lip make the tiny mark readable at 1024.
    line([(326, 239), (292, 364), (299, 498)], (226, 216, 159, 210), 13)
    line([(344, 799), (373, 866), (432, 893)], (230, 184, 125, 190), 10)
    polygon([(358, 866), (420, 900), (580, 900), (651, 865),
             (626, 911), (568, 936), (420, 936), (372, 915)],
            (95, 83, 61, 255), (187, 158, 105, 255), 8, True)

    icon = image.resize((800, 800), RESAMPLE)
    result = Image.new("RGBA", (size, size), (3, 8, 12, 0))
    result.alpha_composite(icon, dest=(112, 112))
    return _save(result, "lookout_badge.png")


def planet() -> Path:
    """Reproducible 2:1 gas-giant map with turbulent bands and wrapped storms."""
    w, h = 1024, 512
    yy = np.arange(h, dtype=np.float32)[:, None] / h
    turbulence = _fbm(
        w, h, 9101,
        octaves=((7, 18, 0.40), (15, 43, 0.29), (31, 91, 0.18),
                 (67, 181, 0.09), (131, 367, 0.04)),
    )
    fine = _value_noise(w, h, 256, 256, 9151)
    warped_y = yy + (turbulence - 0.5) * 0.034
    bands = (0.50 + 0.23 * np.sin(warped_y * math.tau * 8.0 + 0.7)
             + 0.14 * np.sin(warped_y * math.tau * 17.0 - 0.8)
             + 0.07 * np.sin(warped_y * math.tau * 35.0 + turbulence * 3.0))
    bands = np.clip(bands + (turbulence - 0.5) * 0.34, 0.0, 1.0)
    dark = np.array([58.0, 51.0, 47.0], dtype=np.float32)
    mid = np.array([112.0, 91.0, 70.0], dtype=np.float32)
    light = np.array([157.0, 137.0, 107.0], dtype=np.float32)
    lower = np.clip(bands * 2.0, 0.0, 1.0)
    upper = np.clip((bands - 0.5) * 2.0, 0.0, 1.0)
    image = dark[None, None, :] * (1.0 - lower[..., None]) + mid[None, None, :] * lower[..., None]
    image = image * (1.0 - upper[..., None]) + light[None, None, :] * upper[..., None]
    cool_band = np.clip((0.5 + 0.5 * np.sin(warped_y * math.tau * 5.0 - 1.4) - 0.69) * 2.8, 0.0, 1.0)
    image = image * (1.0 - cool_band[..., None] * 0.38) + np.array(
        [74.0, 82.0, 87.0], dtype=np.float32)[None, None, :] * cool_band[..., None] * 0.38
    image += (fine[..., None] - 0.5) * np.array([4.0, 3.6, 3.1], dtype=np.float32)

    yy_px = np.arange(h, dtype=np.float32)[:, None]
    xx_px = np.arange(w, dtype=np.float32)[None, :]
    storms = ((180, 150, 68, 24, 0), (735, 302, 84, 30, 1),
              (475, 397, 52, 18, 0), (925, 100, 43, 16, 1))
    for cx, cy, rx, ry, warm in storms:
        dx = (xx_px - cx + w / 2.0) % w - w / 2.0
        dy = yy_px - cy
        ex, ey = dx / rx, dy / ry
        radius = np.sqrt(ex * ex + ey * ey)
        theta = np.arctan2(ey, ex)
        envelope = np.exp(-radius * radius * 1.7)
        swirl = 0.5 + 0.5 * np.sin(theta * 2.0 + radius * 10.0 + turbulence * 2.0)
        amount = envelope * (0.25 + 0.75 * swirl) * 0.24
        tint = np.array((145.0, 105.0, 72.0) if warm else (169.0, 151.0, 119.0),
                        dtype=np.float32)
        image = image * (1.0 - amount[..., None]) + tint[None, None, :] * amount[..., None]
    return _save(Image.fromarray(np.clip(image, 0, 255).astype(np.uint8), "RGB"),
                 "lookout_planet.png")


def brushed() -> list[Path]:
    """Tileable subtle horizontal brushing plus matching roughness and micronormal."""
    w = h = 1024
    rng = np.random.default_rng(10103)
    fine_line = rng.normal(0.0, 1.0, h).astype(np.float32)
    fine_line = ndimage.gaussian_filter1d(fine_line, 0.62, mode="wrap")
    fine_line /= max(float(fine_line.std()), 1e-6)
    long_grain = _value_noise(w, h, 7, 256, 10111)
    broad = _value_noise(w, h, 9, 13, 10149)
    grain = (long_grain - 0.5) * 2.0
    fine_line = fine_line[:, None]

    base = 190.0 + fine_line * 1.35 + grain * 2.1 + (broad - 0.5) * 1.7
    brushed_rgb = np.empty((h, w, 3), dtype=np.float32)
    brushed_rgb[..., 0] = base - 0.7
    brushed_rgb[..., 1] = base
    brushed_rgb[..., 2] = base + 1.1
    brushed_path = _save(
        Image.fromarray(np.clip(brushed_rgb, 0, 255).astype(np.uint8), "RGB"),
        "lookout_brushed.png",
    )

    roughness = 150.0 + fine_line * 3.0 + grain * 5.5 + (broad - 0.5) * 4.0
    roughness_path = _save(
        Image.fromarray(np.clip(roughness, 0, 255).astype(np.uint8), "L"),
        "lookout_brushed_roughness.png",
    )

    # Periodic central differences keep both seams valid.  The very small
    # slopes are intentional: this is micrograin, not a hammered-metal normal.
    height = grain * 0.55 + fine_line * 0.10 + (broad - 0.5) * 0.18
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5
    nx = -dx * 0.055
    ny = -dy * 0.055
    nz = np.ones_like(nx)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.stack((nx / length, ny / length, nz / length), axis=-1)
    normal_rgb = np.clip((normal * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    normal_path = _save(Image.fromarray(normal_rgb, "RGB"),
                        "lookout_brushed_normal.png")
    return [brushed_path, roughness_path, normal_path]


def main() -> None:
    outputs = []
    outputs.extend(sky_plate())
    outputs.append(nebula())
    outputs.append(badge())
    outputs.append(planet())
    outputs.extend(brushed())
    for path in outputs:
        with Image.open(path) as image:
            print(f"{path.name}: {image.size[0]}x{image.size[1]} {image.mode}")


if __name__ == "__main__":
    main()
