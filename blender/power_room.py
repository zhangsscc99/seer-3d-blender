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
import power_reactor  # noqa: E402
from power_reactor import build_reactor, material, materials  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


GLB, RENDER, SAMPLES = arg('--glb'), arg('--render'), int(arg('--samples', '48'))

bpy.ops.wm.read_factory_settings(use_empty=True)
META = {'colliders': [], 'lights': [], 'animated': {}, 'walk': {}, 'spawn': {}}

M = materials()
M.update(
    wall=material('pw_wall', (.32, .37, .45), .4, .6),
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
glass_bs.inputs['Base Color'].default_value = (.10,.14,.19,1)

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
    for d in o.data.uv_layers.active.data:
        d.uv.x *= 2 / size[0]
        d.uv.y *= 2 / size[1]
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


def shell(name, outline, z0, z1, mat, bevel=.10):
    """Closed extruded footprint; bevelled concave outlines make continuous machine decks."""
    n = len(outline)
    vs = [(x, y, z) for z in (z0, z1) for x, y in outline]
    fs = [tuple(reversed(range(n))), tuple(range(n, 2*n))]
    fs += [(i, (i+1)%n, (i+1)%n+n, i+n) for i in range(n)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    return finish(o, mat, bevel)


def deck(name, outline, z, thickness=.55):
    shell(name+'_undercarriage', outline, z-thickness-.18, z-.12, M['cream'], .14)
    shell(name+'_gasket', outline, z-.10, z+.015, M['rubber'], .07)
    shell(name+'_armor', outline, z+.02, z+.23, M['cream_l'], .10)


def top_vent(name, pts, z):
    # A recessed dark channel with short transverse metallic fins, never standing spikes.
    # Flat inset channel sits inside the pale armor lip.
    for j,(a,b) in enumerate(zip(pts,pts[1:])):
        a,b=Vector(a),Vector(b)
        mid=(a+b)/2
        box(f'{name}_recess{j}',((b-a).length+.09,.145,.025),(mid.x,mid.y,z),M['gun'],.025,
            rot=(0,0,math.atan2(b.y-a.y,b.x-a.x)))
    for j, (a,b) in enumerate(zip(pts,pts[1:])):
        a,b=Vector(a),Vector(b)
        d=b-a
        for k in range(max(2,int(d.length/.105))):
            v=a.lerp(b,(k+.5)/max(2,int(d.length/.105)))
            box(f'{name}_fin_{j}_{k}', (.038,.125,.025), (v.x,v.y,z+.022), M['silver'], .01,
                rot=(0,0,math.atan2(d.y,d.x)))


def top_panel(name, x, y, z, w=.48, h=.65):
    box(name+'_socket', (w+.1,h+.1,.065), (x,y,z), M['cream'], .028)
    screen(name, (w,h), (x,y,z+.037), (-math.pi/2,0,0))


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
WX0, WX1, WY0, WY1 = -2.1, 2.1, -1.5, 1.6
WM = (WY0 + WY1) / 2
# 原图格栅是 4×5 块粗网孔，一直铺到反应堆脚下。
GY1 = 2.9
XS = [WX0 + (WX1 - WX0) * k / 4 for k in range(5)]
YS = [WY0 + (GY1 - WY0) * k / 5 for k in range(6)]
for i in range(4):
    for j in range(5):
        plane(f'floor_grate_{i}{j}', (XS[i + 1] - XS[i] - .08, YS[j + 1] - YS[j] - .08),
              ((XS[i] + XS[i + 1]) / 2, (YS[j] + YS[j + 1]) / 2, .0), M['grate'], uv=1.)
for x in XS:
    box(f'floor_beam_x_{x:.2f}', (.08, GY1 - WY0 + .08, .1), (x, (WY0 + GY1) / 2, -.03), M['silver'], bevel=.012)
for y in YS:
    box(f'floor_beam_y_{y:.2f}', (WX1 - WX0 + .08, .08, .1), (0, y, -.03), M['silver'], bevel=.012)
box('floor_seam_x', (.05, GY1 - WY0 - .2, .02), (0, (WY0 + GY1) / 2, .025), M['seam'], bevel=0)
box('floor_seam_y', (WX1 - WX0 - .2, .05, .02), (0, YS[2], .025), M['seam'], bevel=0)
light((0, WM, .4), (1., .55, .2), 3, 4)
# 格栅下方暗腔。
box('floor_under', (WX1 - WX0, GY1 - WY0, .05), (0, (WY0 + GY1) / 2, -.6), M['wall_d'], bevel=0)
# 反应堆与两侧设备下的深色实心地台。
box('floor_back', (RX * 2, RY1 - GY1, .12), (0, (GY1 + RY1) / 2, -.06), M['gun'], bevel=.01)
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
pipe('pit_riser', [(-1.25, -2.4, -1.7), (-1.25, -2.4, -.4), (-1.25, -1.9, .2)], .11, M['brass'], fillet=.3)
cyl('pit_riser_collar', .2, .22, (-1.25, -2.4, -.7), M['gun'], bevel=.02)
for k in range(2):
    box(f'pit_riser_glow_{k}', (.05, .03, .05), (-1.33 + k * .16, -2.61, -.62), M['glow'], bevel=0)

shell('pit_diagonal_rim',[(-2.16,-1.43),(-1.06,-1.43),(.15,-2.48),(1.20,-2.15),(2.16,-1.43),
                          (2.16,-1.62),(1.25,-2.38),(.08,-2.74),(-1.14,-1.65),(-2.16,-1.65)],-.11,.05,M['silver'],.025)
# ================================================================ 反应堆（后方正中）
RCX, RCY, RS = .25, 3.6, 1.35
build_reactor('reactor', (RCX, RCY, 0), scale=RS)
collider(RCX, RCY, 1.52 * RS)
light((RCX, RCY - 3.0, 2.8), (1., .58, .2), 70, 10)
light((RCX, RCY, 2.3), (1., .6, .25), 30, 6)
# Replace the original placeholder face directly; retain full UV on every quad.
reactor_display = bpy.data.objects['reactor_unit_screen']
reactor_display.data.materials.clear()
reactor_display.data.materials.append(M['ui'])
for poly in reactor_display.data.polygons:
    for loop, uv in zip(poly.loop_indices, ((0,0),(1,0),(1,1),(0,1))):
        reactor_display.data.uv_layers.active.data[loop].uv = uv
bpy.data.objects.remove(bpy.data.objects['reactor_unit_chip'], do_unlink=True)
# 反应堆右侧铜管落入的接口座。
# 位置由 power_reactor 右管落点按缩放换算。
PORT = (RCX + power_reactor.PIPE_R_END[0] * RS, RCY + power_reactor.PIPE_R_END[1] * RS)
cyl('reactor_port_base', .45, 1.59, (*PORT, .795), M['cream'], bevel=.04)
cyl('reactor_port_ring', .37, .1, (*PORT, 1.64), M['brass'], bevel=.02)

# ================================================================ 左侧设备组
# Left: continuous sculpted console decks with an inset T-shaped service plate.
left_outline=[(-5.9,-.05),(-3.05,-.05),(-2.5,.10),(-1.93,.65),(-1.93,1.28),
              (-2.50,1.78),(-3.25,1.91),(-5.9,1.91)]
deck('left_arm',left_outline,1.12,.58)
lamp('left_lamp',(-2.63,.94),math.radians(-22),.92,1.53,.78,M['glow'],spread=math.radians(72))
# two long raised guard cheeks flow into the light drum.
for y in (.10,1.73):
    shell('left_guard_'+str(y),[(-5.65,y-.11),(-2.9,y-.11),(-2.35,y+.05),(-2.25,y+.26),(-5.65,y+.26)],
          1.30,1.57,M['cream'],.10)
top_vent('left_deck_vent',[(-5.5,.38),(-3.45,.38),(-3.45,1.42),(-2.96,1.42)],1.36)
shell('left_service_T',[(-5.6,.53),(-4.25,.53),(-4.25,.79),(-3.58,.79),(-3.58,1.20),(-4.25,1.20),
                        (-4.25,1.6),(-5.6,1.6)],1.35,1.40,M['gun'],.035)
box('left_upper_knuckle',(1.25,.77,.37),(-2.94,1.67,1.62),M['cream'],.16,rot=(0,0,-.18))
# Rear console and integrated blue inset, instead of a floating screen.
deck('left_upper',[(-5.6,1.97),(-3.5,1.97),(-2.92,2.35),(-3.08,3.18),(-5.6,3.35)],1.70,.55)
box('left_upper_screen_boss',(1.05,.86,.18),(-3.75,2.64,1.99),M['cream'],.14)
top_panel('left_upper_scr',-3.75,2.64,2.09,.62,.42)
top_vent('left_upper_vent',[(-5.25,2.13),(-3.52,2.13)],1.96)
# Front desk is low, broad and rounded; a separate thick monitor rises from its back edge.
front_outline=[(-6.2,-3.48),(-3.25,-3.48),(-2.70,-3.18),(-2.32,-2.52),(-2.33,-1.55),
               (-2.72,-.76),(-3.65,-.47),(-6.2,-.47)]
deck('left_console',front_outline,1.33,.75)
box('left_console_pedestal',(2.55,1.35,1.15),(-4.15,-1.55,.57),M['gun'],.22)
# large readable inclined front face + rounded visor and keyboard shelf.
box('left_monitor_body',(1.68,.62,1.32),(-4.20,-1.1,2.03),M['cream'],.19,rot=(-.14,0,0))
screen('left_monitor', (1.34,.91),(-4.20,-1.48,2.03),(-.14,0,0))
box('left_monitor_visor',(1.92,.85,.20),(-4.20,-1.18,2.72),M['cream_l'],.10)
box('left_keyboard_shelf',(1.92,.48,.11),(-4.20,-1.90,1.67),M['silver'],.06)
keypad('left_console_keys',(-3.90,-1.94,1.75),(-math.pi/2,0,0),cols=6,rows=3)
top_panel('left_console_readout',-4.72,-1.92,1.74,.34,.25)
top_vent('left_console_vent',[(-3.27,-3.05),(-2.87,-2.62),(-2.81,-1.72)],1.58)
for x in (-5.75,-3.8):
    pipe('left_console_panel_seam'+str(x),[(x,-3.29,1.57),(x,-2.45,1.57),(x-.3,-2.02,1.57)],.013,M['gun'],.13)
# Rear tall shell with attached vertical terminal and articulated red couplers.
box('left_cabinet',(1.95,1.32,3.8),(-5.5,3.7,1.9),M['cream'],.30)
box('left_cabinet_terminal',(1.40,.58,1.63),(-5.30,2.87,1.4),M['cream_l'],.14)
screen('left_cabinet_scr',(.62,.65),(-5.12,2.54,1.65),(0,0,0))
keypad('left_cabinet_keys',(-5.66,2.53,1.29),(0,0,0),cols=3,rows=5)
for k in range(2):
    y=3.0+k*.4
    pipe(f'left_cabinet_handle{k}',[(-4.9,y,2.38),(-4.45,y,2.38),(-4.1,y,1.96)],.12,M['cream_l'],.2)
    along(f'left_cabinet_red{k}',(-4.65,y,2.12),(-4.35,y,1.96),.10,M['red'])
for c in [(-3.6,1.1,1.0),(-2.40,.95,.9),(-3.8,2.3,1.0),(-3.95,-1.9,1.6),(-5.5,3.7,1.3)]:
    collider(*c)

# ================================================================ 右侧设备组
# R1 仪表臂：底座 + 伸向走道的臂 + 圆形表盘。
box('right_gauge_base', (1.2, 1.1, 1.6), (3.3, 1.4, .8), M['cream'], bevel=.18)
box('right_gauge_arm', (1.5, .8, .4), (3.05, .8, .95), M['cream_l'], bevel=.14, rot=(0, 0, .35))
cyl('right_gauge_dial_body', .58, .3, (2.4, .5, 1.1), M['cream_l'], bevel=.05)
cyl('right_gauge_dial_face', .45, .05, (2.4, .5, 1.27), M['gun'], bevel=.01)
torus('right_gauge_dial_ring', .38, .022, (2.4, .5, 1.3), M['glow'])
cyl('right_gauge_dial_hub', .13, .06, (2.4, .5, 1.3), M['silver'], bevel=.01)
cyl('right_gauge_pedestal', .4, 1.0, (2.4, .5, .45), M['cream'], bevel=.04)
box('right_gauge_screen_housing',(.70,.40,.37),(2.45,.055,.98),M['cream_l'],.10,rot=(0,0,.15))
screen('right_gauge_scr', (.55, .2), (2.45, -.16, 1.0), (-.3, 0, .15))
for k in range(32):
    a=k*math.tau/32
    box(f'right_gauge_tick{k}',(.016,.055,.012),(2.4+.34*math.cos(a),.5+.34*math.sin(a),1.305),
        M['glow'] if k%4==0 else M['silver'],.003,rot=(0,0,a-math.pi/2))
along('right_gauge_needle',(2.4,.5,1.34),(2.18,.68,1.34),.018,M['glow'])
# R2 segmented lower deck, raised twin rails framing the cyan drum.
right_outline=[(2.52,.30),(3.3,.83),(5.85,.83),(6.1,-2.32),(3.3,-2.32),(2.72,-1.75),(2.48,-.7)]
deck('right_machine',right_outline,1.16,.66)
lamp('right_lamp',(3.22,-1.18),math.radians(215),.91,1.53,.86,M['glow'],spread=math.radians(70))
for k,x in enumerate((2.90,4.03)):
    shell(f'right_guard{k}',[(x-.14,-1.75),(x+.14,-1.75),(x+.53,-.83),(x+.67,.24),(x+.36,.39),(x+.12,-.75)],
          1.36,1.69,M['cream'],.11)
top_panel('right_machine_scr',4.14,.15,1.42,.58,.65)
top_vent('right_machine_vent',[(4.76,-1.97),(4.76,-.20),(4.45,.55)],1.41)
# copper harness follows the back edge, inset alongside the large tube.
for k in range(2):
    pipe(f'right_top_copper{k}',[(3.24,2.50,1.64),(3.24,1.95,1.64),(4.47,1.95,1.64),(4.87,.3,1.64),
                               (5.5,-.55,1.64)],.045,M['brass'],.16)
# Red bank sits between two substantial elbow shaped guards at the foreground.
deck('right_red',[(2.50,-2.13),(4.83,-2.13),(5.3,-3.8),(2.26,-4.0)],1.03,.69)
lamp('right_red_lamp',(3.16,-2.93),math.radians(230),1.0,1.59,.86,M['red'])
for x in (2.49,3.73):
    shell('right_red_guard'+str(x),[(x,-3.6),(x+.29,-3.6),(x+.64,-2.60),(x+.6,-2.23),(x+.28,-2.2),(x+.2,-2.67)],
          1.44,1.79,M['cream_l'],.13)
# Front console follows the diagonal pit rim, with controls recessed into its sloping surface.
front=[(.46,-4.0),(1.89,-4.0),(2.48,-2.54),(2.18,-2.03),(1.5,-2.03),(.6,-3.15)]
deck('front_console',front,1.18,1.70)
top_panel('front_console_scr',1.18,-3.17,1.46,.38,.72)
keypad('front_console_keys',(1.71,-2.51,1.47),(-math.pi/2,0,0),cols=4,rows=5)
top_vent('front_console_vent',[(.65,-3.70),(.78,-3.1),(1.15,-2.59)],1.44)
# R5 大玻璃管：从反应堆右后上方斜向右前方，内有蓝、橙能量棒。
S, E = Vector((3.0, 3.3, 3.8)), Vector((6.6, -.8, 1.6))
D = (E - S).normalized()
side = D.cross(Vector((0, 0, 1))).normalized()
up = side.cross(D).normalized()
along('tube_glass', S, E, .65, M['glass'], verts=56)
along('energy_blue', S + D * .3 + up * .26 + side * .13, E - D * .1 + up * .26 + side * .13, .06, M['blue'])
along('energy_orange', S + D * .3 - up * .21 - side * .17, E - D * .1 - up * .21 - side * .17, .045, M['orange'])
along('tube_back_housing', S - D * 1.1, S + D * .4, .85, M['cream'])
along('tube_back_cap', S - D * 1.2, S - D * 1.1, .68, M['gun'])
along('tube_back_ring', S + D * .35, S + D * .5, .72, M['brass'])
torus('tube_front_ring', .69, .095, E, M['cream_l'], D.to_track_quat('Z','Y').to_euler())
for k, t in enumerate((.35, .7)):
    p = S.lerp(E, t)
    torus(f'tube_band_{k}', .655, .042, p, M['silver'], D.to_track_quat('Z','Y').to_euler())
mid = S.lerp(E, .55)
box('tube_saddle', (1.0, 1.0, mid.z - 1.75), (mid.x, mid.y, (mid.z + 1.75) / 2 - .2), M['cream'], bevel=.15,
    rot=(0, 0, math.atan2(D.y, D.x)))
box('right_back_machine', (2.0, 2.4, 2.0), (5.3, 4.1, 1.0), M['cream'], bevel=.25)
# Segmented armored socket, bolt ring and A-shaped support cradle.
for k in range(8):
    a=k*math.tau/8
    radial=side*math.cos(a)+up*math.sin(a)
    q=S-D*.15+radial*.83
    along(f'tube_socket_bolt{k}',q-D*.06,q+D*.06,.073,M['gun'],verts=20)
    along(f'tube_socket_bolt_inset{k}',q+D*.061,q+D*.067,.034,M['silver'],verts=16)
    along(f'tube_housing_seam{k}',S-D*.95+radial*.852,S+D*.05+radial*.852,.012,M['gun'])
for k,sg in enumerate((-1,1)):
    q=S+D*.36+side*sg*.71
    foot=Vector((q.x+sg*.23,q.y,1.44))
    top=q+Vector((0,0,-.13))
    axis=top-foot
    box(f'tube_cradle{k}',(.32,.46,axis.length),(foot+top)/2,M['cream_l'],.08,
        rot=axis.to_track_quat('Z','Y').to_euler())
    box(f'tube_cradle_foot{k}',(.63,.75,.14),(foot.x,foot.y,1.45),M['cream'],.07)
# long narrow highlight on the glass makes its cylindrical silhouette legible.
along('tube_glass_highlight',S+D*.52+up*.63,E-D*.18+up*.63,.018,M['silver'])
light(S.lerp(E, .5), (.35, .6, 1.), 14, 6)
light(S.lerp(E, .8), (1., .55, .2), 8, 4)
for c in [(2.4, .5, .62), (3.3, 1.4, .8), (4.2, -.9, 1.5), (3.2, -3.0, 1.1), (1.15, -3.2, .8), (PORT[0], PORT[1], .48)]:
    collider(c[0], c[1], c[2])

# ================================================================ 元数据
META['walk'] = {'minX': WX0 + .1, 'maxX': WX1 - .1, 'minY': WY0 + .1, 'maxY': 2.4}
META['spawn'] = {'x': 0., 'y': -.6}
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
