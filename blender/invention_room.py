"""发明室 I —— 在 Blender 里程序化建模，导出 GLB 与场景元数据，并可渲染预览图。

用法:
  Blender -b -P blender/invention_room.py -- --glb public/models/inv/invention_room.glb --render out.png
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


ROOT = os.getcwd()
GLB = arg("--glb")
RENDER = arg("--render")
CAM = arg("--cam", "ref")
SAMPLES = int(arg("--samples", "48"))

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
objs_by_group = {}
META = {"colliders": [], "lights": [], "animated": {}}

# ---------------------------------------------------------------- 材质
_mats = {}


def mat(name, base=(0.8, 0.8, 0.8), metal=0.0, rough=0.5, emit=None, strength=0.0, alpha=1.0,
        coat=0.0, image=None, spec=0.5):
    if name in _mats:
        return _mats[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*base, 1)
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
    if emit is not None or image is not None:
        bsdf.inputs["Emission Color"].default_value = (*(emit or (1, 1, 1)), 1)
        bsdf.inputs["Emission Strength"].default_value = strength
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        m.surface_render_method = "BLENDED"
    if image:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(image)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    _mats[name] = m
    return m


CYAN = (0.12, 0.85, 1.0)
M_METAL = mat("steel", (0.72, 0.76, 0.82), 0.85, 0.3, coat=0.2)
M_METAL_D = mat("steel_dark", (0.36, 0.4, 0.47), 0.85, 0.36)
M_METAL_L = mat("steel_light", (0.88, 0.9, 0.94), 0.8, 0.26)
M_FLOOR = mat("floor_tile", (0.66, 0.71, 0.78), 0.8, 0.2, coat=0.4)
M_FLOOR_IN = mat("floor_inlay", (0.46, 0.52, 0.6), 0.85, 0.16, coat=0.5)
M_WALL = mat("wall_panel", (0.62, 0.67, 0.74), 0.8, 0.34)
M_WALL_D = mat("wall_dark", (0.14, 0.17, 0.22), 0.8, 0.45)
M_WHITE = mat("white_plastic", (0.93, 0.95, 0.98), 0.0, 0.28, coat=0.4)
M_GLOW = mat("glow_cyan", (0.02, 0.1, 0.14), 0.0, 0.4, emit=CYAN, strength=5.0)
M_GLOW_SOFT = mat("glow_soft", (0.02, 0.1, 0.14), 0.0, 0.4, emit=CYAN, strength=2.2)
M_GLASS = mat("glass", (0.55, 0.8, 1.0), 0.0, 0.05, alpha=0.22)
M_GLASS_T = mat("glass_tube", (0.6, 0.85, 1.0), 0.0, 0.05, alpha=0.16)
M_DARK = mat("dark_rubber", (0.03, 0.035, 0.05), 0.2, 0.6)
M_EYE = mat("eye", (0.02, 0.03, 0.1), 0.0, 0.2, emit=(0.15, 0.4, 1.0), strength=1.2)
M_SCREEN = mat("hud_screen", (0.02, 0.06, 0.1), 0.0, 0.3, emit=(1, 1, 1), strength=1.6,
               image=os.path.join(ROOT, "blender/hud.png"))
M_GREY = mat("grey_body", (0.55, 0.6, 0.65), 0.6, 0.4)
M_HOLO = mat("holo_body", (0.3, 0.7, 1.0), 0.0, 0.3, emit=(0.35, 0.85, 1.0), strength=2.5, alpha=0.4)
M_ORANGE = mat("accent_orange", (1.0, 0.55, 0.12), 0.2, 0.35, emit=(1.0, 0.5, 0.1), strength=1.5)


# ---------------------------------------------------------------- 几何工具
def _finish(o, name, m, bevel, group):
    o.name = name
    if m is not None:
        o.data.materials.append(m)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        b = o.modifiers.new("bevel", "BEVEL")
        b.width = bevel
        b.segments = 2
        b.limit_method = "ANGLE"
    for p in o.data.polygons:
        p.use_smooth = bevel > 0 or "smooth" in name
    o.select_set(False)
    objs_by_group.setdefault(group, []).append(o)
    return o


def box(name, size, loc, m, bevel=0.02, rot=(0, 0, 0), group="room"):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale = size
    return _finish(o, name, m, bevel, group)


def cyl(name, r, h, loc, m, verts=48, bevel=0.0, rot=(0, 0, 0), r2=None, group="room"):
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=loc, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(radius1=r, radius2=r2, depth=h, vertices=verts, location=loc, rotation=rot)
    o = bpy.context.active_object
    return _finish(o, name, m, bevel, group)


def sph(name, r, loc, m, scale=(1, 1, 1), seg=32, group="room"):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=seg, ring_count=seg // 2, location=loc)
    o = bpy.context.active_object
    o.scale = scale
    return _finish(o, name + "_smooth", m, 0, group)


def torus(name, R, r, loc, m, rot=(0, 0, 0), ms=64, mn=14, group="room"):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=ms, minor_segments=mn,
                                     location=loc, rotation=rot)
    o = bpy.context.active_object
    return _finish(o, name + "_smooth", m, 0, group)


def tube(name, pts, radius, m, closed=True, group="room"):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 3
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0], p[1], p[2], 1)
    sp.use_cyclic_u = closed
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(m)
    objs_by_group.setdefault(group, []).append(o)
    return o


def stadium(cx, cy, z, length, width, n=64):
    r = width / 2
    straight = length - width
    pts = []
    for i in range(n):
        a = i / n * 2 * math.pi
        sx = math.cos(a)
        sy = math.sin(a)
        pts.append((cx + r * sx * 0 + (r * math.cos(a)), cy + (straight / 2 if math.sin(a) > 0 else -straight / 2) + r * math.sin(a), z))
    return pts


def circle(cx, cy, z, r, n=96):
    return [(cx + r * math.cos(i / n * 2 * math.pi), cy + r * math.sin(i / n * 2 * math.pi), z) for i in range(n)]


def collider(x, y, r):
    META["colliders"].append({"x": x, "y": y, "r": r})


def light(x, y, z, color, power, rng=8):
    META["lights"].append({"x": x, "y": y, "z": z, "color": color, "power": power, "range": rng})


# ---------------------------------------------------------------- 房间尺寸
RX, RY, RH = 9.0, 7.0, 5.0     # 半宽、半深、高

# 地板：2m 瓷砖 + 嵌缝
tiles_x = int(RX * 2 / 2)
tiles_y = int(RY * 2 / 2)
for i in range(tiles_x):
    for j in range(tiles_y):
        x = -RX + 1 + i * 2
        y = -RY + 1 + j * 2
        box(f"floor_tile_{i}_{j}", (1.94, 1.94, 0.12), (x, y, -0.06), M_FLOOR, bevel=0.025, group="floor")
box("floor_base", (RX * 2 + 0.2, RY * 2 + 0.2, 0.1), (0, 0, -0.17), M_DARK, bevel=0, group="floor")

# 中央跑道：大圆 + 两侧椭圆（嵌入式发光边）
cyl("floor_disc", 2.45, 0.025, (0, 0, 0.012), M_FLOOR_IN, verts=96, group="floor")
tube("track_circle", circle(0, 0, 0.045, 2.2), 0.045, M_GLOW, group="floor")
tube("track_circle_inner", circle(0, 0, 0.04, 1.55), 0.025, M_GLOW_SOFT, group="floor")
for sx in (-1, 1):
    for yy in (-1.35, 1.35):
        cyl(f"floor_oval_{sx}_{yy}", 0.95, 0.025, (sx * 4.9, yy, 0.012), M_FLOOR_IN, verts=64, group="floor")
    box(f"floor_oval_mid_{sx}", (1.9, 2.7, 0.025), (sx * 4.9, 0, 0.0125), M_FLOOR_IN, bevel=0, group="floor")
    tube(f"track_oval_{sx}", stadium(sx * 4.9, 0, 0.045, 4.6, 1.9), 0.04, M_GLOW, group="floor")
# 透镜（眼形）双弧
def arc_pts(cx, cy, r, z, other, n=120):
    pts = []
    for i in range(n):
        a = i / n * 2 * math.pi
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        if math.hypot(x - other[0], y - other[1]) <= r - 0.02:
            pts.append((x, y, z))
    return pts


for sy_ in (-1, 1):
    pts = arc_pts(0, sy_ * 1.05, 1.95, 0.045, (0, -sy_ * 1.05))
    pts.sort(key=lambda p: math.atan2(p[1] - sy_ * 1.05, p[0]))
    if len(pts) > 3:
        tube(f"track_lens_{sy_}", pts, 0.03, M_GLOW, closed=False, group="floor")
# 胶囊面板边缘圆点灯
for sx in (-1, 1):
    pts = stadium(sx * 4.9, 0, 0.05, 4.6, 1.9, n=48)
    for k, p in enumerate(pts):
        cyl(f"track_dot_{sx}_{k}", 0.04, 0.03, (p[0], p[1], 0.06), M_GLOW, verts=12, group="floor")

# 连接跑道的细线
for sx in (-1, 1):
    box(f"track_link_{sx}", (1.4, 0.05, 0.03), (sx * 3.0, 0, 0.03), M_GLOW_SOFT, bevel=0, group="floor")

# ---------------------------------------------------------------- 墙
def wall(name, size, loc, rot=(0, 0, 0)):
    return box(name, size, loc, M_WALL, bevel=0.03, rot=rot, group="wall")


wall("wall_back", (RX * 2 + 0.6, 0.4, RH), (0, RY + 0.2, RH / 2))
wall("wall_left", (0.4, RY * 2 + 0.6, RH), (-RX - 0.2, 0, RH / 2))
wall("wall_right", (0.4, RY * 2 + 0.6, RH), (RX + 0.2, 0, RH / 2))
wall("wall_front", (RX * 2 + 0.6, 0.4, RH), (0, -RY - 0.2, RH / 2))

# 墙面板：竖向凸起 + 横向凹槽 + 发光带
for i in range(-4, 5):
    x = i * 2.0
    box(f"back_panel_{i}", (1.82, 0.1, 3.3), (x, RY - 0.05, 2.35), M_METAL_D, bevel=0.025, group="wall")
    box(f"back_panel_hi_{i}", (1.62, 0.04, 0.5), (x, RY - 0.12, 3.7), M_METAL, bevel=0.015, group="wall")
for j in range(-3, 4):
    y = j * 2.0
    for sx, nm in ((-1, "left"), (1, "right")):
        box(f"{nm}_panel_{j}", (0.1, 1.82, 3.3), (sx * (RX - 0.05), y, 2.35), M_METAL_D, bevel=0.025, group="wall")
        box(f"{nm}_panel_hi_{j}", (0.04, 1.62, 0.5), (sx * (RX - 0.12), y, 3.7), M_METAL, bevel=0.015, group="wall")
# 踢脚线、顶部饰条、发光带
box("trim_back_low", (RX * 2, 0.16, 0.5), (0, RY - 0.08, 0.25), M_METAL_L, bevel=0.03, group="wall")
box("trim_back_top", (RX * 2, 0.2, 0.3), (0, RY - 0.1, RH - 0.15), M_METAL_L, bevel=0.03, group="wall")
box("glow_back_top", (RX * 2, 0.03, 0.03), (0, RY - 0.22, RH - 0.55), M_GLOW, bevel=0, group="wall")
box("glow_back_low", (RX * 2, 0.03, 0.03), (0, RY - 0.2, 0.62), M_GLOW_SOFT, bevel=0, group="wall")
for sx, nm in ((-1, "left"), (1, "right")):
    box(f"trim_{nm}_low", (0.16, RY * 2, 0.5), (sx * (RX - 0.08), 0, 0.25), M_METAL_L, bevel=0.03, group="wall")
    box(f"trim_{nm}_top", (0.2, RY * 2, 0.3), (sx * (RX - 0.1), 0, RH - 0.15), M_METAL_L, bevel=0.03, group="wall")
    box(f"glow_{nm}_top", (0.03, RY * 2, 0.03), (sx * (RX - 0.22), 0, RH - 0.55), M_GLOW, bevel=0, group="wall")
    box(f"glow_{nm}_low", (0.03, RY * 2, 0.03), (sx * (RX - 0.2), 0, 0.62), M_GLOW_SOFT, bevel=0, group="wall")
# 墙根管线
for k, z in enumerate((0.78, 1.0)):
    cyl(f"pipe_back_{k}", 0.075, RX * 2 - 0.4, (0, RY - 0.3, z), M_METAL, verts=24, rot=(0, math.pi / 2, 0), group="wall")
    for sx, nm in ((-1, "left"), (1, "right")):
        cyl(f"pipe_{nm}_{k}", 0.075, RY * 2 - 0.4, (sx * (RX - 0.3), 0, z), M_METAL, verts=24, rot=(math.pi / 2, 0, 0), group="wall")
for i in range(-4, 5):
    box(f"pipe_clamp_{i}", (0.22, 0.12, 0.42), (i * 2.0 + 1.0, RY - 0.27, 0.9), M_DARK, bevel=0.01, group="wall")

tube("wall_bend_pipe", [(-RX + 0.3, 2.0, 3.9), (-RX + 0.3, 3.5, 3.9), (-RX + 0.3, 4.6, 4.2), (-RX + 0.3, 5.6, 4.35), (-RX + 0.8, 6.4, 4.35), (-RX + 1.6, RY - 0.3, 4.2)], 0.17, M_METAL, closed=False, group="wall")
# ---------------------------------------------------------------- 终端区（后墙中央）
TY = RY - 1.4
box("platform_0", (7.4, 3.1, 0.14), (0, TY - 0.1, 0.07), M_METAL_L, bevel=0.03, group="terminal")
box("platform_1", (6.6, 2.7, 0.14), (0, TY, 0.21), M_METAL_L, bevel=0.03, group="terminal")
box("platform_1b", (5.8, 2.3, 0.14), (0, TY + 0.2, 0.35), M_METAL, bevel=0.03, group="terminal")
box("platform_2", (5.0, 1.8, 0.2), (0, TY + 0.35, 0.52), M_METAL, bevel=0.04, group="terminal")
box("platform_glow_0", (7.2, 0.03, 0.04), (0, TY - 1.65, 0.1), M_GLOW, bevel=0, group="terminal")
box("platform_glow_1", (6.4, 0.04, 0.05), (0, TY - 1.36, 0.22), M_GLOW, bevel=0, group="terminal")
box("platform_glow_2", (4.8, 0.04, 0.05), (0, TY - 0.53, 0.52), M_GLOW, bevel=0, group="terminal")
# 屏幕与框
box("screen_frame", (6.4, 0.22, 3.0), (0, RY - 0.18, 3.2), M_METAL_D, bevel=0.05, group="terminal")
box("screen_surface", (5.9, 0.04, 2.7), (0, RY - 0.31, 3.2), M_SCREEN, bevel=0, group="terminal")
box("screen_glow_l", (0.05, 0.05, 2.9), (-3.28, RY - 0.3, 3.2), M_GLOW, bevel=0, group="terminal")
box("screen_glow_r", (0.05, 0.05, 2.9), (3.28, RY - 0.3, 3.2), M_GLOW, bevel=0, group="terminal")
# 控制台
box("console_body", (4.2, 1.1, 0.95), (0, TY + 0.45, 1.1), M_METAL_D, bevel=0.05, group="terminal")
box("console_top", (4.3, 1.15, 0.12), (0, TY + 0.45, 1.62), M_METAL_L, bevel=0.04, rot=(math.radians(-8), 0, 0), group="terminal")
box("console_glow", (3.9, 0.04, 0.06), (0, TY - 0.15, 1.15), M_GLOW, bevel=0, group="terminal")
for i in range(-4, 5):
    box(f"console_key_{i}", (0.28, 0.2, 0.05), (i * 0.4, TY + 0.15, 1.72), M_GLOW_SOFT, bevel=0.01, group="terminal")
for sx in (-1, 1):
    box(f"console_side_{sx}", (0.5, 0.9, 1.5), (sx * 2.75, TY + 0.45, 1.0), M_METAL, bevel=0.04, group="terminal")
    box(f"console_side_glow_{sx}", (0.3, 0.04, 0.3), (sx * 2.75, TY - 0.02, 1.4), M_GLOW, bevel=0.01, group="terminal")
collider(0, TY, 3.6)
light(0, RY - 2.2, 2.6, CYAN, 90, 12)

# ---------------------------------------------------------------- 孵化舱（前左）
PX, PY = -5.6, -3.1
cyl("pod_base", 1.55, 0.7, (PX, PY, 0.35), M_METAL, bevel=0.04, verts=64, group="pod")
cyl("pod_base_ring", 1.62, 0.12, (PX, PY, 0.76), M_METAL_L, verts=64, group="pod")
cyl("pod_base_top", 1.35, 0.14, (PX, PY, 0.88), M_METAL_D, verts=64, group="pod")
torus("pod_glow_ring", 1.28, 0.05, (PX, PY, 0.97), M_GLOW, group="pod")
for k in range(8):
    a = k / 8 * 2 * math.pi
    box(f"pod_slit_{k}", (0.07, 0.05, 0.4), (PX + 1.55 * math.cos(a), PY + 1.55 * math.sin(a), 0.38), M_GLOW,
        bevel=0, rot=(0, 0, a), group="pod")
cyl("pod_platform_glow", 0.62, 0.04, (PX, PY, 0.97), M_GLOW, verts=48, group="pod")
cyl("pod_foot_glow", 1.66, 0.04, (PX, PY, 0.06), M_GLOW_SOFT, verts=64, group="pod")
# 玻璃罩（半球）
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.25, segments=48, ring_count=24, location=(PX, PY, 0.95))
dome = bpy.context.active_object
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.bisect(plane_co=(0, 0, PX * 0 + 0.95), plane_no=(0, 0, 1), clear_inner=True)
bpy.ops.object.mode_set(mode="OBJECT")
_finish(dome, "pod_dome_smooth", M_GLASS, 0, "pod")
# Nono 兔子
NZ = 0.95 + 0.38
sph("nono_body", 0.34, (PX, PY, NZ), M_WHITE, (1, 0.95, 1.05), group="pod")
sph("nono_head", 0.3, (PX, PY - 0.02, NZ + 0.5), M_WHITE, (1.1, 1, 0.95), group="pod")
for sx in (-1, 1):
    sph(f"nono_ear_{sx}", 0.1, (PX + sx * 0.17, PY, NZ + 0.95), M_WHITE, (0.7, 0.55, 2.4), group="pod")
    sph(f"nono_ear_in_{sx}", 0.06, (PX + sx * 0.17, PY - 0.045, NZ + 0.93), M_ORANGE, (0.6, 0.4, 2.0), group="pod")
    sph(f"nono_eye_{sx}", 0.055, (PX + sx * 0.12, PY - 0.27, NZ + 0.53), M_EYE, (1, 0.5, 1.2), group="pod")
    sph(f"nono_arm_{sx}", 0.1, (PX + sx * 0.33, PY - 0.08, NZ + 0.05), M_WHITE, (0.7, 0.7, 1.3), group="pod")
    sph(f"nono_foot_{sx}", 0.11, (PX + sx * 0.16, PY - 0.12, NZ - 0.33), M_WHITE, (1, 1.3, 0.7), group="pod")
sph("nono_nose", 0.03, (PX, PY - 0.31, NZ + 0.46), M_ORANGE, group="pod")
sph("nono_tail", 0.1, (PX, PY + 0.33, NZ - 0.15), M_WHITE, group="pod")
collider(PX, PY, 1.75)
light(PX, PY, 1.8, CYAN, 70, 8)

# ---------------------------------------------------------------- 全息投影底座（前中偏左）
HX, HY = -1.7, -3.3
for k in range(6):
    pass
bpy.ops.mesh.primitive_cylinder_add(radius=0.75, depth=0.3, vertices=6, location=(HX, HY, 0.15))
hexb = bpy.context.active_object
_finish(hexb, "holo_base", M_METAL_L, 0.03, "holo")
bpy.ops.mesh.primitive_cylinder_add(radius=0.58, depth=0.08, vertices=6, location=(HX, HY, 0.33))
_finish(bpy.context.active_object, "holo_base_top", M_METAL_D, 0.01, "holo")
torus("holo_base_glow", 0.5, 0.025, (HX, HY, 0.38), M_GLOW, group="holo")
HZ = 1.25
torus("holo_icon_ring", 0.36, 0.022, (HX, HY, HZ), M_GLOW, group="holo")
torus("holo_icon_ring2", 0.24, 0.018, (HX, HY, HZ), M_GLOW_SOFT, rot=(math.pi / 2, 0, 0), group="holo")
bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=0.03, vertices=6, location=(HX, HY, HZ))
_finish(bpy.context.active_object, "holo_icon_core", M_GLOW, 0, "holo")
cyl("holo_beam", 0.5, 0.75, (HX, HY, 0.78), M_GLASS_T, verts=6, r2=0.35, group="holo")
sph("holo_man_head", 0.09, (HX, HY, HZ + 0.34), M_HOLO, group="holo")
cyl("holo_man_body", 0.12, 0.34, (HX, HY, HZ + 0.1), M_HOLO, verts=16, r2=0.08, group="holo")
for k in range(5):
    cyl(f"holo_scan_{k}", 0.32 - k * 0.02, 0.008, (HX, HY, HZ - 0.28 + k * 0.17), M_GLOW_SOFT, verts=32, group="holo")
META["animated"]["holo_icon"] = {"x": HX, "y": HY, "z": HZ}
collider(HX, HY, 0.9)
light(HX, HY, 1.3, CYAN, 40, 6)

# ---------------------------------------------------------------- 弧形大型设备（前右）
CX_, CY_ = 5.9, -2.9


def capsule(name, r, length, loc, rot_z, m, group="curve"):
    c = math.cos(rot_z)
    sn = math.sin(rot_z)
    cyl(name + "_mid", r, length, loc, m, verts=40, bevel=0, rot=(0, math.pi / 2, rot_z), group=group)
    for sgn in (-1, 1):
        sph(f"{name}_end{sgn}", r, (loc[0] + sgn * c * length / 2, loc[1] + sgn * sn * length / 2, loc[2]), m, group=group)


segs = [(-0.55, 0.15, 0.55, -0.35), (0.0, 0.0, 0.62, 0.0), (0.55, 0.15, 0.55, 0.35)]
for k, (dx, dy, rr, rz) in enumerate(segs):
    capsule(f"curve_seg{k}", rr, 1.7, (CX_ + dx * 2.2, CY_ + dy * 2.2, 0.75 + rr * 0.4), rz + math.pi / 2, M_METAL if k != 1 else M_METAL_L)
    torus(f"curve_seg{k}_band", rr + 0.02, 0.035, (CX_ + dx * 2.2, CY_ + dy * 2.2, 0.75 + rr * 0.4), M_METAL_D,
          rot=(0, math.pi / 2, rz + math.pi / 2 + math.pi / 2) if False else (math.pi / 2, 0, rz), group="curve")
box("curve_plinth", (4.4, 2.4, 0.35), (CX_, CY_ + 0.2, 0.175), M_METAL_D, bevel=0.05, group="curve")
box("curve_plinth_glow", (4.2, 0.04, 0.05), (CX_, CY_ - 0.98, 0.2), M_GLOW, bevel=0, group="curve")
cyl("curve_port", 0.14, 0.06, (CX_, CY_ - 1.0, 0.95), M_GLOW, verts=24, rot=(math.pi / 2, 0, 0), group="curve")
cyl("curve_port2", 0.1, 0.06, (CX_ + 1.3, CY_ - 0.85, 0.85), M_GLOW_SOFT, verts=24, rot=(math.pi / 2, 0, 0), group="curve")
collider(CX_, CY_, 2.3)
light(CX_, CY_ - 1.0, 1.2, CYAN, 45, 7)

# ---------------------------------------------------------------- 后左设备：矮圆机 + 高个传感机
SX_, SY_ = -6.7, 4.6
cyl("squat_body", 0.95, 1.3, (SX_, SY_, 0.65), M_METAL, bevel=0.04, verts=48, group="machine")
cyl("squat_cap", 1.0, 0.18, (SX_, SY_, 1.39), M_METAL_L, verts=48, group="machine")
torus("squat_top_glow", 0.72, 0.07, (SX_, SY_, 1.5), M_GLOW, group="machine")
cyl("squat_core", 0.55, 0.06, (SX_, SY_, 1.49), M_GLOW_SOFT, verts=48, group="machine")
for k in range(6):
    torus(f"squat_band_{k}", 0.97, 0.03, (SX_, SY_, 0.25 + k * 0.19), M_METAL_D, group="machine")
cyl("squat_pipe", 0.17, 3.2, (SX_ - 0.3, RY - 0.45, 1.6), M_METAL, verts=24, rot=(0, 0, 0), group="machine")
cyl("squat_pipe_h", 0.17, 1.9, (SX_ - 0.3, SY_ + 0.9, 2.55), M_METAL, verts=24, rot=(math.pi / 2, 0, 0), group="machine")
collider(SX_, SY_, 1.1)

TX_, TY_ = -4.3, 5.3
cyl("tall_base", 0.7, 0.4, (TX_, TY_, 0.2), M_METAL_D, bevel=0.03, verts=48, group="machine")
cyl("tall_column", 0.38, 1.9, (TX_, TY_, 1.3), M_METAL, bevel=0.03, verts=32, group="machine")
torus("tall_column_glow", 0.4, 0.035, (TX_, TY_, 1.0), M_GLOW, group="machine")
box("tall_head", (0.95, 0.8, 0.62), (TX_, TY_ - 0.1, 2.5), M_METAL_L, bevel=0.07, group="machine")
cyl("tall_lens", 0.25, 0.3, (TX_, TY_ - 0.62, 2.5), M_DARK, verts=32, rot=(math.pi / 2, 0, 0), group="machine")
torus("tall_lens_ring", 0.26, 0.03, (TX_, TY_ - 0.78, 2.5), M_GLOW, rot=(math.pi / 2, 0, 0), group="machine")
sph("tall_lens_eye", 0.13, (TX_, TY_ - 0.78, 2.5), M_GLOW, group="machine")
box("tall_head_top", (0.6, 0.5, 0.12), (TX_, TY_ - 0.05, 2.88), M_METAL_D, bevel=0.03, group="machine")
collider(TX_, TY_, 0.9)
light(SX_, SY_, 2.2, CYAN, 35, 7)

# ---------------------------------------------------------------- 玻璃培养管（后右）
def containment_tube(idx, x, y, with_bird):
    cyl(f"tube{idx}_base", 0.95, 0.35, (x, y, 0.175), M_METAL_D, bevel=0.03, verts=48, group="tube")
    cyl(f"tube{idx}_base2", 0.82, 0.18, (x, y, 0.44), M_METAL, verts=48, group="tube")
    torus(f"tube{idx}_base_glow", 0.8, 0.04, (x, y, 0.55), M_GLOW, group="tube")
    cyl(f"tube{idx}_glass_smooth", 0.74, 3.5, (x, y, 2.3), M_GLASS_T, verts=48, group="tube")
    cyl(f"tube{idx}_cap", 0.9, 0.3, (x, y, 4.2), M_METAL, bevel=0.03, verts=48, group="tube")
    torus(f"tube{idx}_cap_glow", 0.8, 0.04, (x, y, 4.04), M_GLOW, group="tube")
    for k in range(4):
        a = k / 4 * 2 * math.pi + 0.4
        cyl(f"tube{idx}_rod_{k}", 0.025, 3.5, (x + 0.76 * math.cos(a), y + 0.76 * math.sin(a), 2.3), M_METAL_L,
            verts=10, group="tube")
    if with_bird:
        box(f"tube{idx}_console", (1.0, 0.55, 0.5), (x - 1.35, y - 1.05, 0.5), M_METAL_D, bevel=0.04, group="tube")
        box(f"tube{idx}_screen", (0.8, 0.04, 0.35), (x - 1.35, y - 1.31, 0.6), M_SCREEN, bevel=0, rot=(math.radians(-25), 0, 0), group="tube")
        z = 2.0
        sph(f"bird{idx}_body", 0.3, (x, y, z), M_GREY, (1.0, 1.4, 1.0), group="tube")
        sph(f"bird{idx}_head", 0.18, (x, y - 0.38, z + 0.2), M_METAL_L, group="tube")
        cyl(f"bird{idx}_beak", 0.06, 0.2, (x, y - 0.6, z + 0.18), M_ORANGE, verts=12, r2=0.0, rot=(math.pi / 2, 0, 0), group="tube")
        for sx in (-1, 1):
            sph(f"bird{idx}_wing_{sx}", 0.4, (x + sx * 0.45, y + 0.05, z + 0.05), M_METAL, (0.9, 0.12, 0.6), group="tube")
            sph(f"bird{idx}_eye_{sx}", 0.04, (x + sx * 0.08, y - 0.53, z + 0.26), M_GLOW, group="tube")
        sph(f"bird{idx}_tail", 0.18, (x, y + 0.5, z - 0.1), M_GREY, (0.6, 1.5, 0.15), group="tube")
        sph(f"bird{idx}_core", 0.09, (x, y - 0.02, z + 0.04), M_GLOW, group="tube")
        META["animated"]["bird"] = {"x": x, "y": y, "z": z}
    else:
        sph(f"tube{idx}_mist", 0.4, (x, y, 1.8), M_GLOW_SOFT, (1, 1, 1.8), group="tube")
    collider(x, y, 1.0)


containment_tube(1, 4.7, 5.0, True)
containment_tube(2, 7.0, 4.9, False)
light(5.8, 4.8, 2.6, CYAN, 60, 9)

# ---------------------------------------------------------------- 悬浮小机器人
def drone(idx, x, y, z):
    sph(f"drone{idx}_body", 0.26, (x, y, z), M_WHITE, group="drone")
    torus(f"drone{idx}_band", 0.265, 0.025, (x, y, z), M_DARK, group="drone")
    sph(f"drone{idx}_eye", 0.1, (x, y - 0.22, z + 0.04), M_EYE, (1, 0.5, 1), group="drone")
    for sx in (-1, 1):
        cyl(f"drone{idx}_wing_{sx}", 0.2, 0.012, (x + sx * 0.4, y, z), M_HOLO, verts=32, rot=(0, math.pi / 2, 0), group="drone")
        box(f"drone{idx}_arm_{sx}", (0.16, 0.04, 0.04), (x + sx * 0.26, y, z), M_METAL, bevel=0.01, group="drone")
    sph(f"drone{idx}_light", 0.05, (x, y, z - 0.27), M_GLOW, group="drone")
    META["animated"][f"drone{idx}"] = {"x": x, "y": y, "z": z}


drone(0, -0.6, 0.8, 2.3)
drone(1, 2.4, -0.6, 2.7)
drone(2, 0.9, 2.6, 3.1)
light(0.6, 0.8, 2.6, CYAN, 25, 6)

# ---------------------------------------------------------------- 侧面补充：左右墙边的小设备
for sx in (-1, 1):
    box(f"side_cab_{sx}", (0.9, 2.2, 1.1), (sx * (RX - 0.55), 0.5 * sx, 0.55), M_METAL_D, bevel=0.04, group="side")
    box(f"side_cab_top_{sx}", (0.95, 2.25, 0.1), (sx * (RX - 0.55), 0.5 * sx, 1.15), M_METAL_L, bevel=0.03, group="side")
    box(f"side_cab_glow_{sx}", (0.04, 1.8, 0.08), (sx * (RX - 1.02), 0.5 * sx, 0.9), M_GLOW, bevel=0, group="side")
    collider(sx * (RX - 0.55), 0.5 * sx, 1.3)

# ---------------------------------------------------------------- 曲线转网格
bpy.ops.object.select_all(action="DESELECT")
for o in list(bpy.data.objects):
    if o.type == "CURVE":
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        bpy.ops.object.convert(target="MESH")
        o.select_set(False)

# ---------------------------------------------------------------- 预览灯光与相机
world = bpy.data.worlds.new("w")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.02, 0.04, 0.08, 1)
bg.inputs["Strength"].default_value = 1.4

if RENDER:
    for name, loc, energy, col in [
        ("fill_main", (0, 0, 4.6), 2600, (0.75, 0.88, 1.0)),
        ("fill_left", (-6, -1, 4.2), 1500, (0.7, 0.85, 1.0)),
        ("fill_right", (6, 0, 4.2), 1500, (0.7, 0.85, 1.0)),
    ]:
        ld = bpy.data.lights.new(name, "POINT")
        ld.energy = energy
        ld.color = col
        ld.shadow_soft_size = 1.5
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        bpy.context.collection.objects.link(lo)
    for l in META["lights"]:
        ld = bpy.data.lights.new("g", "POINT")
        ld.energy = l["power"] * 6
        ld.color = l["color"]
        ld.shadow_soft_size = 0.4
        lo = bpy.data.objects.new("g", ld)
        lo.location = (l["x"], l["y"], l["z"])
        bpy.context.collection.objects.link(lo)

    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 24
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    cams = {
        "ref": ((-6.0, -12.5, 7.5), (0.2, 1.2, 1.0)),
        "front": ((0, -14.5, 6.5), (0, 1.5, 1.4)),
        "right": ((11.0, -9.5, 6.0), (-1, 1.5, 1.2)),
    }
    loc, tgt = cams.get(CAM, cams["ref"])
    cam.location = loc
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    # 隐藏前墙以便取景
    for o in bpy.data.objects:
        if o.name == "wall_front":
            o.hide_render = True
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = SAMPLES
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 580
    scene.render.filepath = os.path.join(ROOT, RENDER)
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "Medium High Contrast"
    except Exception:
        pass
    scene.use_nodes = True
    bpy.ops.render.render(write_still=True)
    print("rendered", scene.render.filepath)

# ---------------------------------------------------------------- 导出
if GLB:
    os.makedirs(os.path.dirname(os.path.join(ROOT, GLB)), exist_ok=True)
    for o in bpy.data.objects:
        o.hide_render = False
    bpy.ops.export_scene.gltf(
        filepath=os.path.join(ROOT, GLB),
        export_format="GLB",
        export_apply=True,
        export_yup=True,
        export_cameras=False,
        export_lights=False,
        export_image_format="JPEG",
        export_jpeg_quality=88,
    )
    with open(os.path.join(ROOT, GLB.replace(".glb", ".json")), "w") as f:
        json.dump(META, f, indent=1)
    print("exported", GLB, "objects:", len(bpy.data.objects))
