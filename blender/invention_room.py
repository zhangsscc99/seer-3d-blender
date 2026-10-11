"""发明室 I —— 在 Blender 里程序化建模，导出 GLB 与场景元数据，并可渲染预览图。

用法:
  Blender -b -P blender/invention_room.py -- --glb public/models/inv/invention_room.glb --render out.png
"""
import json
import math
import os
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


ROOT = os.getcwd()
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from nono import build_nono
GLB = arg("--glb")
BLEND = arg("--blend")
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


# 实心定制网格统一计算外向法线，供装甲、环带和地面盖板共用。
def solid(name, vertices, faces, material, bevel=.025, group="room"):
    mesh=bpy.data.meshes.new(name)
    mesh.from_pydata(vertices,[],faces)
    mesh.update()
    bm=bmesh.new(); bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(mesh); bm.free()
    o=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(o)
    return _finish(o,name,material,bevel,group)


def annulus(name,cx,cy,radius,width,z,height,material,group="room",a0=0,a1=math.tau):
    n=max(3,int((a1-a0)*20)); vertices=[]
    for i in range(n+1):
        a=a0+(a1-a0)*i/n
        for r,h in ((radius-width/2,z-height/2),(radius+width/2,z-height/2),
                    (radius+width/2,z+height/2),(radius-width/2,z+height/2)):
            vertices.append((cx+r*math.cos(a),cy+r*math.sin(a),h))
    faces=[(3,2,1,0),tuple(4*n+j for j in range(4))]
    for i in range(n):
        for j in range(4):faces.append((4*i+j,4*i+(j+1)%4,4*(i+1)+(j+1)%4,4*(i+1)+j))
    return solid(name,vertices,faces,material,.015,group)


def front_plate(name,outline,y,depth,material,group="machine",bevel=.025):
    # outline 为世界 XZ 多边形，沿 Y 挤出。
    n=len(outline)
    verts=[(x,y+d,z) for d in (-depth/2,depth/2) for x,z in outline]
    faces=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]
    faces.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
    return solid(name,verts,faces,material,bevel,group)


def floor_plate(name,outline,z,height,material,group="floor",bevel=.008):
    n=len(outline)
    verts=[(x,y,z+d) for d in (-height/2,height/2) for x,y in outline]
    faces=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]
    faces.extend((i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n))
    return solid(name,verts,faces,material,bevel,group)


# ---------------------------------------------------------------- 房间尺寸
RX, RY, RH = 9.0, 7.0, 5.0     # 半宽、半深、高

# 大块金属地板，细接缝；灯带嵌在深灰轨道里。
for i in range(6):
    for j in range(4):
        box(f"floor_tile_{i}_{j}", (2.984, 3.484, 0.12),
            (-7.5 + i * 3, -5.25 + j * 3.5, -0.06), M_FLOOR, bevel=0.006, group="floor")
box("floor_base", (18.2, 14.2, 0.1), (0, 0, -0.17), M_METAL_D, bevel=0, group="floor")
# 区域 6：圆形徽记与横向嵌入通道。
cyl("floor_disc",2.15,.026,(0,0,.014),M_METAL_D,verts=128,group="floor")
cyl("floor_disc_inner",1.94,.025,(0,0,.031),M_FLOOR_IN,verts=128,group="floor")
annulus("floor_disc_rim",0,0,2.06,.11,.049,.025,M_BRUSHED,"floor")
annulus("floor_emblem_border",0,0,1.69,.045,.05,.016,M_METAL_D,"floor")
# 上方暗色弧面和下方两条内收曲线构成原图的三瓣弧形标记。
def bezier2(p0,p1,p2,n=40):
    return [tuple((1-t)**2*p0[j]+2*(1-t)*t*p1[j]+t*t*p2[j] for j in range(2)) for t in [i/n for i in range(n+1)]]
top_y=.46
start=math.asin(top_y/1.66)
upper=[(1.66*math.cos(a),1.66*math.sin(a)) for a in [start+(math.pi-2*start)*i/60 for i in range(61)]]
upper+=bezier2((-1.66*math.cos(start),top_y),(0,.10),(1.66*math.cos(start),top_y))
floor_plate("floor_emblem_upper",upper,.054,.009,M_METAL_D)
for side in (-1,1):
    curve=bezier2((side*1.60,.36),(side*.58,-.12),(side*.61,-1.55))
    tube(f"floor_emblem_curve_{side}",[(x,y,.061) for x,y in curve],.025,M_METAL_D,closed=False,group="floor")
for side in (-1,1):
    cx=side*4.35
    box(f"floor_lane_{side}",(4.55,1.94,.026),(cx,0,.016),M_METAL_D,bevel=.08,group="floor")
    box(f"floor_lane_inner_{side}",(4.40,1.71,.020),(cx,0,.043),M_FLOOR_IN,bevel=.065,group="floor")
    for edge in (-1,1):
        box(f"track_edge_{side}_{edge}",(4.43,.043,.024),(cx,edge*.93,.056),M_BRUSHED,bevel=.007,group="floor")
        for k in range(9):
            x=side*(2.55+k*.42)
            box(f"track_light_{side}_{edge}_{k}",(.27,.025,.009),(x,edge*.86,.061),M_GLOW_SOFT,bevel=.004,group="floor")
    for k,x in enumerate((side*3.60,side*5.47)):
        shape=[(x-.47,-.74),(x-.57,-.47),(x-.57,.47),(x-.34,.75),
               (x+.42,.75),(x+.54,.47),(x+.54,-.47),(x+.30,-.74)]
        floor_plate(f"track_cover_groove_{side}_{k}",shape,.066,.019,M_METAL_D)
        inner=[(x+(xx-x)*.88,yy*.88) for xx,yy in shape]
        floor_plate(f"track_cover_{side}_{k}",inner,.083,.019,M_BRUSHED,bevel=.015)
        tube(f"track_cover_stamp_{side}_{k}",[(x-.18,-.48,.099),(x+.24,-.32,.099),(x+.24,.32,.099),(x-.18,.48,.099)],
             .012,M_METAL_L,closed=False,group="floor")
    for edge in (-1,1):
        for k in range(3):
            a=(.24+k*.085)*edge+(0 if side==1 else math.pi)
            cyl(f"floor_disc_light_{side}_{edge}_{k}",.043,.008,
                (2.04*math.cos(a),2.04*math.sin(a),.067),M_GLOW_SOFT,verts=16,group="floor")

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
# ---------------------------------------------------------------- 区域 5：厚框诊断终端，与两层深色台阶形成整组。
TY = RY - 1.4
box("terminal_backplate",(4.36,.22,4.42),(0,RY-.16,2.40),M_WALL,bevel=.12,group="terminal")
for side in (-1,1):
    box(f"terminal_back_reveal_{side}",(.12,.08,3.90),(side*2.03,RY-.30,2.48),M_BRUSHED,bevel=.02,group="terminal")
box("terminal_header",(4.56,.24,.18),(0,RY-.24,4.65),M_BRUSHED,bevel=.035,group="terminal")
box("platform_0",(4.6,2.5,.14),(0,TY,.07),M_METAL_D,bevel=.025,group="terminal")
box("platform_1",(4.0,1.95,.14),(0,TY+.25,.21),M_WALL_D,bevel=.025,group="terminal")
for side in (-1,1):
    # 外侧斜装甲仍在既有扶轨碰撞盒内。
    box(f"platform_rail_{side}",(.40,2.6,.30),(side*2.25,TY,.15),M_METAL_D,bevel=.05,group="terminal")
    box(f"platform_marker_{side}",(.18,.17,.014),(side*2.25,TY-1.12,.31),M_BRUSHED,bevel=.012,group="terminal")
for y,z,w in ((TY-1.25,.14,4.15),(TY-.725,.28,3.75)):
    box(f"platform_nosing_{z}",(w,.06,.028),(0,y+.02,z),M_BRUSHED,bevel=.008,group="terminal")
# 屏幕中心降低，外壳的厚圆角侧翼包住内侧深蓝面板。
SZ=2.57
box("screen_outer_housing",(3.75,.42,2.85),(0,RY-.46,SZ),M_BRUSHED,bevel=.19,group="terminal")
box("screen_dark_gasket",(3.39,.08,2.48),(0,RY-.71,SZ),M_METAL_D,bevel=.17,group="terminal")
box("screen_inner_rim",(3.20,.06,2.30),(0,RY-.77,SZ),M_BLUE,bevel=.13,group="terminal")
bpy.ops.mesh.primitive_plane_add(size=2,location=(0,RY-.815,SZ),rotation=(math.pi/2,0,0))
screen=bpy.context.active_object
screen.scale=(1.51,1.07,1)
_finish(screen,"screen_surface",M_SCREEN,0,"terminal")
for side in (-1,1):
    box(f"screen_side_mount_{side}",(.13,.30,1.28),(side*1.93,RY-.46,SZ),M_METAL_D,bevel=.055,group="terminal")
    for z in (SZ-.39,SZ+.39):
        box(f"screen_side_grip_{side}_{z}",(.16,.13,.27),(side*1.93,RY-.65,z),M_METAL_L,bevel=.03,group="terminal")
box("screen_top_light",(2.70,.06,.055),(0,RY-.695,SZ+1.40),M_GLOW_SOFT,bevel=.015,group="terminal")
box("screen_bottom_lip",(2.90,.24,.12),(0,RY-.70,1.12),M_METAL_L,bevel=.035,group="terminal")
# 紧接屏幕的矮控制台，保留原可行走台阶高度。
box("console_body",(2.90,.50,.48),(0,TY+.50,.53),M_METAL_D,bevel=.06,group="terminal")
box("console_status",(1.10,.10,.045),(0,TY+.28,.79),M_GLOW_SOFT,bevel=.015,group="terminal")
for k in range(4):
    box(f"console_vent_{k}",(2.5,.017,.026),(0,TY+.237,.36+k*.085),M_DARK,bevel=.008,group="terminal")
for x in (-3.9,-3.65):
    tube(f"pipe_back_vertical_{x}",[(x,6.6,5),(x,6.6,3.8),(x+.3,6.6,3.3),(x+.3,6.6,1)],
         .075,M_METAL_D,closed=False,group="wall")
collider(0,TY,2.4)
light(0,RY-2.2,2.6,CYAN,28,9)

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

# ---------------------------------------------------------------- 区域 4：分瓣投影底座与青色机器人投影
HX, HY = -2.35, -3.55
cyl("holo_base",.75,.12,(HX,HY,.06),M_METAL_D,verts=12,bevel=.035,group="holo")
for k in range(8):
    a=k*math.tau/8
    annulus(f"holo_base_petal_{k}",HX,HY,.58,.28,.20,.22,M_BRUSHED,"holo",a+.035,a+math.tau/8-.035)
    if k%2==0:
        box(f"holo_base_clamp_{k}",(.16,.23,.24),(HX+.70*math.cos(a),HY+.70*math.sin(a),.16),
            M_METAL_D,bevel=.025,rot=(0,0,a),group="holo")
cyl("holo_emitter",.45,.04,(HX,HY,.28),M_BLUE,verts=48,group="holo")
torus("holo_emitter_ring",.40,.02,(HX,HY,.307),M_GLOW_SOFT,group="holo")
cyl("holo_beam",.41,.94,(HX,HY,.79),M_BEAM,verts=48,r2=.21,group="holo")
HZ=.85
sph("holo_man_head",.175,(HX,HY,HZ+.27),M_HOLO,scale=(1,.84,1),group="holo")
sph("holo_man_visor",.13,(HX,HY-.108,HZ+.285),M_BEAM,scale=(1,.45,.55),group="holo")
cyl("holo_man_body",.13,.28,(HX,HY,HZ-.02),M_HOLO,verts=20,r2=.18,bevel=.025,group="holo")
for side in (-1,1):
    tube(f"holo_man_arm_{side}",[(HX+side*.17,HY,HZ+.08),(HX+side*.26,HY,HZ+(.19 if side==-1 else -.02)),
        (HX+side*.28,HY-.02,HZ+(.36 if side==-1 else -.13))],.046,M_HOLO,closed=False,group="holo")
    cyl(f"holo_man_leg_{side}",.056,.20,(HX+side*.085,HY,HZ-.24),M_HOLO,verts=16,group="holo")
    sph(f"holo_man_foot_{side}",.075,(HX+side*.09,HY-.035,HZ-.35),M_HOLO,scale=(.8,1.3,.5),group="holo")
for k in range(3):
    torus(f"holo_scan_{k}",.26,.006,(HX,HY,.47+k*.27),M_GLOW_SOFT,group="holo")
META["animated"]["holo_icon"]={"x":HX,"y":HY,"z":HZ}
collider(HX,HY,.80)
light(HX,HY,1.3,CYAN,12,4)

# ---------------------------------------------------------------- 区域 8：完整弧形设备，内部有实体机身而非空拱门。
CX_, CY_ = 8.65, -1.45

def curve_piece(name,a0,a1,inner,outer,depth,material,yoffset=0):
    steps=max(6,int((a1-a0)/3)); verts=[]
    for y in (-depth/2,depth/2):
        for r in (inner,outer):
            for i in range(steps+1):
                a=math.radians(a0+(a1-a0)*i/steps)
                verts.append((CX_-r*math.cos(a),CY_+y+yoffset,.14+1.30*r*math.sin(a)))
    n=steps+1
    faces=[]
    for i in range(steps):
        for u,v in ((0,n),(2*n,3*n),(0,2*n),(n,3*n)):
            faces.append((u+i,u+i+1,v+i+1,v+i))
    faces.extend([(0,n,3*n,2*n),(n-1,2*n-1,4*n-1,3*n-1)])
    return solid(name,verts,faces,material,.035,"curve")

# 中央机身使用很小但非零内径，配竖向背脊封闭；避免轴心退化三角面。
curve_piece("curve_solid_core",0,90,.09,2.86,2.32,M_METAL_D)
box("curve_backbone",(.32,2.35,3.77),(CX_-.02,CY_,1.98),M_BRUSHED,bevel=.10,group="curve")
box("curve_plinth",(3.05,2.53,.22),(CX_-1.36,CY_,.13),M_METAL_D,bevel=.09,group="curve")
for k in range(5):
    a0,a1=1+k*17.5,17.5+k*17.5
    curve_piece(f"curve_outer_armor_{k}",a0,a1,2.66,2.97,2.45,M_BRUSHED)
    curve_piece(f"curve_front_plate_{k}",a0+.8,a1-.8,.27,2.64,.16,M_METAL,yoffset=-1.24)
    curve_piece(f"curve_armor_gasket_{k}",a1,a1+.9,.24,2.97,.04,M_DARK,yoffset=-1.335)
for k,deg in enumerate((35,55,75)):
    a=math.radians(deg)
    x,z=CX_-2.57*math.cos(a),.14+1.30*2.57*math.sin(a)
    box(f"curve_panel_frame_{k}",(.47,.13,.55),(x,CY_-1.36,z),M_METAL_D,bevel=.045,rot=(0,-a*.7,0),group="curve")
    box(f"curve_panel_{k}",(.32,.035,.38),(x,CY_-1.445,z),M_BLUE,bevel=.035,rot=(0,-a*.7,0),group="curve")
    box(f"curve_panel_light_{k}",(.19,.018,.045),(x,CY_-1.472,z+.10),M_GLOW_SOFT,bevel=.01,rot=(0,-a*.7,0),group="curve")
# 实体机壳上的三只圆鼓形模块，深蓝嵌口和独立接缝。
for k,z in enumerate((.82,1.80,2.78)):
    x=CX_-.43
    cyl(f"curve_drum_mount_{k}",.49,.17,(x,CY_-1.38,z),M_METAL_D,rot=(math.pi/2,0,0),verts=48,bevel=.025,group="curve")
    sph(f"curve_drum_{k}",.445,(x,CY_-1.50,z),M_BRUSHED,scale=(1,.58,1),seg=48,group="curve")
    torus(f"curve_drum_seal_{k}",.40,.024,(x,CY_-1.53,z),M_METAL_D,rot=(math.pi/2,0,0),group="curve")
    cyl(f"curve_drum_insert_{k}",.16,.028,(x-.10,CY_-1.751,z+.06),M_BLUE,rot=(math.pi/2,0,0),verts=32,group="curve")
box("curve_lower_access",(.56,.11,.60),(6.65,CY_-1.36,1.01),M_BRUSHED,bevel=.06,rot=(0,-.35,0),group="curve")
box("curve_lower_access_blue",(.34,.025,.37),(6.65,CY_-1.43,1.01),M_BLUE,bevel=.025,rot=(0,-.35,0),group="curve")
for x in (6.85,8.0):collider(x,CY_,1.42)
light(6.4,CY_-1,1.5,CYAN,18,5)
# 原图右前独立小设备。
UX,UY=4.90,-3.60
cyl("utility_foot",.72,.13,(UX,UY,.065),M_BRUSHED,verts=64,bevel=.025,group="utility")
cyl("utility_base",.62,.22,(UX,UY,.23),M_METAL_D,verts=12,r2=.49,bevel=.03,group="utility")
for k in range(8):
    a=k*math.tau/8
    box(f"utility_base_readout_{k}",(.035,.18,.10),(UX+.56*math.cos(a),UY+.56*math.sin(a),.26),M_BLUE,
        bevel=.014,rot=(0,-.22,a),group="utility")
cyl("utility_neck",.30,.25,(UX,UY,.45),M_BRUSHED,verts=24,group="utility")
box("utility_head",(.61,.57,.54),(UX,UY,.80),M_METAL_D,bevel=.10,rot=(0,.15,-.15),group="utility")
box("utility_front_screen",(.34,.035,.30),(UX,UY-.30,.81),M_BLUE,bevel=.03,group="utility")
box("utility_top_lamp",(.17,.51,.05),(UX-.06,UY,1.09),M_GLOW_SOFT,bevel=.02,group="utility")
for side in (-1,1):
    box(f"utility_cheek_{side}",(.10,.44,.38),(UX+side*.32,UY,.83),M_BRUSHED,bevel=.045,group="utility")
collider(UX,UY,.76)

# ---------------------------------------------------------------- 区域 2：开口发光圆柱
SX_, SY_ = -5.8, 4.65
cyl("squat_foot",1.06,.15,(SX_,SY_,.075),M_METAL_D,verts=64,bevel=.025,group="machine")
cyl("squat_lower",.98,.93,(SX_,SY_,.60),M_METAL_D,verts=12,bevel=.035,group="machine")
for k in range(8):
    a=k*math.tau/8
    annulus(f"squat_armor_{k}",SX_,SY_,1.00,.10,.61,.78,M_BRUSHED,"machine",a+.035,a+math.tau/8-.035)
    if k in (4,7):
        box(f"squat_lower_lamp_{k}",(.045,.21,.26),
            (SX_+1.06*math.cos(a),SY_+1.06*math.sin(a),.46),M_GLOW_SOFT,
            rot=(0,.15,a),bevel=.025,group="machine")
annulus("squat_waist",SX_,SY_,.98,.12,1.08,.13,M_METAL_D,"machine")
cyl("squat_slot_recess",.86,.62,(SX_,SY_,1.44),M_DARK,verts=64,group="machine")
for k in range(16):
    a=k*math.tau/16
    box(f"squat_lamp_slot_{k}",(.08,.11,.38),(SX_+.872*math.cos(a),SY_+.872*math.sin(a),1.46),
        M_GLOW_SOFT,rot=(0,0,a),bevel=.018,group="machine")
for k in range(8):
    a=k*math.tau/8
    box(f"squat_upper_rib_{k}",(.13,.10,.75),(SX_+.97*math.cos(a),SY_+.97*math.sin(a),1.47),
        M_METAL_D,rot=(0,0,a),bevel=.025,group="machine")
annulus("squat_upper_shoulder",SX_,SY_,.93,.27,1.86,.27,M_BRUSHED,"machine")
annulus("squat_aperture_dark",SX_,SY_,.82,.12,2.02,.13,M_METAL_D,"machine")
torus("squat_aperture_light",.76,.055,(SX_,SY_,2.10),M_GLOW,group="machine")
cyl("squat_aperture_well",.73,.10,(SX_,SY_,1.86),M_BLUE,verts=64,group="machine")
box("squat_display_frame",(.70,.15,.48),(SX_,SY_-1.0,.67),M_METAL_D,bevel=.07,group="machine")
box("squat_display",(.56,.02,.34),(SX_,SY_-1.09,.67),M_BLUE,bevel=.035,group="machine")
for k in (-1,1):
    torus(f"squat_display_glyph_{k}",.088,.012,(SX_+k*.135,SY_-1.112,.69),M_GLOW_SOFT,rot=(math.pi/2,0,0),ms=24,mn=8,group="machine")
box("squat_display_readout",(.33,.012,.018),(SX_,SY_-1.114,.56),M_GLOW_SOFT,bevel=0,group="machine")
for dx in (-.26,.26):
    tube(f"squat_back_hose_{dx}",[(SX_+dx,SY_+.5,1.8),(SX_+dx,SY_+.9,2.35),
        (SX_+dx,SY_+1.4,2.65),(SX_+dx,SY_+1.75,2.65)],.075,M_METAL_D,closed=False,group="machine")
collider(SX_,SY_,1.12)
light(SX_,SY_,2.2,CYAN,18,6)

# ---------------------------------------------------------------- 区域 3：横筒机械单元
TX_, TY_ = -3.6, 5.05
cyl("tall_foot",1.08,.15,(TX_,TY_,.075),M_METAL_D,verts=12,bevel=.035,group="machine")
cyl("tall_reactor",1.02,1.12,(TX_,TY_,.68),M_METAL_D,verts=12,r2=.66,bevel=.04,group="machine")
for side in (-1,1):
    outline=[(TX_+side*.43,.20),(TX_+side*1.02,.22),(TX_+side*.83,1.12),(TX_+side*.52,1.27)]
    front_plate(f"tall_sloping_armor_{side}",outline,TY_-.40,.63,M_BRUSHED,bevel=.05)
    for j in range(3):
        box(f"tall_armor_light_{side}_{j}",(.035,.02,.045),
            (TX_+side*(.76-j*.06),TY_-.728,.43+j*.17),M_GLOW_SOFT,bevel=.008,group="machine")
front_plate("tall_front_lamp",[(TX_-.48,.19),(TX_+.48,.19),(TX_+.37,.44),(TX_-.37,.44)],
            TY_-.88,.07,M_GLOW_SOFT,bevel=.04)
cyl("tall_socket_collar",.34,.13,(TX_,TY_-.88,.82),M_BRUSHED,verts=48,rot=(math.pi/2,0,0),bevel=.025,group="machine")
cyl("tall_socket_center",.24,.15,(TX_,TY_-.96,.82),M_BLUE,verts=48,rot=(math.pi/2,0,0),group="machine")
torus("tall_socket_light",.18,.025,(TX_,TY_-1.05,.82),M_GLOW_SOFT,rot=(math.pi/2,0,0),group="machine")
box("tall_socket_bar",(.22,.025,.06),(TX_,TY_-1.08,.83),M_METAL_L,bevel=.01,group="machine")
cyl("tall_rotary_neck",.51,.22,(TX_,TY_,1.34),M_METAL,verts=48,bevel=.025,group="machine")
box("tall_head_cradle",(1.25,.69,.23),(TX_,TY_,1.53),M_METAL_D,bevel=.07,group="machine")
cyl("tall_head",.48,1.38,(TX_,TY_,2.02),M_BRUSHED,verts=64,bevel=.065,rot=(0,math.pi/2,0),group="machine")
for side in (-1,1):
    cyl(f"tall_head_cap_{side}",.41,.10,(TX_+side*.73,TY_,2.02),M_METAL_D,verts=48,rot=(0,math.pi/2,0),bevel=.025,group="machine")
    cyl(f"tall_head_pivot_{side}",.23,.16,(TX_+side*.82,TY_,2.02),M_BRUSHED,verts=32,rot=(0,math.pi/2,0),bevel=.025,group="machine")
box("tall_head_handle",(.76,.20,.09),(TX_,TY_,2.53),M_METAL_D,bevel=.035,group="machine")
box("tall_head_lower_accent",(.97,.035,.085),(TX_,TY_-.40,1.79),M_BLUE,bevel=.025,group="machine")
collider(TX_,TY_,1.15)

# ---------------------------------------------------------------- 区域 7：机械顶底座培养管，左管爪与 NONO 同舱。
def containment_tube(idx,x,y,with_nono):
    cyl(f"tube{idx}_foot",1.08,.15,(x,y,.075),M_BRUSHED,verts=64,bevel=.03,group="tube")
    cyl(f"tube{idx}_base",1.02,.32,(x,y,.31),M_METAL_D,verts=12,bevel=.04,group="tube")
    annulus(f"tube{idx}_lower_collar",x,y,.94,.18,.57,.20,M_BRUSHED,"tube")
    torus(f"tube{idx}_lower_light",.84,.022,(x,y,.68),M_GLOW_SOFT,group="tube")
    cyl(f"tube{idx}_inner_deck",.82,.035,(x,y,.58),M_BLUE,verts=64,group="tube")
    cyl(f"tube{idx}_glass_smooth",.86,3.62,(x,y,2.49),M_GLASS_T,verts=64,group="tube")
    annulus(f"tube{idx}_top_collar",x,y,.94,.18,4.36,.26,M_BRUSHED,"tube")
    cyl(f"tube{idx}_upper_housing",1.02,.38,(x,y,4.62),M_METAL_D,verts=12,bevel=.045,group="tube")
    cyl(f"tube{idx}_cap",1.06,.13,(x,y,4.87),M_BRUSHED,verts=64,bevel=.035,group="tube")
    torus(f"tube{idx}_top_light",.84,.022,(x,y,4.22),M_GLOW_SOFT,group="tube")
    # 承力结构移到后侧，让前方玻璃与内部装置完整可见。
    for side in (-1,1):
        box(f"tube{idx}_rear_spine_{side}",(.13,.18,3.73),(x+side*.73,y+.51,2.46),M_METAL_D,bevel=.035,group="tube")
        for z in (1.35,3.40):
            box(f"tube{idx}_spine_coupling_{side}_{z}",(.19,.23,.19),(x+side*.73,y+.51,z),M_BRUSHED,bevel=.025,group="tube")
    for k in range(10):
        a=k*math.tau/10
        box(f"tube{idx}_housing_inset_{k}",(.035,.11,.16),(x+1.023*math.cos(a),y+1.023*math.sin(a),4.62),
            M_BRUSHED,rot=(0,0,a),bevel=.014,group="tube")
    if with_nono:
        cyl(f"claw{idx}_suspension",.17,.49,(x,y,4.10),M_BRUSHED,verts=24,group="tube")
        cyl(f"claw{idx}_hub",.31,.43,(x,y,3.70),M_METAL_D,verts=8,bevel=.03,group="tube")
        torus(f"claw{idx}_ring",.30,.027,(x,y,3.83),M_GLOW_SOFT,group="tube")
        for k in range(3):
            a=-math.pi/2+k*math.tau/3
            pts=[(x+.28*math.cos(a),y+.28*math.sin(a),3.77),
                 (x+.58*math.cos(a),y+.58*math.sin(a),3.24),
                 (x+.43*math.cos(a),y+.43*math.sin(a),2.76),
                 (x+.21*math.cos(a),y+.21*math.sin(a),2.55)]
            tube(f"claw{idx}_finger_{k}",pts,.075,M_BRUSHED,closed=False,group="tube")
            sph(f"claw{idx}_joint_{k}",.12,pts[1],M_METAL_D,seg=20,group="tube")
        build_nono('nono2',(x,y,1.68),scale=.95,pitch=-.24)
        META["animated"]["nono2"]={"x":x,"y":y,"z":1.68}
        # 读数台位于正前方，屏幕完整呈现诊断纹理。
        box(f"tube{idx}_console",(.86,.55,.79),(x,y-1.18,.395),M_METAL_D,bevel=.05,group="tube")
        box(f"tube{idx}_console_top",(.90,.57,.12),(x,y-1.18,.82),M_BRUSHED,bevel=.04,group="tube")
        box(f"tube{idx}_console_screen",(.66,.027,.30),(x,y-1.468,.63),M_BLUE,bevel=.025,group="tube")
        for j in range(3):
            box(f"tube{idx}_console_line_{j}",(.42-j*.07,.012,.022),(x,y-1.49,.57+j*.058),M_GLOW_SOFT,bevel=.006,group="tube")
        collider(x,y-1.18,.55)
    else:
        # 右管在参考图中被设备遮挡，只补扫描层，不新增角色。
        for k,z in enumerate((1.33,2.15,3.02)):
            cyl(f"tube{idx}_scan_layer_{k}",.60,.016,(x,y,z),M_BEAM,verts=48,group="tube")
            torus(f"tube{idx}_scan_ring_{k}",.59,.012,(x,y,z),M_GLOW_SOFT,group="tube")
    collider(x,y,1.08)

containment_tube(1,4.70,5.00,True)
containment_tube(2,7.12,4.92,False)
light(5.8,4.8,2.6,CYAN,22,7)

# ---------------------------------------------------------------- 中央悬浮 NONO
# 轻微侧倾复刻特写中左翼近水平、右翼上扬的投影。
build_nono('nono1', (-2.40,3.15,1.12), scale=.95, yaw=.18, bank=-.34, pitch=-.24)
META["animated"]["nono1"]={"x":-2.40,"y":3.15,"z":1.12}

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
if BLEND:
    blend_path=os.path.join(ROOT,BLEND)
    os.makedirs(os.path.dirname(blend_path),exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend_path,compress=True)
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
