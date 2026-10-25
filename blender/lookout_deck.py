"""瞭望露台 I —— 参考机位标定的分层舰体与机械甲板。

用法:
  python3 blender/make_lookout_textures.py
  Blender -b -P blender/lookout_deck.py -- --glb public/models/lookout/lookout_deck.glb \
      --blend renders/lookout/rebuild/lookout_deck.blend \
      --render renders/lookout/rebuild/blender.png --samples 32

坐标：Blender Z 向上，正面朝 -Y；Babylon 为 (-x,z,-y)。
主体轮廓由固定参考相机反投影到有物理意义的平面，再建立真实厚度、背面和连接件。
参考天空只允许包含远景，不包含建筑、甲板或标题。
"""
import argparse
import hashlib
import json
import math
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
parser.add_argument('--reference', default=str(ROOT / 'public/models/lookout/lookout_reference.json'))
args = parser.parse_args(argv)

# 与 lookout_reference.json 相同的长焦初值。旧 10.54m 广角会让竖直设备明显向外倾斜。
REF = {}
if Path(args.reference).exists():
    REF = json.loads(Path(args.reference).read_text())
CAM = REF.get('camera', {})
RADIUS = float(CAM.get('radius', 40.0))
BETA = float(CAM.get('beta', 1.182))
FOV = float(CAM.get('fov', 0.26514004445810213))
# 标定文件同时保留 Babylon 与 Blender 坐标；Babylon (x,y,z) 对应 Blender (-x,z,-y)。
if CAM.get('targetBlender') is not None:
    TARGET = Vector(CAM['targetBlender'])
elif CAM.get('target') is not None:
    # toB(blender) = (-x, z, -y)，所以逆变换是 (-bx, -bz, by)。
    bx, by, bz = CAM['target']
    TARGET = Vector((-bx, -bz, by))
else:
    TARGET = Vector((0.0, 1.15, 1.4))
# alpha=pi/2，beta=1.182 与旧机位方向一致。
FORWARD = Vector((0.0, math.sin(BETA), -math.cos(BETA)))
CAM_POS = TARGET - FORWARD * RADIUS
RIGHT = Vector((1.0, 0.0, 0.0))
UP = RIGHT.cross(FORWARD)
FOCAL = 360.0 / math.tan(FOV / 2.0)

bpy.ops.wm.read_factory_settings(use_empty=True)
META = {'colliders': [], 'lights': [], 'animated': {}, 'walk': {}, 'spawn': {}, 'boxes': [], 'landmarks': []}


def ray(px, py):
    return FORWARD + RIGHT * ((px - 640.0) / FOCAL) + UP * ((360.0 - py) / FOCAL)


def at_z(px, py, z=0.0):
    d = ray(px, py)
    return CAM_POS + d * ((z - CAM_POS.z) / d.z)


def at_y(px, py, y):
    d = ray(px, py)
    return CAM_POS + d * ((y - CAM_POS.y) / d.y)


def project(p):
    q = Vector(p) - CAM_POS
    depth = q.dot(FORWARD)
    return (640.0 + FOCAL * q.dot(RIGHT) / depth, 360.0 - FOCAL * q.dot(UP) / depth)


def anchor(name, p):
    META['landmarks'].append({'id': name, 'x': p[0], 'y': p[1], 'z': p[2]})


def image_material(name, color, path, strength=1.0, alpha=False):
    m = material(name, color, .55, 0., emit=(1, 1, 1), strength=strength, image=path)
    if alpha:
        bs = m.node_tree.nodes.get('Principled BSDF')
        tex = next(n for n in m.node_tree.nodes if n.type == 'TEX_IMAGE')
        m.node_tree.links.new(tex.outputs['Alpha'], bs.inputs['Alpha'])
        m.surface_render_method = 'BLENDED'
    return m


M = dict(
    white=material('lo_white', (.76, .745, .705), .48, .04, coat=.07),
    white2=material('lo_white_warm', (.635, .635, .595), .52, .06, coat=.05),
    panel=material('lo_panel', (.44, .465, .465), .52, .16),
    edge=material('lo_edge', (.185, .215, .225), .46, .48),
    silver=material('lo_silver', (.585, .60, .585), .42, .38, coat=.06),
    dark=material('lo_dark', (.052, .066, .074), .46, .42),
    black=material('lo_black', (.010, .016, .020), .54, .18),
    rubber=material('lo_rubber', (.020, .024, .026), .80, .01),
    glass=material('lo_glass', (.13, .26, .30), .13, .03, coat=.30),
    window=material('lo_window', (.012, .022, .028), .18, .08),
    glow=material('lo_glow_cyan', (.08, .55, .64), .30, .05, emit=(.16, .88, 1.0), strength=2.2, coat=.15),
    glow_dim=material('lo_glow_dim', (.03, .13, .17), .34, .20, emit=(.06, .30, .38), strength=.7),
    red=material('lo_red', (.40, .105, .09), .46, .18),
    red_light=material('lo_red_light', (.58, .22, .18), .40, .24),
    cloth=material('lo_cloth', (.39, .42, .27), .72, 0.),
    visor=material('lo_visor', (.035, .065, .085), .17, .28, coat=.28),
)
for key in ('glass', 'window'):
    bs = M[key].node_tree.nodes['Principled BSDF']
    bs.inputs['Alpha'].default_value = .23 if key == 'glass' else .10
    bs.inputs['Transmission Weight'].default_value = 0.
    M[key].surface_render_method = 'BLENDED'

badge_path = HERE / 'lookout_badge.png'
if badge_path.exists():
    M['badge'] = image_material('lo_badge', (.2, .2, .2), badge_path, 1.0, True)
else:
    M['badge'] = M['glow_dim']
sky_path = HERE / 'lookout_nebula.png'
M['sky'] = image_material('lo_sky', (.01, .015, .025), sky_path, 1.15)

objs = []


def finish(o, mat, bevel=0., smooth=None):
    if mat:
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
        b.angle_limit = math.radians(28)
        w = o.modifiers.new('wn', 'WEIGHTED_NORMAL')
        w.keep_sharp = True
        w.weight = 40
    objs.append(o)
    return o


def mesh(name, verts, faces, mat, bevel=0., smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    return finish(o, mat, bevel, smooth)


def box(name, size, loc, mat, bevel=.025, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale, o.name = size, name
    return finish(o, mat, bevel)


def cyl(name, r, h, loc, mat, rot=(0, 0, 0), verts=48, bevel=.01, smooth=True):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    return finish(o, mat, bevel, smooth)


def sphere(name, r, loc, mat, scale=(1, 1, 1), segments=32, rings=20):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=segments, ring_count=rings, location=loc)
    o = bpy.context.active_object
    o.scale, o.name = scale, name
    return finish(o, mat, 0, True)


def torus(name, R, r, loc, mat, rot=(0, 0, 0), major=64, minor=12):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=major,
                                     minor_segments=minor, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    return finish(o, mat, 0, True)


def along(name, a, b, r, mat, verts=32):
    a, b = Vector(a), Vector(b)
    d = b - a
    return cyl(name, r, d.length, (a + b) / 2, mat, d.to_track_quat('Z', 'Y').to_euler(), verts, .005)


def pipe(name, pts, r, mat, fillet=.25, resolution=5):
    P = [Vector(p) for p in pts]
    path = [P[0]]
    for k in range(1, len(P) - 1):
        a, b, c = P[k - 1], P[k], P[k + 1]
        d = min(fillet, (b - a).length / 2, (c - b).length / 2)
        s, e = b + (a - b).normalized() * d, b + (c - b).normalized() * d
        for i in range(10):
            t = i / 9
            path.append((1 - t) ** 2 * s + 2 * (1 - t) * t * b + t * t * e)
    path.append(P[-1])
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth, cu.bevel_resolution, cu.use_fill_caps = r, resolution, True
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


def signed_area(poly):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1])) / 2


def offset_poly(poly, distance):
    """二维等宽偏置；正值向多边形内部，不用质心缩放。"""
    P = [Vector(p) for p in poly]
    n = len(P)
    orient = 1 if signed_area(poly) > 0 else -1
    lines = []
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        t = (b - a).normalized()
        normal = Vector((-t.y, t.x)) * orient
        lines.append((a + normal * distance, t))
    out = []
    for i in range(n):
        p, u = lines[(i - 1) % n]
        q, v = lines[i]
        cross = u.x * v.y - u.y * v.x
        if abs(cross) < 1e-8:
            out.append(P[i])
            continue
        qp = q - p
        t = (qp.x * v.y - qp.y * v.x) / cross
        out.append(p + u * t)
    return out


def shell(name, outline, z0, z1, mat, bevel=.03):
    n = len(outline)
    verts = [(p[0], p[1], z) for z in (z0, z1) for p in outline]
    faces = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    return mesh(name, verts, faces, mat, bevel)


def loft_xy(name, loops, mat, caps=True, bevel=0., smooth=False):
    # loops: [(z, [(x,y),...]), ...]，同一顶点数。
    n = len(loops[0][1])
    verts = [(p[0], p[1], z) for z, poly in loops for p in poly]
    faces = []
    for k in range(len(loops) - 1):
        for i in range(n):
            j = (i + 1) % n
            faces.append((k * n + i, k * n + j, (k + 1) * n + j, (k + 1) * n + i))
    if caps:
        faces += [tuple(reversed(range(n))), tuple((len(loops) - 1) * n + i for i in range(n))]
    return mesh(name, verts, faces, mat, bevel, smooth)


def loft_xz(name, loops, mat, close=True, bevel=0., smooth=False):
    # loops: [(y, [(x,z),...]), ...]，形成有厚度的环截面。
    n = len(loops[0][1])
    verts = [(p[0], y, p[1]) for y, poly in loops for p in poly]
    faces = []
    count = len(loops) if close else len(loops) - 1
    for k in range(count):
        kk = (k + 1) % len(loops)
        for i in range(n):
            j = (i + 1) % n
            faces.append((k * n + i, k * n + j, kk * n + j, kk * n + i))
    return mesh(name, verts, faces, mat, bevel, smooth)


def plate_xz(name, poly, y, mat):
    return mesh(name, [(p[0], y, p[1]) for p in poly], [tuple(range(len(poly)))], mat)


def extrude_xz(name, poly, yf, yb, mat, bevel=.02):
    n = len(poly)
    verts = [(p[0], y, p[1]) for y in (yf, yb) for p in poly]
    faces = [tuple(range(n)), tuple(reversed(range(n, 2 * n)))]
    faces += [(i, i + n, (i + 1) % n + n, (i + 1) % n) for i in range(n)]
    return mesh(name, verts, faces, mat, bevel)


def rounded_panel(name, center, u, v, length, width, depth, mat, radius=.06):
    """任意朝向的圆角矩形实体；u/v 为面内方向，法线由 u×v 给出。"""
    c = Vector(center)
    u = Vector((u[0], 0, u[1])) if len(u) == 2 else Vector(u)
    u.normalize()
    v = Vector((v[0], 0, v[1])) if len(v) == 2 else Vector(v)
    v.normalize()
    normal = u.cross(v).normalized()
    r = min(radius, length / 2 - .001, width / 2 - .001)
    poly = []
    for cx, cy, a0 in ((length / 2 - r, width / 2 - r, 0),
                       (-length / 2 + r, width / 2 - r, 90),
                       (-length / 2 + r, -width / 2 + r, 180),
                       (length / 2 - r, -width / 2 + r, 270)):
        for j in range(6):
            a = math.radians(a0 + j * 90 / 5)
            poly.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    # 上述角点顺序为 CCW。
    n = len(poly)
    verts = []
    for s in (-1, 1):
        for x, y in poly:
            verts.append(c + u * x + v * y + normal * (s * depth / 2))
    faces = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    return mesh(name, verts, faces, mat, 0, False)


def lathe(name, profile, center, mat, segments=64, axis=(0, 0, 1), cap=True):
    """profile=[(轴向距离,半径)]，可沿任意轴制作法兰、舱体和光学件。"""
    c, axis = Vector(center), Vector(axis).normalized()
    u = axis.cross(Vector((0, 0, 1)))
    if u.length < .01:
        u = axis.cross(Vector((0, 1, 0)))
    u.normalize()
    v = axis.cross(u).normalized()
    verts, faces = [], []
    for s, r in profile:
        for i in range(segments):
            a = 2 * math.pi * i / segments
            verts.append(c + axis * s + u * (r * math.cos(a)) + v * (r * math.sin(a)))
    for k in range(len(profile) - 1):
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((k * segments + i, k * segments + j, (k + 1) * segments + j, (k + 1) * segments + i))
    if cap:
        faces.append(tuple(reversed(range(segments))))
        faces.append(tuple((len(profile) - 1) * segments + i for i in range(segments)))
    return mesh(name, verts, faces, mat, 0, True)


def dome(name, r, h, center, mat, segments=64, rings=18):
    verts, faces = [], []
    c = Vector(center)
    for j in range(rings + 1):
        phi = (math.pi / 2) * j / rings
        rr, zz = r * math.cos(phi), h * math.sin(phi)
        for i in range(segments):
            a = 2 * math.pi * i / segments
            verts.append(c + Vector((rr * math.cos(a), rr * math.sin(a), zz)))
    for j in range(rings):
        for i in range(segments):
            ni = (i + 1) % segments
            faces.append((j * segments + i, j * segments + ni, (j + 1) * segments + ni, (j + 1) * segments + i))
    return mesh(name, verts, faces, mat, 0, True)


def circle(x, y, r):
    META['colliders'].append({'x': x, 'y': y, 'r': r})


def obstacle(min_x, max_x, min_y, max_y):
    META['boxes'].append({'minX': min_x, 'maxX': max_x, 'minY': min_y, 'maxY': max_y})


def light(p, color, power, rng):
    META['lights'].append({'x': p[0], 'y': p[1], 'z': p[2], 'color': list(color), 'power': power, 'range': rng})


def ground_point(px, py, z=.025):
    return at_z(px, py, z)


def ground_strip(name, points, width=.065, mat=None, z=.025):
    mat = mat or M['dark']
    for i, (a, b) in enumerate(zip(points, points[1:])):
        pa, pb = ground_point(*a, z), ground_point(*b, z)
        d = pb - pa
        side = Vector((-d.y, d.x, 0)).normalized() * width / 2
        verts = [pa - side, pb - side, pb + side, pa + side]
        mesh(f'{name}_{i}', verts, [(0, 1, 2, 3)], mat)


def rivet_row(name, a, b, spacing=.24, radius=.018, z=.056):
    pa, pb = ground_point(*a, z), ground_point(*b, z)
    count = max(2, int((pb - pa).length / spacing))
    for i in range(count + 1):
        p = pa.lerp(pb, i / count)
        cyl(f'{name}_{i}', radius, .016, p, M['edge'], verts=8, bevel=0)


# ---------------------------------------------------------------- 舰体甲板：参考轮廓 + 真实分层侧壳
# 顺时针围住整个可见甲板，前缘延伸到画面外。
deck_pixels = [
    (305, 333), (205, 369), (112, 425), (22, 497), (-70, 595), (-100, 790),
    (1380, 790), (1360, 545), (1265, 468), (1165, 405), (1030, 347), (942, 329),
    (795, 326), (640, 330), (470, 326),
]
deck_outline = [at_z(u, v, 0)[:] [:2] for u, v in deck_pixels]
# Vector[:] [:2] 兼容写法得到 (x,y)；统一转 Vector 便于偏置。
deck_outline = [Vector(p) for p in deck_outline]
loft_xy('deck_hull', [(-.48, offset_poly(deck_outline, .10)), (-.12, deck_outline), (0, deck_outline)], M['white2'], bevel=.045)
loft_xy('deck_lower_gasket', [(-.34, offset_poly(deck_outline, -.035)), (-.23, offset_poly(deck_outline, -.035))], M['dark'], caps=False)
loft_xy('deck_armor_lip', [(-.04, deck_outline), (.035, offset_poly(deck_outline, .07))], M['white'], caps=False, bevel=.018)
# 后部和两侧的分层装甲折线。
for side, pts in (
    ('l', [(18, 520), (82, 455), (184, 391), (306, 351), (390, 337)]),
    ('r', [(951, 343), (1070, 376), (1195, 439), (1300, 522)]),
):
    ground_strip(f'deck_{side}_panel_seam', pts, .055, M['edge'], .035)

# 真实下沉沟槽和独立面板，不再是整张贴黑线。
for name, pts, w in [
    ('lane_l_outer', [(454, 359), (421, 413), (371, 512), (327, 641)], .085),
    ('lane_l_inner', [(508, 382), (492, 477), (486, 531), (451, 641)], .070),
    ('lane_l_panel', [(368, 493), (486, 493)], .055),
    ('lane_center_l', [(565, 474), (558, 640)], .045),
    ('lane_center_r', [(756, 476), (828, 640)], .050),
    ('rover_pad', [(884, 411), (1081, 385), (1164, 447), (1110, 523), (920, 515), (884, 411)], .045),
    ('right_lane', [(821, 414), (852, 516), (1048, 548)], .050),
    ('left_panel', [(118, 443), (210, 410), (292, 435)], .045),
]:
    ground_strip(name, pts, w)
for i, (a, b) in enumerate([
    ((450, 371), (337, 632)), ((472, 374), (390, 640)), ((515, 404), (474, 635)),
    ((552, 482), (545, 640)), ((579, 482), (579, 640)), ((805, 420), (846, 628)),
    ((895, 424), (933, 512)), ((1081, 403), (1134, 456)),
]):
    rivet_row(f'deck_rivets_{i}', a, b)


def deck_plate(name, pts, mat=None, inset=.055, z0=.018, z1=.050):
    """把参考里的大块装甲做成有真实厚度的凸台，而非在平面上画黑线。"""
    poly = [Vector(at_z(u, v, z0)[:2]) for u, v in pts]
    return shell(name, offset_poly(poly, inset), z0, z1, mat or M['white2'], .016)


# 甲板主装甲板。参考里的板缝阴影来自真实高差，这里给每块板独立的顶面和倒角。
for name, pts, mat in (
    ('deck_plate_left_rear', [(82, 442), (238, 404), (292, 429), (268, 474), (139, 510), (92, 475)], M['white']),
    ('deck_plate_left_low', [(27, 505), (143, 472), (214, 519), (179, 610), (47, 590)], M['white2']),
    ('deck_plate_left_lane', [(208, 524), (348, 480), (404, 523), (366, 623), (238, 657), (202, 607)], M['white']),
    ('deck_plate_center_left', [(444, 449), (518, 430), (548, 477), (510, 539), (469, 608), (441, 549)], M['white2']),
    ('deck_plate_center_floor', [(558, 448), (758, 449), (778, 546), (754, 616), (558, 612)], M['white']),
    ('deck_plate_right_mid', [(826, 432), (954, 410), (1086, 457), (1120, 539), (990, 578), (894, 526)], M['white']),
    ('deck_plate_right_low', [(1002, 586), (1161, 511), (1236, 575), (1098, 651), (1015, 625)], M['white2']),
    ('deck_plate_right_out', [(1102, 454), (1241, 508), (1322, 638), (1204, 690), (1152, 574)], M['white']),
    ('deck_plate_fore_left', [(110, 640), (322, 646), (362, 705), (188, 715)], M['white2']),
):
    deck_plate(name, pts, mat)
    # 沿外缘布置铆钉，间距随相机投影均匀变化。
    for i in range(len(pts)):
        rivet_row(f'{name}_edge_rivets_{i}', pts[i], pts[(i + 1) % len(pts)], .27, .015, .058)
# 板缝之间的窄压条和两组横向检修盖，让大面积白漆有尺度参照。
for side, pts in (
    ('l', [(303, 504), (329, 575), (343, 645)]),
    ('r', [(811, 500), (827, 565), (846, 635)]),
):
    ground_strip(f'deck_service_rail_{side}', pts, .035, M['silver'], .040)
for i, (a, b) in enumerate((((394, 458), (424, 447)), ((498, 602), (536, 598)),
                            ((922, 404), (986, 397)), ((1023, 547), (1073, 542)))):
    p0, p1 = at_z(*a, .042), at_z(*b, .042)
    d = p1 - p0
    box(f'deck_handle_{i}', (d.length, .055, .035), ((p0.x + p1.x) / 2, (p0.y + p1.y) / 2, .052),
        M['silver'], .012, (0, 0, math.atan2(d.y, d.x)))

# 前景舱口：多层八边形框架与真实暗井。
hatch_outer_px = [(440, 641), (815, 641), (852, 662), (1020, 682), (1080, 742),
                  (300, 742), (350, 687), (417, 663)]
hatch_inner_px = [(474, 666), (792, 666), (824, 688), (966, 706), (995, 742),
                  (403, 742), (425, 709), (455, 688)]
hatch_outer = [at_z(u, v, .055)[:] [:2] for u, v in hatch_outer_px]
hatch_inner = [at_z(u, v, .055)[:] [:2] for u, v in hatch_inner_px]
hatch_outer = [Vector(p) for p in hatch_outer]
hatch_inner = [Vector(p) for p in hatch_inner]
loft_xy('fore_hatch_frame', [(-.12, hatch_outer), (.075, hatch_outer), (.10, hatch_inner), (-.12, hatch_inner)], M['edge'], caps=False, bevel=.025)
loft_xy('fore_hatch_silver', [(.07, offset_poly(hatch_outer, .10)), (.12, offset_poly(hatch_inner, -.07))], M['silver'], caps=False, bevel=.012)
shell('fore_hatch_well', hatch_inner, -.20, -.11, M['black'], .02)
ground_strip('fore_hatch_glow', [(490, 704), (820, 704)], .06, M['glow_dim'], -.08)

# 后部 U 形管线/扶手。
for i, pt in enumerate([(388, 350), (421, 344), (454, 340), (485, 337)]):
    p = at_z(*pt, 0)
    pipe(f'rear_loop_{i}', [(p.x - .13, p.y, .04), (p.x - .13, p.y, .64),
                            (p.x + .13, p.y, .64), (p.x + .13, p.y, .04)], .090, M['panel'], .16)
    box(f'rear_loop_foot_{i}', (.48, .34, .09), (p.x, p.y, .045), M['edge'], .025)

# ---------------------------------------------------------------- 中央高台：多边形顶面、斜面、前脸与独立格栅
# 顶面边界直接采用标定文件的 fit landmarks；旧值整体向内缩了约 30px。
platform_pixels = [(529, 325), (767, 325), (778, 394), (744, 418), (532, 418), (518, 394)]
platform = [Vector(at_z(u, v, .95)[:2]) for u, v in platform_pixels]
# 参考中台体下沿比顶面更宽：用真实外扩截面，而不是直立盒体。
bottom_px = [(529, 325), (767, 325), (778, 394), (778, 468), (517, 468), (518, 394)]
platform_bottom = [Vector(at_z(u, v, .16)[:2]) for u, v in bottom_px]
platform_top = offset_poly(platform, .045)
shell('dais_under', offset_poly(platform_bottom, -.035), .055, .17, M['dark'], .045)
loft_xy('dais_body', [(.16, platform_bottom), (.90, platform_top)], M['white2'], bevel=.075)
shell('dais_top', platform_top, .90, .99, M['white'], .040)
# 顶面分模与铆钉沿实际 footprint 布置。
for i in range(len(platform)):
    a, b = platform[i], platform[(i + 1) % len(platform)]
    aa, bb = a.lerp(b, .08), a.lerp(b, .92)
    count = max(2, int((bb - aa).length / .25))
    for j in range(count + 1):
        p = aa.lerp(b, j / count)
        cyl(f'dais_rivet_{i}_{j}', .018, .014, (p.x, p.y, 1.002), M['edge'], verts=8, bevel=0)
anchor('platform_back_left', (platform_top[0].x, platform_top[0].y, .99))
anchor('platform_back_right', (platform_top[1].x, platform_top[1].y, .99))
anchor('platform_top_front_right', (platform_top[3].x, platform_top[3].y, .99))
anchor('platform_top_front_left', (platform_top[4].x, platform_top[4].y, .99))
anchor('platform_front_base_right', (platform_bottom[3].x, platform_bottom[3].y, .16))
anchor('platform_front_base_left', (platform_bottom[4].x, platform_bottom[4].y, .16))
# 顶面不是一块空白板：内圈椭圆接缝、横向检修板和四角分模线。
for k, pts in enumerate((
    [(548, 348), (736, 347), (767, 364)],
    [(543, 381), (742, 381)],
    [(535, 403), (746, 403)],
    [(549, 333), (594, 373), (622, 404)],
    [(744, 333), (706, 372), (674, 404)],
)):
    ground_strip(f'dais_top_seam_{k}', pts, .028, M['edge'], .997)
for k, pts in enumerate((
    [(548, 344), (600, 344)], [(676, 344), (735, 344)],
    [(554, 363), (592, 363)], [(680, 363), (730, 363)],
    [(548, 393), (580, 393)], [(700, 393), (740, 393)],
)):
    ground_strip(f'dais_inner_panel_{k}', pts, .022, M['silver'], .998)
# 前脸：白色上带 + 参考像素反投影的宽梯形深凹槽。
front_mid = (platform[3] + platform[4]) / 2
front_y = front_mid.y - .035
front_plane = front_y - .055
box('dais_front_upper_band', (2.26, .06, .24), (front_mid.x, front_plane - .012, .81), M['white'], .035)
for name, px, yf, yb, mat, bevel in (
    ('dais_front_bezel', [(558, 437), (729, 437), (746, 472), (545, 472)], front_plane - .030, front_plane + .010, M['silver'], .022),
    ('dais_front_recess', [(567, 443), (720, 443), (739, 470), (551, 470)], front_plane + .004, front_plane + .050, M['black'], .020),
    ('dais_front_inner', [(577, 449), (710, 449), (727, 468), (562, 468)], front_plane + .048, front_plane + .085, M['edge'], .016),
):
    pts = [at_y(u, v, (yf + yb) / 2) for u, v in px]
    poly = [(p.x, p.z) for p in pts]
    extrude_xz(name, poly, yf, yb, mat, bevel)
# 凹槽左上角的青色状态灯与内侧高光条。
status = at_y(585, 451, front_plane + .048)
box('dais_front_status', (.22, .03, .035), (status.x, status.y, status.z), M['glow'], .008)
inner_top = at_y(640, 455, front_plane + .048)
box('dais_front_highlight', (1.28, .025, .018), (inner_top.x, inner_top.y, inner_top.z), M['glow_dim'], .004)
anchor('platform_recess_top_left', at_y(567, 443, front_plane + .004))
anchor('platform_recess_top_right', at_y(720, 443, front_plane + .004))
# 左右青格栅由参考四角反投影到各自竖直平面。
for side, pts in (
    ('l', [(485, 405), (525, 405), (522, 466), (478, 466)]),
    ('r', [(779, 405), (817, 405), (826, 466), (782, 466)]),
):
    base = at_z(*((500, 466) if side == 'l' else (804, 466)), .10)
    poly = [at_y(u, v, base.y)[:] for u, v in pts]
    poly = [(p[0], p[2]) for p in poly]
    extrude_xz(f'vent_{side}_housing', poly, base.y + .03, base.y + .62, M['white'], .045)
    cx = sum(p[0] for p in poly) / 4
    cz = sum(p[1] for p in poly) / 4
    inset = [(cx + (x - cx) * .87, cz + (z - cz) * .90) for x, z in poly]
    extrude_xz(f'vent_{side}_recess', inset, base.y - .015, base.y + .035, M['dark'], .018)
    z0, z1 = min(z for x, z in inset), max(z for x, z in inset)
    for row in range(5):
        z = z0 + (row + .5) * (z1 - z0) / 5
        xl = min(x for x, zz in inset)
        xr = max(x for x, zz in inset)
        width = (xr - xl) * .90
        rounded_panel(f'vent_{side}_cyan_{row}', (cx, base.y - .055, z), (1, 0, 0), (0, 0, 1),
                      width, (z1 - z0) / 5 * .74, .055, M['glow'], .042)
    light((cx, base.y - .35, .62), (.25, .85, 1), 3.5, 2.2)
# 两根与甲板齐平的供能管。
for i, xoff in enumerate((-.17, .17)):
    x = front_mid.x + xoff
    along(f'feed_pipe_{i}', (x, -.10, .13), (x, -2.55, .13), .085, M['silver'])
    for y in (-.28, -1.10, -2.28):
        cyl(f'feed_collar_{i}_{y}', .112, .12, (x, y, .13), M['dark'], (math.pi / 2, 0, 0), 32, .008)
obstacle(-2.65, 2.85, -.20, 2.72)

# ---------------------------------------------------------------- 玻璃舱与舱内小人
POD = at_z(650, 372, .99)
px, py = POD.x, POD.y
lathe('pod_foot', [(0, .49), (.06, .60), (.14, .60), (.20, .52)], (px, py, .99), M['silver'])
lathe('pod_base', [(.18, .47), (.26, .51), (.52, .51), (.65, .435), (.69, .405)], (px, py, .99), M['white'])
torus('pod_base_gasket', .535, .025, (px, py, 1.19), M['dark'])
# 四个外张支脚和侧向接口。
for i, a in enumerate((math.pi / 4, 3 * math.pi / 4, 5 * math.pi / 4, 7 * math.pi / 4)):
    d = Vector((math.cos(a), math.sin(a), 0))
    along(f'pod_leg_{i}', (px + d.x * .43, py + d.y * .43, 1.40),
          (px + d.x * .69, py + d.y * .69, 1.00), .065, M['silver'])
    cyl(f'pod_foot_bolt_{i}', .10, .07, (px + d.x * .68, py + d.y * .68, 1.01), M['dark'], verts=24)
rounded_panel('pod_door_frame', (px, py - .585, 1.31), (1, 0, 0), (0, 0, 1), .40, .30, .06, M['dark'], .075)
rounded_panel('pod_door', (px, py - .625, 1.30), (1, 0, 0), (0, 0, 1), .26, .20, .04, M['glow'], .055)
for i, xo in enumerate((-.33, .33)):
    cyl(f'pod_status_light_{i}', .045, .025, (px + xo, py - .60, 1.13), M['glow_dim'] if i else M['glow'],
        (math.pi / 2, 0, 0), 20, 0)
for side in (-1, 1):
    rounded_panel(f'pod_side_screen_{side}', (px + side * .34, py - .49, 1.49), (1, 0, 0), (0, 0, 1), .24, .18, .035, M['visor'], .04)
    torus(f'pod_port_{side}', .12, .035, (px + side * .58, py, 1.48), M['silver'], (0, math.pi / 2, 0), 40, 10)
# 舱内小人先于玻璃生成，所有部件保留 pilot_ 前缀。
# 舱内座椅与操控台，透明罩下能看到分层内部。
box('pilot_seat', (.44, .38, .16), (px, py + .10, 1.78), M['panel'], .05)
box('pilot_seat_back', (.42, .12, .42), (px, py + .30, 1.98), M['edge'], .045)
box('pilot_console', (.44, .18, .14), (px, py - .24, 1.90), M['white2'], .035)
box('pilot_console_screen', (.28, .03, .08), (px, py - .335, 1.96), M['glow_dim'], .012)
sphere('pilot_body', .30, (px, py, 1.93), M['cloth'], (.90, .75, 1.20))
sphere('pilot_helm', .31, (px, py - .015, 2.36), M['white'], (1, .94, 1.04), 40, 24)
sphere('pilot_visor', .255, (px, py - .19, 2.37), M['visor'], (.86, .34, .73), 32, 20)
for side in (-1, 1):
    along(f'pilot_arm_{side}', (px + side * .24, py, 2.02), (px + side * .36, py - .08, 1.76), .09, M['cloth'])
    sphere(f'pilot_glove_{side}', .10, (px + side * .36, py - .08, 1.74), M['white2'], segments=24, rings=16)
    along(f'pilot_leg_{side}', (px + side * .13, py, 1.76), (px + side * .15, py - .04, 1.58), .105, M['cloth'])
box('pilot_backpack', (.36, .18, .43), (px, py + .25, 1.96), M['panel'], .06)
# 有厚度的透明罩、圆润顶盖和密封圈；罩体上收下阔，避免直筒感。
lathe('pod_glass', [(0, .385), (.05, .425), (.16, .450), (.92, .450), (1.06, .420), (1.16, .340)],
      (px, py, 1.80), M['glass'], 88)
torus('pod_lower_seal', .430, .032, (px, py, 1.82), M['edge'])
torus('pod_upper_seal', .340, .028, (px, py, 2.96), M['silver'], major=56, minor=8)
lathe('pod_cap', [(0, .15), (.03, .27), (.08, .335), (.15, .345), (.22, .29), (.26, .20)], (px, py, 2.94), M['glow_dim'])
lathe('pod_cap_ring', [(.21, .19), (.24, .23), (.27, .19)], (px, py, 2.94), M['silver'], 48)
cyl('pod_cap_vent', .085, .022, (px, py, 3.20), M['dark'], verts=32)
light((px, py - .35, 1.80), (.35, .85, 1), 4.5, 2.8)
anchor('pod_base_center', (px, py, .99))
anchor('pod_cap_center', (px, py, 3.12))
anchor('pod_cap_left', (px - .33, py, 3.09))
anchor('pod_cap_right', (px + .33, py, 3.09))
anchor('pod_glass_base_center', (px, py, 1.80))
anchor('pod_base_bottom_center', (px, py - .54, .99))
anchor('pod_lamp_center', (px, py - .625, 1.29))

# ---------------------------------------------------------------- 十段可见灯组的装甲观察窗（底边由平台遮挡）
ARCH_Y = 3.25
# 八角框的内外轮廓与 lookout_reference.json 的 8 个 fit landmarks 完全一致。
outer_px = [(571.226, 100.755), (729.717, 100.755), (803.302, 166.415),
            (837.264, 226.415), (752.358, 328.302), (548.585, 328.302),
            (466.509, 226.415), (497.642, 166.415)]
inner_px = [(602.358, 131.321), (695.755, 131.321), (769.340, 169.811),
            (803.302, 223.585), (735.377, 311.321), (565.566, 311.321),
            (497.642, 223.585), (531.604, 169.811)]
outer = [Vector(at_y(u, v, ARCH_Y)[:1] + at_y(u, v, ARCH_Y)[2:3]) for u, v in outer_px]
inner = [Vector(at_y(u, v, ARCH_Y)[:1] + at_y(u, v, ARCH_Y)[2:3]) for u, v in inner_px]
# 上面分别取世界 x,z，避免把 Blender y 当成向量 y。
outer = [Vector((p[0], p[1])) for p in outer]
inner = [Vector((p[0], p[1])) for p in inner]
outer_in = offset_poly(outer, .09)
inner_out = offset_poly(inner, -.11)
loft_xz('arch_body', [(ARCH_Y + .55, outer), (ARCH_Y + .08, outer), (ARCH_Y - .10, outer_in),
                      (ARCH_Y - .10, inner_out), (ARCH_Y + .03, inner), (ARCH_Y + .55, inner)], M['white'], bevel=.022)
# 外圈枪灰承力脊和内圈深色密封槽。
loft_xz('arch_outer_spine', [(ARCH_Y + .58, offset_poly(outer, -.06)), (ARCH_Y + .22, offset_poly(outer, -.06)),
                             (ARCH_Y + .22, offset_poly(outer, .035)), (ARCH_Y + .58, offset_poly(outer, .035))], M['edge'], bevel=.015)
loft_xz('arch_inner_trim', [(ARCH_Y - .13, inner_out), (ARCH_Y - .17, offset_poly(inner, -.02)),
                            (ARCH_Y + .02, inner), (ARCH_Y + .06, offset_poly(inner, .16))], M['silver'], bevel=.010)
# 外缘前脸的浅灰压边，模拟参考里两级折边的受光。
loft_xz('arch_front_rim', [(ARCH_Y - .155, offset_poly(outer, -.018)), (ARCH_Y - .10, offset_poly(outer, -.018)),
                           (ARCH_Y - .10, offset_poly(outer, -.070)), (ARCH_Y - .155, offset_poly(outer, -.070))],
        M['silver'], bevel=.012)
loft_xz('arch_gasket', [(ARCH_Y + .015, offset_poly(inner, -.045)), (ARCH_Y + .02, inner),
                        (ARCH_Y + .18, inner), (ARCH_Y + .18, offset_poly(inner, -.045))], M['dark'])
plate_xz('arch_glass', inner, ARCH_Y + .20, M['window'])
# 背部加强筋与落地支座，保证自由视角不是薄片。
for i in (0, 1, 2, 3, 5, 6, 7):
    p = outer[i]
    box(f'arch_back_rib_{i}', (.14, .26, .30), (p.x, ARCH_Y + .55, p.y - .18), M['edge'], .025)
for side in (-1, 1):
    x = .16 + side * 2.25
    box(f'arch_support_{side}', (.48, .85, .95), (x, ARCH_Y + .08, .46), M['white2'], .08)
    box(f'arch_support_foot_{side}', (.82, 1.10, .16), (x, ARCH_Y + .02, .08), M['panel'], .045)
# 每条边中段的独立灯槽；顶边为双灯，底边（第 4 条边）藏在平台后。
for i in range(len(outer)):
    j = (i + 1) % len(outer)
    if i in (0, 4):
        continue
    edge = outer[j] - outer[i]
    length = edge.length
    tangent = edge.normalized()
    mid = (outer[i] + outer[j] + inner[i] + inner[j]) / 4
    ts = (.5,)
    for k, t in enumerate(ts):
        c = (outer[i].lerp(outer[j], t) + inner[i].lerp(inner[j], t)) / 2
        ll = length * .62
        rounded_panel(f'arch_recess_{i}_{k}', (c.x, ARCH_Y - .16, c.y), tangent, (0, 0, 1), ll + .13, .44, .08, M['dark'], .075)
        rounded_panel(f'arch_lamp_{i}_{k}', (c.x, ARCH_Y - .225, c.y), tangent, (0, 0, 1), ll + .015, .33, .055, M['glow'], .075)
for k, (u, v) in enumerate(((575, 112), (733, 112))):
    c = at_y(u, v, ARCH_Y - .225)
    rounded_panel(f'arch_recess_top_{k}', (c.x, ARCH_Y - .16, c.z), (1, 0, 0), (0, 0, 1), .88, .42, .08, M['dark'], .07)
    rounded_panel(f'arch_lamp_top_{k}', c, (1, 0, 0), (0, 0, 1), .74, .29, .055, M['glow'], .065)
# 八个框角增加独立压条、深色分模缝和两枚螺栓，打断整圈白件的“玩具感”。
for i, (po, pi) in enumerate(zip(outer, inner)):
    d = pi - po
    length = d.length
    u = d.normalized()
    v = Vector((-u.y, u.x))
    c = (po + pi) / 2
    rounded_panel(f'arch_joint_seam_{i}', (c.x, ARCH_Y - .075, c.y), u, v, length * .96, .052, .035, M['dark'], .024)
    for t in (.12, .88):
        q = po.lerp(pi, t)
        cyl(f'arch_joint_bolt_{i}_{t}', .025, .025, (q.x, ARCH_Y - .15, q.y), M['edge'],
            (math.pi / 2, 0, 0), 8, .004)
# 外圈下沿的枪灰护唇和内侧连续压边，和参考的层叠关系一致。
loft_xz('arch_outer_lip', [(ARCH_Y + .04, offset_poly(outer, -.02)),
                           (ARCH_Y - .10, offset_poly(outer, -.02)),
                           (ARCH_Y - .14, offset_poly(outer, -.08)),
                           (ARCH_Y + .04, offset_poly(outer, -.08))], M['edge'], bevel=.018)
for i, p in enumerate(outer):
    anchor(f'arch_outer_{i:02d}', (p.x, ARCH_Y - .10, p.y))
for i, p in enumerate(inner):
    anchor(f'arch_inner_{i:02d}', (p.x, ARCH_Y + .02, p.y))
for i, name in enumerate((
    'window_outer_top_left', 'window_outer_top_right', 'window_outer_upper_right',
    'window_outer_right', 'window_outer_lower_right', 'window_outer_lower_left',
    'window_outer_left', 'window_outer_upper_left',
)):
    anchor(name, (outer[i].x, ARCH_Y - .10, outer[i].y))
for i, name in enumerate((
    'window_inner_top_left', 'window_inner_top_right', 'window_inner_upper_right',
    'window_inner_right', 'window_inner_lower_right', 'window_inner_lower_left',
    'window_inner_left', 'window_inner_upper_left',
)):
    anchor(name, (inner[i].x, ARCH_Y + .03, inner[i].y))
light((0, ARCH_Y - .5, 3.2), (.35, .8, 1), 7, 5)

# 顶部六边形徽章：独立金属框、深色底板和仅含标志的 UV 面。
badge_outer_px = [(613.679, 86.604), (681.604, 86.604), (697.453, 117.170),
                  (681.604, 148.868), (613.679, 148.868), (598.396, 117.170)]
badge_inner_px = [(618.7, 91.6), (676.6, 91.6), (690.4, 117.17),
                  (676.6, 143.7), (618.7, 143.7), (605.4, 117.17)]
badge_outer = [Vector((at_y(u, v, ARCH_Y - .30).x, at_y(u, v, ARCH_Y - .30).z)) for u, v in badge_outer_px]
badge_inner = [Vector((at_y(u, v, ARCH_Y - .30).x, at_y(u, v, ARCH_Y - .30).z)) for u, v in badge_inner_px]
loft_xz('arch_badge_frame', [(ARCH_Y - .20, badge_outer), (ARCH_Y - .34, badge_outer),
                             (ARCH_Y - .36, badge_inner), (ARCH_Y - .20, badge_inner)], M['silver'], bevel=.012)
plate_xz('arch_badge_back', badge_inner, ARCH_Y - .24, M['dark'])
# UV 四角直接由参考区域反投影，材质只含重绘标志。
bp = [at_y(626, 96, ARCH_Y - .37), at_y(670, 96, ARCH_Y - .37), at_y(670, 140, ARCH_Y - .37), at_y(626, 140, ARCH_Y - .37)]
o = mesh('arch_badge_icon', bp, [(0, 1, 2, 3)], M['badge'])
uv = o.data.uv_layers.new(name='UVMap')
for poly in o.data.polygons:
    for li in poly.loop_indices:
        vi = o.data.loops[li].vertex_index
        uv.data[li].uv = [(0, 1), (1, 1), (1, 0), (0, 0)][vi]
anchor('badge_center', at_y(648.2, 117.17, ARCH_Y - .36))
anchor('badge_top_left', (badge_outer[0].x, ARCH_Y - .33, badge_outer[0].y))
anchor('badge_top_right', (badge_outer[1].x, ARCH_Y - .33, badge_outer[1].y))
anchor('badge_left_vertex', (badge_outer[5].x, ARCH_Y - .33, badge_outer[5].y))
anchor('badge_right_vertex', (badge_outer[2].x, ARCH_Y - .33, badge_outer[2].y))
anchor('badge_bottom_center', at_y(648.2, 148.868, ARCH_Y - .33))
anchor('badge_emblem_center', at_y(648.2, 117.17, ARCH_Y - .37))

# ---------------------------------------------------------------- 左侧红色斜面与黑色弧管
HEAT = at_z(239, 459, 0)
hx, hy = HEAT.x, HEAT.y
# 楔体：前低后高，红色散热槽在真实斜面上。
wedge_outline = [Vector((hx - .95, hy - .72)), Vector((hx + .95, hy - .72)),
                 Vector((hx + .82, hy + .85)), Vector((hx - .82, hy + .85))]
verts = [(p.x, p.y, .12) for p in wedge_outline] + [
    (hx - .95, hy - .72, .38), (hx + .95, hy - .72, .38),
    (hx + 1.17, hy + .85, 1.22), (hx - .47, hy + .85, 1.22)]
mesh('heat_wedge', verts, [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)], M['white'], .07)
sphere('heat_side_cowl', .65, (hx + .83, hy + .10, .65), M['white'], (.58, 1.18, 1.0), 36, 22)
# 斜面暗槽和六根红色鳍片。
for i in range(7):
    t = (i + .5) / 7
    y = hy - .54 + t * 1.20
    z = .38 + (y - (hy - .72)) / 1.57 * .84 + .025
    box(f'heat_fin_{i}', (1.50, .12, .035), (hx + .35 * t, y, z), M['red_light'] if i % 2 else M['red'], .012,
        rot=(math.atan2(.84, 1.57), 0, 0))
for side in (-1, 1):
    pipe(f'heat_edge_{side}', [(hx + side * .88, hy - .70, .39), (hx + .35 + side * .75, hy + .82, 1.24)], .055, M['silver'])
circle(hx, hy, 1.12)
# 三根弧管直接按参考投影中心线放到同一高度。
for i in range(3):
    pts = [at_z(318, 379 + i * 4, .20 + i * .10), at_z(355, 392 + i * 3, .20 + i * .10),
           at_z(410, 397 + i * 3, .20 + i * .10), at_z(480, 381 + i * 3, .20 + i * .10)]
    pipe(f'heat_cable_{i}', pts, .065, M['rubber'], .38)
    for p in (pts[0], pts[-1]):
        cyl(f'heat_cable_clamp_{i}_{p.x:.2f}', .095, .16, p, M['silver'], verts=24)

# ---------------------------------------------------------------- 左前光学机组：底座、肋状壳、同心镜头与顶部环
SENSOR = at_z(207, 598, 0)
sx, sy = SENSOR.x, SENSOR.y
# 底座是阶梯转台：暗色裙边、八块独立垫脚、白色承台和密封圈。
lathe('sensor_base_skirt', [(0, .66), (.05, .74), (.14, .74), (.20, .68)], (sx, sy, 0), M['panel'])
lathe('sensor_base', [(.18, .70), (.24, .76), (.34, .76), (.42, .68), (.46, .60)], (sx, sy, 0), M['white2'])
torus('sensor_base_gasket', .70, .030, (sx, sy, .35), M['dark'])
for i in range(8):
    a = 2 * math.pi * i / 8 + math.pi / 8
    box(f'sensor_base_block_{i}', (.18, .20, .14),
        (sx + .72 * math.cos(a), sy + .72 * math.sin(a), .075), M['panel'], .018, (0, 0, a))
    cyl(f'sensor_base_bolt_{i}', .026, .024, (sx + .63 * math.cos(a), sy + .63 * math.sin(a), .465),
        M['edge'], verts=8, bevel=0)
sphere('sensor_core', .615, (sx, sy + .10, 1.02), M['dark'], (.98, .90, 1.12), 40, 24)
sphere('sensor_shell', .65, (sx, sy + .16, 1.06), M['white2'], (.98, .88, 1.06), 48, 28)
# 白色外壳由多块圆弧装甲和侧护板构成；上左装甲带最宽，右后收进暗缝。
for i, (a, w, h, zc, rz) in enumerate(((-1.05, .38, .62, 1.13, -.28), (-.48, .34, .78, 1.04, -.12),
                                      (.10, .30, .86, .98, .02), (.70, .28, .80, 1.00, .16),
                                      (2.30, .32, .70, 1.06, .30), (3.85, .30, .58, 1.00, -.10))):
    x, y = sx + .52 * math.sin(a), sy + .10 - .44 * math.cos(a)
    box(f'sensor_armor_{i}', (w, .24, h), (x, y, zc), M['white'], .075,
        rot=(0, rz, -a * .30))
    box(f'sensor_armor_shadow_{i}', (w * .55, .06, h * .82), (x, y - .14, zc - .03), M['white2'], .02,
        rot=(0, rz, -a * .30))
for side in (-1, 1):
    box(f'sensor_cheek_{side}', (.26, .64, .72), (sx + side * .60, sy + .02, .84), M['white2'], .065,
        rot=(0, side * .14, side * .06))
    pipe(f'sensor_side_pipe_{side}', [(sx + side * .50, sy + .28, .42), (sx + side * .79, sy + .40, .50),
                                      (sx + side * .77, sy + .52, 1.14), (sx + side * .47, sy + .45, 1.48)], .046, M['silver'], .18)
# 镜头中心由参考点反投影到前方平面；底座与镜头是偏置的转台，不是同轴圆柱。
# 参考里的可见光学中心（192.5, 544）是镜头前表面；轴心需向上、向右让出前伸量。
LENS = at_y(196, 532, sy - .58)
lens_axis = Vector((0, -1, -.08)).normalized()
lens_rot = lens_axis.to_track_quat('Z', 'Y').to_euler()
# 镜头座：背面大圆盘 + 外圈八角压板 + 三层同心圆。
lathe('sensor_lens_mount', [(-.38, .58), (-.30, .62), (-.12, .62), (-.02, .56)], LENS, M['white2'], 64, lens_axis)
lathe('sensor_lens_barrel', [(-.06, .50), (.02, .56), (.12, .56), (.18, .48)], LENS, M['edge'], 64, lens_axis)
lathe('sensor_lens_silver', [(.14, .45), (.18, .50), (.24, .50), (.27, .43)], LENS, M['silver'], 64, lens_axis)
lathe('sensor_lens_dark', [(.255, .36), (.275, .385), (.305, .36)], LENS, M['black'], 64, lens_axis)
lathe('sensor_lens_glass', [(.305, .275), (.328, .275)], LENS, M['visor'], 64, lens_axis)
lathe('sensor_lens_pupil', [(.328, .115), (.342, .115)], LENS, M['black'], 48, lens_axis)
torus('sensor_lens_rim', .515, .038, LENS + lens_axis * .18, M['dark'], lens_rot, 64, 12)
for i in range(8):
    a = math.pi / 8 + i * math.pi / 4
    q = LENS + lens_axis * .20 + Vector((math.cos(a) * .47, 0, math.sin(a) * .47))
    cyl(f'sensor_lens_bolt_{i}', .024, .026, q, M['edge'], lens_rot, 8, 0)
# 镜头下方铸件与右侧散热片，补足参考里不对称的下颌结构。
box('sensor_chin', (.52, .34, .24), (sx - .04, sy - .40, .66), M['white2'], .06, (0, 0, -.10))
rounded_panel('sensor_vent_panel', (sx + .43, sy - .43, .80), (0, 1, 0), (0, 0, 1), .20, .30, .05, M['dark'], .03)
for i in range(4):
    box(f'sensor_front_vent_{i}', (.045, .035, .22), (sx + .38 + i * .052, sy - .435, .80), M['silver'], .006)
# 白色壳体的分模弧线，避免整颗球壳像玩具。
for i, (a0, a1) in enumerate(((-1.25, -.35), (-.15, .55), (.65, 1.55), (2.25, 3.05))):
    pts = []
    for t in range(5):
        a = a0 + (a1 - a0) * t / 4
        pts.append((sx + .665 * math.sin(a), sy + .14 - .585 * math.cos(a), 1.08))
    pipe(f'sensor_shell_seam_{i}', pts, .014, M['edge'], .12)
# 顶部水平环与后倾连接座；颈部是圆柱，不再是一只大盒子。
TOPRING = at_y(206, 463, sy + .65)
lathe('sensor_top_neck', [(.02, .34), (.06, .40), (.36, .40), (.42, .33)],
      (TOPRING.x, TOPRING.y, TOPRING.z - .52), M['white2'], 48)
lathe('sensor_top_ring', [(0, .40), (.06, .50), (.20, .50), (.28, .40)], TOPRING - Vector((0, 0, .16)), M['silver'])
torus('sensor_top_lip', .43, .042, TOPRING + Vector((0, 0, .14)), M['white'])
cyl('sensor_top_hole', .345, .03, TOPRING + Vector((0, 0, .135)), M['dark'], verts=48)
cyl('sensor_top_glass', .315, .018, TOPRING + Vector((0, 0, .148)), M['visor'], verts=48)
circle(sx, sy, .88)
anchor('sensor_lens_center', LENS)
anchor('sensor_top_center', TOPRING)
anchor('left_lens_top_ring_center', TOPRING)
anchor('left_lens_optic_center', LENS + lens_axis * .30)
anchor('left_lens_base_front_center', at_z(206.1, 611.3, .02))

# ---------------------------------------------------------------- 右后穹顶、管线盒
# 参考是白色不透明头盔式穹顶 + 正面深色观察带，不是透明玻璃罩。
DOME = at_z(950, 385, 0)
dx, dy = DOME.x, DOME.y
lathe('dome_foot', [(0, .78), (.06, .86), (.16, .86), (.26, .79), (.32, .73)], DOME, M['white2'])
lathe('dome_base', [(.26, .75), (.34, .79), (.46, .79), (.54, .72), (.58, .67)], DOME, M['white2'])
torus('dome_seal', .72, .038, (dx, dy, .58), M['edge'])
for i in range(8):
    a = 2 * math.pi * i / 8
    box(f'dome_base_bolt_{i}', (.09, .12, .06),
        (dx + .71 * math.cos(a), dy + .71 * math.sin(a), .56), M['panel'], .010, (0, 0, a))
# 白色球冠：R=.78，中心 z=.34，顶点 z=1.16。
dome('dome_helmet', .78, .82, (dx, dy, .34), M['white'], 64, 24)
# 正面深色观察带，贴合球面，覆盖 -52°..+52°。
zv0, zv1, R, zc, hh = .48, 1.06, .78, .34, .82
verts, faces = [], []
rings, segs = 8, 18
for j in range(rings):
    z = zv0 + (zv1 - zv0) * j / (rings - 1)
    rr = R * math.sqrt(max(0.0, 1.0 - ((z - zc) / hh) ** 2)) + .014
    for i in range(segs):
        a = math.radians(-58 + 116 * i / (segs - 1))
        verts.append((dx + rr * math.sin(a), dy - rr * math.cos(a), z))
for j in range(rings - 1):
    for i in range(segs - 1):
        k = j * segs + i
        faces.append((k, k + 1, k + segs + 1, k + segs))
mesh('dome_visor', verts, faces, M['visor'])
# 观察带两侧的银色压条和铰链。
for side in (-1, 1):
    pipe(f'dome_visor_trim_{side}', [(dx + side * .61, dy - .40, .56), (dx + side * .48, dy - .58, 1.02)],
         .028, M['silver'], .10)
    cyl(f'dome_hinge_{side}', .08, .075, (dx + side * .70, dy - .26, .62), M['panel'],
        (0, math.pi / 2, 0), 24, .008)
torus('dome_top_ring', .13, .018, (dx, dy, 1.155), M['silver'], major=40, minor=8)
cyl('dome_top_hatch', .095, .035, (dx, dy, 1.165), M['white2'], verts=40, bevel=.008)
rounded_panel('dome_front_panel', (dx, dy - .745, .36), (1, 0, 0), (0, 0, 1), .54, .20, .035, M['panel'], .035)
circle(dx, dy, .92)
anchor('dome_base_center', DOME)
anchor('dome_top', (dx, dy, 1.16))
anchor('right_dome_top', (dx, dy, 1.16))
anchor('right_dome_window_center', (dx, dy - .58, .78))
anchor('right_dome_base_bottom', at_z(955, 386.6, .03))

PIPEBOX = at_z(865, 365, 0)
qx, qy = PIPEBOX.x, PIPEBOX.y
box('pipebox_body', (1.05, .72, .62), (qx, qy, .40), M['panel'], .10)
box('pipebox_lid', (.94, .68, .12), (qx, qy, .73), M['silver'], .05)
rounded_panel('pipebox_slot', (qx, qy - .375, .39), (1, 0, 0), (0, 0, 1), .48, .10, .035, M['dark'], .025)
for i in range(3):
    z = .12 + i * .11
    pts = [(qx - .48, qy - .18, .42 + i * .08), (qx - .82, qy - .40, .42 + i * .08),
           (qx - .88, qy - .95, z), (2.45, 2.55, z)]
    pipe(f'pipebox_tube_{i}', pts, .045, M['silver'], .24)
circle(qx, qy, .72)

# ---------------------------------------------------------------- 探测车：真实轮轴、轮胎、防滚架与仪表
# 轮距、轴距、朝向和整体高度按三个可见轮心与顶部横杆拟合；旧版偏大且偏高。
ROVER = at_z(964, 480, 0)
rx, ry = ROVER.x, ROVER.y
# 参考里鼻锥朝左下；旧 -43° 让车头偏左约 12px，改到 -33° 后轮心不动、鼻锥和防滚架对齐。
yaw = math.radians(-33)
ca, sa = math.cos(yaw), math.sin(yaw)
ROVER_SCALE = .86
rover_start = len(objs)

def RV(x, y, z):
    return Vector((rx + x * ca - y * sa, ry + x * sa + y * ca, z))

box('rover_chassis', (1.08, 1.70, .24), RV(0, 0, .40), M['dark'], .07, (0, 0, yaw))
box('rover_deck', (1.00, 1.52, .12), RV(0, 0, .56), M['white2'], .05, (0, 0, yaw))
box('rover_nose', (.94, .50, .26), RV(0, -.84, .56), M['white'], .065, (0, 0, yaw))
box('rover_front_grille', (.60, .06, .16), RV(0, -1.10, .55), M['dark'], .022, (0, 0, yaw))
for side in (-1, 1):
    box(f'rover_side_armor_{side}', (.15, 1.16, .30), RV(side * .56, .02, .62), M['white'], .04, (0, 0, yaw))
    box(f'rover_seat_{side}', (.38, .46, .15), RV(side * .27, .10, .74), M['rubber'], .06, (0, 0, yaw))
    box(f'rover_seat_back_{side}', (.38, .12, .40), RV(side * .27, .34, .92), M['dark'], .05, (0, 0, yaw))
    for yy in (-.62, .62):
        c = RV(side * .73, yy, .37)
        axis = Vector((ca, sa, 0))
        lathe(f'rover_tire_{side}_{yy}', [(-.16, .30), (-.13, .38), (.13, .38), (.16, .30)], c, M['rubber'], 48, axis)
        lathe(f'rover_hub_{side}_{yy}', [(-.17, .17), (-.06, .17), (.06, .17), (.17, .15)], c, M['panel'], 40, axis)
        cyl(f'rover_hub_cap_{side}_{yy}', .075, .36, c, M['dark'], axis.to_track_quat('Z', 'Y').to_euler(), 24, 0)
        for k in range(14):
            a = 2 * math.pi * k / 14
            # 胎纹小块沿轮轴和周向分布。
            center = c + Vector((-sa, ca, 0)) * (.355 * math.cos(a)) + Vector((0, 0, .355 * math.sin(a)))
            box(f'rover_tread_{side}_{yy}_{k}', (.27, .11, .06), center, M['black'], .010,
                (a, 0, yaw))
# 防滚架由圆管连续弯成，不是四根方梁；参考里是枪灰管，不是亮银。
for side in (-1, 1):
    pipe(f'rover_cage_side_{side}', [RV(side * .50, -.64, .58), RV(side * .50, -.50, .98),
                                    RV(side * .50, .50, 1.03), RV(side * .50, .70, .61)], .045, M['panel'], .18)
pipe('rover_cage_front', [RV(-.50, -.50, .98), RV(.50, -.50, .98)], .045, M['panel'])
pipe('rover_cage_rear', [RV(-.50, .50, 1.03), RV(.50, .50, 1.03)], .045, M['panel'])
pipe('rover_cage_cross', [RV(-.50, -.50, .98), RV(.50, .50, 1.03)], .035, M['edge'])
# 座椅后的裸露动力单元、散热片和排气管，补足参考里的深色机械块。
box('rover_engine', (.58, .42, .34), RV(0, .36, .78), M['black'], .035, (0, 0, yaw))
for i in range(5):
    box(f'rover_engine_fin_{i}', (.05, .36, .16), RV(-.20 + i * .10, .36, .95), M['panel'], .008, (0, 0, yaw))
for side in (-1, 1):
    pipe(f'rover_exhaust_{side}', [RV(side * .34, .40, .62), RV(side * .36, .46, .92),
                                  RV(side * .40, .50, 1.12)], .035, M['edge'], .10)
box('rover_console', (.66, .20, .28), RV(0, -.42, .86), M['panel'], .04, (math.radians(15), 0, yaw))
rounded_panel('rover_screen', RV(0, -.535, .93), (ca, sa, 0), (0, 0, 1), .36, .11, .03, M['glow_dim'], .022)
for side in (-1, 1):
    sphere(f'rover_headlight_{side}', .075, RV(side * .32, -1.10, .64), M['glow_dim'], (1, .45, .65), 24, 16)
pipe('rover_front_bumper', [RV(-.58, -1.02, .32), RV(-.42, -1.18, .28), RV(.42, -1.18, .28), RV(.58, -1.02, .32)], .045, M['panel'], .12)

# 所有探测车部件已经应用变换；统一围绕落地点缩小，保持轮心位置与参考一致。
for o in objs[rover_start:]:
    for v in o.data.vertices:
        v.co = ROVER + (v.co - ROVER) * ROVER_SCALE

def RVS(x, y, z):
    p = RV(x, y, z)
    return ROVER + (p - ROVER) * ROVER_SCALE

circle(rx, ry, 1.05)
anchor('rover_center', ROVER)
anchor('rover_cage_front', RVS(0, -.50, .98))
anchor('rover_rollcage_top', RVS(0, .50, 1.03))
anchor('rover_nose_center', RVS(0, -.84, .56))
anchor('rover_wheel_left_center', RVS(-.73, -.62, .37))
anchor('rover_wheel_right_center', RVS(.73, .62, .37))
anchor('rover_wheel_near_center', RVS(.73, -.62, .37))

# ---------------------------------------------------------------- 右侧立罐：旋转截面、环形盖与面板
CAN = at_z(1131.5, 585, 0)
cx, cy = CAN.x, CAN.y
lathe('can_foot', [(0, .56), (.08, .72), (.24, .72), (.33, .61)], CAN, M['white2'])
for i in range(8):
    a = 2 * math.pi * i / 8
    box(f'can_foot_block_{i}', (.16, .24, .16),
        (cx + .63 * math.cos(a), cy + .63 * math.sin(a), .10), M['panel'], .018, (0, 0, a))
lathe('can_body', [(.27, .53), (.40, .55), (1.56, .55), (1.67, .52)], CAN, M['white'])
for z in (.42, 1.55):
    torus(f'can_band_{z}', .55, .035, (cx, cy, z), M['edge'])
lathe('can_cap', [(1.62, .52), (1.70, .62), (1.82, .62), (1.91, .48), (2.00, .45)], CAN, M['panel'])
torus('can_cap_lip', .45, .04, (cx, cy, 2.00), M['white'])
cyl('can_cap_top', .38, .035, (cx, cy, 2.015), M['white2'], verts=64)
# 顶部不是一只平盖：加一圈收口、隆起顶盖和中央深色观察孔。
lathe('can_crown', [(1.99, .40), (2.05, .42), (2.13, .37), (2.21, .29), (2.27, .21)], CAN, M['white2'])
torus('can_crown_lip', .32, .025, (cx, cy, 2.22), M['edge'], major=48, minor=8)
cyl('can_crown_recess', .205, .025, (cx, cy, 2.245), M['dark'], verts=48)
cyl('can_crown_glass', .165, .014, (cx, cy, 2.258), M['visor'], verts=48)
for i in range(6):
    a = 2 * math.pi * i / 6
    box(f'can_crown_clip_{i}', (.055, .07, .08),
        (cx + .35 * math.cos(a), cy + .35 * math.sin(a), 2.03), M['edge'], .010, (0, 0, a))
for i in range(8):
    a = 2 * math.pi * i / 8
    cyl(f'can_bolt_{i}', .035, .035, (cx + .50 * math.cos(a), cy + .50 * math.sin(a), 1.86), M['dark'], verts=8, bevel=0)
# 面板中心由参考像素反投影，不按轴心居中；参考面板明显偏左。
rounded_panel('can_front_frame', (cx - .206, cy - .555, 1.035), (1, 0, 0), (0, 0, 1), .84, 1.12, .05, M['edge'], .065)
rounded_panel('can_front_panel', (cx - .206, cy - .59, 1.035), (1, 0, 0), (0, 0, 1), .68, .94, .035, M['silver'], .048)
rounded_panel('can_front_display', (cx - .236, cy - .612, 1.245), (1, 0, 0), (0, 0, 1), .40, .20, .018, M['visor'], .028)
for i in range(3):
    box(f'can_front_vent_{i}', (.46, .020, .026), (cx - .206, cy - .614, .86 + i * .075), M['edge'], .004)
box('can_panel_split', (.70, .028, .035), (cx - .206, cy - .618, 1.36), M['dark'], .005)
for side in (-1, 1):
    rounded_panel(f'can_side_screen_{side}', (cx + side * .47, cy + .16, 1.28), (0, side, 0), (0, 0, 1),
                  .26, .16, .035, M['visor'], .04)
circle(cx, cy, .78)
anchor('canister_cap_center', (cx, cy, 2.00))
anchor('canister_panel_center', at_y(1128.8, 534.9, cy - .59))
anchor('canister_base_center', at_z(1131.6, 602.8, .03))
anchor('can_base_center', CAN)
anchor('can_cap_center', (cx, cy, 2.02))

# ---------------------------------------------------------------- 近景横向机组：法兰、机壳、开放电机与连接管
FORE_L = at_z(734, 638, 0)
FORE_R = at_z(937, 638, 0)
fy = (FORE_L.y + FORE_R.y) / 2
lx, rx2 = FORE_L.x, FORE_R.x
axis_z = .86
# 左机壳两端的旋转法兰；参考端面跨度比旧版宽约 13px。
lathe('fore_left_flanges', [(-1.07, .44), (-1.01, .64), (-.87, .67), (-.77, .60),
                            (.67, .60), (.79, .67), (.93, .64), (1.01, .44)], (lx, fy, axis_z), M['silver'], 80, (1, 0, 0))
lathe('fore_left_core', [(-.79, .50), (.69, .50)], (lx, fy, axis_z), M['dark'], 64, (1, 0, 0))
for side in (-1, 1):
    x = lx + side * 1.055
    lathe(f'fore_flange_plate_{side}', [(-.045, .66), (-.025, .69), (.035, .69), (.055, .63)],
          (x, fy, axis_z), M['white2'], 80, (1, 0, 0))
    torus(f'fore_flange_rim_{side}', .47, .028, (x - side * .055, fy, axis_z), M['edge'],
          (0, math.pi / 2, 0), major=64, minor=8)
    for i in range(8):
        a = 2 * math.pi * i / 8
        cyl(f'fore_flange_face_bolt_{side}_{i}', .022, .03, (x - side * .075, fy + .33 * math.cos(a), axis_z + .33 * math.sin(a)),
            M['panel'], (0, math.pi / 2, 0), 8, 0)
    for i in range(12):
        a = 2 * math.pi * i / 12
        cyl(f'fore_flange_bolt_{side}_{i}', .032, .050, (x, fy + .585 * math.cos(a), axis_z + .585 * math.sin(a)),
            M['dark'], (0, math.pi / 2, 0), 8, 0)
# 左机壳不是一只光滑盒子：下部承力框、上部圆弧盖、顶脊和分段侧甲。
box('fore_left_cowling', (1.30, .92, .86), (lx, fy - .03, axis_z + .05), M['white2'], .10)
lathe('fore_left_top_hump', [(-.62, .22), (-.52, .34), (-.40, .40), (.40, .40), (.52, .34), (.62, .22)],
      (lx, fy + .02, axis_z + .18), M['white'], 64, (1, 0, 0))
box('fore_left_top_hatch', (.88, .56, .10), (lx - .04, fy + .03, axis_z + .61), M['white'], .045)
box('fore_left_top_ridge', (1.10, .22, .10), (lx - .01, fy + .18, axis_z + .58), M['white2'], .035)
# 正面斜切装甲面：上部略向前倾，给屏幕一个真实的安装基面。
box('fore_left_brow', (1.08, .30, .22), (lx - .02, fy - .36, axis_z + .34), M['white'], .035,
    (math.radians(-14), 0, 0))
box('fore_left_face_plate', (1.02, .16, .34), (lx - .03, fy - .40, axis_z - .10), M['white'], .03)
for side in (-1, 1):
    box(f'fore_left_side_plate_{side}', (.11, .82, .46), (lx + side * .60, fy - .02, axis_z + .12), M['white'], .035)
    box(f'fore_left_side_seam_{side}', (.030, .70, .30), (lx + side * .657, fy - .03, axis_z + .12), M['edge'], .006)
    box(f'fore_left_side_lower_{side}', (.14, .70, .18), (lx + side * .58, fy - .04, axis_z - .24), M['panel'], .022)
    for k in (0, 1):
        cyl(f'fore_side_bolt_{side}_{k}', .026, .028, (lx + side * .668, fy + (-.28 + k * .52), axis_z + .26),
            M['edge'], (0, math.pi / 2, 0), 8, 0)
# 右前侧圆形检修口和螺栓圈。
torus('fore_side_port', .155, .028, (lx + .665, fy - .06, axis_z + .20), M['edge'], (0, math.pi / 2, 0), major=40, minor=8)
cyl('fore_side_port_glass', .135, .02, (lx + .672, fy - .06, axis_z + .20), M['visor'], (0, math.pi / 2, 0), 40, 0)
for i in range(6):
    a = 2 * math.pi * i / 6
    cyl(f'fore_side_port_bolt_{i}', .019, .02, (lx + .676, fy - .06 + .20 * math.cos(a), axis_z + .20 + .20 * math.sin(a)),
        M['panel'], (0, math.pi / 2, 0), 8, 0)
# 屏幕吊舱：真实凸出的盒体、上檐、侧支架和倾斜屏面。
bp_screen = at_y(718.4, 557.0, fy - .45)
bp_slot = at_y(724.1, 617.0, fy - .45)
screen_v = Vector((0, .50, .866)).normalized()
screen_n = Vector((1, 0, 0)).cross(screen_v).normalized()
pod_center = bp_screen - screen_n * .10
box('fore_screen_pod', (1.00, .44, .26), pod_center, M['white'], .055, (math.radians(-30), 0, 0))
box('fore_screen_brow', (1.04, .07, .08), bp_screen - screen_n * .055 + screen_v * .17, M['white2'], .018)
rounded_panel('fore_left_screen_frame', bp_screen, (1, 0, 0), screen_v, .92, .30, .05, M['edge'], .048)
rounded_panel('fore_left_screen', bp_screen + screen_n * .008,
              (1, 0, 0), screen_v, .78, .17, .035, M['glow_dim'], .030)
for side in (-1, 1):
    box(f'fore_screen_bracket_{side}', (.055, .13, .12),
        bp_screen - screen_n * .035 + Vector((side * .45, 0, 0)), M['panel'], .012)
# 屏幕下方的三条横向散热缝和铆钉。
for i in range(3):
    box(f'fore_face_slit_{i}', (.58, .025, .022),
        (lx - .06, fy - .468, axis_z + .08 - i * .085), M['edge'], .004)
# 下部抓手凹槽：黑色内腔 + 银色横杆 + 两侧端盖。
rounded_panel('fore_left_vent_frame', bp_slot, (1, 0, 0), (0, 0, 1), 1.04, .52, .05, M['silver'], .055)
rounded_panel('fore_left_vent', bp_slot - Vector((0, .025, 0)), (1, 0, 0), (0, 0, 1), .94, .44, .07, M['black'], .045)
for i in range(3):
    box(f'fore_vent_bar_{i}', (.86, .025, .026),
        (bp_slot.x, bp_slot.y - .075, bp_slot.z - .13 + i * .13), M['panel'], .005)
box('fore_grip_bar', (.78, .06, .06), (bp_slot.x, bp_slot.y - .10, bp_slot.z), M['silver'], .018)
for side in (-1, 1):
    box(f'fore_grip_cap_{side}', (.07, .08, .12), (bp_slot.x + side * .45, bp_slot.y - .085, bp_slot.z), M['edge'], .014)
    for k in range(2):
        cyl(f'fore_face_bolt_{side}_{k}', .022, .026,
            (bp_slot.x + side * .52, bp_slot.y - .055, bp_slot.z + (-.20 + k * .40)),
            M['edge'], (math.pi / 2, 0, 0), 8, 0)
box('fore_left_bumper', (1.12, .08, .16), (lx - .03, fy - .45, axis_z - .34), M['black'], .02)
box('fore_left_chin', (1.06, .18, .12), (lx - .02, fy - .36, axis_z - .46), M['white2'], .03)
# 顶部小把手，呼应参考中屏幕后方的细支架。
pipe('fore_top_handle', [(lx - .30, fy - .12, axis_z + .70), (lx - .30, fy - .12, axis_z + .80),
                         (lx + .16, fy - .12, axis_z + .80), (lx + .16, fy - .12, axis_z + .70)], .028, M['silver'], .08)
# 中间裸露轴系与右侧开放电机；电机端环间距扩到参考的 125px。
lathe('fore_shaft', [(lx + .95, .21), (rx2 - .86, .21)], (0, fy, axis_z), M['dark'], 48, (1, 0, 0))
lathe('fore_shaft_collar_l', [(lx + 1.03, .27), (lx + 1.14, .27)], (0, fy, axis_z), M['silver'], 40, (1, 0, 0))
lathe('fore_shaft_collar_r', [(rx2 - 1.00, .30), (rx2 - .86, .30)], (0, fy, axis_z), M['edge'], 40, (1, 0, 0))
lathe('fore_motor_core', [(-.72, .34), (.72, .34)], (rx2, fy, axis_z), M['black'], 64, (1, 0, 0))
# 开放电机：内鼓 + 八根厚肋 + 两道箍，肋间能看到黑色内腔。
for i in range(8):
    a = 2 * math.pi * i / 8
    y, z = fy + .455 * math.cos(a), axis_z + .455 * math.sin(a)
    box(f'fore_motor_fin_{i}', (1.18, .12, .16), (rx2, y, z), M['edge'], .022, (a, 0, 0))
for x in (rx2 - .38, rx2 + .38):
    torus(f'fore_motor_band_{x:.2f}', .50, .042, (x, fy, axis_z), M['dark'], (0, math.pi / 2, 0), major=64, minor=10)
for x in (rx2 - .84, rx2 + .84):
    lathe(f'fore_motor_ring_{x:.2f}', [(-.13, .46), (-.09, .58), (-.02, .62), (.07, .62), (.11, .52)],
          (x, fy, axis_z), M['silver'], 80, (1, 0, 0))
    lathe(f'fore_motor_ring_face_{x:.2f}', [(-.16, .40), (-.13, .46)], (x, fy, axis_z), M['edge'], 64, (1, 0, 0))
    for i in range(10):
        a = 2 * math.pi * i / 10
        cyl(f'fore_motor_bolt_{x:.2f}_{i}', .023, .028,
            (x + (.145 if x > rx2 else -.145), fy + .52 * math.cos(a), axis_z + .52 * math.sin(a)),
            M['dark'], (0, math.pi / 2, 0), 8, 0)
# 顶部端子盒：厚方块、五枚散热鳍和正面 U 形把手。
box('fore_motor_terminal', (.78, .56, .30), (rx2 - .12, fy + .02, axis_z + .64), M['edge'], .055)
box('fore_terminal_base', (.86, .62, .10), (rx2 - .12, fy + .02, axis_z + .47), M['dark'], .025)
for i in range(5):
    box(f'fore_terminal_fin_{i}', (.060, .54, .15), (rx2 - .44 + i * .12, fy + .02, axis_z + .85), M['silver'], .014)
pipe('fore_terminal_handle', [(rx2 - .34, fy - .29, axis_z + .58), (rx2 - .34, fy - .34, axis_z + .78),
                              (rx2 + .12, fy - .34, axis_z + .78), (rx2 + .12, fy - .29, axis_z + .58)],
     .030, M['silver'], .06)
# 右端双弯管接入立罐。
for i in range(2):
    z = .34 + i * .22
    pipe(f'fore_can_pipe_{i}', [(rx2 + .94, fy, axis_z), (rx2 + 1.12, fy, axis_z),
                                (rx2 + 1.18, fy, z), (cx - .65, cy - .20, z), (cx - .48, cy - .20, z)], .055, M['silver'], .18)
obstacle(lx - 1.12, rx2 + 1.10, fy - .74, fy + .74)
anchor('fore_left_axis', (lx, fy, axis_z))
anchor('fore_motor_axis', (rx2, fy, axis_z))
anchor('fore_flange_left_center', (lx - 1.07, fy, axis_z))
anchor('fore_core_screen_center', bp_screen)
anchor('fore_core_slot_center', bp_slot)
anchor('fore_flange_right_center', (lx + 1.01, fy, axis_z))
anchor('fore_motor_left_flange_center', (rx2 - .84, fy, axis_z))
anchor('fore_motor_vent_center', (rx2 - .085, fy, axis_z + .10))
anchor('fore_motor_cap_center', (rx2 + .84, fy, axis_z))

# ---------------------------------------------------------------- 远景：内翻程序天空；参考天空板后续在运行时叠加到同一天空层。
bpy.ops.mesh.primitive_uv_sphere_add(radius=150, segments=96, ring_count=48, location=(0, 0, 0))
sky = bpy.context.active_object
sky.name = 'sky_dome'
sky.rotation_euler = (0, 0, math.radians(70))
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.flip_normals()
bpy.ops.object.mode_set(mode='OBJECT')
finish(sky, M['sky'], 0, True)

light((-6, -2, 9), (1, .95, .86), 24, 18)
light((6, 2, 7), (.65, .76, 1), 12, 15)
light((0, -5, 4), (.9, .95, 1), 7, 10)

META['walk'] = {'minX': -6.7, 'maxX': 6.7, 'minY': -4.1, 'maxY': 4.3}
META['spawn'] = {'x': 0., 'y': -1.55}
META['animated']['pilot'] = {'x': px, 'y': py, 'z': 1.9}
META['referenceCamera'] = {
    'radius': RADIUS, 'beta': BETA, 'fov': FOV,
    'position': list(CAM_POS), 'target': list(TARGET),
}
META['referenceHash'] = hashlib.sha256((ROOT / 'refs/lookout_deck.png').read_bytes()).hexdigest()


def render_preview(path):
    scene = bpy.context.scene
    world = bpy.data.worlds.new('w')
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.16, .175, .20, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = .55
    # 网页主光的近似预览，只用于检查几何。
    for name, loc, energy, size, color in (
        ('key', (-7, -10, 14), 1500, 12.0, (1, .95, .87)),
        ('fill', (8, -1, 10), 750, 10.0, (.62, .75, 1)),
    ):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy, ld.shape, ld.size, ld.color = energy, 'DISK', size, color
        ob = bpy.data.objects.new(name, ld)
        bpy.context.collection.objects.link(ob)
        ob.location = loc
        ob.rotation_euler = (Vector((0, 0, 0)) - ob.location).to_track_quat('-Z', 'Y').to_euler()
    # META 里的点光只给运行时使用；预览里若照搬会形成硬黑阴影，干扰形体判断。
    cam_data = bpy.data.cameras.new('ref_cam')
    cam_data.lens = FOCAL * 36 / 1280
    cam_data.sensor_width = 36
    cam_data.sensor_fit = 'HORIZONTAL'
    cam_data.clip_end = 400
    cam = bpy.data.objects.new('ref_cam', cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = CAM_POS
    cam.rotation_euler = (TARGET - CAM_POS).to_track_quat('-Z', 'Y').to_euler()
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
    scene.view_settings.exposure = .2
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
