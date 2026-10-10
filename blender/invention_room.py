"""发明室 I —— 在 Blender 里程序化建模，导出 GLB 与场景元数据，并可渲染预览图。

用法:
  Blender -b -P blender/invention_room.py -- --glb public/models/inv/invention_room.glb --render out.png
"""
import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


ROOT = os.getcwd()
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from nono import build_nono
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
M_FLOOR = mat("floor_tile", (0.66, 0.71, 0.78), 0.55, 0.42, coat=0.15)
M_FLOOR_IN = mat("floor_inlay", (0.46, 0.52, 0.6), 0.65, 0.4, coat=0.15)
M_WALL = mat("wall_panel", (0.62, 0.67, 0.74), 0.8, 0.34)
M_WALL_D = mat("wall_dark", (0.14, 0.17, 0.22), 0.8, 0.45)
M_WHITE = mat("white_plastic", (0.93, 0.95, 0.98), 0.0, 0.28, coat=0.4)
M_GLOW = mat("glow_cyan", (0.02, 0.1, 0.14), 0.0, 0.4, emit=CYAN, strength=2.4)
M_GLOW_SOFT = mat("glow_soft", (0.02, 0.1, 0.14), 0.0, 0.4, emit=CYAN, strength=1.2)
M_GLASS = mat("glass", (0.55, 0.8, 1.0), 0.0, 0.05, alpha=0.22)
M_GLASS_T = mat("glass_tube", (0.6, 0.85, 1.0), 0.0, 0.05, alpha=0.16)
M_DARK = mat("dark_rubber", (0.03, 0.035, 0.05), 0.2, 0.6)
M_EYE = mat("eye", (0.02, 0.03, 0.1), 0.0, 0.2, emit=(0.15, 0.4, 1.0), strength=1.2)
M_SCREEN = mat("hud_screen", (0.02, 0.06, 0.1), 0.0, 0.3, emit=(1, 1, 1), strength=1.6,
               image=os.path.join(ROOT, "blender/hud.png"))
M_GREY = mat("grey_body", (0.55, 0.6, 0.65), 0.6, 0.4)
M_HOLO = mat("holo_body", (0.3, 0.7, 1.0), 0.0, 0.3, emit=(0.35, 0.85, 1.0), strength=2.5, alpha=0.4)
M_ORANGE = mat("accent_orange", (1.0, 0.55, 0.12), 0.2, 0.35, emit=(1.0, 0.5, 0.1), strength=1.5)


M_BLUE = mat("blue_enamel", (0.015, 0.13, 0.32), 0.55, 0.28, coat=0.3)
M_BRUSHED = mat("brushed_steel", (0.68, 0.73, 0.79), 0.8, 0.35)
M_BEAM = mat("holo_beam", (0.12, 0.5, 0.75), rough=0.5, emit=CYAN, strength=0.6, alpha=0.09)

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

# 大块金属地板，细接缝；灯带嵌在深灰轨道里。
for i in range(6):
    for j in range(4):
        box(f"floor_tile_{i}_{j}", (2.984, 3.484, 0.12),
            (-7.5 + i * 3, -5.25 + j * 3.5, -0.06), M_FLOOR, bevel=0.006, group="floor")
box("floor_base", (18.2, 14.2, 0.1), (0, 0, -0.17), M_METAL_D, bevel=0, group="floor")
cyl("floor_disc", 2.15, 0.02, (0, 0, 0.011), M_METAL_D, verts=96, group="floor")
cyl("floor_disc_inner", 1.98, 0.024, (0, 0, 0.015), M_FLOOR_IN, verts=96, group="floor")
tube("track_circle", circle(0, 0, 0.026, 2.05), 0.015, M_GLOW_SOFT, group="floor")
for sy in (-1, 1):
    # 中央眼形标记：两条相向弧线。
    pts = [(1.78 * math.cos(a), sy * (0.60 * math.sin(a)), 0.036)
           for a in [i * math.pi / 64 for i in range(65)]]
    tube(f"track_lens_{sy}", pts, 0.018, M_METAL_L, closed=False, group="floor")
for sx in (-1, 1):
    cx = sx * 4.25
    pts = [(cx + (p[1]), p[0], 0.025) for p in stadium(0, 0, 0, 4.7, 1.65)]
    box(f"floor_lane_{sx}", (4.6, 1.72, 0.024), (cx, 0, 0.014), M_FLOOR_IN, bevel=0.12, group="floor")
    tube(f"track_groove_{sx}", pts, 0.048, M_METAL_D, group="floor")
    tube(f"track_oval_{sx}", [(x,y,0.061) for x,y,z in pts], 0.016, M_GLOW_SOFT, group="floor")
    for k, (x,y,z) in enumerate(pts[::4]):
        cyl(f"track_dot_{sx}_{k}", 0.026, 0.006, (x,y,0.075), M_GLOW, verts=10, group="floor")
    box(f"track_bridge_{sx}", (0.36, 1.3, 0.04), (sx*2.05,0,0.036), M_FLOOR_IN, bevel=0.025, group="floor")
    for dx in (-1.2, 1.2):
        tube(f"track_bracket_{sx}_{dx}", [(cx+dx+0.14,-0.67,0.055),(cx+dx,-0.45,0.055),
             (cx+dx,0.45,0.055),(cx+dx+0.14,0.67,0.055)], 0.023, M_METAL_L, closed=False, group="floor")

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
    box(f"back_panel_{i}", (1.82, 0.1, 3.3), (x, RY - 0.05, 2.35), M_WALL, bevel=0.025, group="wall")
    box(f"back_panel_hi_{i}", (1.62, 0.04, 0.5), (x, RY - 0.12, 3.7), M_METAL, bevel=0.015, group="wall")
for j in range(-3, 4):
    y = j * 2.0
    for sx, nm in ((-1, "left"), (1, "right")):
        box(f"{nm}_panel_{j}", (0.1, 1.82, 3.3), (sx * (RX - 0.05), y, 2.35), M_WALL, bevel=0.025, group="wall")
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
box("platform_0", (4.6, 2.5, 0.14), (0, TY, 0.07), M_METAL_D, bevel=0.03, group="terminal")
box("platform_1", (4.0, 1.95, 0.14), (0, TY+0.25, 0.21), M_METAL_D, bevel=0.03, group="terminal")
for sx in (-1, 1):
    box(f"platform_rail_{sx}", (0.4, 2.6, 0.3), (sx*2.25, TY, 0.15), M_BRUSHED, bevel=0.04, group="terminal")
    box(f"platform_marker_{sx}", (0.2, 0.18, 0.012), (sx*2.25, TY-1.1, 0.307), M_GLOW_SOFT, group="terminal")
# 屏幕与框
box("screen_frame", (4.3, 0.22, 2.65), (0, RY - 0.18, 3.2), M_METAL_D, bevel=0.05, group="terminal")
# 独立平面保留完整 0..1 UV，避免立方体 UV 把 HUD 裁切。
bpy.ops.mesh.primitive_plane_add(size=2, location=(0, RY-0.31, 3.2), rotation=(math.pi/2,0,0))
screen = bpy.context.active_object
screen.scale = (1.96, 1.16, 1)
_finish(screen, "screen_surface", M_SCREEN, 0, "terminal")
box("screen_glow_l", (0.03, 0.05, 2.35), (-2.1, RY - 0.3, 3.2), M_GLOW, bevel=0, group="terminal")
box("screen_glow_r", (0.03, 0.05, 2.35), (2.1, RY - 0.3, 3.2), M_GLOW, bevel=0, group="terminal")
# 台阶上方的薄控制面板。
box("console_body", (2.9, 0.5, 0.22), (0, TY+0.5, 0.4), M_METAL_D, bevel=0.04, group="terminal")
for i in range(-3, 4):
    box(f"console_key_{i}", (0.25,0.16,0.018), (i*0.36,TY+0.4,0.52), M_GLOW_SOFT, group="terminal")
for x in (-3.9,-3.65):
    tube(f"pipe_back_vertical_{x}", [(x,6.6,5),(x,6.6,3.8),(x+0.3,6.6,3.3),(x+0.3,6.6,1)],
         0.075, M_METAL_D, closed=False, group="wall")
collider(0, TY, 2.4)
light(0, RY - 2.2, 2.6, CYAN, 28, 9)

# ---------------------------------------------------------------- NONO 大舱（前左，参考图区域 1）
# 轮廓分成玻璃罩、粗分段环管、深色机械基座与六边形外护沿。
PX, PY = -6.3, -0.8
POD_FOOTPRINT = 2.64
POD_DECK = 1.86
POD_GLASS_R = 1.83
M_POD_DARK = mat("pod_navy", (0.035, 0.085, 0.115), 0.62, 0.34)
M_POD_SILVER = mat("pod_silver", (0.59, 0.67, 0.71), 0.78, 0.30, coat=0.22)
M_POD_GLASS = mat("pod_glass", (0.10, 0.46, 0.58), 0.12, 0.14, alpha=0.19, coat=0.35)
M_POD_LIGHT = mat("pod_light", (0.035, 0.3, 0.34), 0.18, 0.3, emit=(0.10, 0.76, 0.85), strength=1.4)


def pod_ring_band(name, radius, width, z, height, a0=0, a1=2*math.pi, material=M_POD_SILVER):
    # 实心环扇：可留接缝，又不会像整圆柱那样封住玻璃下的舱内空间。
    count = max(4, int((a1-a0)*24))
    vertices = []
    for i in range(count+1):
        angle = a0+(a1-a0)*i/count
        for r, h in ((radius-width/2,z-height/2),(radius+width/2,z-height/2),
                     (radius+width/2,z+height/2),(radius-width/2,z+height/2)):
            vertices.append((PX+r*math.cos(angle),PY+r*math.sin(angle),h))
    faces = [(3,2,1,0)]
    for i in range(count):
        for j in range(4):
            faces.append((4*i+j,4*i+(j+1)%4,4*(i+1)+(j+1)%4,4*(i+1)+j))
    faces.append(tuple(4*count+j for j in range(4)))
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], [tuple(reversed(face)) for face in faces])
    mesh.update()
    o=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(o)
    return _finish(o,name,material,.022,"pod")


def pod_pipe_arc(name, radius, z, thickness, a0, a1, material=M_POD_SILVER):
    return tube(name, [(PX+radius*math.cos(a0+(a1-a0)*i/20),
                        PY+radius*math.sin(a0+(a1-a0)*i/20),z) for i in range(21)],
                thickness, material, closed=False, group="pod")


# 下沉检修槽，护沿在最大 2.64m 半径内，保留与左墙的间隙。
bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=POD_FOOTPRINT, depth=.6, location=(PX,PY,0))
cutter=bpy.context.active_object
for tile in list(objs_by_group["floor"]):
    if tile.name.startswith("floor_tile") and (tile.location.x-PX)**2+(tile.location.y-PY)**2 < 30:
        mod=tile.modifiers.new("pod_recess", "BOOLEAN")
        mod.operation="DIFFERENCE"
        mod.object=cutter
        bpy.context.view_layer.objects.active=tile
        bpy.ops.object.modifier_apply(modifier=mod.name)
bpy.data.objects.remove(cutter, do_unlink=True)
cyl("pod_recess_floor", POD_FOOTPRINT, .04, (PX,PY,-.13), M_DARK, verts=6, group="pod")
cyl("pod_lower_foot", 2.13, .18, (PX,PY,.02), M_METAL_D, bevel=.035, verts=96, group="pod")
cyl("pod_reactor_body", 1.93, 1.15, (PX,PY,.64), M_POD_DARK, verts=96, group="pod")
pod_ring_band("pod_bottom_collar", 1.94, .15, .14, .17)
pod_ring_band("pod_upper_support", 1.97, .22, 1.17, .23, material=M_METAL_D)

# 12 块深色机身面板，边肋、凹槽和折线灯路清晰区分。
for k in range(12):
    a=k*math.tau/12
    radial=Vector((math.cos(a),math.sin(a),0))
    tangent=Vector((-math.sin(a),math.cos(a),0))
    center=Vector((PX,PY,0))+radial*1.94
    box(f"pod_body_rib_{k}",(.09,.10,.94),(*center[:2],.65),M_POD_SILVER,
        bevel=.025,rot=(0,0,a),group="pod")
    pts=[]
    for side,z in ((.13,.23),(.13,.80),(.45,.80),(.45,1.01)):
        p=Vector((PX,PY,z))+radial*1.956+tangent*side
        pts.append(tuple(p))
    tube(f"pod_panel_circuit_{k}",pts,.014,M_POD_LIGHT,closed=False,group="pod")

# 两层环形主管：每段留暗缝，外露夹箍，避免原版简单圆盘堆叠。
for k in range(24):
    a=k*math.tau/24
    pod_pipe_arc(f"pod_manifold_{k}",2.04,1.48,.19,a+.012,a+math.tau/24-.012)
    if k%3==0:
        pod_pipe_arc(f"pod_manifold_clamp_{k}",2.04,1.48,.212,a-.021,a+.021,M_METAL_D)
for k in range(12):
    a=k*math.tau/12
    pod_pipe_arc(f"pod_lower_pipe_{k}",2.10,1.19,.13,a+.01,a+math.tau/12-.01)
pod_ring_band("pod_neck_shadow",1.83,.25,1.72,.17,material=M_POD_DARK)
pod_ring_band("pod_glass_bezel",1.86,.28,1.87,.15,material=M_POD_DARK)
for k in range(16):
    a=k*math.tau/16
    pod_ring_band(f"pod_bezel_segment_{k}",1.99,.08,1.86,.17,a+.012,a+math.tau/16-.012)
    if k%2==0:
        for j in range(3):
            theta=a+.10+j*.065
            sph(f"pod_bezel_indicator_{k}_{j}",.026,
                (PX+1.925*math.cos(theta),PY+1.925*math.sin(theta),1.955),M_POD_LIGHT,
                scale=(1,1,.4),seg=12,group="pod")

# 舱底为深青色甲板与平行细灯轨，NONO 下方不再放实心发光圆饼。
cyl("pod_inner_deck",1.76,.045,(PX,PY,POD_DECK-.02),M_POD_DARK,verts=96,group="pod")
for k,dx in enumerate((-.98,-.49,0,.49,.98)):
    length=2*math.sqrt(1.68**2-dx**2)
    box(f"pod_deck_track_{k}",(.035,length,.012),(PX+dx,PY,POD_DECK+.012),
        M_POD_LIGHT,bevel=.006,group="pod")

# 半椭球罩。金属脊只跨后半圈，前方保持通透以看清 NONO。
bpy.ops.mesh.primitive_uv_sphere_add(radius=POD_GLASS_R,segments=64,ring_count=32,
                                     location=(PX,PY,1.94))
dome=bpy.context.active_object
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.bisect(plane_co=(0,0,0),plane_no=(0,0,1),clear_inner=True)
bpy.ops.object.mode_set(mode="OBJECT")
dome.scale.z=.92
_finish(dome,"pod_dome_smooth",M_POD_GLASS,0,"pod")
# 从左右基座跨过后顶部的弧形脊，和参考图的包边一致。
for name,yoff,radius,thick,material in (("pod_dome_spine",.34,1.80,.065,M_POD_SILVER),
                                      ("pod_dome_seal",.34,1.74,.023,M_POD_DARK)):
    pts=[(PX+radius*math.cos(t*math.pi/64),PY+yoff,
          1.94+radius*.92*math.sin(t*math.pi/64)) for t in range(65)]
    tube(name,pts,thick,material,closed=False,group="pod")

# 机身外侧的立式液压筒，顶盖青光但保留金属边。
for k,deg in enumerate((-150,-90,-30,30,150)):
    a=math.radians(deg)
    x,y=PX+2.20*math.cos(a),PY+2.20*math.sin(a)
    cyl(f"pod_piston_{k}",.18,.98,(x,y,.49),M_METAL_D,bevel=.022,group="pod")
    for j in range(8):
        t=j*math.tau/8
        cyl(f"pod_piston_flute_{k}_{j}",.024,.82,(x+.17*math.cos(t),y+.17*math.sin(t),.48),
            M_POD_SILVER,verts=8,group="pod")
    cyl(f"pod_piston_cap_{k}",.205,.105,(x,y,1.03),M_POD_SILVER,bevel=.025,group="pod")
    cyl(f"pod_piston_lamp_{k}",.158,.03,(x,y,1.093),M_POD_LIGHT,bevel=.012,group="pod")

# 宽实的六边形护沿和嵌入式双灯条，不再使用细铁丝状围栏。
rail_pts=circle(PX,PY,.23,2.48,n=6)
for k in range(6):
    p,q=Vector(rail_pts[k]),Vector(rail_pts[(k+1)%6])
    d=q-p
    c=(p+q)*.5
    angle=math.atan2(d.y,d.x)
    box(f"pod_guard_{k}",(d.length+.09,.26,.28),c,M_POD_SILVER,
        bevel=.07,rot=(0,0,angle),group="pod")
    box(f"pod_guard_gasket_{k}",(d.length-.07,.27,.032),(c.x,c.y,.115),M_METAL_D,
        bevel=.01,rot=(0,0,angle),group="pod")
    for j in (-1,1):
        v=c+d.normalized()*(j*.53)
        box(f"pod_guard_inset_{k}_{j}",(.48,.135,.018),(v.x,v.y,.375),M_POD_DARK,
            bevel=.018,rot=(0,0,angle),group="pod")
        box(f"pod_guard_light_{k}_{j}",(.38,.038,.014),(v.x,v.y,.388),M_POD_LIGHT,
            bevel=.006,rot=(0,0,angle),group="pod")

# 右前肩部斜置的小控制面板。
a=-math.pi/5
cx,cy=PX+1.99*math.cos(a),PY+1.99*math.sin(a)
box("pod_control_shell",(.55,.44,.20),(cx,cy,1.78),M_POD_SILVER,bevel=.065,rot=(0,.25,a),group="pod")
box("pod_control_face",(.38,.30,.025),(cx,cy,1.90),M_POD_DARK,bevel=.04,rot=(0,.25,a),group="pod")
torus("pod_control_symbol",.083,.015,(cx,cy,1.93),M_POD_LIGHT,rot=(0,.25,0),ms=24,mn=8,group="pod")

# 大舱在总览中要有前景的高度；仅拉高机壳，NONO 保持原本比例。
POD_HEIGHT_SCALE = 1.18
for part in objs_by_group['pod']:
    part.matrix_world = Matrix.Diagonal((1,1,POD_HEIGHT_SCALE,1)) @ part.matrix_world
# 放大舱内实例以匹配大罩；NONO 的共享几何保持 v7。
build_nono('nono0',(PX,PY,2.43*POD_HEIGHT_SCALE),scale=1.42,yaw=.40,bank=-.24,pitch=-.24)
META["animated"]["nono0"]={"x":PX,"y":PY,"z":2.43*POD_HEIGHT_SCALE}
collider(PX,PY,POD_FOOTPRINT)
light(PX,PY,2.35*POD_HEIGHT_SCALE,CYAN,22,6)

# ---------------------------------------------------------------- 全息投影底座（前中偏左）
HX, HY = -1.7, -3.3
cyl("holo_base", 0.75, 0.09, (HX,HY,0.045), M_METAL_D, verts=6, bevel=0.018, group="holo")
cyl("holo_base_top", 0.56, 0.015, (HX,HY,0.1), M_DARK, verts=6, group="holo")
torus("holo_base_glow", 0.43, 0.015, (HX,HY,0.115), M_GLOW_SOFT, group="holo")
HZ = 0.78
cyl("holo_beam", 0.46, 0.92, (HX,HY,0.57), M_BEAM, verts=32, r2=0.3, group="holo")
sph("holo_man_head", 0.12, (HX,HY,HZ+0.25), M_HOLO, group="holo")
cyl("holo_man_body", 0.14, 0.35, (HX,HY,HZ), M_HOLO, verts=16, r2=0.09, group="holo")
for k in range(3):
    torus(f"holo_scan_{k}", 0.28, 0.008, (HX,HY,0.4+k*0.24), M_GLOW_SOFT, group="holo")
META["animated"]["holo_icon"] = {"x": HX, "y": HY, "z": HZ}
collider(HX, HY, 0.8)
light(HX, HY, 1.3, CYAN, 12, 4)

# ---------------------------------------------------------------- 弧形大型设备（前右）
CX_, CY_ = 8.5, -2.7
# 竖直圆弧外壳：截面绕 Y 轴展开，内侧朝向房间中央。
def arch_segment(name, a0, a1, inner, outer, depth, m):
    verts=[]
    steps=10
    for y in (-depth/2,depth/2):
        for r in (inner,outer):
            for i in range(steps+1):
                a=math.radians(a0+(a1-a0)*i/steps)
                verts.append((CX_-r*math.cos(a),CY_+y,0.2+r*math.sin(a)))
    n=steps+1
    faces=[]
    for i in range(steps):
        for u,v in ((0,n),(2*n,3*n),(0,2*n),(n,3*n)):
            faces.append((u+i,u+i+1,v+i+1,v+i))
    faces += [(0,n,3*n,2*n),(n-1,2*n-1,4*n-1,3*n-1)]
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    o=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(o)
    _finish(o,name,m,0.045,"curve")
    # 网格顶点顺序统一，保证从房间内侧看也正确受光。
    bpy.context.view_layer.objects.active=o
    o.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    o.select_set(False)

for k in range(4):
    a0,a1=8+k*21,28+k*21
    arch_segment(f"curve_shell_{k}",a0,a1,2.5,3.25,2.1,M_BRUSHED)
    arch_segment(f"curve_seam_{k}",a1,a1+1,2.49,3.27,2.13,M_METAL_D)
    a=math.radians((a0+a1)/2)
    x,z=CX_-2.88*math.cos(a),0.2+2.88*math.sin(a)
    box(f"curve_panel_frame_{k}",(0.55,0.11,0.63),(x,CY_-1.10,z),M_METAL_D,bevel=0.04,rot=(0,a,0),group="curve")
    box(f"curve_panel_{k}",(0.38,0.03,0.44),(x,CY_-1.17,z),M_BLUE,bevel=0.025,rot=(0,a,0),group="curve")
    box(f"curve_panel_light_{k}",(0.28,0.02,0.055),(x,CY_-1.20,z+0.10),M_GLOW_SOFT,rot=(0,a,0),group="curve")
    cyl(f"curve_port_rim_{k}",0.22,0.12,(x,CY_+1.12,z),M_METAL_L,verts=32,rot=(math.pi/2,0,0),group="curve")
    cyl(f"curve_port_{k}",0.16,0.13,(x,CY_+1.19,z),M_BLUE,verts=32,rot=(math.pi/2,0,0),group="curve")
    px,pz=CX_-3.12*math.cos(a),0.2+3.12*math.sin(a)
    cyl(f"curve_front_rim_{k}",0.13,0.05,(px,CY_-1.11,pz),M_METAL_L,verts=32,rot=(math.pi/2,0,0),group="curve")
    cyl(f"curve_front_port_{k}",0.09,0.055,(px,CY_-1.15,pz),M_BLUE,verts=32,rot=(math.pi/2,0,0),group="curve")
box("curve_foot",(0.85,2.25,0.5),(5.65,CY_,0.25),M_METAL_D,bevel=0.1,group="curve")
for x in (6.2,7.3,8.2):
    collider(x,CY_,1.15)
light(6.4,CY_-1,1.5,CYAN,18,5)

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

TX_, TY_ = -4.1, 5.1
cyl("tall_base",0.82,0.28,(TX_,TY_,0.14),M_METAL_D,verts=48,group="machine")
cyl("tall_base_glow",0.68,0.16,(TX_,TY_,0.32),M_GLOW_SOFT,verts=48,group="machine")
cyl("tall_column",0.43,0.95,(TX_,TY_,0.88),M_METAL,verts=32,group="machine")
cyl("tall_head",0.47,1.25,(TX_,TY_,1.75),M_BRUSHED,verts=48,bevel=0.06,rot=(0,math.pi/2,0),group="machine")
for sx in (-1,1):
    cyl(f"tall_head_cap_{sx}",0.40,0.1,(TX_+sx*0.67,TY_,1.75),M_METAL_D,verts=32,rot=(0,math.pi/2,0),group="machine")
    box(f"tall_leg_{sx}",(0.22,0.5,0.8),(TX_+sx*0.55,TY_,0.7),M_METAL_D,rot=(0,sx*0.25,0),group="machine")
box("tall_status",(0.38,0.035,0.24),(TX_,TY_-0.45,0.94),M_GLOW_SOFT,group="machine")
collider(TX_,TY_,0.9)
light(SX_,SY_,2.2,CYAN,18,6)

# ---------------------------------------------------------------- 玻璃培养管（后右）
def containment_tube(idx, x, y, with_nono):
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
    box(f"tube{idx}_readout_frame",(0.62,0.12,0.25),(x,y-0.92,0.25),M_METAL,group="tube")
    box(f"tube{idx}_readout",(0.48,0.025,0.14),(x,y-0.99,0.27),M_BLUE,group="tube")
    for k in range(3):
        box(f"tube{idx}_readout_line{k}",(0.3-k*0.055,0.01,0.015),(x,y-1.01,0.23+k*0.045),M_GLOW_SOFT,group="tube")
    if with_nono:
        box(f"tube{idx}_console", (1.0, 0.55, 0.5), (x - 1.35, y - 1.05, 0.5), M_METAL_D, bevel=0.04, group="tube")
        box(f"tube{idx}_screen", (0.8, 0.04, 0.35), (x - 1.35, y - 1.31, 0.6), M_SCREEN, bevel=0, rot=(math.radians(-25), 0, 0), group="tube")
        build_nono('nono2', (x,y,1.65), scale=.95, pitch=-.24)
        META["animated"]["nono2"]={"x":x,"y":y,"z":1.65}
    else:
        cyl(f"claw{idx}_hub",0.25,0.45,(x,y,3.0),M_METAL_D,verts=24,group="tube")
        torus(f"claw{idx}_ring",0.27,0.025,(x,y,3.12),M_GLOW_SOFT,group="tube")
        for k in range(3):
            a=k*math.tau/3
            pts=[(x+0.23*math.cos(a),y+0.23*math.sin(a),3.05),
                 (x+0.49*math.cos(a),y+0.49*math.sin(a),2.65),
                 (x+0.39*math.cos(a),y+0.39*math.sin(a),2.2),
                 (x+0.17*math.cos(a),y+0.17*math.sin(a),2.02)]
            tube(f"claw{idx}_finger{k}",pts,0.085,M_BRUSHED,closed=False,group="tube")
        sph(f"claw{idx}_core",0.16,(x,y,2.48),M_BLUE,group="tube")
    collider(x, y, 1.0)


containment_tube(1, 4.7, 5.0, True)
containment_tube(2, 7.0, 4.9, False)
light(5.8, 4.8, 2.6, CYAN, 22, 7)

# ---------------------------------------------------------------- 中央悬浮 NONO
# 轻微侧倾复刻特写中左翼近水平、右翼上扬的投影。
build_nono('nono1', (-2.9,3.5,1.12), scale=.95, yaw=.18, bank=-.34, pitch=-.24)
META["animated"]["nono1"]={"x":-2.9,"y":3.5,"z":1.12}

# ---------------------------------------------------------------- 右侧墙边的小设备
# 左侧旧占位柜位于扩大的大舱检修区内，随区域 1 重建移除。
for sx in (1,):
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
