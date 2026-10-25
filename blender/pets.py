"""赛尔号跟随宠物 —— 纯程序化建模：布布种子 / 小火猴 / 伊优 / 米咔。

每只宠物正面朝 Blender -Y，脚底在 z=0；导出独立 GLB，并渲染透明背景背包图标。

用法:
  Blender -b -P blender/pets.py -- \
      --glb public/models/player/pets --icons public/ui/pets \
      [--only bubu,huohou] [--no-render] [--samples 24]
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


GLB_DIR = Path(arg('--glb', 'public/models/player/pets')).resolve()
ICON_DIR = Path(arg('--icons', 'public/ui/pets')).resolve()
ONLY = [x for x in (arg('--only', '') or '').split(',') if x]
RENDER = '--no-render' not in argv
SAMPLES = int(arg('--samples', '24'))

OBJS = []


def reset():
    global OBJS
    bpy.ops.wm.read_factory_settings(use_empty=True)
    OBJS = []


def material(name, color, rough=.35, metal=0., emit=None, strength=0., coat=0.):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bs = m.node_tree.nodes['Principled BSDF']
    bs.inputs['Base Color'].default_value = (*color, 1)
    bs.inputs['Metallic'].default_value = metal
    bs.inputs['Roughness'].default_value = rough
    bs.inputs['Coat Weight'].default_value = coat
    if emit:
        bs.inputs['Emission Color'].default_value = (*emit, 1)
        bs.inputs['Emission Strength'].default_value = strength
    return m


def finish(o, mat, bevel=0., smooth=True):
    o.data.materials.append(mat)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    o.select_set(False)
    for p in getattr(o.data, 'polygons', ()):
        p.use_smooth = smooth
    if bevel:
        b = o.modifiers.new('bevel', 'BEVEL')
        b.width, b.segments, b.limit_method = bevel, 2, 'ANGLE'
        o.modifiers.new('wn', 'WEIGHTED_NORMAL').keep_sharp = True
    OBJS.append(o)
    return o


def sphere(name, r, loc, mat, scale=(1, 1, 1), rot=(0, 0, 0), segs=40, rings=20):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=segs, ring_count=rings, location=loc)
    o = bpy.context.active_object
    o.name, o.scale, o.rotation_euler = name, scale, rot
    return finish(o, mat)


def ell(name, loc, rx, ry, rz, mat, rot=(0, 0, 0)):
    return sphere(name, 1., loc, mat, (rx, ry, rz), rot)


def cone(name, r1, r2, h, loc, mat, rot=(0, 0, 0), verts=32):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=h, vertices=verts,
                                    location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    return finish(o, mat)


def torus(name, R, r, loc, mat, rot=(0, 0, 0), major=48, minor=10):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=major,
                                     minor_segments=minor, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    return finish(o, mat)


def recalc(o):
    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    me.update()


def teardrop(name, p0, p1, width, depth, mat, bulge=.75, steps=14, sections=12):
    """两端收尖的叶片/火苗/鳍：沿 p0→p1 的轴，截面为椭圆。"""
    a, b = Vector(p0), Vector(p1)
    axis = b - a
    d = axis.normalized()
    ref = Vector((0, 0, 1)) if abs(d.z) < .9 else Vector((0, 1, 0))
    u = d.cross(ref).normalized()
    v = d.cross(u).normalized()
    verts = [tuple(a)]
    for k in range(1, steps):
        t = k / steps
        c = a + axis * t
        taper = math.sin(math.pi * t) ** bulge
        for j in range(sections):
            ang = math.tau * j / sections
            p = c + u * (width * taper * math.cos(ang)) + v * (depth * taper * math.sin(ang))
            verts.append(tuple(p))
    verts.append(tuple(b))
    last = len(verts) - 1
    faces = []
    for j in range(sections):
        faces.append((0, 1 + (j + 1) % sections, 1 + j))
    for k in range(steps - 2):
        s = 1 + k * sections
        n = s + sections
        for j in range(sections):
            faces.append((s + j, s + (j + 1) % sections, n + (j + 1) % sections, n + j))
    s = 1 + (steps - 2) * sections
    for j in range(sections):
        faces.append((s + j, s + (j + 1) % sections, last))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    recalc(o)
    return finish(o, mat)


def curve(name, pts, r, mat, closed=False):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = r
    cu.bevel_resolution = 2
    cu.resolution_u = 6
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for p, co in zip(sp.points, pts):
        p.co = (*co, 1)
    sp.use_cyclic_u = closed
    o = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(o)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.ops.object.convert(target='MESH')
    o = bpy.context.active_object
    return finish(o, mat)


# ---------------------------------------------------------------- 布布种子
def build_bubu():
    M = dict(
        green=material('bubu_green', (.035, .20, .065), .34, 0., coat=.30),
        green_l=material('bubu_green_light', (.16, .40, .10), .32, 0., coat=.35),
        cream=material('bubu_cream', (.80, .73, .50), .45, 0.),
        pink=material('bubu_pink', (.88, .42, .60), .32, 0., coat=.18),
        pink_l=material('bubu_pink_light', (.97, .66, .78), .30, 0., coat=.15),
        eye=material('bubu_eye', (.008, .010, .008), .16, 0., coat=.65),
        white=material('bubu_white', (.97, .96, .90), .30, 0.),
        foot=material('bubu_foot', (.58, .66, .30), .38, 0., coat=.2),
    )
    ell('bubu_body', (0, 0, .40), .295, .255, .355, M['green'])
    ell('bubu_face', (0, -.225, .47), .165, .075, .185, M['cream'])
    for sx in (-1, 1):
        ell('bubu_eye_' + str(sx), (sx * .078, -.285, .515), .046, .026, .066, M['eye'])
        ell('bubu_glint_' + str(sx), (sx * .062, -.305, .548), .014, .010, .018, M['white'])
    curve('bubu_smile', [(-.040, -.299, .438), (-.020, -.303, .425), (0, -.305, .421),
                         (.020, -.303, .425), (.040, -.299, .438)], .0045, M['eye'])
    # 叶子帽：侧后一圈下垂叶片 + 正面上方一片帽檐。
    for k in range(7):
        ang = -math.pi / 2 + math.tau * k / 7
        if math.sin(ang) < -.2:
            continue
        tip = Vector((math.cos(ang) * .31, math.sin(ang) * .28, .405))
        base = Vector((math.cos(ang) * .06, math.sin(ang) * .05, .66))
        teardrop(f'bubu_leaf_{k}', base, tip, .105, .030, M['green_l'], bulge=.55)
    teardrop('bubu_brim', (0, 0, .70), (0, -.315, .585), .175, .032, M['green_l'], bulge=.6)
    # 粉色花苞
    ell('bubu_bud', (0, .015, .805), .175, .160, .155, M['pink'])
    for k in range(5):
        a = math.tau * k / 5 + .3
        ell(f'bubu_petal_{k}', (math.cos(a) * .11, .015 + math.sin(a) * .10, .855),
            .075, .062, .075, M['pink_l'])
    ell('bubu_bud_top', (0, .015, .905), .09, .085, .06, M['pink_l'])
    # 花瓣手
    for sx in (-1, 1):
        teardrop('bubu_arm_' + str(sx), (sx * .235, -.01, .44), (sx * .405, -.015, .48),
                 .072, .060, M['pink'], bulge=.6)
        ell('bubu_hand_a_' + str(sx), (sx * .375, -.02, .49), .055, .050, .050, M['pink_l'])
        ell('bubu_hand_b_' + str(sx), (sx * .405, .015, .455), .040, .045, .040, M['pink'])
    # 脚
    for sx in (-1, 1):
        ell('bubu_foot_' + str(sx), (sx * .105, -.045, .055), .070, .105, .055, M['foot'])
    return .96


# ---------------------------------------------------------------- 小火猴
def build_huohou():
    M = dict(
        red=material('huohou_red', (.68, .055, .012), .33, 0., coat=.22),
        red_l=material('huohou_red_light', (.92, .20, .02), .30, 0., coat=.2),
        orange=material('huohou_orange', (.98, .43, .045), .30, 0., coat=.18),
        orange_l=material('huohou_orange_light', (1., .68, .16), .28, 0.),
        cream=material('huohou_cream', (.87, .74, .52), .44, 0.),
        brown=material('huohou_iris', (.20, .085, .035), .24, 0., coat=.35),
        ink=material('huohou_ink', (.012, .008, .006), .18, 0., coat=.55),
        white=material('huohou_white', (.97, .96, .9), .3, 0.),
    )
    ell('huohou_body', (0, 0, .32), .195, .175, .235, M['red'])
    ell('huohou_belly', (0, -.155, .31), .125, .055, .175, M['cream'])
    ell('huohou_head', (0, 0, .60), .245, .225, .225, M['red'])
    ell('huohou_face', (0, -.185, .585), .165, .052, .150, M['cream'])
    for sx in (-1, 1):
        ell('huohou_eye_' + str(sx), (sx * .080, -.225, .615), .055, .028, .077, M['brown'])
        ell('huohou_pupil_' + str(sx), (sx * .078, -.248, .610), .031, .014, .050, M['ink'])
        ell('huohou_glint_' + str(sx), (sx * .060, -.260, .650), .014, .008, .018, M['white'])
    curve('huohou_smile', [(-.042, -.238, .520), (-.020, -.244, .510), (0, -.246, .507),
                           (.020, -.244, .510), (.042, -.238, .520)], .005, M['ink'])
    # 火苗鬃毛：五簇，外红内橙
    tips = [(-.185, .015, .955), (-.095, .01, 1.035), (0, .015, 1.095),
            (.095, .01, 1.03), (.185, .015, .945)]
    for i, tip in enumerate(tips):
        base = (tip[0] * .45, .0, .735)
        teardrop(f'huohou_flame_{i}', base, tip, .072, .050,
                 M['red_l'] if i % 2 else M['orange'], bulge=.62)
        inner = (tip[0] * .5, -.015, .78)
        tip2 = (tip[0] * .95, -.01, tip[2] - .055)
        teardrop(f'huohou_flame_in_{i}', inner, tip2, .034, .020, M['orange_l'], bulge=.6)
    torus('huohou_curl', .046, .016, (0, -.205, .725), M['orange'], rot=(math.pi / 2, 0, 0),
          major=32, minor=8)
    for sx in (-1, 1):
        teardrop('huohou_ear_' + str(sx), (sx * .19, .0, .625), (sx * .315, .015, .735),
                 .055, .038, M['orange'], bulge=.6)
        # 手臂与火焰手
        teardrop('huohou_arm_' + str(sx), (sx * .155, -.015, .40), (sx * .285, -.03, .305),
                 .052, .045, M['red'], bulge=.55)
        for j, (dx, dy, dz) in enumerate([(.105, 0, .075), (.125, .02, -.005), (.09, .05, -.09)]):
            teardrop(f'huohou_finger_{sx}_{j}', (sx * .285, -.03, .305),
                     (sx * (.285 + dx), dy - .03, .305 + dz), .027, .022,
                     M['orange'] if j == 1 else M['red_l'], bulge=.6)
        ell('huohou_foot_' + str(sx), (sx * .10, -.035, .058), .075, .105, .058, M['red'])
        ell('huohou_toe_' + str(sx), (sx * .10, -.12, .045), .052, .035, .030, M['cream'])
    # 尾巴火苗
    teardrop('huohou_tail', (0, .135, .30), (0, .315, .44), .062, .045, M['orange'], bulge=.6)
    teardrop('huohou_tail_in', (0, .16, .32), (0, .29, .40), .030, .022, M['orange_l'], bulge=.6)
    return 1.09


# ---------------------------------------------------------------- 伊优
def build_yiyou():
    M = dict(
        blue=material('yiyou_blue', (.035, .38, .78), .30, 0., coat=.38),
        blue_l=material('yiyou_blue_light', (.18, .58, .90), .30, 0., coat=.35),
        pale=material('yiyou_pale', (.55, .82, .95), .32, 0., coat=.3),
        white=material('yiyou_white', (.93, .96, .97), .38, 0., coat=.3),
        pink=material('yiyou_pink', (.95, .22, .52), .28, 0.),
        ink=material('yiyou_ink', (.008, .012, .022), .16, 0., coat=.6),
        glint=material('yiyou_glint', (.98, .98, 1.), .28, 0.),
    )
    ell('yiyou_body', (0, .01, .30), .185, .165, .245, M['blue'])
    ell('yiyou_belly', (0, -.145, .285), .120, .050, .190, M['white'])
    ell('yiyou_head', (0, .0, .585), .255, .215, .235, M['blue'])
    ell('yiyou_muzzle', (0, -.195, .520), .135, .052, .095, M['white'])
    ell('yiyou_forehead', (0, -.200, .655), .062, .040, .145, M['white'])
    for sx in (-1, 1):
        ell('yiyou_eye_' + str(sx), (sx * .090, -.220, .610), .055, .028, .078, M['ink'])
        ell('yiyou_iris_' + str(sx), (sx * .090, -.240, .598), .033, .013, .037, M['pink'])
        ell('yiyou_glint_' + str(sx), (sx * .072, -.253, .647), .014, .008, .018, M['glint'])
        # 耳鳍
        teardrop('yiyou_ear_' + str(sx), (sx * .205, .0, .655), (sx * .365, .025, .760),
                 .095, .030, M['blue'], bulge=.6)
        teardrop('yiyou_ear_in_' + str(sx), (sx * .235, -.018, .675), (sx * .345, .0, .745),
                 .048, .012, M['pale'], bulge=.6)
        # 臂鳍
        teardrop('yiyou_arm_' + str(sx), (sx * .155, -.015, .355), (sx * .350, -.035, .245),
                 .082, .038, M['blue'], bulge=.55)
        teardrop('yiyou_arm_tip_' + str(sx), (sx * .285, -.025, .290), (sx * .360, -.04, .245),
                 .036, .016, M['pale'], bulge=.6)
        ell('yiyou_foot_' + str(sx), (sx * .10, -.04, .055), .072, .105, .052, M['blue'])
        ell('yiyou_toe_' + str(sx), (sx * .10, -.125, .04), .050, .035, .026, M['white'])
    # 背鳍与尾鳍
    teardrop('yiyou_dorsal', (0, .125, .34), (0, .265, .62), .105, .028, M['blue_l'], bulge=.55)
    teardrop('yiyou_tail', (0, .10, .14), (0, .31, .19), .075, .022, M['pale'], bulge=.55)
    return .84


# ---------------------------------------------------------------- 米咔
def build_mika():
    M = dict(
        red=material('mika_red', (.74, .085, .035), .32, 0., coat=.28),
        red_d=material('mika_red_dark', (.52, .045, .018), .35, 0., coat=.2),
        orange=material('mika_orange', (.98, .63, .10), .30, 0., coat=.2),
        cream=material('mika_cream', (.96, .82, .58), .42, 0.),
        pink=material('mika_pink', (.96, .46, .52), .36, 0.),
        ink=material('mika_ink', (.012, .008, .008), .16, 0., coat=.6),
        glint=material('mika_glint', (.99, .99, .96), .28, 0.),
    )
    ell('mika_body', (0, .005, .32), .185, .165, .235, M['red'])
    ell('mika_belly', (0, -.145, .30), .120, .050, .175, M['cream'])
    ell('mika_head', (0, .0, .615), .240, .215, .215, M['red'])
    ell('mika_face', (0, -.180, .595), .165, .052, .150, M['cream'])
    ell('mika_brow_patch', (0, -.190, .725), .075, .035, .045, M['orange'])
    for sx in (-1, 1):
        # 大耳朵：外红内黄
        teardrop('mika_ear_' + str(sx), (sx * .115, .0, .775), (sx * .245, .015, 1.115),
                 .085, .040, M['red'], bulge=.5)
        teardrop('mika_ear_in_' + str(sx), (sx * .125, -.022, .800), (sx * .220, -.005, 1.070),
                 .050, .014, M['orange'], bulge=.5)
        ell('mika_eye_' + str(sx), (sx * .082, -.222, .640), .056, .028, .078, M['ink'])
        ell('mika_glint_' + str(sx), (sx * .064, -.248, .675), .015, .008, .019, M['glint'])
        ell('mika_cheek_' + str(sx), (sx * .135, -.230, .555), .035, .012, .034, M['pink'])
        teardrop('mika_arm_' + str(sx), (sx * .150, -.015, .365), (sx * .285, -.03, .305),
                 .045, .038, M['red'], bulge=.55)
        ell('mika_foot_' + str(sx), (sx * .10, -.045, .060), .075, .110, .060, M['red_d'])
        ell('mika_toe_' + str(sx), (sx * .10, -.135, .045), .052, .035, .028, M['cream'])
    # 张嘴笑 + 舌头
    ell('mika_mouth', (0, -.240, .525), .048, .020, .038, M['ink'])
    ell('mika_tongue', (0, -.252, .512), .024, .010, .018, M['pink'])
    teardrop('mika_tail', (0, .13, .24), (0, .30, .35), .055, .035, M['red'], bulge=.55)
    return 1.13


# ---------------------------------------------------------------- 导出与图标
def setup_studio(height):
    scene = bpy.context.scene
    world = bpy.data.worlds.new('studio')
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes['Background']
    bg.inputs[0].default_value = (.72, .80, .90, 1)
    bg.inputs[1].default_value = .38
    for name, loc, power, size in [('key', (-3, -4, 4.5), 420, 4),
                                   ('fill', (4, -2, 2.5), 160, 3),
                                   ('rim', (0, 3, 4), 280, 3)]:
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy, ld.shape, ld.size = power, 'DISK', size
        ob = bpy.data.objects.new(name, ld)
        bpy.context.collection.objects.link(ob)
        ob.location = loc
        ob.rotation_euler = (-ob.location).to_track_quat('-Z', 'Y').to_euler()
    cam_data = bpy.data.cameras.new('icon_cam')
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = max(1.25, height * 1.28)
    cam = bpy.data.objects.new('icon_cam', cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (1.55, -4.4, height * .95 + .35)
    cam.rotation_euler = (Vector((0, 0, height * .48)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = 'AgX'
    try:
        scene.view_settings.look = 'AgX - Medium High Contrast'
    except TypeError:
        pass
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    return scene


def export_and_icon(pid, root, height):
    GLB_DIR.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    root.select_set(True)
    for o in OBJS:
        o.select_set(True)
    bpy.context.view_layer.objects.active = root
    glb = GLB_DIR / f'{pid}.glb'
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB',
                              use_selection=True, export_apply=True, export_lights=False)
    print('exported', glb, len(OBJS), 'objects')
    if not RENDER:
        return
    scene = setup_studio(height)
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(ICON_DIR / f'{pid}.png')
    bpy.ops.render.render(write_still=True)
    print('rendered', scene.render.filepath)


def make_root(pid):
    root = bpy.data.objects.new(f'{pid}_root', None)
    bpy.context.collection.objects.link(root)
    for o in OBJS:
        o.parent = root
        o.matrix_parent_inverse = root.matrix_world.inverted()
    return root


BUILDERS = dict(bubu=build_bubu, huohou=build_huohou, yiyou=build_yiyou, mika=build_mika)

if __name__ == '__main__':
    for pid, builder in BUILDERS.items():
        if ONLY and pid not in ONLY:
            continue
        reset()
        height = builder()
        root = make_root(pid)
        export_and_icon(pid, root, height)
    print('pets done')
