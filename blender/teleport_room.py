"""传送舱 I —— 纯程序化建模：圆形传送台、4 组传送终端、弧形后墙与放射地面。

用法:
  Blender -b -P blender/teleport_room.py -- --glb public/models/teleport/teleport_room.glb \
      --render renders/teleport_v1.png --samples 24 --campos 0,-7.4,5.4 --target 0,0.9,0.8 --lens 20
坐标：Blender z 向上，正面（参考相机方向）为 -Y。导入 Babylon 后 (x,y,z) -> (-x,z,-y)。
"""
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from power_reactor import material  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


GLB, RENDER, SAMPLES = arg('--glb'), arg('--render'), int(arg('--samples', '24'))

bpy.ops.wm.read_factory_settings(use_empty=True)
META = {'colliders': [], 'lights': [], 'animated': {}, 'walk': {}, 'spawn': {},
        'room': {}, 'pad': {}, 'terminals': [], 'portals': []}

# ================================================================ 材质
M = dict(
    silver=material('tp_silver', (.40, .42, .44), .34, .65, coat=.10),
    silver_bright=material('tp_trim_silver', (.44, .46, .48), .30, .55, coat=.08),
    silver_dark=material('tp_silver_dark', (.22, .25, .29), .42, .60),
    bluegray=material('tp_bluegray', (.28, .33, .40), .38, .55),
    bluegray_dark=material('tp_bluegray_dark', (.09, .12, .17), .44, .50),
    column=material('tp_column', (.42, .50, .62), .20, .25, coat=.40),
    navy=material('tp_navy', (.012, .026, .045), .40, .15),
    navy_glass=material('tp_navy_glass', (.02, .05, .09), .22, .10),
    lens=material('tp_lens', (.32, .37, .43), .34, .30, coat=.18),
    hub=material('tp_hub', (.28, .33, .40), .38, .32, coat=.10),
    visor=material('tp_visor', (.50, .50, .49), .38, .10, coat=.10),
    cream=material('tp_cream', (.58, .58, .56), .40, .10, coat=.20),
    cream_l=material('tp_cream_light', (.67, .67, .65), .36, .12, coat=.25),
    brass=material('tp_brass', (.42, .35, .15), .48, .50),
    black=material('tp_black', (.012, .015, .02), .68, 0.),
    cushion=material('tp_cushion', (.30, .16, .08), .70, 0.),
    glass=material('tp_glass', (.60, .75, .85), .07, 0.),
    etch=material('tp_etch', (.55, .63, .70), .30, .20, emit=(.62, .84, 1.), strength=.18),
    glow_cyan=material('tp_glow_cyan', (.02, .40, .55), .40, emit=(.55, .92, 1.), strength=1.4),
    glow_pill=material('tp_glow_pill', (.05, .60, .80), .40, emit=(.45, .88, 1.), strength=2.6),
    glow_green=material('tp_glow_green', (.05, .30, .12), .40, emit=(.50, 1., .80), strength=1.1),
    hazard=material('tp_hazard', (.50, .40, .10), .45, 0., image=HERE / 'tele_hazard.png'),
    ribs=material('tp_ribs', (.42, .43, .44), .55, .18, image=HERE / 'tele_ribs.png'),
    vent=material('tp_vent', (.10, .12, .16), .48, .60, image=HERE / 'tele_vent.png'),
    brushed=material('tp_brushed', (.60, .60, .60), .36, .55, image=HERE / 'tele_brushed.png'),
    starfield=material('tp_starfield', (.01, .02, .04), .40, 0., emit=(1., 1., 1.), strength=0.9,
                       image=HERE / 'tele_nebula.png'),
    chase=material('tp_chase', (.01, .05, .06), .40, 0., emit=(1., 1., 1.), strength=2.8,
                   image=HERE / 'tele_chase.png'),
    portal=material('tp_portal', (.01, .03, .05), .30, .20, emit=(1., 1., 1.), strength=3.0,
                    image=HERE / 'tele_ring.png'),
    diaphragm=material('tp_diaphragm', (.02, .05, .09), .30, .10, emit=(1., 1., 1.), strength=1.35,
                       image=HERE / 'tele_diaphragm.png'),
)
glass_bs = M['glass'].node_tree.nodes['Principled BSDF']
glass_bs.inputs['Alpha'].default_value = .42
glass_bs.inputs['Transmission Weight'].default_value = 0.
glass_bs.inputs['Coat Weight'].default_value = .65
glass_bs.inputs['Coat Roughness'].default_value = .06
M['glass'].surface_render_method = 'BLENDED'
glass_bs.inputs['Base Color'].default_value = (.012, .028, .050, 1)

objs = []


# ================================================================ 基础工具（沿用动力室）
def finish(o, mat, bevel=0., smooth=None):
    o.data.materials.append(mat)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    o.select_set(False)
    for p in getattr(o.data, 'polygons', ()):
        p.use_smooth = bevel > 0 if smooth is None else smooth
    if bevel:
        b = o.modifiers.new('bevel', 'BEVEL')
        b.width, b.segments, b.limit_method = bevel, 3, 'ANGLE'
        o.modifiers.new('wn', 'WEIGHTED_NORMAL').keep_sharp = True
    objs.append(o)
    return o


def box(name, size, loc, mat, bevel=.03, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale, o.name = size, name
    return finish(o, mat, bevel)


def cyl(name, r, h, loc, mat, rot=(0, 0, 0), verts=48, bevel=0., smooth=True, scale=(1, 1)):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = (scale[0], scale[1], 1)
    return finish(o, mat, bevel, smooth)


def cone(name, r1, r2, h, loc, mat, rot=(0, 0, 0), verts=32, scale=(1, 1)):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=h, vertices=verts, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = (scale[0], scale[1], 1)
    return finish(o, mat, 0, True)


def lathe(name, profile, c, mat, verts=48, scale=(1, 1), bevel=0., yaw=0.):
    """竖直旋转体：profile 为 [(z, r), ...]（自下而上），两端封口。

    scale/yaw 可把横截面压成任意朝向的椭圆（立柱用切向宽、径向窄）。
    """
    ca, sa = math.cos(yaw), math.sin(yaw)
    vv, faces = [], []
    for z, r in profile:
        for i in range(verts):
            a = 2 * math.pi * i / verts
            lx, ly = r * scale[0] * math.cos(a), r * scale[1] * math.sin(a)
            vv.append((c[0] + lx * ca - ly * sa, c[1] + lx * sa + ly * ca, z))
    n = len(profile)
    for k in range(n - 1):
        for i in range(verts):
            i2 = (i + 1) % verts
            faces.append((k * verts + i, k * verts + i2, (k + 1) * verts + i2, (k + 1) * verts + i))
    faces.append(tuple(reversed(range(verts))))
    faces.append(tuple((n - 1) * verts + i for i in range(verts)))
    me = bpy.data.meshes.new(name)
    me.from_pydata(vv, [], faces)
    me.validate()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    return finish(o, mat, bevel, True)


def plane(name, size, loc, mat, rot=(0, 0, 0), uv=1.):
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale, o.name = (size[0], size[1], 1), name
    for d in o.data.uv_layers.active.data:
        d.uv = (d.uv[0] * uv * size[0] / 2, d.uv[1] * uv * size[1] / 2)
    return finish(o, mat, 0, False)


def uv_disc(name, r, loc, mat, rot=(0, 0, 0), segs=96):
    """平面圆盘，UV 为整圆径向映射，避免圆柱端盖默认 UV 只采样贴图一角。"""
    verts, faces, uvs = [(0., 0., 0.)], [], [(.5, .5)]
    for i in range(segs):
        a = 2 * math.pi * i / segs
        verts.append((r * math.cos(a), r * math.sin(a), 0.))
        uvs.append((.5 + .5 * math.cos(a), .5 + .5 * math.sin(a)))
    for i in range(segs):
        faces.append((0, 1 + i, 1 + (i + 1) % segs))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    layer = me.uv_layers.new(name='UVMap')
    for poly in me.polygons:
        for li in poly.loop_indices:
            layer.data[li].uv = uvs[me.loops[li].vertex_index]
    o.location, o.rotation_euler = loc, rot
    return finish(o, mat, 0, False)


def torus(name, R, r, loc, mat, rot=(0, 0, 0), scale=(1, 1), major=48, minor=12):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=major,
                                     minor_segments=minor, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = (scale[0], scale[1], 1)
    return finish(o, mat, 0, True)


def disc(name, r, h, loc, mat, scale=(1, 1), verts=64, bevel=0.):
    return cyl(name, r, h, loc, mat, verts=verts, bevel=bevel, scale=scale)


def dome(name, r, h, c, mat, segs=72, rings=18):
    """半球冠：底圈半径 r、底高 c[2]，顶点高 h；法线朝外，平滑着色。"""
    verts, faces = [], []
    for j in range(1, rings):
        phi = (math.pi / 2) * j / rings
        rr, zz = r * math.cos(phi), h * math.sin(phi)
        for i in range(segs):
            a = 2 * math.pi * i / segs
            verts.append((c[0] + rr * math.cos(a), c[1] + rr * math.sin(a), c[2] + zz))
    pole = len(verts)
    verts.append((c[0], c[1], c[2] + h))
    base = len(verts)
    for i in range(segs):
        a = 2 * math.pi * i / segs
        verts.append((c[0] + r * math.cos(a), c[1] + r * math.sin(a), c[2]))
    for i in range(segs):
        i2 = (i + 1) % segs
        faces.append((base + i, base + i2, i2, i))
    for k in range(rings - 2):
        o0, o1 = k * segs, (k + 1) * segs
        for i in range(segs):
            i2 = (i + 1) % segs
            faces.append((o0 + i, o0 + i2, o1 + i2, o1 + i))
    o0 = (rings - 2) * segs
    for i in range(segs):
        i2 = (i + 1) % segs
        faces.append((o0 + i, o0 + i2, pole))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    return finish(o, mat, 0, True)


def dome_spoke(name, a, r0, r1, w, c, r_dome, h, mat, seg=12):
    """贴着球冠表面的弧形扁条（用作传送台辐条）。"""
    verts, faces = [], []
    ca, sa = math.cos(a), math.sin(a)
    px, py = -sa, ca
    for i in range(seg + 1):
        rr = r0 + (r1 - r0) * i / seg
        z = c[2] + h * math.sqrt(max(0., 1 - (rr / r_dome) ** 2)) + .01
        for sw in (-1, 1):
            verts.append((c[0] + rr * ca + px * w * sw, c[1] + rr * sa + py * w * sw, z))
    for i in range(seg):
        q = i * 2
        faces.append((q, q + 3, q + 2, q + 1))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    return finish(o, mat, 0, True)


def arc_solid(name, c, r0, r1, a0, a1, z0, z1, mat, n=28, bevel=.02, uv=None):
    """扇形实体；uv=(u_scale, v_scale) 时按角度/半径写入 UV，便于贴图。"""
    verts, faces = [], []
    for i in range(n + 1):
        a = a0 + (a1 - a0) * i / n
        ca, sa = math.cos(a), math.sin(a)
        for r, z in ((r0, z0), (r1, z0), (r1, z1), (r0, z1)):
            verts.append((c[0] + r * ca, c[1] + r * sa, z))
    for i in range(n):
        for k in range(4):
            q = (k + 1) % 4
            faces.append((i * 4 + k, i * 4 + q, (i + 1) * 4 + q, (i + 1) * 4 + k))
    faces += [(0, 3, 2, 1), (n * 4, n * 4 + 1, n * 4 + 2, n * 4 + 3)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    if uv:
        layer = me.uv_layers.new(name='UVMap')
        for poly in me.polygons:
            for li in poly.loop_indices:
                co = me.vertices[me.loops[li].vertex_index].co
                ang = math.atan2(co.y - c[1], co.x - c[0])
                while ang < a0 - 1e-6:
                    ang += 2 * math.pi
                while ang > a0 + 2 * math.pi:
                    ang -= 2 * math.pi
                rr = math.hypot(co.x - c[0], co.y - c[1])
                u = (ang - a0) / max(1e-6, a1 - a0)
                v = (rr - r0) / max(1e-6, r1 - r0)
                layer.data[li].uv = (u * uv[0], v * uv[1])
    return finish(o, mat, bevel, True)


def ellipse_ring(name, c, rx0, ry0, rx1, ry1, z0, z1, mat, n=64, bevel=.01):
    """椭圆环形实体（用于传送台下沉边），中间留孔避免遮住星云。"""
    verts = []
    for z in (z0, z1):
        for rx, ry in ((rx0, ry0), (rx1, ry1)):
            for i in range(n):
                a = 2 * math.pi * i / n
                verts.append((c[0] + rx * math.cos(a), c[1] + ry * math.sin(a), z))

    def idx(z, ring, i):
        return (z * 2 + ring) * n + (i % n)

    faces = []
    for i in range(n):
        faces.append((idx(0, 0, i), idx(0, 0, i + 1), idx(1, 0, i + 1), idx(1, 0, i)))
        faces.append((idx(1, 1, i), idx(1, 1, i + 1), idx(0, 1, i + 1), idx(0, 1, i)))
        faces.append((idx(1, 0, i), idx(1, 0, i + 1), idx(1, 1, i + 1), idx(1, 1, i)))
        faces.append((idx(0, 1, i), idx(0, 1, i + 1), idx(0, 0, i + 1), idx(0, 0, i)))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    return finish(o, mat, bevel, True)


def light(p, color, power, rng):
    META['lights'].append({'x': p[0], 'y': p[1], 'z': p[2], 'color': list(color),
                           'power': power, 'range': rng})


def collider(x, y, r):
    META['colliders'].append({'x': x, 'y': y, 'r': r})


# ================================================================ 布局常量
ROOM_C = (0.0, 0.4)
WALL_R0, WALL_R1, WALL_H = 6.25, 6.55, 8.0
WALK_R = 5.9
PAD_C, PAD_R = (0.0, 0.5), 2.3
TERM_R = 5.0
TERM_DEFS = [
    (36.75, 'power', '动力室 I'),
    (63.25, 'invention', '发明室 I'),
    (89.75, 'station', '赛尔号空间站'),
    (116.25, 'kelosi', '克洛斯星'),
]
COL_ANGS = [23.5, 50.0, 76.5, 103.0, 129.5]
CONSOLE_ANG = 172.0


def polar(r, a, c=ROOM_C):
    return (c[0] + r * math.cos(math.radians(a)), c[1] + r * math.sin(math.radians(a)))


def place(center, yaw, lx, ly, z):
    c, s = math.cos(yaw), math.sin(yaw)
    return (center[0] + lx * c - ly * s, center[1] + lx * s + ly * c, z)


def lbox(name, center, yaw, lx, ly, z, size, mat, bevel=.03, rz=0.):
    return box(name, size, place(center, yaw, lx, ly, z), mat, bevel, rot=(0, 0, yaw + rz))


def lcyl(name, center, yaw, lx, ly, z, r, h, mat, verts=40, bevel=0., scale=(1, 1)):
    return cyl(name, r, h, place(center, yaw, lx, ly, z), mat, rot=(math.pi / 2, 0, yaw),
               verts=verts, bevel=bevel, scale=scale)


def ltorus(name, center, yaw, lx, ly, z, R, r, mat, scale=(1, 1), major=48, minor=12):
    return torus(name, R, r, place(center, yaw, lx, ly, z), mat,
                 rot=(math.pi / 2, 0, yaw), scale=scale, major=major, minor=minor)


def lplane(name, center, yaw, lx, ly, z, size, mat, uv=1.):
    return plane(name, size, place(center, yaw, lx, ly, z), mat, rot=(math.pi / 2, 0, yaw), uv=uv)


def trap(name, center, yaw, lx, ly, z, top_w, bot_w, h, depth, mat, bevel=.02, tilt=0., smooth=False):
    """上宽下窄的梯形面板（参考图终端顶罩的盾形轮廓）。"""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= top_w if v.co.z > 0 else bot_w
        v.co.y *= depth
        v.co.z *= h
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    o.location = place(center, yaw, lx, ly, z)
    o.rotation_euler = (tilt, 0, yaw)
    return finish(o, mat, bevel, smooth)


# ================================================================ 地面
# 中间留出传送台井口，避免遮住星云底盘。
arc_solid('floor_base', ROOM_C, 2.36, 6.55, 0, 2 * math.pi, -.22, 0,
          M['silver_dark'], n=96, bevel=0)
arc_solid('floor_under', ROOM_C, 2.36, 6.3, 0, 2 * math.pi, -.03, .04,
          M['bluegray_dark'], n=96, bevel=0)

# 12 块放射地板，板间留 2° 缝。
for i in range(12):
    a0 = math.radians(i * 30 + 2.1)
    a1 = math.radians((i + 1) * 30 - 2.1)
    arc_solid(f'floor_plate_{i:02d}', ROOM_C, 3.30, 6.2, a0, a1, .02, .10,
              M['brushed'], n=10, bevel=.018, uv=(1.6, 1.2))

# 放射格栅条 + 每个扇区一条短横向格栅，形成风车/分叉感（加宽成真正的凹槽状格栅）。
for i in range(12):
    a = math.radians(i * 30 + 3.0)
    mid = polar(4.75, i * 30 + 3.0)
    yaw = a + math.pi / 2
    plane(f'floor_vent_{i:02d}', (.46, 2.45), (mid[0], mid[1], .112), M['ribs'],
          rot=(0, 0, yaw), uv=1.05)
    am = math.radians(i * 30 + 15)
    tm = polar(5.55, i * 30 + 15)
    plane(f'floor_vent_cross_{i:02d}', (1.55, .42), (tm[0], tm[1], .114), M['ribs'],
          rot=(0, 0, am), uv=1.1)

# 后墙脚金色弧线。
arc_solid('floor_trim_back', ROOM_C, 6.02, 6.22, math.radians(28), math.radians(152), .06, .13,
          M['brass'], n=40, bevel=.012)
arc_solid('floor_track_outer', ROOM_C, 6.18, 6.34, math.radians(-30), math.radians(210), .04, .14,
          M['silver_dark'], n=80, bevel=.01)
# ================================================================ 中央传送台
# 椭圆下沉区（环形体，中间是玻璃井）。
ellipse_ring('pad_recess', PAD_C, 2.34, 2.34, 3.10, 3.10, .03, .07, M['navy'], n=72, bevel=.015)
ellipse_ring('pad_recess_rim', PAD_C, 3.04, 3.04, 3.18, 3.18, .05, .10, M['silver_dark'], n=72, bevel=.01)
# 井壁（圆管，无顶盖）与星云底盘。
arc_solid('pad_well', PAD_C, 2.30, 2.36, 0, 2 * math.pi, -.39, .10,
          M['bluegray_dark'], n=72, bevel=0)
disc('pad_starfield', 2.31, .02, (PAD_C[0], PAD_C[1], -.10), M['starfield'], verts=72)
# 宽黄铜环 + 细银边（参考图黄铜环约占半径的 1/3）。
arc_solid('pad_brass_band', PAD_C, 2.34, 3.02, 0, 2 * math.pi, .03, .11,
          M['brass'], n=96, bevel=.02)
torus('pad_glass_rim', 2.345, .024, (PAD_C[0], PAD_C[1], .085), M['silver'], major=96, minor=8)
# 黄铜环的放射分缝与螺栓（参考图为大块黄铜板拼成，16 条缝）。
for k in range(16):
    a = math.radians(k * 22.5 + 3)
    box(f'pad_brass_seam_{k:02d}', (.70, .016, .004),
        (PAD_C[0] + math.cos(a) * 2.70, PAD_C[1] + math.sin(a) * 2.70, .113),
        M['silver_dark'], bevel=.002, rot=(0, 0, a))
for k in range(24):
    a = k * math.pi / 12
    cyl(f'pad_bolt_{k:02d}', .026, .022,
        (PAD_C[0] + math.cos(a) * 2.955, PAD_C[1] + math.sin(a) * 2.955, .112),
        M['silver'], verts=12)
# 微拱玻璃罩（参考图中玻璃盘是浅穹顶）。
DOME_R, DOME_H, DOME_Z = 2.33, .10, .095
dome('pad_glass', DOME_R, DOME_H, (PAD_C[0], PAD_C[1], DOME_Z), M['glass'], segs=72, rings=18)


def dz(r):
    return DOME_Z + DOME_H * math.sqrt(max(0., 1 - (r / DOME_R) ** 2))


# 贴着拱面的细辐条与同心环（参考图中是极细的白色刻线，8 根辐条即可）。
for k in range(8):
    a = k * math.pi / 4
    dome_spoke(f'pad_spoke_{k}', a, .24, 1.72, .005, (PAD_C[0], PAD_C[1], DOME_Z),
               DOME_R, DOME_H, M['etch'])
for k, rr in enumerate((.32, .55, .78, 1.02, 1.30, 1.58)):
    torus(f'pad_ring_etch_{k}', rr, .0028, (PAD_C[0], PAD_C[1], dz(rr) + .009),
          M['etch'], major=48 + k * 8, minor=6)
# 跑灯环 + 32 段青色小灯（沿玻璃边缘）。
torus('pad_chase', 2.20, .024, (PAD_C[0], PAD_C[1], dz(2.20) + .008), M['chase'], major=96, minor=10)
for k in range(32):
    a = k * math.pi / 16
    box(f'pad_seg_{k:02d}', (.055, .020, .012),
        (PAD_C[0] + math.cos(a) * 2.265, PAD_C[1] + math.sin(a) * 2.265, dz(2.265) + .008),
        M['glow_cyan'], bevel=.004, rot=(0, 0, a + math.pi / 2))
light((PAD_C[0], PAD_C[1], .62), (1., .70, .40), 1.6, 3.4)


# ================================================================ 后墙终端
def build_terminal(idx, ang, scene_id, label):
    a = math.radians(ang)
    c = polar(TERM_R, ang)
    yaw = a - math.pi / 2  # 本地 -Y 朝向房间中心
    p = f'term_{idx}'
    TILT = -0.12  # 顶罩略向后倾，保持参考图里接近竖直的盾面
    # 白色圆角柜体与主壳；顶罩上方仍是白色壳体，不是黑盒。
    lbox(f'{p}_cabinet', c, yaw, 0, .02, .40, (2.26, .86, .80), M['cream'], .10)
    lbox(f'{p}_base_trim', c, yaw, 0, -.44, .035, (2.10, .10, .06), M['silver_dark'], .015)
    lbox(f'{p}_shell', c, yaw, 0, .10, 1.62, (2.16, .72, 1.86), M['cream_l'], .12)
    lbox(f'{p}_shell_top', c, yaw, 0, .10, 3.065, (2.26, .72, 1.03), M['cream_l'], .10)
    lbox(f'{p}_front_plate', c, yaw, 0, -.30, 1.56, (2.12, .10, 1.64), M['cream'], .10)
    # 圆环装置：黑色凹槽面板 + 外银圈 + 分段青光带 + 宽亮内环 + 蓝灰中心帽。
    RZ = 1.15
    # 参考图的环安装在黑色圆形凹槽里，而不是方形面板；环占柜宽约 3/4。
    lcyl(f'{p}_recess_panel', c, yaw, 0, -.375, RZ, 1.02, .05, M['black'], verts=64)
    lcyl(f'{p}_backing', c, yaw, 0, -.395, RZ, .94, .04, M['navy'], verts=64)
    ltorus(f'{p}_ring_seam', c, yaw, 0, -.465, RZ, .945, .007, M['silver_dark'], major=64, minor=8)
    ltorus(f'{p}_ring_outer', c, yaw, 0, -.47, RZ, .875, .055, M['silver_bright'], major=72, minor=16)
    ltorus(f'{p}_ring_glow', c, yaw, 0, -.492, RZ, .838, .012, M['glow_cyan'], major=72, minor=8)
    uv_disc(f'{p}_portal', .820, place(c, yaw, 0, -.455, RZ), M['diaphragm'],
            rot=(math.pi / 2, 0, yaw))
    # 中心大金属帽：参考图里灰蓝圆帽约占环半径的一半，只在正中有更暗的内圆。
    ltorus(f'{p}_ring_mid', c, yaw, 0, -.472, RZ, .520, .020, M['silver_dark'], major=56, minor=10)
    lcyl(f'{p}_lens', c, yaw, 0, -.478, RZ, .465, .05, M['lens'], verts=64, bevel=.020)
    ltorus(f'{p}_lens_seam', c, yaw, 0, -.503, RZ, .468, .008, M['navy'], major=56, minor=8)
    # 帽面上两圈细刻线，避免大面积纯灰。
    for k, rr in enumerate((.405, .318)):
        ltorus(f'{p}_lens_ring_{k}', c, yaw, 0, -.505, RZ, rr, .0035, M['silver_dark'],
               major=64, minor=6)
    lcyl(f'{p}_hub_center', c, yaw, 0, -.506, RZ, .205, .012, M['hub'], verts=48, bevel=.01)
    # 环下沿的一圈点状灯（沿圆弧排列，而不是横贯柜体的直条）。
    for k in range(13):
        aa = math.radians(205 + k * 11)
        lbox(f'{p}_led_{k:02d}', c, yaw, math.cos(aa) * .972, -.402, RZ + math.sin(aa) * .972,
             (.050, .012, .019), M['glow_cyan'], .004)
    # 黑檐 + 黄黑警示条 + 绿色指示灯；参考图黑檐是顶罩下缘的窄带。
    trap(f'{p}_brow', c, yaw, 0, -.44, 2.38, 1.92, 1.74, .50, .14, M['black'], .035)
    lplane(f'{p}_hazard', c, yaw, 0, -.515, 2.30, (1.66, .29), M['hazard'], uv=.83)
    lcyl(f'{p}_indicator_ring', c, yaw, 0, -.515, 2.56, .078, .03, M['silver_dark'], verts=24)
    lcyl(f'{p}_indicator', c, yaw, 0, -.532, 2.56, .060, .028, M['glow_green'], verts=20)
    # 顶罩：上宽下窄的盾形黑框 + 银框 + 浅白视窗，贴合参考图轮廓。
    trap(f'{p}_visor_outline', c, yaw, 0, -.34, 3.04, 2.14, 1.72, 1.00, .030,
         M['black'], .022, tilt=TILT)
    trap(f'{p}_visor_frame', c, yaw, 0, -.42, 3.04, 2.04, 1.64, .90, .025,
         M['silver_bright'], .022, tilt=TILT)
    trap(f'{p}_visor', c, yaw, 0, -.44, 3.04, 1.90, 1.52, .78, .020,
         M['cream_l'], .016, tilt=TILT)
    # 白面板下部的浅折线，模拟参考图顶罩的曲面转折。
    lbox(f'{p}_visor_seam', c, yaw, 0, -.452, 2.80, (1.55, .006, .012), M['silver_dark'], .003)
    # 两侧暗银窄缝与底部检修面板。
    for s in (-1, 1):
        lbox(f'{p}_side_{s}', c, yaw, s * 1.03, -.16, 1.45, (.04, .12, 1.50), M['silver_dark'], .01)
        lbox(f'{p}_side_foot_{s}', c, yaw, s * .975, -.22, .38, (.12, .22, .18), M['bluegray_dark'], .02)
    lbox(f'{p}_chin', c, yaw, 0, -.35, .30, (1.58, .06, .18), M['cream'], .03)
    lbox(f'{p}_service_groove', c, yaw, 0, -.385, .13, (.78, .04, .18), M['bluegray_dark'], .015)
    lbox(f'{p}_service', c, yaw, 0, -.40, .13, (.70, .04, .16), M['cream_l'], .015)
    for s in (-1, 1):
        lcyl(f'{p}_screw{s}', c, yaw, s * .25, -.423, .13, .016, .015, M['silver_dark'], verts=12)
    # 元数据。
    ix, iy = polar(3.3, ang)
    collider(c[0], c[1], 1.18)
    META['terminals'].append({'x': c[0], 'y': c[1], 'ix': ix, 'iy': iy, 'r': 1.4,
                              'scene': scene_id, 'label': label})
    META['portals'].append({'x': c[0], 'y': c[1], 'z': 1.15, 'r': .70})
    light(place(c, yaw, 0, -1.0, 1.70), (.45, .84, 1.), 1.2, 2.6)


for i, (ang, scene_id, label) in enumerate(TERM_DEFS):
    build_terminal(i, ang, scene_id, label)

# ================================================================ 立柱
for i, ang in enumerate(COL_ANGS):
    a = math.radians(ang)
    c = polar(TERM_R + .15, ang)
    yaw = a - math.pi / 2
    p = f'col_{i}'
    # 下鼓、中部收腰、上部再外扩的鳍柱；腰部比早期版本更粗，避免像细花瓶。
    prof = [(.02, .38), (.10, .54), (.30, .66), (.60, .62), (.95, .52),
            (1.30, .44), (1.80, .38), (2.40, .345), (3.10, .36),
            (3.80, .42), (4.70, .52), (5.70, .64), (6.70, .80),
            (7.55, .94), (7.98, 1.0)]
    lathe(f'{p}_body', prof, c, M['column'], verts=48, scale=(.95, 1.), yaw=yaw)
    # 横向分模线与底脚。
    for k, (z, rr) in enumerate(((1.04, .50), (2.38, .345), (5.20, .58))):
        torus(f'{p}_seam_{k}', rr + .006, .014, (c[0], c[1], z), M['silver_dark'],
              scale=(.95, 1.), major=48, minor=8)
    lbox(f'{p}_plinth', c, yaw, 0, 0, .025, (.98, .84, .05), M['bluegray_dark'], .02)
    # 正面青色胶囊灯（参考图位于立柱下段），贴合加粗后的柱面。
    lbox(f'{p}_light_frame', c, yaw, 0, -.465, 1.15, (.36, .05, .76), M['silver_dark'], .016)
    lbox(f'{p}_light', c, yaw, 0, -.495, 1.15, (.29, .04, .64), M['glow_pill'], .022)
    collider(c[0], c[1], .45)
    light(place(c, yaw, 0, -.60, 1.25), (.30, .78, 1.), .55, 2.0)

# ================================================================ 左侧墙内座位舱
CONSOLE_C = polar(5.80, CONSOLE_ANG)
CON_YAW = math.atan2(ROOM_C[0] - CONSOLE_C[0], -(ROOM_C[1] - CONSOLE_C[1]))
cp = 'left_console'
# 贴墙的白色内凹座位舱：底板 + 背板 + 两侧壁 + 顶棚。
lbox(f'{cp}_plinth', CONSOLE_C, CON_YAW, 0, .08, .07, (2.10, 1.25, .14), M['silver_dark'], .03)
lbox(f'{cp}_back', CONSOLE_C, CON_YAW, 0, .52, 1.45, (1.92, .22, 2.90), M['cream'], .10)
for s in (-1, 1):
    lbox(f'{cp}_wall_{s}', CONSOLE_C, CON_YAW, s * .88, .10, 1.45, (.34, 1.06, 2.90), M['cream_l'], .14)
    lbox(f'{cp}_arm_top_{s}', CONSOLE_C, CON_YAW, s * .88, .02, 2.40, (.42, 1.12, .20), M['cream'], .08)
lbox(f'{cp}_canopy', CONSOLE_C, CON_YAW, 0, .08, 2.88, (2.12, 1.26, .26), M['cream_l'], .07)
lbox(f'{cp}_canopy_trim', CONSOLE_C, CON_YAW, 0, -.56, 2.82, (2.12, .06, .08), M['silver'], .015)
# 座垫与棕色地垫。
lbox(f'{cp}_bench', CONSOLE_C, CON_YAW, 0, .18, .34, (1.32, .72, .34), M['cream'], .05)
lbox(f'{cp}_cushion', CONSOLE_C, CON_YAW, 0, .18, .535, (1.18, .62, .08), M['cushion'], .03)
lbox(f'{cp}_mat', CONSOLE_C, CON_YAW, 0, -.18, .16, (1.30, .58, .035), M['cushion'], .01)
lbox(f'{cp}_backrest', CONSOLE_C, CON_YAW, 0, .36, .74, (1.22, .14, .46), M['cream'], .05)
# 舱内后面的通风格栅（蓝光）。
lbox(f'{cp}_vent_frame', CONSOLE_C, CON_YAW, 0, .405, 1.82, (.92, .06, .84), M['silver_dark'], .014)
lplane(f'{cp}_vent', CONSOLE_C, CON_YAW, 0, .368, 1.82, (.80, .72), M['vent'], uv=1.2)
# 左侧壁内的小控制面板。
lbox(f'{cp}_panel', CONSOLE_C, CON_YAW, -.70, .02, 1.02, (.24, .30, .34), M['cream_l'], .03)
lplane(f'{cp}_panel_face', CONSOLE_C, CON_YAW, -.70, -.14, 1.02, (.17, .22), M['navy'], uv=1.)
# 舱壁分缝。
for s in (-1, 1):
    lbox(f'{cp}_seam_{s}', CONSOLE_C, CON_YAW, s * 1.05, .28, .62, (.035, .05, 1.16), M['silver_dark'], .008)
collider(CONSOLE_C[0], CONSOLE_C[1] - .10, 1.05)
light(place(CONSOLE_C, CON_YAW, 0, -.35, 1.80), (.40, .66, 1.), .8, 2.2)

# ================================================================ 墙体 / 顶棚
# 240° 弧墙：后部与两侧，前方 120° 开口。
WALL_SEGS = 12
for i in range(WALL_SEGS):
    a0 = math.radians(-30 + i * 20)
    a1 = math.radians(-10 + i * 20)
    p = f'wall_arc_{i:02d}'
    arc_solid(f'{p}_struct', ROOM_C, WALL_R0, WALL_R1, a0, a1, 0, WALL_H,
              M['bluegray'], n=10, bevel=.035)
    arc_solid(f'{p}_panel_low', ROOM_C, WALL_R0 - .025, WALL_R1 - .015,
              a0 + .008, a1 - .008, .28, 2.45, M['cream'], n=10, bevel=.02)
    arc_solid(f'{p}_seam', ROOM_C, WALL_R0 - .035, WALL_R1 - .02,
              a0 + .006, a1 - .006, 2.45, 2.55, M['silver_dark'], n=10, bevel=.008)
    arc_solid(f'{p}_panel_up', ROOM_C, WALL_R0 - .018, WALL_R1 - .012,
              a0 + .012, a1 - .012, 2.55, 7.95, M['cream_l'], n=10, bevel=.03)
    arc_solid(f'{p}_base', ROOM_C, WALL_R0 - .05, WALL_R1, a0, a1, 0, .28,
              M['silver_dark'], n=10, bevel=.015)

# 弧墙分段处的竖向凸条：让白墙有参考图里的立体拼板感。
for i in range(WALL_SEGS):
    ang = math.radians(-30 + i * 20)
    q = polar(WALL_R0 - .055, math.degrees(ang))
    box(f'wall_trim_{i:02d}', (.12, .07, 7.72), (q[0], q[1], 4.0), M['cream_l'],
        bevel=.014, rot=(0, 0, ang + math.pi / 2))

# 上部竖向通风格栅与立柱一一对齐，形成“柱—墙—柱”的竖向节奏（只占上部一段）。
for j, ang in enumerate(COL_ANGS):
    am = math.radians(ang)
    mp = polar(WALL_R0 - .08, ang)
    plane(f'wall_vent_{j}', (.86, 3.10), (mp[0], mp[1], 4.72), M['ribs'],
          rot=(math.pi / 2, 0, am - math.pi / 2), uv=1.6)
    for s in (-1, 1):
        sp = polar(WALL_R0 - .095, ang + s * 4.3)
        plane(f'wall_vent_trim_{j}_{s}', (.06, 3.20), (sp[0], sp[1], 4.72),
              M['silver_bright'], rot=(math.pi / 2, 0, am - math.pi / 2))

# 顶部环形顶棚 + 中央暗槽与青色环。
disc('ceiling', 6.7, .22, (0, 0, WALL_H + .11), M['bluegray_dark'], verts=96)
disc('ceiling_inner', 3.1, .06, (0, 0, WALL_H - .02), M['navy'], verts=64)
torus('ceiling_ring', 3.25, .10, (0, 0, WALL_H - .04), M['silver'], major=72, minor=12)
torus('ceiling_glow', 2.55, .055, (0, 0, WALL_H - .06), M['glow_cyan'], major=64, minor=10)
for k in range(4):
    a = k * math.pi / 2 + math.pi / 4
    box(f'ceiling_spoke_{k}', (.07, 2.8, .05), (math.cos(a) * 1.55, math.sin(a) * 1.55, WALL_H - .08),
        M['silver'], bevel=.01, rot=(0, 0, a - math.pi / 2))
# 顶棚补光。
light((-2.8, .4, 6.6), (.92, .95, 1.), 12, 9)
light((2.8, .4, 6.6), (.92, .95, 1.), 12, 9)
light((0, 5.0, 4.3), (1., .92, .82), 8, 8)
# 前方顶部偏右的暖色柔光：给玻璃盘留下参考图里右下方那团暖色反射。
light((1.6, -3.0, 5.8), (1., .94, .86), 4, 8)

# 外侧深色围壳，避免从开口看到虚空。
arc_solid('backdrop_shell', ROOM_C, WALL_R1, WALL_R1 + .35,
          math.radians(-30), math.radians(210), 0, WALL_H, M['bluegray_dark'], n=80, bevel=.02)
# 底衬做成环，中间留出传送井，避免从上方盖住星云底盘。
arc_solid('backdrop_floor', ROOM_C, 6.2, 7.3, 0, 2 * math.pi, -.22, -.02,
          M['bluegray_dark'], n=96, bevel=0)

# ================================================================ 元数据
META['walk'] = {'minX': ROOM_C[0] - WALK_R, 'maxX': ROOM_C[0] + WALK_R,
                'minY': ROOM_C[1] - WALK_R, 'maxY': ROOM_C[1] + WALK_R}
META['room'] = {'x': ROOM_C[0], 'y': ROOM_C[1], 'r': WALK_R}
META['pad'] = {'x': PAD_C[0], 'y': PAD_C[1], 'r': PAD_R}
META['spawn'] = {'x': 0., 'y': -4.0}
META['animated']['pad_center'] = {'x': PAD_C[0], 'y': PAD_C[1], 'z': .1}


def render_preview(path):
    scene = bpy.context.scene
    world = bpy.data.worlds.new('w')
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.05, .065, .09, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = .20
    for i, l in enumerate(META['lights']):
        ld = bpy.data.lights.new(f'l{i}', 'POINT')
        ld.energy, ld.color, ld.shadow_soft_size = l['power'] * 12, l['color'], .4
        ob = bpy.data.objects.new(f'l{i}', ld)
        bpy.context.collection.objects.link(ob)
        ob.location = (l['x'], l['y'], l['z'])
    ld = bpy.data.lights.new('fill', 'AREA')
    ld.energy, ld.size, ld.color = 340, 10, (1., .97, .92)
    ob = bpy.data.objects.new('fill', ld)
    bpy.context.collection.objects.link(ob)
    ob.location = (0, -4.5, 6.0)
    cam_data = bpy.data.cameras.new('cam')
    cam_data.lens = float(arg('--lens', '26.7'))
    cam = bpy.data.objects.new('cam', cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = tuple(map(float, arg('--campos', '0.38,-8.63,4.98').split(',')))
    cam.rotation_euler = (Vector(tuple(map(float, arg('--target', '-0.06,1.32,0.87').split(','))))
                          - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam
    for name in [n for n in (arg('--hide', '') or '').split(',') if n]:
        ob = bpy.data.objects.get(name)
        if ob:
            ob.hide_render = True
            print('hidden', name)
        else:
            print('hide: not found', name)
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.exposure = -.62
    # 预览端加一层类 Bloom 的辉光，贴近参考图的青色泛光（不影响 GLB）。
    scene.use_nodes = True
    nt = bpy.data.node_groups.new('tele_comp', 'CompositorNodeTree')
    scene.compositing_node_group = nt
    nt.nodes.clear()
    rl = nt.nodes.new('CompositorNodeRLayers')
    glare = nt.nodes.new('CompositorNodeGlare')
    glare.inputs['Type'].default_value = 'Fog Glow'
    glare.inputs['Quality'].default_value = 'High'
    glare.inputs['Threshold'].default_value = .85
    glare.inputs['Size'].default_value = .68
    glare.inputs['Strength'].default_value = .55
    glare.inputs['Saturation'].default_value = 1.0
    nt.interface.new_socket(name='Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    comp = nt.nodes.new('NodeGroupOutput')
    nt.links.new(rl.outputs['Image'], glare.inputs['Image'])
    nt.links.new(glare.outputs['Image'], comp.inputs['Image'])
    scene.render.filepath = str(Path(path).resolve())
    bpy.ops.render.render(write_still=True)


if GLB:
    out = Path(GLB).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(out), export_format='GLB', export_apply=True, export_lights=False)
    out.with_suffix('.json').write_text(json.dumps(META, indent=1))
    print('exported', out, len(bpy.data.objects), 'objects')
if RENDER:
    render_preview(RENDER)
    print('rendered', RENDER)
