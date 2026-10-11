"""动力室 I —— 程序化建模房间，复用 power_reactor.build_reactor；导出 GLB + 元数据，可渲染预览。

用法:
  Blender -b -P blender/power_room.py -- --glb public/models/power/power_room.glb --render renders/power_v1.png
坐标：Blender z 向上，正面（参考相机方向）为 -Y。导入 Babylon 后 (x,y,z) -> (-x,z,-y)。
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from power_reactor import build_reactor, material, materials  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


GLB, RENDER, SAMPLES = arg('--glb'), arg('--render'), int(arg('--samples', '48'))

bpy.ops.wm.read_factory_settings(use_empty=True)
META = {'colliders': [], 'lights': [], 'animated': {}, 'walk': {}, 'spawn': {}}

M = materials()
M.update(
    wall=material('pw_wall', (.2, .24, .3), .42, .6),
    wall_d=material('pw_wall_dark', (.05, .07, .09), .5, .6),
    silver=material('pw_silver', (.62, .64, .67), .3, .9),
    grate=material('pw_grate', (.36, .36, .37), .42, .8, image=HERE / 'grate.png'),
    window=material('pw_window', (.7, .85, 1.), .3, emit=(.75, .88, 1.), strength=3.),
    glass=material('pw_glass', (.6, .75, .85), .04, 0.),
    blue=material('pw_energy_blue', (.2, .5, 1.), .3, emit=(1, 1, 1), strength=4., image=HERE / 'energy_blue.png'),
    orange=material('pw_energy_orange', (1, .5, .1), .3, emit=(1, 1, 1), strength=4., image=HERE / 'energy_orange.png'),
    ui=material('pw_screen_ui', (.02, .05, .08), .25, emit=(1, 1, 1), strength=1.6, image=HERE / 'screen_ui.png'),
    red=material('pw_glow_red', (.2, .02, .02), .4, emit=(1., .12, .08), strength=4.),
    seam=material('pw_glow_orange', (.3, .1, .02), .4, emit=(1., .55, .15), strength=10.),
    rubber=material('pw_rubber', (.03, .035, .04), .6, .1),
)
glass_bs = M['glass'].node_tree.nodes['Principled BSDF']
glass_bs.inputs['Alpha'].default_value = .18
glass_bs.inputs['Transmission Weight'].default_value = .9
M['glass'].surface_render_method = 'BLENDED'

objs = []


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


def cyl(name, r, h, loc, mat, rot=(0, 0, 0), verts=48, bevel=0., smooth=True):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    return finish(o, mat, bevel, smooth)


def plane(name, size, loc, mat, rot=(0, 0, 0), uv=1.):
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale, o.name = (size[0], size[1], 1), name
    for d in o.data.uv_layers.active.data:
        d.uv = (d.uv[0] * uv * size[0] / 2, d.uv[1] * uv * size[1] / 2)
    return finish(o, mat, 0, False)


def torus(name, R, r, loc, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=48, minor_segments=12,
                                     location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    return finish(o, mat, 0, True)


def along(name, a, b, r, mat, verts=40):
    # 两点间圆柱（玻璃管、能量棒）；UV 的 V 沿长度方向。
    a, b = Vector(a), Vector(b)
    d = b - a
    rot = d.to_track_quat('Z', 'Y').to_euler()
    return cyl(name, r, d.length, (a + b) / 2, mat, rot=rot, verts=verts)


def pipe(name, pts, r, mat, fillet=.25):
    P = [Vector(p) for p in pts]
    path = [P[0]]
    for k in range(1, len(P) - 1):
        a, b, c = P[k - 1], P[k], P[k + 1]
        d = min(fillet, (b - a).length / 2, (c - b).length / 2)
        s, e = b + (a - b).normalized() * d, b + (c - b).normalized() * d
        path += [(1 - t) ** 2 * s + 2 * (1 - t) * t * b + t * t * e for t in [i / 8 for i in range(9)]]
    path.append(P[-1])
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions, cu.bevel_depth, cu.bevel_resolution, cu.use_fill_caps = '3D', r, 5, True
    sp = cu.splines.new('POLY')
    sp.points.add(len(path) - 1)
    for p, co in zip(sp.points, path):
        p.co = (*co, 1)
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.convert(target='MESH')
    o.select_set(False)
    return finish(o, mat, 0, True)


def arc_solid(name, c, r0, r1, a0, a1, z0, z1, mat, n=28, bevel=.02):
    # 扇形实体（角度为标准方向，0=+X 逆时针）。
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
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    return finish(o, mat, bevel, True)


def lamp(name, c, facing, z0, z1, R, glow, n=7, spread=math.radians(62)):
    # 横纹灯：凸弧面上一排竖直发光条，条间露出白色底壳；上下有米白弧形盖。
    arc_solid(f'{name}_core', c, 0, R - .03, facing - spread - .1, facing + spread + .1, z0, z1, M['cream_l'], bevel=.01)
    for zz in (z0 - .1, z1):
        arc_solid(f'{name}_cap_{zz:.2f}', c, 0, R + .1, facing - spread - .18, facing + spread + .18, zz, zz + .1,
                  M['cream'], bevel=.03)
    w = 2 * spread * R / n
    color = 'cyan' if glow is M['glow'] else 'red'
    for k in range(n):
        a = facing - spread + 2 * spread * (k + .5) / n
        box(f'strip_{color}_{name}_{k}', (w * .8, .07, z1 - z0 - .04),
            (c[0] + R * math.cos(a), c[1] + R * math.sin(a), (z0 + z1) / 2), glow, bevel=.012,
            rot=(0, 0, a + math.pi / 2))
    p = Vector((c[0] + (R + .6) * math.cos(facing), c[1] + (R + .6) * math.sin(facing), (z0 + z1) / 2))
    light(p, (.3, .85, 1.) if color == 'cyan' else (1., .2, .12), 9, 4)


def screen(name, size, loc, rot, frame=True):
    # 带框小屏：屏面法线由 rot 决定（默认朝 -Y）。
    if frame:
        box(f'{name}_frame', (size[0] + .08, .05, size[1] + .08), loc, M['gun'], bevel=.015, rot=rot)
    o = plane(f'{name}_ui', size, loc, M['ui'], rot=(rot[0] + math.pi / 2, rot[1], rot[2]))
    # 屏面略微前移，避免与框体 Z-fighting。
    n = Vector((0, -1, 0))
    n.rotate(__import__('mathutils').Euler(rot))
    for v in o.data.vertices:
        v.co += n * .03
    return o


def keypad(name, loc, rot, cols=4, rows=3):
    box(f'{name}_base', (cols * .07 + .04, .03, rows * .07 + .04), loc, M['gun'], bevel=.01, rot=rot)
    e = __import__('mathutils').Euler(rot)
    for i in range(cols):
        for j in range(rows):
            off = Vector(((i - (cols - 1) / 2) * .07, -.025, (j - (rows - 1) / 2) * .07))
            off.rotate(e)
            box(f'{name}_k{i}{j}', (.05, .02, .05), Vector(loc) + off,
                M['red'] if (i + j) % 5 == 0 else M['cream_l'], bevel=.006, rot=rot)


def vents(name, start, end, z, n, mat=None):
    # 机身上的深色百叶槽。
    a, b = Vector(start), Vector(end)
    for k in range(n):
        p = a.lerp(b, (k + .5) / n)
        yaw = math.atan2(b.y - a.y, b.x - a.x)
        box(f'{name}_{k}', (.035, .1, .16), (p.x, p.y, z), mat or M['wall_d'], bevel=.008, rot=(0, 0, yaw))


def light(p, color, power, rng):
    META['lights'].append({'x': p[0], 'y': p[1], 'z': p[2], 'color': list(color), 'power': power, 'range': rng})


def collider(x, y, r):
    META['colliders'].append({'x': x, 'y': y, 'r': r})


# ================================================================ 房间外壳
RX, RY0, RY1, RH = 6.6, -5.2, 5.6, 6.2
box('wall_back', (RX * 2, .3, RH), (0, RY1 + .15, RH / 2), M['wall'], bevel=0)
box('wall_left', (.3, RY1 - RY0, RH), (-RX - .15, (RY0 + RY1) / 2, RH / 2), M['wall'], bevel=0)
box('wall_right', (.3, RY1 - RY0, RH), (RX + .15, (RY0 + RY1) / 2, RH / 2), M['wall'], bevel=0)
for i in range(-5, 6):
    box(f'wall_back_panel_{i}', (1.12, .12, 2.6), (i * 1.2, RY1 - .06, 1.5), M['wall'], bevel=.03)
    box(f'wall_back_panel_hi_{i}', (1.12, .14, 1.0), (i * 1.2, RY1 - .07, 3.4), M['wall_d'], bevel=.03)
for side, nm in ((-1, 'left'), (1, 'right')):
    for j in range(-4, 5):
        box(f'wall_{nm}_panel_{j}', (.12, 1.12, 2.6), (side * (RX - .06), j * 1.2 + .2, 1.5), M['wall'], bevel=.03)
# 后墙两扇高窗（参考图反应堆左上、右上的亮面）。
for k, x in enumerate((-1.45, 1.75)):
    box(f'wall_back_window_frame_{k}', (1.25, .16, 2.3), (x, RY1 - .1, 4.75), M['silver'], bevel=.04)
    plane(f'wall_back_window_{k}', (1.05, 2.1), (x, RY1 - .2, 4.75), M['window'], rot=(math.pi / 2, 0, 0))
    for z in (4.2, 4.75, 5.3):
        box(f'wall_back_window_bar_{k}_{z}', (1.05, .06, .05), (x, RY1 - .24, z), M['silver'], bevel=.01)
box('wall_right_window_frame', (.16, 1.8, 1.6), (RX - .1, 3.0, 4.4), M['silver'], bevel=.04)
plane('wall_right_window', (1.6, 1.4), (RX - .2, 3.0, 4.4), M['window'], rot=(math.pi / 2, 0, math.pi / 2))
# 后墙左侧线缆束与竖管（反应堆左后方）。
for k in range(6):
    x = -2.3 - k * .13
    pipe(f'wall_back_cable_{k}', [(x, RY1 - .3, RH), (x, RY1 - .3, 3.2), (x - .2 - k * .05, RY1 - .45, 2.2),
                                  (x - .5 - k * .05, RY1 - .5, .05)], .045, M['rubber'], fillet=.5)
for k, x in enumerate((-1.95, -1.7)):
    pipe(f'wall_back_brass_{k}', [(x, RY1 - .35, RH), (x, RY1 - .35, 1.6), (x + .35, RY1 - .9, 1.1),
                                  (x + .35, 5.0, .05)], .09, M['brass'], fillet=.3)

# ================================================================ 地面
# 中央格栅走道：2×2 块，银色框梁，中心十字橙色发光缝。
WX0, WX1, WY0, WY1 = -2.1, 2.1, -2.0, 1.6
WM = (WY0 + WY1) / 2
for i, (x0, x1) in enumerate(((WX0, 0), (0, WX1))):
    for j, (y0, y1) in enumerate(((WY0, WM), (WM, WY1))):
        plane(f'floor_grate_{i}{j}', (x1 - x0 - .12, y1 - y0 - .12), ((x0 + x1) / 2, (y0 + y1) / 2, .0),
              M['grate'], uv=3.)
for x in (WX0, 0, WX1):
    box(f'floor_beam_x_{x}', (.12, WY1 - WY0 + .12, .1), (x, (WY0 + WY1) / 2, -.03), M['silver'], bevel=.015)
for y in (WY0, WM, WY1):
    box(f'floor_beam_y_{y}', (WX1 - WX0 + .12, .12, .1), (0, y, -.03), M['silver'], bevel=.015)
box('floor_seam_x', (.06, WY1 - WY0 - .2, .02), (0, (WY0 + WY1) / 2, .025), M['seam'], bevel=0)
box('floor_seam_y', (WX1 - WX0 - .2, .06, .02), (0, WM, .025), M['seam'], bevel=0)
light((0, WM, .4), (1., .55, .2), 3, 4)
# 格栅下方暗腔。
box('floor_under', (WX1 - WX0, WY1 - WY0, .05), (0, (WY0 + WY1) / 2, -.6), M['wall_d'], bevel=0)
# 反应堆与两侧设备下的深色实心地台。
box('floor_back', (RX * 2, RY1 - WY1, .12), (0, (WY1 + RY1) / 2, -.06), M['gun'], bevel=.01)
for s in (-1, 1):
    box(f'floor_side_{s}', (RX - WX1, WY1 - RY0, .12), (s * (RX + WX1) / 2, (WY1 + RY0) / 2, -.06), M['gun'],
        bevel=.01)
# 前方地坑：下层地面、斜撑、黄铜管和带青灯的管箍。
box('pit_floor', (WX1 - WX0 + 1, WY0 - RY0, .1), (0, (WY0 + RY0) / 2, -1.7), M['wall_d'], bevel=0)
box('pit_beam_front', (WX1 - WX0 + .2, .16, .2), (0, WY0 - .1, -.1), M['silver'], bevel=.02)
for s in (-1, 1):
    box(f'pit_brace_{s}', (.14, 2.4, .14), (s * 1.2, WY0 - 1.0, -.85), M['silver'], bevel=.02, rot=(.75, 0, 0))
for k, z in enumerate((-1.25, -.95)):
    along(f'pit_pipe_{k}', (-3.5, WY0 - .7 - k * .5, z), (3.5, WY0 - .7 - k * .5, z), .1, M['brass'])
pipe('pit_riser', [(-1.25, -2.9, -1.7), (-1.25, -2.9, -.4), (-1.25, -2.4, .2)], .11, M['brass'], fillet=.3)
cyl('pit_riser_collar', .2, .22, (-1.25, -2.9, -.7), M['gun'], bevel=.02)
for k in range(2):
    box(f'pit_riser_glow_{k}', (.05, .03, .05), (-1.33 + k * .16, -3.11, -.62), M['glow'], bevel=0)

# ================================================================ 反应堆（后方正中）
RCX, RCY, RS = 0., 3.5, 1.15
build_reactor('reactor', (RCX, RCY, 0), scale=RS)
collider(RCX, RCY, 1.85 * RS)
light((RCX, RCY - 3.0, 2.8), (1., .58, .2), 70, 10)
light((RCX, RCY, 2.3), (1., .6, .25), 30, 6)
# 反应堆右侧铜管落入的接口座。
# 位置由 power_reactor 右管落点 (1.94, -0.34, 0.6) 按缩放换算。
PORT = (RCX + 1.94 * RS, RCY - .34 * RS)
cyl('reactor_port_base', .45, .69, (*PORT, .345), M['cream'], bevel=.04)
cyl('reactor_port_ring', .37, .1, (*PORT, .72), M['brass'], bevel=.02)

# ================================================================ 左侧设备组
# L1 扶手机组：长条机身，末端是朝向走道的青色横纹灯。
box('left_arm_plinth', (3.4, 1.05, .8), (-3.7, .6, .4), M['cream'], bevel=.08)
box('left_arm_body', (3.5, 1.4, .7), (-3.8, .6, 1.1), M['cream_l'], bevel=.18)
box('left_arm_top', (3.3, 1.2, .16), (-3.9, .6, 1.52), M['cream'], bevel=.06)
lamp('left_lamp', (-2.25, .6), 0., .8, 1.45, .7, M['glow'])
vents('left_arm_vents', (-5.1, -.11, 0), (-2.9, -.11, 0), 1.0, 14)
# L2 后方上层"拳形"机组，顶部深色十字面板。
box('left_upper_body', (2.3, 1.3, .8), (-3.9, 1.55, 1.25), M['cream_l'], bevel=.2)
box('left_upper_nose', (.8, 1.0, .6), (-2.55, 1.45, 1.15), M['cream'], bevel=.18, rot=(0, 0, -.25))
box('left_upper_plate', (1.5, 1.0, .04), (-4.1, 1.5, 1.66), M['gun'], bevel=.01)
box('left_upper_plate_x', (.4, 1.3, .045), (-4.1, 1.5, 1.665), M['gun'], bevel=.01)
screen('left_upper_scr', (.42, .26), (-3.0, 1.0, 1.75), (-.5, 0, .25))
# L3 前左控制台：斜面上的屏幕 + 键盘，侧面百叶。
box('left_console_body', (3.2, 2.4, 1.8), (-3.9, -2.4, .9), M['cream_l'], bevel=.25)
box('left_console_slope', (2.8, 1.3, .2), (-3.85, -3.05, 1.92), M['cream'], bevel=.06, rot=(.55, 0, 0))
box('left_console_head', (2.9, 1.0, .7), (-3.95, -1.75, 2.05), M['cream'], bevel=.18)
screen('left_console_scr', (.7, .45), (-3.45, -3.12, 1.98), (.55 - math.pi / 2, 0, 0))
keypad('left_console_keys', (-4.5, -3.14, 1.95), (.55 - math.pi / 2, 0, 0))
vents('left_console_vents', (-2.28, -3.5, 0), (-2.28, -1.3, 0), .7, 12)
# L4 后左高柜（靠墙），带小屏和红灯。
box('left_cabinet', (2.3, 1.6, 3.4), (-5.2, 3.2, 1.7), M['cream'], bevel=.2)
box('left_cabinet_front', (1.9, .2, 2.4), (-5.1, 2.35, 1.6), M['cream_l'], bevel=.08)
screen('left_cabinet_scr', (.5, .35), (-4.6, 2.22, 2.3), (0, 0, 0))
for k in range(3):
    box(f'left_cabinet_red_{k}', (.1, .04, .06), (-5.6 + k * .18, 2.22, 2.25), M['red'], bevel=.01)
box('left_mid_box', (1.0, .9, 1.0), (-3.1, 2.75, .9), M['cream_l'], bevel=.14)
screen('left_mid_box_scr', (.5, .36), (-3.1, 2.27, 1.05), (0, 0, 0))
for c in [(-3.6, .6, 1.0), (-2.25, .6, .72), (-3.6, 1.5, 1.0), (-3.9, -2.4, 1.6), (-5.2, 3.2, 1.6), (-3.1, 2.75, .7)]:
    collider(c[0], c[1], c[2])

# ================================================================ 右侧设备组
# R1 仪表臂：底座 + 伸向走道的臂 + 圆形表盘。
box('right_gauge_base', (1.2, 1.1, 1.6), (3.3, 1.4, .8), M['cream'], bevel=.18)
box('right_gauge_arm', (1.5, .7, .36), (2.5, 1.05, 1.3), M['cream_l'], bevel=.12, rot=(0, 0, .35))
cyl('right_gauge_dial_body', .42, .22, (1.85, .78, 1.45), M['cream_l'], bevel=.04)
cyl('right_gauge_dial_face', .32, .04, (1.85, .78, 1.58), M['gun'], bevel=.01)
torus('right_gauge_dial_ring', .27, .018, (1.85, .78, 1.6), M['glow'])
cyl('right_gauge_dial_hub', .1, .05, (1.85, .78, 1.6), M['silver'], bevel=.01)
screen('right_gauge_scr', (.42, .16), (1.95, .36, 1.32), (-.3, 0, .35))
# R2 右侧大机组：圆润机身 + 青色横纹灯 + 顶部面板。
box('right_machine_body', (3.0, 2.6, 1.6), (4.2, -.9, .8), M['cream_l'], bevel=.3)
box('right_machine_top', (2.6, 2.2, .3), (4.3, -.8, 1.7), M['cream'], bevel=.12)
lamp('right_lamp', (2.5, -1.3), math.radians(210), .55, 1.3, .7, M['glow'])
screen('right_machine_scr', (.5, .32), (3.35, .1, 1.9), (-.6, 0, -.3))
keypad('right_machine_keys', (3.9, -.2, 1.9), (-.6, 0, -.3), cols=3)
vents('right_machine_vents', (2.9, -2.25, 0), (5.4, -2.25, 0), .9, 14)
# R3 前右红色横纹灯机组。
box('right_red_body', (2.0, 1.6, 1.4), (3.2, -3.0, .7), M['cream'], bevel=.25)
lamp('right_red_lamp', (2.6, -3.0), math.radians(235), .6, 1.25, .55, M['red'])
# R4 前中右控制台：斜面百叶 + 正面键盘与屏幕。
# 立在地坑里，顶面比走道高 1.6。
box('front_console_body', (1.5, 1.3, 3.3), (1.15, -3.2, -.05), M['cream_l'], bevel=.3)
box('front_console_slope', (1.35, .9, .2), (1.15, -2.8, 1.62), M['cream'], bevel=.08, rot=(-.35, 0, 0))
vents('front_console_vents', (.65, -2.7, 0), (1.65, -2.7, 0), 1.72, 10)
keypad('front_console_keys', (1.5, -3.88, 1.2), (0, 0, 0), cols=3)
screen('front_console_scr', (.42, .34), (.85, -3.88, 1.1), (0, 0, 0))
box('front_console_glow', (1.1, .03, .04), (1.15, -3.87, .72), M['glow'], bevel=.01)
vents('front_console_face_vents', (.5, -3.87, 0), (1.8, -3.87, 0), .45, 9)
# R5 大玻璃管：从反应堆右后上方斜向右前方，内有蓝、橙能量棒。
S, E = Vector((2.4, 3.3, 4.3)), Vector((6.6, -.8, 2.1))
D = (E - S).normalized()
side = D.cross(Vector((0, 0, 1))).normalized()
up = side.cross(D).normalized()
along('tube_glass', S, E, .78, M['glass'], verts=56)
along('energy_blue', S + D * .3 + up * .3 + side * .15, E - D * .1 + up * .3 + side * .15, .07, M['blue'])
along('energy_orange', S + D * .3 - up * .25 - side * .2, E - D * .1 - up * .25 - side * .2, .05, M['orange'])
along('tube_back_housing', S - D * 1.1, S + D * .4, 1.02, M['cream'])
along('tube_back_cap', S - D * 1.2, S - D * 1.1, .8, M['gun'])
along('tube_back_ring', S + D * .35, S + D * .5, .86, M['brass'])
along('tube_front_ring', E - D * .15, E + D * .1, .88, M['cream_l'])
for k, t in enumerate((.35, .7)):
    p = S.lerp(E, t)
    along(f'tube_band_{k}', p - D * .06, p + D * .06, .82, M['silver'])
mid = S.lerp(E, .55)
box('tube_saddle', (1.0, 1.0, mid.z - 1.75), (mid.x, mid.y, (mid.z + 1.75) / 2 - .2), M['cream'], bevel=.15,
    rot=(0, 0, math.atan2(D.y, D.x)))
box('right_back_machine', (2.0, 2.4, 5.2), (5.3, 4.1, 2.6), M['cream'], bevel=.25)
cyl('right_back_port', .55, .1, (5.3, 2.86, 3.3), M['gun'], rot=(math.pi / 2, 0, 0), bevel=.02)
torus('right_back_port_ring', .5, .04, (5.3, 2.86 - .04, 3.3), M['glow'], rot=(math.pi / 2, 0, 0))
light(S.lerp(E, .5), (.35, .6, 1.), 14, 6)
light(S.lerp(E, .8), (1., .55, .2), 8, 4)
for c in [(1.85, .78, .5), (3.3, 1.4, .8), (4.2, -.9, 1.5), (3.2, -3.0, 1.1), (1.15, -3.2, .8), (PORT[0], PORT[1], .48)]:
    collider(c[0], c[1], c[2])

# ================================================================ 元数据
META['walk'] = {'minX': WX0 + .1, 'maxX': WX1 - .1, 'minY': WY0 + .1, 'maxY': 2.4}
META['spawn'] = {'x': 0., 'y': -1.0}
META['animated']['flame_core'] = {'x': RCX, 'y': RCY, 'z': 2.05}


def render_preview(path):
    scene = bpy.context.scene
    world = bpy.data.worlds.new('w')
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.16, .2, .25, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = .4
    for i, l in enumerate(META['lights']):
        ld = bpy.data.lights.new(f'l{i}', 'POINT')
        ld.energy, ld.color, ld.shadow_soft_size = l['power'] * 12, l['color'], .4
        ob = bpy.data.objects.new(f'l{i}', ld)
        bpy.context.collection.objects.link(ob)
        ob.location = (l['x'], l['y'], l['z'])
    ld = bpy.data.lights.new('fill', 'AREA')
    ld.energy, ld.size, ld.color = 700, 9, (1., .95, .88)
    ob = bpy.data.objects.new('fill', ld)
    bpy.context.collection.objects.link(ob)
    ob.location = (0, -2, 6.0)
    cam_data = bpy.data.cameras.new('cam')
    cam_data.lens = float(arg('--lens', '18'))
    cam = bpy.data.objects.new('cam', cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = tuple(map(float, arg('--campos', '0,-6.4,6.6').split(',')))
    cam.rotation_euler = (Vector(tuple(map(float, arg('--target', '0,0.9,1.0').split(',')))) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 1024, 465
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.exposure = -.3
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
