"""克洛斯星户外场景 —— 明亮卡通 3D 盆地、河流、珊瑚与传送平台。

用法:
  Blender -b -P blender/kelosi_scene.py -- \
      --glb public/models/kelosi/kelosi_outdoor.glb \
      --blend renders/kelosi_rebuild/kelosi_scene.blend \
      --render renders/kelosi_rebuild/01_blender_blockout.png --samples 24

坐标约定：Blender Z 向上；导出后经 glTF 转为 Babylon 左手系。
所有地标先在 Babylon 坐标中定义，再通过 bp() 转到 Blender；x 方向整体镜像以匹配参考构图。
地形高度网格与 JSON 高度场来自同一个 ground() 函数。
"""
import argparse
import json
import math
import random
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from power_reactor import material  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
parser = argparse.ArgumentParser()
parser.add_argument('--glb')
parser.add_argument('--blend')
parser.add_argument('--render')
parser.add_argument('--samples', type=int, default=24)
args = parser.parse_args(argv)

rng = random.Random(20261025)

# ---------------------------------------------------------------- 坐标与地形
WATER = 0.0
GROUND_MIN_X, GROUND_MAX_X = -112.0, 112.0
GROUND_MIN_Y, GROUND_MAX_Y = -96.0, 96.0
CELL = 1.2
COLS = int(round((GROUND_MAX_X - GROUND_MIN_X) / CELL)) + 1
ROWS = int(round((GROUND_MAX_Y - GROUND_MIN_Y) / CELL)) + 1


def bp(x, y, z):
    """Babylon (x, y, z) -> Blender (x, -z, y)；整体沿 x 镜像。"""
    return (x, -z, y)


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def lin(r, g, b):
    """sRGB 0-255 -> Blender/PBR 线性色。"""
    def f(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f(r), f(g), f(b))


def sstep(a, b, x):
    t = clamp((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def river_center(x):
    return 2.8 + 6.2 * math.sin(0.045 * x) + 1.4 * math.sin(0.11 * x + 0.6)


def dune(x, z):
    return (
        math.sin(x * 0.073 + math.sin(z * 0.061) * 1.7) * 0.5
        + math.sin(z * 0.117 - x * 0.043 + 1.3) * 0.32
        + math.sin((x + z) * 0.191 + 0.4) * 0.18
    )


def ground(x, z):
    """Babylon 坐标下的可行走地表高度。"""
    h = 2.0 + 0.32 * sstep(12, 28, z)
    h += 3.25 * (1.0 - sstep(-23, -6, z))
    h += dune(x, z) * 0.34

    # 西侧珊瑚丘的地表隆起
    h += 1.55 * math.exp(-(((x + 46) / 16) ** 2 + ((z - 24) / 13) ** 2))
    h += 1.25 * math.exp(-(((x + 58) / 15) ** 2 + ((z - 36) / 12) ** 2))
    h += 1.05 * math.exp(-(((x + 43) / 14) ** 2 + ((z - 15) / 12) ** 2))
    h += 1.00 * math.exp(-(((x + 52) / 14) ** 2 + ((z + 22) / 12) ** 2))
    # 东北台地隆起
    h += 1.05 * math.exp(-(((x - 47) / 28) ** 2 + ((z + 27) / 20) ** 2))

    # 河道下切
    d = abs(z - river_center(x))
    h -= 3.42 * (1.0 - sstep(5.0, 15.5, d))

    # 浅滩：x=12 附近抬升河床，保持深度小于 1m
    ford = math.exp(-((x - 12.0) / 6.8) ** 2) * math.exp(-(d / 8.2) ** 2)
    h += 1.52 * ford

    # 出生点与传送平台做局部找平
    h = lerp(h, 2.05, 1.0 - sstep(3.0, 10.0, math.hypot(x, z - 24)))
    h = lerp(h, 5.02, 1.0 - sstep(5.2, 10.5, math.hypot(x - 34, z + 20)))

    return h


def face_noise(x, z):
    return (
        math.sin(x * 0.31 + math.sin(z * 0.23) * 2.1)
        + math.sin(z * 0.37 - x * 0.13 + 2.0) * 0.7
        + math.sin((x - z) * 0.61) * 0.35
    )


# ---------------------------------------------------------------- 材质
bpy.ops.wm.read_factory_settings(use_empty=True)
M = {
    'sand': material('k_sand', lin(228, 105, 64), 0.92, 0.0),
    'sand_pink': material('k_sand_pink', lin(231, 131, 96), 0.94, 0.0),
    'bank': material('k_bank', lin(222, 174, 108), 0.94, 0.0),
    'grass': material('k_grass', lin(88, 183, 52), 0.90, 0.0),
    'grass_dark': material('k_grass_dark', lin(57, 133, 36), 0.92, 0.0),
    'rock_warm': material('k_rock_warm', lin(210, 154, 95), 0.86, 0.0),
    'rock_shadow': material('k_rock_shadow', lin(165, 113, 65), 0.90, 0.0),
    'coral': material('k_coral_pink', lin(238, 91, 138), 0.76, 0.0),
    'coral_light': material('k_coral_light', lin(255, 147, 179), 0.72, 0.0),
    'coral_dark': material('k_coral_dark', lin(166, 50, 91), 0.82, 0.0),
    'vine': material('k_vine', lin(122, 43, 75), 0.84, 0.0),
    'berry': material('k_berry', lin(107, 74, 196), 0.58, 0.0, coat=0.15),
    'crystal': material('k_crystal_glow', lin(255, 201, 40), 0.34, 0.0, emit=lin(255, 190, 35), strength=2.2),
    'crystal_light': material('k_crystal_light', lin(255, 228, 122), 0.26, 0.0, emit=lin(255, 225, 150), strength=3.2),
    'plant_red': material('k_plant_red', lin(212, 46, 60), 0.72, 0.0),
    'plant_dark': material('k_plant_dark', lin(74, 17, 24), 0.84, 0.0),
    'teeth': material('k_plant_teeth', lin(255, 240, 200), 0.58, 0.0),
    'platform_white': material('k_platform_white', lin(229, 233, 224), 0.42, 0.20, coat=0.2),
    'platform_silver': material('k_platform_silver', lin(143, 162, 168), 0.30, 0.65, coat=0.2),
    'portal_inner': material('k_portal_inner', lin(11, 53, 71), 0.18, 0.1, emit=lin(20, 150, 200), strength=1.1),
    'teleport': material('k_teleport_glow', lin(47, 208, 232), 0.24, 0.0, emit=lin(70, 225, 245), strength=3.6),
    'wood': material('k_wood', lin(106, 58, 31), 0.90, 0.0),
    'shell': material('k_shell', lin(236, 210, 182), 0.68, 0.0, coat=0.05),
    'tree': material('k_tree_green', lin(62, 168, 44), 0.86, 0.0),
    'tree_light': material('k_tree_light', lin(114, 205, 63), 0.82, 0.0),
    'mountain_dark': material('bg_mountain_dark', lin(103, 42, 33), 0.96, 0.0),
    'mountain': material('bg_mountain', lin(150, 61, 40), 0.96, 0.0),
    'mountain_light': material('bg_mountain_light', lin(184, 89, 54), 0.96, 0.0),
}
# 水面单独设置透明度
WATER_MAT = material('k_water', lin(38, 146, 199), 0.10, 0.0, emit=lin(10, 72, 104), strength=0.3)
WATER_MAT.node_tree.nodes['Principled BSDF'].inputs['Alpha'].default_value = 0.82
try:
    WATER_MAT.surface_render_method = 'BLENDED'
except Exception:
    WATER_MAT.blend_method = 'BLEND'

# 地表使用顶点色，避免 1.2m 网格材质分块产生马赛克边界。
GROUND_MAT = bpy.data.materials.new('k_ground')
GROUND_MAT.use_nodes = True
_gn = GROUND_MAT.node_tree
_bs = _gn.nodes['Principled BSDF']
_bs.inputs['Roughness'].default_value = 0.93
_bs.inputs['Metallic'].default_value = 0.0
_vc = _gn.nodes.new('ShaderNodeVertexColor')
_vc.layer_name = 'Col'
_gn.links.new(_vc.outputs['Color'], _bs.inputs['Base Color'])

OBJS = []
KEEP = set()


def finish(o, mat, bevel=0.0, smooth=None):
    if mat is not None:
        o.data.materials.append(mat)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    o.select_set(False)
    for p in getattr(o.data, 'polygons', ()):
        p.use_smooth = bevel > 0 if smooth is None else smooth
    if bevel:
        b = o.modifiers.new('bevel', 'BEVEL')
        b.width, b.segments, b.limit_method = bevel, 2, 'ANGLE'
        b.angle_limit = math.radians(35)
        w = o.modifiers.new('wn', 'WEIGHTED_NORMAL')
        w.keep_sharp = True
        w.weight = 40
    OBJS.append(o)
    return o


def mesh(name, verts, faces, mat, bevel=0.0, smooth=False, uvs=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    if uvs is not None:
        layer = me.uv_layers.new(name='UVMap')
        for poly in me.polygons:
            for li in poly.loop_indices:
                vi = me.loops[li].vertex_index
                layer.data[li].uv = uvs[vi]
    return finish(o, mat, bevel, smooth)


def box(name, size, loc, mat, bevel=0.02, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale, o.name = size, name
    return finish(o, mat, bevel)


def cyl(name, r, h, loc, mat, rot=(0, 0, 0), verts=24, bevel=0.0, smooth=True):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    return finish(o, mat, bevel, smooth)


def cone(name, r1, r2, h, loc, mat, rot=(0, 0, 0), verts=12, bevel=0.0, smooth=True):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=h, vertices=verts, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    return finish(o, mat, bevel, smooth)


def sphere(name, r, loc, mat, scale=(1, 1, 1), segments=20, rings=12):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=segments, ring_count=rings, location=loc)
    o = bpy.context.active_object
    o.scale, o.name = scale, name
    return finish(o, mat, 0, True)


def torus(name, R, r, loc, mat, rot=(0, 0, 0), major=40, minor=10):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=major,
                                     minor_segments=minor, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    return finish(o, mat, 0, True)


def along(name, a, b, r, mat, verts=16):
    a, b = Vector(a), Vector(b)
    d = b - a
    return cyl(name, r, d.length, (a + b) / 2, mat, d.to_track_quat('Z', 'Y').to_euler(), verts, 0.0)


def tube(name, pts, radii, mat, sides=10):
    """沿 Babylon 坐标折线生成锥形圆管。"""
    P = [Vector(p) for p in pts]
    verts, faces = [], []
    for i, p in enumerate(P):
        if i == 0:
            d = (P[1] - P[0]).normalized()
        elif i == len(P) - 1:
            d = (P[-1] - P[-2]).normalized()
        else:
            d = (P[i + 1] - P[i - 1]).normalized()
        up = Vector((0, 0, 1)) if abs(d.z) < 0.92 else Vector((0, 1, 0))
        u = d.cross(up).normalized()
        v = u.cross(d).normalized()
        for k in range(sides):
            a = 2 * math.pi * k / sides
            q = p + (u * math.cos(a) + v * math.sin(a)) * radii[i]
            verts.append(bp(q.x, q.y, q.z))
    for i in range(len(P) - 1):
        for k in range(sides):
            a = i * sides + k
            b = i * sides + (k + 1) % sides
            c = (i + 1) * sides + (k + 1) % sides
            d = (i + 1) * sides + k
            faces.append((a, b, c, d))
    faces.append(tuple(range(sides - 1, -1, -1)))
    base = (len(P) - 1) * sides
    faces.append(tuple(base + k for k in range(sides)))
    return mesh(name, verts, faces, mat, 0, True)


def empty(name, loc):
    o = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(o)
    o.location = loc
    return o


# ---------------------------------------------------------------- 地形网格
def mixc(a, b, t):
    t = clamp(t, 0.0, 1.0)
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def terrain_color(x, z, h):
    sand = lin(228, 105, 64)
    pink = lin(234, 146, 122)
    bank = lin(222, 174, 108)
    grass = lin(88, 183, 52)
    grass_dark = lin(57, 133, 36)
    warm_rock = lin(204, 141, 83)
    c = sand

    # 前景大片粉桃色斑块
    p = 0.5 + 0.5 * math.sin(x * 0.075 + math.sin(z * 0.047) * 1.9 + 0.6)
    c = mixc(c, pink, sstep(0.34, 0.84, p) * 0.30)
    # 西侧珊瑚盆地更粉
    c = mixc(c, pink, 0.30 * (1.0 - sstep(-18, 6, x)) * (1.0 - sstep(-18, 4, z)))
    # 河岸浅色带
    d = abs(z - river_center(x))
    c = mixc(c, bank, (1.0 - sstep(5.5, 16.0, d)) * 0.78)
    # 东北绿色台地；边缘留 7m 过渡
    gx = sstep(-14.0, 2.0, x)
    gz = 1.0 - sstep(-17.0, -7.0, z)
    gn = 0.5 + 0.5 * math.sin(x * 0.13 + math.sin(z * 0.09) * 2.2)
    green = mixc(grass, grass_dark, sstep(0.35, 0.8, gn) * 0.55)
    c = mixc(c, green, gx * gz * 0.95)
    # 陡坡与高处略压暗，保留手绘层次
    shade = 0.9 + 0.1 * (0.5 + 0.5 * math.sin(x * 0.21 + z * 0.17))
    c = mixc(c, warm_rock, sstep(4.2, 5.8, h) * 0.10)
    return (c[0] * shade, c[1] * shade, c[2] * shade)


def build_terrain():
    verts, faces = [], []
    for r in range(ROWS):
        by = GROUND_MIN_Y + r * CELL
        for c in range(COLS):
            bx = GROUND_MIN_X + c * CELL
            # 输入 (bx, by) 是 Babylon 坐标系；Blender 的 y 轴取反，
            # 这样导出后地面高度才与道具、水面共用同一套 ground(x, z)。
            verts.append((bx, -by, ground(bx, by)))
    for r in range(ROWS - 1):
        for c in range(COLS - 1):
            a = r * COLS + c
            b = a + 1
            cc = a + COLS
            dd = cc + 1
            faces.append((a, b, dd, cc))
    me = bpy.data.meshes.new('terrain')
    me.from_pydata(verts, [], faces)
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    o = bpy.data.objects.new('kelosi_terrain', me)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(GROUND_MAT)
    colors = me.color_attributes.new(name='Col', type='FLOAT_COLOR', domain='POINT')
    for i, v in enumerate(me.vertices):
        r, g, b = terrain_color(v.co.x, -v.co.y, v.co.z)
        colors.data[i].color = (r, g, b, 1.0)
    OBJS.append(o)
    KEEP.add(o.name)
    return o


# ---------------------------------------------------------------- 地面装饰
def ground_patch(name, cx, cz, radius, mat, seed=0, irregular=0.24):
    rr = random.Random(seed)
    rings = 3
    sides = 18
    verts = []
    base_h = ground(cx, cz) + 0.026
    bv = bp(cx, base_h, cz)
    verts.append(bv)
    for ring in range(1, rings + 1):
        t = ring / rings
        for k in range(sides):
            a = 2 * math.pi * k / sides
            wob = 1.0 + math.sin(a * 3 + seed) * irregular + math.sin(a * 5 - seed) * irregular * 0.45
            x = cx + math.cos(a) * radius * t * wob
            z = cz + math.sin(a) * radius * t * wob
            verts.append(bp(x, ground(x, z) + 0.028, z))
    # 顶点顺序：中心 + rings*sides 圆环；在 Blender 坐标中保持朝上
    faces = []
    for k in range(sides):
        faces.append((0, 1 + k, 1 + (k + 1) % sides))
    for ring in range(rings - 1):
        a0 = 1 + ring * sides
        b0 = 1 + (ring + 1) * sides
        for k in range(sides):
            a = a0 + k
            b = a0 + (k + 1) % sides
            c = b0 + (k + 1) % sides
            d = b0 + k
            faces.append((a, b, c, d))
    return mesh(name, verts, faces, mat, 0, True)


# ---------------------------------------------------------------- 水体
def build_water():
    n = 224
    cols = 9
    verts, uvs, faces = [], [], []
    xs = [-112 + 224 * i / n for i in range(n + 1)]
    half = 14.2
    for i, x in enumerate(xs):
        cz = river_center(x)
        for j in range(cols):
            t = -1.0 + 2.0 * j / (cols - 1)
            z = cz + t * half
            verts.append(bp(x, 0.0, z))
            uvs.append((i / n * 26.0, j / (cols - 1) * 8.0))
    for i in range(n):
        for j in range(cols - 1):
            a = i * cols + j
            b = a + 1
            c = (i + 1) * cols + j + 1
            d = (i + 1) * cols + j
            faces.append((a, b, c, d))
    o = mesh('water_river', verts, faces, WATER_MAT, 0, True, uvs)
    KEEP.add(o.name)
    return o


# ---------------------------------------------------------------- 珊瑚
def coral_cluster(name, cx, cz, scale, seed, collider_r=None):
    rr = random.Random(seed)
    base = ground(cx, cz)
    mb = bpy.data.metaballs.new(name + '_mb')
    mb.resolution = 0.32
    mb.render_resolution = 0.28
    parts = int(5 + scale * 1.2)
    for i in range(parts):
        a = rr.random() * math.pi * 2
        d = rr.random() * 2.8 * scale
        r = (1.8 + rr.random() * 2.6) * scale
        p = bp(cx + math.cos(a) * d, base + r * (0.52 + rr.random() * 0.36), cz + math.sin(a) * d)
        el = mb.elements.new()
        el.co = p
        el.radius = r
    # 一根向上伸出的主枝
    el = mb.elements.new()
    el.co = bp(cx + 0.7 * scale, base + 5.2 * scale, cz - 0.4 * scale)
    el.radius = 1.8 * scale
    ob = bpy.data.objects.new(name, mb)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.convert(target='MESH')
    o = bpy.context.view_layer.objects.active
    o.name = name
    o.data.materials.append(M['coral'])
    for p in o.data.polygons:
        p.use_smooth = True
    OBJS.append(o)

    # 参考图里珊瑚有明显分叉的上枝
    for i in range(4):
        a = -0.7 + i * 0.52 + rr.uniform(-0.16, 0.16)
        reach = (2.0 + rr.random() * 2.2) * scale
        pts = [
            (cx + math.cos(a) * 0.9 * scale, base + 2.0 * scale, cz + math.sin(a) * 0.9 * scale),
            (cx + math.cos(a) * reach * 0.55, base + 3.5 * scale, cz + math.sin(a) * reach * 0.55),
            (cx + math.cos(a) * reach, base + (4.7 + rr.random() * 1.5) * scale,
             cz + math.sin(a) * reach),
        ]
        rad = [0.95 * scale, 0.62 * scale, 0.30 * scale]
        tube(f'{name}_arm{i}', pts, rad, M['coral'] if i % 3 else M['coral_light'], 10)
        sphere(f'{name}_tip{i}', 0.42 * scale, bp(pts[-1][0], pts[-1][1] + 0.1, pts[-1][2]),
               M['coral_light'], (1, 0.8, 1), 10, 8)

    # 深色根须，从珊瑚脚向四周爬行
    roots = int(7 + scale * 3)
    for i in range(roots):
        a = i / roots * math.pi * 2 + rr.random() * 0.35
        length = (4.0 + rr.random() * 6.0) * scale
        pts, rad = [], []
        for k in range(7):
            t = k / 6
            x = cx + math.cos(a) * length * t + math.sin(t * 5 + i) * 0.7
            z = cz + math.sin(a) * length * t + math.cos(t * 4 + i) * 0.55
            y = ground(x, z) + (0.34 if k == 0 else 0.16 + 0.07 * math.sin(i + k)) * scale
            pts.append((x, y, z))
            rad.append((0.48 - 0.38 * t) * scale)
        tube(f'{name}_root{i}', pts, rad, M['vine'] if i % 3 else M['coral_dark'], 8)
        if i % 3 == 0:
            for k in range(3):
                bx = cx + math.cos(a) * length * (0.35 + k * 0.2)
                bz = cz + math.sin(a) * length * (0.35 + k * 0.2)
                sphere(f'{name}_berry{i}_{k}', (0.20 + rr.random() * 0.15) * scale,
                       bp(bx, ground(bx, bz) + 0.45 * scale, bz), M['berry'], (1, 1, 1), 10, 6)

    # 浅粉色的瘤状凸起
    for i in range(int(5 + scale * 2)):
        a = rr.random() * math.pi * 2
        d = rr.random() * 3.4 * scale
        bx = cx + math.cos(a) * d
        bz = cz + math.sin(a) * d
        by = base + (1.0 + rr.random() * 4.0) * scale
        sphere(f'{name}_bump{i}', (0.35 + rr.random() * 0.5) * scale,
               bp(bx, by, bz), M['coral_light'], (1, 0.8, 1), 10, 6)

    if collider_r:
        META['colliders'].append({'id': name, 'x': cx, 'y': -cz, 'r': collider_r})
    META['landmarks'].append({'id': name, 'x': cx, 'y': -cz, 'z': base})
    return base


# ---------------------------------------------------------------- 水晶
def crystal(name, cx, cz, radius, height, seed, mat=None, tilt=0.16):
    rr = random.Random(seed)
    base = ground(cx, cz)
    sides = 6
    verts, faces = [], []
    lean = (rr.uniform(-1, 1) * tilt, rr.uniform(-1, 1) * tilt)
    for ring, (t, rad) in enumerate(((0.0, radius), (0.62, radius * 0.82), (0.86, radius * 0.46))):
        for k in range(sides):
            a = 2 * math.pi * k / sides
            x = cx + math.cos(a) * rad + lean[0] * height * t
            z = cz + math.sin(a) * rad + lean[1] * height * t
            y = base + height * t
            verts.append(bp(x, y, z))
    apex = bp(cx + lean[0] * height, base + height, cz + lean[1] * height)
    verts.append(apex)
    for ring in range(2):
        for k in range(sides):
            a = ring * sides + k
            b = ring * sides + (k + 1) % sides
            c = (ring + 1) * sides + (k + 1) % sides
            d = (ring + 1) * sides + k
            faces.append((a, b, c, d))
    top = 2 * sides
    for k in range(sides):
        faces.append((top + k, top + (k + 1) % sides, 3 * sides))
    faces.append(tuple(range(sides - 1, -1, -1)))
    return mesh(name, verts, faces, mat or M['crystal'], 0, False)


def crystal_cluster(name, cx, cz, scale, seed, collider_r=None):
    rr = random.Random(seed)
    count = int(4 + scale * 2)
    base = ground(cx, cz)
    for i in range(count):
        a = rr.random() * math.pi * 2
        d = rr.random() * 1.6 * scale
        x, z = cx + math.cos(a) * d, cz + math.sin(a) * d
        h = (1.5 + rr.random() * 3.2) * scale
        crystal(f'{name}_c{i}', x, z, (0.28 + rr.random() * 0.34) * scale, h,
                seed * 17 + i, M['crystal_light'] if i % 4 == 0 else M['crystal'])
    if collider_r:
        META['colliders'].append({'id': name, 'x': cx, 'y': -cz, 'r': collider_r})
    META['landmarks'].append({'id': name, 'x': cx, 'y': -cz, 'z': base})
    META['lights'].append({'x': cx, 'y': -cz, 'z': 2.2,
                           'color': [1.0, 0.72, 0.16], 'power': 9.0, 'range': 17.0})
    return base


# ---------------------------------------------------------------- 植被与岩石
def tree(name, cx, cz, scale, seed):
    rr = random.Random(seed)
    base = ground(cx, cz)
    trunk_h = 3.0 * scale
    cyl(f'{name}_trunk', 0.30 * scale, trunk_h, bp(cx, base + trunk_h / 2, cz), M['wood'],
        verts=10, bevel=0.03, smooth=True)
    for i in range(3):
        ox = rr.uniform(-1.0, 1.0) * scale
        oz = rr.uniform(-1.0, 1.0) * scale
        oy = trunk_h + (0.9 + i * 0.55) * scale
        sphere(f'{name}_canopy{i}', (1.3 + rr.random() * 0.55) * scale,
               bp(cx + ox, base + oy, cz + oz),
               M['tree_light'] if i == 0 else M['tree'], (1.0, 0.86, 1.0), 16, 10)
    # 树枝
    for i in range(2):
        a = rr.random() * math.pi * 2
        along(f'{name}_branch{i}',
              bp(cx, base + trunk_h * 0.65, cz),
              bp(cx + math.cos(a) * 1.1 * scale, base + trunk_h * 0.95, cz + math.sin(a) * 1.1 * scale),
              0.12 * scale, M['wood'], 8)
    META['colliders'].append({'id': name, 'x': cx, 'y': -cz, 'r': 0.75 * scale})


def bush(name, cx, cz, scale, seed):
    rr = random.Random(seed)
    base = ground(cx, cz)
    for i in range(3):
        a = rr.random() * math.pi * 2
        d = rr.random() * 0.65 * scale
        sphere(f'{name}_{i}', (0.65 + rr.random() * 0.35) * scale,
               bp(cx + math.cos(a) * d, base + (0.48 + rr.random() * 0.3) * scale, cz + math.sin(a) * d),
               M['tree'] if i else M['tree_light'], (1, 0.82, 1), 12, 8)


def grass_tuft(name, cx, cz, scale, seed):
    rr = random.Random(seed)
    base = ground(cx, cz)
    verts, faces = [], []
    for i in range(5):
        a = rr.random() * math.pi * 2
        w = 0.055 * scale
        h = (0.48 + rr.random() * 0.55) * scale
        c = math.cos(a)
        s = math.sin(a)
        # 三顶点细长叶片，在 Blender 坐标中朝上
        p0 = bp(cx - s * w, base, cz + c * w)
        p1 = bp(cx + s * w, base, cz - c * w)
        p2 = bp(cx + c * h * 0.22, base + h, cz + s * h * 0.22)
        idx = len(verts)
        verts += [p0, p1, p2]
        faces.append((idx, idx + 1, idx + 2))
    return mesh(name, verts, faces, M['grass_dark'] if seed % 3 else M['tree'], 0, False)


def flytrap(name, cx, cz, scale, seed):
    rr = random.Random(seed)
    base = ground(cx, cz)
    h = 2.0 * scale
    along(f'{name}_stem', bp(cx, base, cz), bp(cx + 0.15 * scale, base + h, cz - 0.1 * scale),
          0.10 * scale, M['grass_dark'], 8)
    head = bp(cx + 0.18 * scale, base + h + 0.5 * scale, cz - 0.12 * scale)
    sphere(f'{name}_jaw0', 0.95 * scale, head, M['plant_red'], (1.0, 0.40, 0.78), 16, 10)
    sphere(f'{name}_jaw1', 0.78 * scale,
           (head[0], head[1] + 0.22 * scale, head[2] + 0.44 * scale),
           M['plant_red'], (0.9, 0.34, 0.66), 16, 10)
    sphere(f'{name}_mouth', 0.52 * scale,
           (head[0], head[1] + 0.10 * scale, head[2] + 0.34 * scale),
           M['plant_dark'], (1.0, 0.26, 0.82), 12, 8)
    for i in range(6):
        a = -1.0 + i * 0.4
        cone(f'{name}_tooth{i}', 0.09 * scale, 0.0, 0.34 * scale,
             (head[0] + math.sin(a) * 0.58 * scale, head[1] + math.cos(a) * 0.52 * scale,
              head[2] + 0.35 * scale),
             M['teeth'], (math.radians(90 - a * 22), 0, math.radians(a * 58)), 8, 0.0, False)


def boulder(name, cx, cz, radius, seed, mat=None, collider=False):
    rr = random.Random(seed)
    base = ground(cx, cz)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=radius,
                                          location=bp(cx, base + radius * 0.45, cz))
    o = bpy.context.active_object
    o.name = name
    o.scale = (1.0 + rr.random() * 0.4, 0.55 + rr.random() * 0.3, 0.85 + rr.random() * 0.4)
    o.rotation_euler[2] = rr.random() * math.pi
    finish(o, mat or M['rock_warm'], 0.04, False)
    if collider:
        META['colliders'].append({'id': name, 'x': cx, 'y': -cz, 'r': radius * 0.85})
    return base


# ---------------------------------------------------------------- 岩壁
def ledge_run(name, x0, x1, side, offset, height, seed):
    """低矮岩唇：用压扁的碎岩堆出连续河岸，避免方块感。"""
    rr = random.Random(seed)
    step = 3.6
    x = x0
    i = 0
    while x < x1:
        z = river_center(x) + side * offset
        y = ground(x, z)
        dx = river_center(x + 0.5) - river_center(x - 0.5)
        ang = math.atan(dx)
        for row in range(2):
            r = height * (1.10 + rr.random() * 0.40)
            bx = x + (rr.random() - 0.5) * 1.5
            bz = z - side * (row * 2.1 + rr.random() * 0.8)
            by = ground(bx, bz) + r * 0.28
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=r,
                                                  location=bp(bx, by, bz))
            o = bpy.context.active_object
            o.name = f'{name}_{i}_{row}'
            o.scale = (2.0 + rr.random() * 0.6, 1.15 + rr.random() * 0.35,
                       0.40 + rr.random() * 0.18)
            o.rotation_euler[2] = -ang + (rr.random() - 0.5) * 0.32
            finish(o, M['rock_warm'] if (i + row) % 3 else M['rock_shadow'], 0.035, False)
        x += step
        i += 1


# ---------------------------------------------------------------- 传送平台
def build_platform():
    cx, cz = 34.0, -20.0
    base = ground(cx, cz)
    top = base + 0.02
    cyl('platform_base', 5.9, 0.40, bp(cx, top - 0.20, cz), M['platform_silver'], (0, 0, 0), 8, 0.05)
    cyl('platform_deck', 5.55, 0.06, bp(cx, top + 0.02, cz), M['platform_white'], (0, 0, 0), 8, 0.02)
    torus('platform_rim', 4.90, 0.12, bp(cx, top + 0.07, cz), M['platform_silver'], (0, 0, 0), 48, 8)
    cyl('platform_inner', 4.22, 0.04, bp(cx, top + 0.055, cz), M['portal_inner'], (0, 0, 0), 48, 0.01)
    torus('platform_glow', 4.53, 0.06, bp(cx, top + 0.09, cz), M['teleport'], (0, 0, 0), 56, 8)

    ring_y = top + 3.35
    torus('portal_ring', 3.18, 0.34, bp(cx, ring_y, cz), M['platform_white'],
          (math.radians(90), 0, 0), 56, 12)
    torus('portal_ring_inner', 2.70, 0.085, bp(cx, ring_y, cz), M['teleport'],
          (math.radians(90), 0, 0), 56, 8)
    cyl('portal_disc', 2.52, 0.06, bp(cx, ring_y, cz), M['portal_inner'],
        (math.radians(90), 0, 0), 48, 0.01)
    for i, s in enumerate((-1, 1)):
        box(f'portal_leg{i}', (0.46, 0.60, 3.45), bp(cx + s * 3.28, top + 1.62, cz),
            M['platform_silver'], 0.06, (0, 0, 0))
        sphere(f'portal_foot{i}', 0.46, bp(cx + s * 3.28, top + 0.12, cz),
               M['platform_silver'], (1, 0.55, 1), 12, 8)

    # 旋转的浮游碎片：空物体 + 三个自发光晶体
    orbit = empty('fx_teleport_ring', bp(cx, ring_y, cz))
    bpy.context.view_layer.update()
    for i in range(3):
        a = 2 * math.pi * i / 3
        ox = math.cos(a) * 3.95
        oz = math.sin(a) * 3.95
        shard = empty(f'fx_shard_{i}', bp(cx + ox, ring_y, cz + oz))
        bpy.context.view_layer.update()
        shard.parent = orbit
        shard.matrix_parent_inverse = orbit.matrix_world.inverted()
        crystal(f'fx_shard_geo_{i}', cx + ox, cz + oz, 0.18, 0.75, 910 + i,
                M['teleport'], 0.05)
        shard_geo = bpy.data.objects.get(f'fx_shard_geo_{i}')
        if shard_geo:
            bpy.context.view_layer.update()
            shard_geo.parent = shard
            shard_geo.matrix_parent_inverse = shard.matrix_world.inverted()

    META['landmarks'].append({'id': 'teleport_platform', 'x': cx, 'y': -cz, 'z': top})
    META['lights'].append({'x': cx, 'y': -cz, 'z': ring_y + 0.8,
                           'color': [0.22, 0.82, 1.0], 'power': 15.0, 'range': 22.0})
    return base


# ---------------------------------------------------------------- 远景
def peak(name, cx, cz, radius, height, mat, seed):
    rr = random.Random(seed)
    sides = 9
    verts, faces = [], []
    base_y = -7.0
    for ring, (t, rad) in enumerate(((0.0, 1.0), (0.42, 0.62), (0.74, 0.28))):
        for k in range(sides):
            a = 2 * math.pi * k / sides
            wob = 0.82 + rr.random() * 0.36
            x = cx + math.cos(a) * radius * rad * wob
            z = cz + math.sin(a) * radius * rad * wob
            y = base_y + height * t + (rr.random() - 0.5) * height * 0.07
            verts.append(bp(x, y, z))
    apex = bp(cx + rr.uniform(-3, 3), base_y + height, cz + rr.uniform(-3, 3))
    verts.append(apex)
    for ring in range(2):
        for k in range(sides):
            a = ring * sides + k
            b = ring * sides + (k + 1) % sides
            c = (ring + 1) * sides + (k + 1) % sides
            d = (ring + 1) * sides + k
            faces.append((a, b, c, d))
    top = 2 * sides
    for k in range(sides):
        faces.append((top + k, top + (k + 1) % sides, 3 * sides))
    return mesh(name, verts, faces, mat, 0, False)


def build_backdrop():
    # 连续的低矮山脊填补地形边缘
    for i in range(20):
        a = 2 * math.pi * i / 20
        r = 138 + (i % 3) * 8
        cx, cz = math.cos(a) * r, math.sin(a) * r
        peak(f'bg_ridge_{i}', cx, cz, 25 + (i % 4) * 5, 8 + (i % 5) * 2.4,
             M['mountain_dark'] if i % 3 else M['mountain'], 330 + i)
    # 远处山群：更多重叠、更低更宽，形成层叠山脊而不是一排尖锥
    for i in range(18):
        a = 2 * math.pi * i / 18 + 0.09
        r = 162 + (i % 3) * 14
        cx, cz = math.cos(a) * r, math.sin(a) * r
        peak(f'bg_mountain_{i}', cx, cz, 38 + (i % 4) * 6, 26 + (i % 6) * 4.2,
             M['mountain'] if i % 3 else M['mountain_light'], 500 + i)


# ---------------------------------------------------------------- 场景装配
META = {
    'version': 1,
    'units': 'meters',
    'waterLevel': WATER,
    'walk': {'minX': -92.0, 'maxX': 92.0, 'minY': -80.0, 'maxY': 80.0},
    'spawn': {'x': 0.0, 'y': -24.0, 'heading': math.pi},
    'colliders': [],
    'boxes': [],
    'landmarks': [],
    'lights': [],
    'animated': {},
    'animatedMaterials': [
        {'name': 'k_water', 'kind': 'uvScroll', 'speed': [0.035, 0.008]},
        {'name': 'k_crystal_glow', 'kind': 'pulse', 'hz': 0.42, 'amount': 0.30},
        {'name': 'k_crystal_light', 'kind': 'pulse', 'hz': 0.52, 'amount': 0.26},
        {'name': 'k_teleport_glow', 'kind': 'pulse', 'hz': 0.95, 'amount': 0.38},
    ],
    'animatedNodes': [{'name': 'fx_teleport_ring', 'kind': 'spinY', 'speed': 0.42}],
    'referenceCamera': {
        'position': [0.0, 24.0, 80.0],
        'target': [0.0, 4.0, -6.0],
        'fov': 0.90,
        'fovMode': 'vertical_fixed',
    },
    'shadowCasters': ['m_k_coral', 'm_k_rock', 'm_k_tree', 'm_k_plant', 'm_k_crystal',
                      'm_k_platform', 'm_k_wood', 'm_k_teleport'],
}

build_terrain()
build_water()

# 地面色斑
for i in range(8):
    cx = rng.uniform(-42, 52)
    cz = rng.uniform(18, 50)
    ground_patch(f'patch_pink_{i}', cx, cz, rng.uniform(2.2, 4.4), M['sand_pink'], 700 + i, 0.26)
for i in range(9):
    cx = rng.uniform(4, 56)
    cz = rng.uniform(-48, -16)
    ground_patch(f'patch_grass_{i}', cx, cz, rng.uniform(2.0, 4.6),
                 M['grass_dark'] if i % 2 else M['grass'], 760 + i, 0.22)
for i in range(7):
    cx = rng.uniform(-64, -6)
    cz = rng.uniform(-32, 8)
    ground_patch(f'patch_sand_{i}', cx, cz, rng.uniform(2.0, 4.0), M['bank'], 800 + i, 0.30)

# 西侧珊瑚主体
coral_cluster('coral_west_a', -46.0, 24.0, 1.62, 11, 7.4)
coral_cluster('coral_west_b', -58.0, 36.0, 1.16, 12, 6.0)
coral_cluster('coral_west_c', -43.0, 15.0, 0.92, 13, 5.4)
coral_cluster('coral_west_d', -52.0, -22.0, 0.78, 16, 4.5)
coral_cluster('coral_fore_w', -54.0, 48.0, 0.78, 17, 4.2)
coral_cluster('coral_north_e', 60.0, -34.0, 0.72, 14, 4.0)
coral_cluster('coral_fore_e', 62.0, 36.0, 0.68, 15, 3.8)
# 扩大后的外圈珊瑚群落：把可行走边界推进到远处，又不让远景露空。
for i, (cx, cz, s, r) in enumerate((
    (-82.0, 46.0, 1.10, 5.6), (-90.0, -26.0, 0.96, 5.2),
    (84.0, 54.0, 1.02, 5.0), (90.0, -14.0, 0.88, 4.8),
    (74.0, 22.0, 0.82, 4.4), (-76.0, -58.0, 0.90, 4.6),
)):
    coral_cluster(f'coral_outer_{i}', cx, cz, s, 2100 + i, r)

# 黄水晶
crystal_cluster('crystal_a', -27.0, 17.5, 1.50, 21, 3.6)
crystal_cluster('crystal_b', -16.0, 20.0, 1.08, 22, 2.8)
crystal_cluster('crystal_c', -33.0, 14.0, 1.20, 23, 3.0)
crystal_cluster('crystal_d', -39.0, 22.0, 0.72, 24, None)

# 河岸岩台
ledge_run('ledge_south_w', -66, -24, 1, 18.3, 1.10, 31)
ledge_run('ledge_north_w', -70, -20, -1, 19.2, 1.30, 32)
ledge_run('ledge_north_c', -10, 7, -1, 20.0, 0.78, 33)
ledge_run('ledge_north_e', 43, 63, -1, 18.5, 1.20, 34)

# 浅滩踏脚石
META['shallows'] = []
for i, (x, off) in enumerate(((8.2, -2.2), (10.0, 0.4), (12.0, -0.8), (14.0, 1.8), (16.0, -1.4))):
    boulder(f'ford_stone_{i}', x, river_center(x) + off, 0.62 + i * 0.03, 900 + i,
            M['rock_shadow'] if i % 2 else M['rock_warm'])
    # 河床被下切后部分踏脚石会没入水里：抬到水面以上，形成可辨认的浅滩。
    stone = bpy.data.objects[f'ford_stone_{i}']
    stone.location.z = max(stone.location.z, 0.22)
    # 水面着色器用这些点把石顶烘成浅点，水线泡沫自然绕石一圈。
    META['shallows'].append({'x': x, 'z': river_center(x) + off, 'r': 0.62 + i * 0.03})

# 东北台地植被
for i, (cx, cz, s) in enumerate((
    (14, -30, 1.05), (22, -38, 0.95), (29, -44, 1.1), (42, -42, 1.0),
    (50, -34, 0.9), (56, -47, 1.05), (18, -47, 0.85), (47, -52, 0.95),
    (60, -20, 0.8), (39, -33, 0.86),
    (78, -55, 1.02), (86, -34, 0.92), (90, 12, 1.08), (82, 46, 0.96),
    (-82, 40, 0.94), (-90, 4, 1.04), (-76, -38, 0.90), (-88, -62, 0.98),
)):
    tree(f'tree_{i}', cx, cz, s, 1000 + i)

for i, (cx, cz, s) in enumerate(((16, -22, 1.35), (25, -26, 1.10), (32, -31, 1.22),
                                  (45, -25, 1.02), (53, -40, 1.20), (12, -38, 0.95),
                                  (62, -30, 1.10), (37, -48, 1.35))):
    flytrap(f'flytrap_{i}', cx, cz, s, 1100 + i)

for i in range(40):
    cx = rng.uniform(8, 90)
    cz = rng.uniform(-72, -10)
    if abs(cx - 34) < 5 and abs(cz + 20) < 5:
        continue
    bush(f'bush_e_{i}', cx, cz, rng.uniform(0.65, 1.15), 1200 + i)

for i in range(86):
    cx = rng.uniform(6, 92)
    cz = rng.uniform(-76, -8)
    grass_tuft(f'grass_e_{i}', cx, cz, rng.uniform(0.7, 1.2), 1300 + i)

# 前景与西侧植被
for i, (cx, cz, s) in enumerate(((-20, 34, 0.9), (-36, 42, 1.0), (54, 28, 0.75), (-12, 46, 0.8),
                                  (-62, 58, 1.05), (70, 62, 0.95), (-30, 66, 1.12), (48, 52, 0.88))):
    bush(f'bush_s_{i}', cx, cz, s, 1400 + i)
# 出生点周围与更远的南侧外圈：扩大场景后仍保持前后景都有内容。
for i, (cx, cz, s) in enumerate(((-84, 34, 1.0), (86, 48, 0.96), (24, 70, 0.92),
                                  (-48, 44, 0.88), (-72, 68, 1.06), (58, 74, 0.98))):
    coral_cluster(f'coral_fore_outer_{i}', cx, cz, s, 2300 + i, 4.2)
for i, (cx, cz, s) in enumerate(((-74, 52, 0.9), (-40, 58, 1.0), (12, 64, 0.86),
                                  (34, 58, 1.04), (64, 44, 0.92), (82, 70, 1.0),
                                  (-88, 16, 0.88), (90, 6, 0.96))):
    tree(f'tree_outer_{i}', cx, cz, s, 2400 + i)
for i in range(150):
    cx = rng.uniform(-96, 96)
    cz = rng.uniform(10, 86)
    grass_tuft(f'grass_s_{i}', cx, cz, rng.uniform(0.65, 1.15), 1450 + i)

# 右侧浅色岩壁，呼应参考图右边的岩崖与粉色晶簇
for i, (cx, cz, r) in enumerate(((58, 6, 4.6), (63, 15, 5.2), (60, 25, 4.2),
                                  (66, 34, 5.8), (58, 40, 3.8), (65, 48, 4.6),
                                  (76, 62, 5.0), (84, 74, 5.4), (74, -6, 4.4),
                                  (82, -24, 5.2), (72, 6, 4.0), (88, 36, 5.6))):
    boulder(f'cliff_e_{i}', cx, cz, r, 1700 + i, M['rock_warm'] if i % 2 else M['rock_shadow'],
            collider=True)
for i, (cx, cz, r) in enumerate(((48, 26, 4.2), (53, 36, 4.8), (50, 46, 3.8), (55, 56, 4.4))):
    boulder(f'cliff_near_e_{i}', cx, cz, r, 1750 + i,
            M['rock_warm'] if i % 2 else M['rock_shadow'], collider=True)
for i, (cx, cz) in enumerate(((50, 31), (54, 42), (51, 50))):
    for k in range(3):
        rr = random.Random(1850 + i * 5 + k)
        sphere(f'cliff_near_gem_{i}_{k}', 0.38 + rr.random() * 0.30,
               bp(cx + rr.uniform(-1.6, 1.6), ground(cx, cz) + 1.3 + rr.random() * 2.2,
                  cz + rr.uniform(-1.6, 1.6)),
               M['coral_light'], (1, 0.7, 1), 10, 8)
for i, (cx, cz) in enumerate(((60, 11), (65, 20), (62, 30), (58, 36), (66, 43))):
    for k in range(3):
        rr = random.Random(1800 + i * 5 + k)
        sphere(f'cliff_gem_{i}_{k}', 0.42 + rr.random() * 0.35,
               bp(cx + rr.uniform(-1.8, 1.8), ground(cx, cz) + 1.2 + rr.random() * 2.6,
                  cz + rr.uniform(-1.8, 1.8)),
               M['coral_light'], (1, 0.7, 1), 10, 8)

# 散落石块
for i in range(44):
    cx = rng.uniform(-98, 98)
    cz = rng.uniform(-86, 86)
    if abs(cz - river_center(cx)) < 7:
        continue
    boulder(f'rock_{i}', cx, cz, rng.uniform(0.55, 1.45), 1500 + i,
            M['rock_warm'] if i % 3 else M['rock_shadow'], collider=i < 6)

# 出生海滩前景：小碎石、贝壳、浮木与贴岸草丛。镜头压低后前景占比变大，
# 这些低矮细节提供尺度参照，也让空地不至于像一块纯色平面。
for i in range(64):
    rr = random.Random(3100 + i)
    cx = rr.uniform(-40, 40)
    cz = rr.uniform(16, 50)
    if math.hypot(cx, cz - 24) < 5.0 or ground(cx, cz) < 0.35:
        continue
    boulder(f'beach_pebble_{i}', cx, cz, rr.uniform(0.10, 0.32), 3200 + i,
            M['rock_warm'] if i % 3 else M['rock_shadow'])

for i in range(22):
    rr = random.Random(3400 + i)
    cx = rr.uniform(-34, 34)
    cz = rr.uniform(20, 46)
    if math.hypot(cx, cz - 24) < 5.4 or ground(cx, cz) < 0.3:
        continue
    b = ground(cx, cz)
    sphere(f'beach_shell_{i}', rr.uniform(0.11, 0.21),
           bp(cx, b + 0.03, cz), M['shell'],
           (1.0, 0.72, 0.24 + rr.random() * 0.08), 12, 6)

for i, (cx, cz, ang, length) in enumerate(((-7.5, 30.0, 0.55, 2.7),
                                           (10.5, 33.5, -0.75, 1.9),
                                           (-18.0, 41.0, 1.15, 3.1))):
    b = ground(cx, cz)
    dx = math.cos(ang) * length * 0.5
    dz = math.sin(ang) * length * 0.5
    along(f'beach_log_{i}', bp(cx - dx, b + 0.13, cz - dz),
          bp(cx + dx, b + 0.15, cz + dz), 0.14 + i * 0.01, M['wood'], 8)
    # 一小截断枝，避免浮木看起来像一根规则圆柱。
    along(f'beach_log_{i}_stub', bp(cx + dx * 0.2, b + 0.14, cz + dz * 0.2),
          bp(cx + dx * 0.2 + 0.55, b + 0.30, cz + dz * 0.2 - 0.35), 0.055, M['wood'], 6)

for i in range(86):
    rr = random.Random(3600 + i)
    cx = rr.uniform(-56, 56)
    cz = rr.uniform(15, 34)
    if math.hypot(cx, cz - 24) < 3.4 or ground(cx, cz) < 0.22:
        continue
    grass_tuft(f'grass_beach_{i}', cx, cz, rr.uniform(0.55, 1.0), 3700 + i)

# 背景山脊 + 主峰
build_backdrop()
build_platform()

# 平台周围低矮石台，增强地标
for i in range(6):
    a = 2 * math.pi * i / 6 + 0.3
    cx = 34 + math.cos(a) * 6.3
    cz = -20 + math.sin(a) * 6.3
    boulder(f'platform_stone_{i}', cx, cz, 0.55, 1600 + i, M['platform_silver'])


# ---------------------------------------------------------------- 合并静态几何
def merge_group(prefix, objs, out_prefix='m_'):
    groups = {}
    for o in objs:
        if o.type != 'MESH' or len(o.data.materials) != 1:
            continue
        groups.setdefault(o.data.materials[0].name, []).append(o)
    for mat, items in groups.items():
        if not items:
            continue
        bpy.ops.object.select_all(action='DESELECT')
        for o in items:
            o.select_set(True)
        bpy.context.view_layer.objects.active = items[0]
        bpy.ops.object.join()
        o = bpy.context.view_layer.objects.active
        o.name = out_prefix + mat
        o.select_set(False)


static = []
background = []
for o in list(bpy.data.objects):
    if o.type != 'MESH':
        continue
    if o.name in KEEP or o.name.startswith('fx_'):
        continue
    if o.name.startswith('bg_'):
        background.append(o)
    else:
        static.append(o)
merge_group('', static, 'm_')
merge_group('', background, 'm_')


# ---------------------------------------------------------------- 高度场元数据
heights = []
max_err = 0.0
for r in range(ROWS):
    by = GROUND_MIN_Y + r * CELL
    for c in range(COLS):
        bx = GROUND_MIN_X + c * CELL
        h = ground(bx, by)
        heights.append(round(h, 6))
        max_err = max(max_err, abs(h - h))
META['heightfield'] = {
    'minX': GROUND_MIN_X, 'maxX': GROUND_MAX_X,
    'minY': GROUND_MIN_Y, 'maxY': GROUND_MAX_Y,
    'cell': CELL, 'cols': COLS, 'rows': ROWS,
    'heights': heights,
}
# 用实际地形网格顶点复核高度场
terrain_obj = bpy.data.objects.get('kelosi_terrain')
mesh_err = 0.0
if terrain_obj:
    for i, v in enumerate(terrain_obj.data.vertices):
        # 网格行优先，与 heights 顺序一致
        h = heights[i]
        mesh_err = max(mesh_err, abs(v.co.z - h))
print(f'heightfield {COLS}x{ROWS}, max mesh error {mesh_err:.8f}')
if mesh_err > 1e-5:
    raise RuntimeError(f'heightfield/mesh drift: {mesh_err}')

META['bounds'] = {'minX': -84, 'maxX': 84, 'minZ': -72, 'maxZ': 72}

# 岩台栏盒（远景装饰区的粗略阻挡）
META['boxes'].extend([
    {'id': 'ledge_south_w_guard', 'minX': -66.0, 'maxX': -24.0, 'minY': -16.0, 'maxY': -10.5},
    {'id': 'ledge_north_e_guard', 'minX': 43.0, 'maxX': 63.0, 'minY': 10.0, 'maxY': 15.0},
])


# ---------------------------------------------------------------- 导出与预览
def render_preview(path):
    scene = bpy.context.scene
    world = bpy.data.worlds.new('w')
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs[0].default_value = (0.92, 0.55, 0.32, 1)
    bg.inputs[1].default_value = 0.9

    for name, loc, energy, size, color in (
        ('key', (-32, -50, 60), 5000, 18.0, (1.0, 0.92, 0.78)),
        ('fill', (40, -10, 28), 1800, 16.0, (0.68, 0.82, 1.0)),
    ):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy, ld.shape, ld.size, ld.color = energy, 'DISK', size, color
        ob = bpy.data.objects.new(name, ld)
        bpy.context.collection.objects.link(ob)
        ob.location = loc
        ob.rotation_euler = (Vector((0, 0, 0)) - ob.location).to_track_quat('-Z', 'Y').to_euler()
    for i, item in enumerate(META['lights']):
        ld = bpy.data.lights.new(f'l{i}', 'POINT')
        ld.energy, ld.color, ld.shadow_soft_size = item['power'] * 16, item['color'], 0.6
        ob = bpy.data.objects.new(f'l{i}', ld)
        bpy.context.collection.objects.link(ob)
        ob.location = (item['x'], item['y'], item['z'])

    cam_data = bpy.data.cameras.new('ref_cam')
    cam_data.lens = 24
    cam_data.sensor_fit = 'VERTICAL'
    cam_data.angle = META['referenceCamera']['fov']
    cam_data.clip_end = 500
    cam = bpy.data.objects.new('ref_cam', cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = bp(0.0, 24.0, 80.0)
    cam.rotation_euler = (Vector(bp(0.0, 4.0, -6.0)) - Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam

    scene.render.engine = 'CYCLES'
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'AgX'
    try:
        scene.view_settings.look = 'AgX - Medium High Contrast'
    except Exception:
        pass
    scene.view_settings.exposure = 0.35
    scene.render.filepath = str(Path(path).resolve())
    bpy.ops.render.render(write_still=True)


if args.blend:
    out_blend = Path(args.blend).resolve()
    out_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
if args.glb:
    out = Path(args.glb).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(out), export_format='GLB', export_apply=True, export_lights=False)
    out.with_suffix('.json').write_text(json.dumps(META, indent=1))
    print('exported', out, len(bpy.data.objects), 'objects')
if args.render:
    render_preview(args.render)
    print('rendered', args.render)
