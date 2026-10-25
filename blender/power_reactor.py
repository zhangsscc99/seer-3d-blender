"""动力室 I 反应堆：米白分块蛋形外壳、竖向观察窗 + 两道横肋、橙色火焰核心、黄铜弯管、深色底座。

独立审核（不触碰场景资产）：
  Blender -b -P blender/power_reactor.py -- --out renders/reactor_v1
build_reactor 可由动力室房间脚本复用；正面朝 Blender -Y。
"""
import math
import sys
from pathlib import Path
import bpy
import bmesh
from mathutils import Vector

HERE = Path(__file__).resolve().parent
PIPE_R_END = (0., 0.)  # 右侧铜管落地点（未缩放的局部坐标），供房间放置接口座
_mats = {}


def material(name, color, rough=.35, metal=0., emit=None, strength=0., coat=0., image=None):
    if name in _mats:
        return _mats[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bs = nt.nodes['Principled BSDF']
    bs.inputs['Base Color'].default_value = (*color, 1)
    bs.inputs['Metallic'].default_value = metal
    bs.inputs['Roughness'].default_value = rough
    bs.inputs['Coat Weight'].default_value = coat
    if emit or image:
        bs.inputs['Emission Color'].default_value = (*(emit or (1, 1, 1)), 1)
        bs.inputs['Emission Strength'].default_value = strength
    if image:
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = bpy.data.images.load(str(image))
        nt.links.new(tex.outputs['Color'], bs.inputs['Emission Color'])
        nt.links.new(tex.outputs['Color'], bs.inputs['Base Color'])
    _mats[name] = m
    return m


def materials():
    return dict(
        cream=material('pw_cream', (.52, .49, .42), .31, .38, coat=.35),
        cream_l=material('pw_cream_light', (.65, .61, .52), .29, .32, coat=.4),
        brass=material('pw_brass', (.86, .52, .26), .24, 1.),
        gun=material('pw_gunmetal', (.07, .08, .09), .42, .8),
        glow=material('pw_glow_cyan', (.02, .12, .16), .4, emit=(.25, .85, 1.), strength=4.),
        flame=material('pw_flame', (1, .5, .1), .5, emit=(1, 1, 1), strength=5.5, image=HERE / 'flame.png'),
        jamb=material('pw_jamb', (.32, .16, .07), .38, .7, emit=(1, .55, .2), strength=1.),
        screen=material('pw_screen', (.01, .02, .03), .25, emit=(1., .72, .25), strength=.6),
    )


# 蛋形外轮廓：下半椭圆更长（底部宽），上半收得更快。
R, ZC, HB, HT, Z0, ZTOP = 1.34, 1.9, 4.6, 2.2, .14, 4.1


def egg(z):
    h = HB if z < ZC else HT
    return R * math.sqrt(max(0., 1 - ((z - ZC) / h) ** 2))


def build_reactor(prefix='reactor', origin=(0, 0, 0), scale=1., yaw=0.):
    M = materials()
    objects = []

    def finish(o, mat, bevel=0., smooth=True):
        o.data.materials.append(mat)
        for p in getattr(o.data, 'polygons', ()):
            p.use_smooth = smooth
        if bevel:
            b = o.modifiers.new('bevel', 'BEVEL')
            b.width = bevel
            b.segments = 3
            b.limit_method = 'ANGLE'
            b.angle_limit = math.radians(40)
            o.modifiers.new('wn', 'WEIGHTED_NORMAL').keep_sharp = True
        objects.append(o)
        return o

    def from_data(name, verts, faces, mat, bevel=0.):
        me = bpy.data.meshes.new(f'{prefix}_{name}')
        me.from_pydata(verts, [], faces)
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-6)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(f'{prefix}_{name}', me)
        bpy.context.collection.objects.link(o)
        return finish(o, mat, bevel)

    def patch(name, a0, a1, z0, z1, mat, off=0., t=.12, bevel=.025, na=None, nz=None):
        # 旋转体壳片：角度 a（0=正前方 -Y），外表面沿蛋形外扩 off，厚度 t。
        na = na or max(4, int(abs(a1 - a0) / math.radians(4)))
        nz = nz or max(2, int((z1 - z0) / .08))
        verts = []
        for side in (0, 1):
            for i in range(nz + 1):
                z = z0 + (z1 - z0) * i / nz
                r = egg(z) + off - side * t
                for j in range(na + 1):
                    a = a0 + (a1 - a0) * j / na
                    verts.append((r * math.sin(a), -r * math.cos(a), z))
        W = na + 1
        L = (nz + 1) * W
        idx = lambda s, i, j: s * L + i * W + j
        faces = []
        for i in range(nz):
            for j in range(na):
                faces.append((idx(0, i, j), idx(0, i, j + 1), idx(0, i + 1, j + 1), idx(0, i + 1, j)))
                faces.append((idx(1, i, j), idx(1, i + 1, j), idx(1, i + 1, j + 1), idx(1, i, j + 1)))
        for j in range(na):
            faces.append((idx(0, 0, j), idx(1, 0, j), idx(1, 0, j + 1), idx(0, 0, j + 1)))
            faces.append((idx(0, nz, j), idx(0, nz, j + 1), idx(1, nz, j + 1), idx(1, nz, j)))
        for i in range(nz):
            faces.append((idx(0, i, 0), idx(0, i + 1, 0), idx(1, i + 1, 0), idx(1, i, 0)))
            faces.append((idx(0, i, na), idx(1, i, na), idx(1, i + 1, na), idx(0, i + 1, na)))
        return from_data(name, verts, faces, mat, bevel)

    def prim(kind, name, mat, bevel=0., smooth=False, **kw):
        getattr(bpy.ops.mesh, f'primitive_{kind}_add')(**kw)
        o = bpy.context.active_object
        o.name = f'{prefix}_{name}'
        o.data.name = o.name
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        return finish(o, mat, bevel, smooth)

    def box(name, size, loc, mat, bevel=.03, rot=(0, 0, 0)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
        o = bpy.context.active_object
        o.scale = size
        o.name = f'{prefix}_{name}'
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        return finish(o, mat, bevel, smooth=bevel > 0)

    def pipe(name, pts, r, mat, fillet=.28):
        # 折线 + 圆角弯头；转网格后统一烘焙。
        P = [Vector(p) for p in pts]
        path = [P[0]]
        for k in range(1, len(P) - 1):
            a, b, c = P[k - 1], P[k], P[k + 1]
            d = min(fillet, (b - a).length / 2, (c - b).length / 2)
            s, e = b + (a - b).normalized() * d, b + (c - b).normalized() * d
            for i in range(9):
                t = i / 8
                path.append((1 - t) ** 2 * s + 2 * (1 - t) * t * b + t * t * e)
        path.append(P[-1])
        cu = bpy.data.curves.new(f'{prefix}_{name}', 'CURVE')
        cu.dimensions = '3D'
        cu.bevel_depth = r
        cu.bevel_resolution = 6
        cu.use_fill_caps = True
        sp = cu.splines.new('POLY')
        sp.points.add(len(path) - 1)
        for p, co in zip(sp.points, path):
            p.co = (*co, 1)
        o = bpy.data.objects.new(f'{prefix}_{name}', cu)
        bpy.context.collection.objects.link(o)
        return finish(o, mat)

    def collar(name, at, direction, r, length, mat):
        d = Vector(direction).normalized()
        rot = d.to_track_quat('Z', 'Y').to_euler()
        return prim('cylinder', name, mat, bevel=.012, radius=r, depth=length, vertices=40,
                    location=at, rotation=rot)

    deg = math.radians
    WIN = deg(50)          # 外壳开口半张角
    GLASS = deg(36)        # 发光玻璃半张角；两者之间是深色凹陷窗框
    G = deg(1.1)           # 壳片缝隙
    # ---------------- 外壳分块
    bands = [(Z0, 1.0), (1.0, 1.86), (1.86, 3.06), (3.06, 3.62)]
    for bi, (z0, z1) in enumerate(bands):
        if bi in (1, 2):
            cuts = [WIN, deg(100), deg(150), deg(210), deg(260), deg(360) - WIN]
        elif bi == 0:
            cuts = [deg(-30 + 60 * k) for k in range(7)]
        else:
            cuts = [deg(-28), deg(28), deg(95), deg(150), deg(210), deg(265), deg(332)]
        for k in range(len(cuts) - 1):
            a0, a1 = cuts[k] + G, cuts[k + 1] - G
            front_top = bi == 3 and k == 0
            patch(f'shell_{bi}_{k}', a0, a1, z0 + .012, z1 - .012,
                  M['cream_l'] if front_top else M['cream'], off=.03 if front_top else 0.)
    # 壳片后的深色内衬，避免核心光从缝隙透出。
    patch('liner_mid', WIN + deg(2), deg(360) - WIN - deg(2), 1.0, 3.06, M['gun'], off=-.12, t=.04, bevel=0)
    patch('liner_low', 0, deg(359.5), Z0, 1.0, M['gun'], off=-.12, t=.04, bevel=0)
    patch('liner_top', 0, deg(359.5), 3.06, 3.7, M['gun'], off=-.12, t=.04, bevel=0)
    patch('shell_cap', 0, deg(359.5), 3.63, ZTOP - .02, M['cream'], t=.2, bevel=.02, nz=8)

    # ---------------- 观察窗：铜色内框 + 两道横肋
    for s in (-1, 1):
        a = s * GLASS
        patch(f'jamb_{s}', min(s * GLASS, s * WIN), max(s * GLASS, s * WIN), 1.0, 3.06, M['jamb'], off=-.06, t=.1, bevel=.015)
        pts = [((egg(z) - .1) * math.sin(a), -(egg(z) - .1) * math.cos(a), z) for z in
               [1.0 + i * .1 for i in range(21)]]
        pipe(f'win_frame_{s}', pts, .025, M['brass'], fillet=.01)
    top = [((egg(3.04) - .1) * math.sin(a), -(egg(3.04) - .1) * math.cos(a), 3.04) for a in
           [-GLASS + 2 * GLASS * i / 24 for i in range(25)]]
    pipe('win_frame_top', top, .025, M['brass'], fillet=.01)
    patch('rib_big', -WIN - deg(7), WIN + deg(7), 1.66, 1.89, M['cream_l'], off=.12, t=.29, bevel=.05)
    patch('rib_low', -WIN - deg(6), WIN + deg(6), 0.99, 1.18, M['cream_l'], off=.10, t=.28, bevel=.045)
    patch('lintel', -WIN - deg(3), WIN + deg(3), 3.0, 3.12, M['cream_l'], off=.05, t=.3, bevel=.03)
    box('lintel_plate', (.5, .08, .3), (0, -egg(3.32) - .03, 3.32), M['cream_l'], bevel=.03, rot=(-.42, 0, 0))

    # ---------------- 火焰核心（UV 圆柱，网页端滚动 UV）
    core = prim('cylinder', 'flame_core', M['flame'], smooth=True, radius=1., depth=2.1, vertices=64,
                location=(0, 0, 2.05))
    # 按蛋形逐层收放半径，让火焰贴近玻璃而不穿出上部壳片。
    for v in core.data.vertices:
        k = egg(v.co.z) - .15
        v.co.x *= k
        v.co.y *= k
    core.name = 'flame_core' if prefix == 'reactor' else f'{prefix}_flame_core'

    # ---------------- 下部检修单元
    unit_start = len(objects)
    box('unit_body', (.8, .5, .62), (0, -.98, .5), M['cream_l'], bevel=.05)
    box('unit_screen_frame', (.56, .04, .22), (0, -1.24, .62), M['gun'], bevel=.012)
    box('unit_screen', (.48, .02, .15), (0, -1.262, .62), M['screen'], bevel=0)
    box('unit_chip', (.08, .02, .08), (.0, -1.275, .62), M['flame'], bevel=0)
    box('unit_drawer', (.58, .44, .25), (0, -1.0, .24), M['cream'], bevel=.04)
    box('unit_drawer_face', (.5, .03, .18), (0, -1.225, .24), M['brass'], bevel=.015)
    for s in (-1, 1):
        box(f'unit_pillar_{s}', (.26, .5, .82), (s * .56, -1.0, .55), M['cream'], bevel=.06)
        box(f'unit_pillar_cap_{s}', (.3, .54, .08), (s * .56, -1.01, .97), M['cream_l'], bevel=.03)

    # 机身加胖后整体前移，保持检修单元凸出壳面。
    for o in objects[unit_start:]:
        for v in o.data.vertices:
            v.co.y -= .08
    # ---------------- 底座
    prim('cylinder', 'base', M['gun'], bevel=.03, radius=1.5, depth=.14, vertices=72, location=(0, 0, .07))
    prim('cylinder', 'base_top', M['gun'], bevel=.015, radius=1.28, depth=.05, vertices=72, location=(0, 0, .16))
    box('glow_strip_front', (.5, .05, .035), (0, -1.44, .15), M['glow'], bevel=.01)
    for k in range(4):
        a = deg(28 + k * 6)
        box(f'glow_dot_{k}', (.07, .05, .035), (1.4 * math.sin(a), -1.4 * math.cos(a), .15), M['glow'],
            bevel=.008, rot=(0, 0, a))

    # ---------------- 黄铜管：左侧低位下折入地，右侧高位水平伸出
    def on_shell(a, z, extra=0.):
        r = egg(z) + extra
        return Vector((r * math.sin(a), -r * math.cos(a), z))

    aL = deg(-72)
    out = Vector((math.sin(aL), -math.cos(aL), 0))
    p0 = on_shell(aL, 1.42, -.05)
    p1 = p0 + out * .4 + Vector((0, 0, -.3))
    p2 = p1 + out * .25 + Vector((0, 0, -.25))
    p3 = Vector((p2.x, p2.y, -.2))
    pipe('pipe_left', [p0, p1, p2, p3], .2, M['brass'], fillet=.18)
    collar('pipe_left_flange', on_shell(aL, 1.42, .04), out, .32, .12, M['brass'])
    collar('pipe_left_ring', p1 + out * .05, out, .24, .1, M['brass'])
    collar('pipe_left_ring2', p2 + Vector((0, 0, -.12)), (0, 0, 1), .24, .1, M['brass'])
    collar('pipe_left_foot', Vector((p3.x, p3.y, .08)), (0, 0, 1), .28, .16, M['brass'])

    aR = deg(88)
    outR = Vector((math.sin(aR), -math.cos(aR), 0))
    q0 = on_shell(aR, 2.3, -.05)
    q1 = q0 + outR * .95
    q2 = Vector((q1.x, q1.y, 1.28))
    global PIPE_R_END
    PIPE_R_END = (q2.x, q2.y)
    pipe('pipe_right', [q0, q1, q2], .19, M['brass'], fillet=.2)
    collar('pipe_right_flange', on_shell(aR, 2.3, .04), outR, .31, .12, M['brass'])
    collar('pipe_right_ring', q0 + outR * .4, outR, .23, .09, M['brass'])
    collar('pipe_right_end', q2 + Vector((0, 0, .04)), (0, 0, 1), .3, .12, M['brass'])

    # 曲线转网格；放置变换烘进顶点，便于房间脚本整体复用。
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:
        if o.type == 'CURVE':
            bpy.context.view_layer.objects.active = o
            o.select_set(True)
            bpy.ops.object.convert(target='MESH')
            o.select_set(False)
        c, s = math.cos(yaw), math.sin(yaw)
        for v in o.data.vertices:
            x, y, z = v.co
            v.co = (origin[0] + scale * (x * c - y * s), origin[1] + scale * (x * s + y * c), origin[2] + scale * z)
    return objects


def preview(out):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects = build_reactor()
    scene = bpy.context.scene
    world = bpy.data.worlds.new('studio')
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.2, .22, .24, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = .6
    bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.data.materials.append(material('preview_floor', (.05, .055, .06), .5, .7))
    for name, loc, power, size, col in [('key', (-4, -6, 7), 900, 5, (1, .97, .92)),
                                        ('fill', (5, -3, 3), 300, 4, (.75, .85, 1)),
                                        ('rim', (0, 5, 6), 500, 4, (.8, .9, 1))]:
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy, ld.shape, ld.size, ld.color = power, 'DISK', size, col
        ob = bpy.data.objects.new(name, ld)
        bpy.context.collection.objects.link(ob)
        ob.location = loc
        ob.rotation_euler = (-ob.location).to_track_quat('-Z', 'Y').to_euler()
    core = bpy.data.lights.new('core', 'POINT')
    core.energy, core.color, core.shadow_soft_size = 250, (1, .55, .15), .8
    ob = bpy.data.objects.new('core', core)
    bpy.context.collection.objects.link(ob)
    ob.location = (0, -.4, 2.1)
    cam_data = bpy.data.cameras.new('cam')
    cam_data.lens = 40
    cam = bpy.data.objects.new('cam', cam_data)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 800, 900
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.exposure = -.35
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    for label, loc in [('front', (0, -9.5, 2.6)), ('reference', (-.6, -8.5, 5.4)), ('three_quarter', (6.2, -6.8, 4.0))]:
        cam.location = loc
        cam.rotation_euler = (Vector((0, 0, 1.75)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = str(out / f'{label}.png')
        bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out / 'reactor.blend'))
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:
        o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(out / 'reactor.glb'), export_format='GLB', use_selection=True,
                              export_apply=True)
    print('REACTOR review ready:', out)


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    preview(args[args.index('--out') + 1] if '--out' in args else 'renders/reactor_review')
