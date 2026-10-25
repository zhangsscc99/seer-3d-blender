"""赛尔机器人（主角）—— 纯程序化建模。

造型依据：球形舱体、黑色圆形面窗 + 双白眼、金色腰带、头顶调压阀、
纤细机械腿 + 钟形脚。正面朝 Blender -Y（与传送舱一致）。

用法:
  Blender -b -P blender/seer_robot.py -- --glb public/models/player/seer_robot.glb \
      --render renders/seer_robot_front.png --render-back renders/seer_robot_back.png --samples 32
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from power_reactor import material  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


GLB = arg('--glb')
RENDER = arg('--render')
RENDER_BACK = arg('--render-back')
SAMPLES = int(arg('--samples', '32'))

bpy.ops.wm.read_factory_settings(use_empty=True)

M = dict(
    body=material('seer_body', (.018, .020, .024), .38, .18, coat=.28),
    body_soft=material('seer_body_soft', (.038, .041, .046), .34, .20, coat=.25),
    gun=material('seer_gunmetal', (.075, .082, .092), .30, .80),
    gun_dark=material('seer_gunmetal_dark', (.028, .031, .036), .38, .65),
    steel=material('seer_steel', (.34, .36, .39), .30, .90),
    steel_l=material('seer_steel_light', (.52, .54, .57), .28, .85),
    gold=material('seer_gold', (.42, .29, .08), .34, .80, coat=.10),
    gold_d=material('seer_gold_dark', (.34, .23, .07), .34, .75),
    blue=material('seer_blue', (.03, .22, .42), .26, .55, coat=.30),
    face=material('seer_face', (.02, .02, .025), .55, 0., emit=(1., 1., 1.), strength=.35,
                  image=HERE / 'seer_face.png'),
    eye_glow=material('seer_eye_glow', (.02, .06, .08), .35, 0., emit=(.55, .92, 1.), strength=.9),
)

objs = []


def finish(o, mat, bevel=0., smooth=True):
    o.data.materials.append(mat)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    o.select_set(False)
    for p in getattr(o.data, 'polygons', ()):
        p.use_smooth = smooth if bevel <= 0 else True
    if bevel:
        b = o.modifiers.new('bevel', 'BEVEL')
        b.width, b.segments, b.limit_method = bevel, 3, 'ANGLE'
        o.modifiers.new('wn', 'WEIGHTED_NORMAL').keep_sharp = True
    objs.append(o)
    return o


def sphere(name, r, loc, mat, scale=(1, 1, 1), segs=64, rings=32):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=segs, ring_count=rings, location=loc)
    o = bpy.context.active_object
    o.name, o.scale = name, scale
    return finish(o, mat)


def cyl(name, r, h, loc, mat, rot=(0, 0, 0), verts=48, bevel=0., scale=(1, 1)):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name, o.scale = name, (scale[0], scale[1], 1)
    return finish(o, mat, bevel)


def cone(name, r1, r2, h, loc, mat, rot=(0, 0, 0), verts=48):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=h, vertices=verts, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    return finish(o, mat)


def box(name, size, loc, mat, bevel=.01, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name, o.scale = name, size
    return finish(o, mat, bevel)


def torus(name, R, r, loc, mat, rot=(0, 0, 0), major=64, minor=12):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=major,
                                     minor_segments=minor, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    return finish(o, mat)


def lathe(name, profile, mat, cx=0., cy=0., verts=64, rot=None):
    """绕 Z 轴的旋转体，profile 为 [(z, r), ...]（自下而上）。"""
    vv, faces = [], []
    for z, r in profile:
        for i in range(verts):
            a = 2 * math.pi * i / verts
            vv.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
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
    if rot:
        o.rotation_euler = rot
    return finish(o, mat)


def uv_disc(name, r, loc, mat, rot=(0, 0, 0), segs=96):
    """平面圆盘，UV 为整圆径向映射（面窗贴图用）。"""
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
    return finish(o, mat)


# ================================================================ 主体
BODY_C = (0., 0., .72)
BODY_R = .30
FRONT = -.30
sphere('seer_body', BODY_R, BODY_C, M['body'], segs=80, rings=40)

# 两道极细的舱体分模线（避开正面面窗区域）
for k, dz in enumerate((.105, -.105)):
    rr = math.sqrt(BODY_R ** 2 - dz ** 2) + .0006
    torus(f'seer_seam_{k}', rr, .0032, (0., 0., BODY_C[2] + dz), M['gun_dark'],
          major=96, minor=6)

# ---- 面窗：外圈金属框 + 螺栓 + 贴图面盘
FACE_Z = .735
cyl('seer_face_collar', .238, .085, (0., -.255, FACE_Z), M['gun'], rot=(math.pi / 2, 0, 0), verts=80, bevel=.014)
torus('seer_face_rim', .228, .024, (0., -.294, FACE_Z), M['gun_dark'], rot=(math.pi / 2, 0, 0), major=80, minor=14)
torus('seer_face_lip', .201, .007, (0., -.300, FACE_Z), M['steel_l'], rot=(math.pi / 2, 0, 0), major=80, minor=8)
uv_disc('seer_face_screen', .196, (0., -.305, FACE_Z), M['face'], rot=(math.pi / 2, 0, 0), segs=96)
# 面窗螺栓（10 颗，错开正上方）
for k in range(10):
    a = math.radians(18 + k * 36)
    sphere(f'seer_face_bolt_{k}', .0155,
           (math.cos(a) * .228, -.302, FACE_Z + math.sin(a) * .228), M['steel_l'], segs=20, rings=10)
    sphere(f'seer_face_bolt_hole_{k}', .0068,
           (math.cos(a) * .228, -.315, FACE_Z + math.sin(a) * .228), M['gun_dark'], segs=16, rings=8)

# ---- 侧面金色舷窗
for s, side in ((-1, 'l'), (1, 'r')):
    x = s * .288
    cyl(f'seer_port_{side}_rim', .078, .04, (x, -.012, .735), M['gold'],
        rot=(0, math.pi / 2, 0), verts=48, bevel=.010)
    cyl(f'seer_port_{side}_glass', .058, .05, (x + s * .012, -.012, .735), M['gun_dark'],
        rot=(0, math.pi / 2, 0), verts=48)
    torus(f'seer_port_{side}_ring', .078, .009, (x + s * .023, -.012, .735), M['gold_d'],
          rot=(0, math.pi / 2, 0), major=48, minor=8)
    # 小臂桩
    cyl(f'seer_arm_{side}', .030, .07, (s * .305, -.040, .552), M['steel'],
        rot=(0, math.pi / 2.6, 0), verts=24)
    sphere(f'seer_hand_{side}', .038, (s * .340, -.060, .528), M['gold'], segs=32, rings=16)

# ---- 金色腰带 / 下裙
lathe('seer_belt', [(.420, .205), (.438, .252), (.462, .278), (.492, .276),
                    (.515, .248), (.528, .222)], M['gold'], verts=80)
lathe('seer_belt_lip', [(.412, .198), (.424, .230), (.430, .232), (.430, .198)], M['gold_d'], verts=80)
# 腰带螺栓
for k in range(10):
    a = math.radians(k * 36)
    sphere(f'seer_belt_bolt_{k}', .0145,
           (math.cos(a) * .272, math.sin(a) * .272, .468), M['gun'], segs=20, rings=10)

# 下裙遮住球体底部
cyl('seer_underskirt', .198, .09, (0., 0., .408), M['gun_dark'], verts=64, bevel=.008)
torus('seer_underskirt_ring', .196, .011, (0., 0., .372), M['steel'], major=64, minor=8)

# ---- 头顶调压阀（略向后倾）
NECK_Z = 1.065
cyl('seer_valve_neck', .036, .13, (0., .006, NECK_Z), M['steel'], verts=32, bevel=.006)
torus('seer_valve_neck_ring', .040, .008, (0., .006, 1.012), M['gun'], major=32, minor=8)
CAP_C = Vector((0., .018, 1.155))
CAP_ROT = Euler((-.13, .10, 0.))
cyl('seer_valve_cap', .132, .052, CAP_C, M['gun'], rot=tuple(CAP_ROT), verts=64, bevel=.010)
cyl('seer_valve_cap_top', .112, .014, CAP_C + Vector((0., 0., .030)), M['steel_l'],
    rot=tuple(CAP_ROT), verts=64, bevel=.005)
# 防滑滚花：绕盖缘一圈小竖条
rot_m = CAP_ROT.to_matrix()
for k in range(18):
    a = 2 * math.pi * k / 18
    local = Vector((math.cos(a) * .133, math.sin(a) * .133, -.004))
    world = CAP_C + rot_m @ local
    box(f'seer_valve_knurl_{k}', (.010, .020, .046), world, M['gun_dark'], bevel=.002,
        rot=tuple(CAP_ROT))

# ---- 背部检修盖（第三人称主要看到这一面）
BACK_Y = .292
torus('seer_back_rim', .112, .014, (0., BACK_Y, .795), M['gold_d'], rot=(math.pi / 2, 0, 0), major=64, minor=10)
cyl('seer_back_hatch', .104, .018, (0., BACK_Y + .004, .795), M['gun_dark'],
    rot=(math.pi / 2, 0, 0), verts=64, bevel=.005)
cyl('seer_back_hatch_inner', .082, .024, (0., BACK_Y + .008, .795), M['gun_dark'],
    rot=(math.pi / 2, 0, 0), verts=64)
torus('seer_back_glow', .090, .005, (0., BACK_Y + .020, .795), M['eye_glow'],
      rot=(math.pi / 2, 0, 0), major=64, minor=8)
for k in range(6):
    a = math.radians(30 + k * 60)
    sphere(f'seer_back_bolt_{k}', .0105,
           (math.cos(a) * .126, BACK_Y + .006, .795 + math.sin(a) * .126), M['steel_l'], segs=16, rings=8)
# 背部下方两条散热槽
for s, side in ((-1, 'l'), (1, 'r')):
    box(f'seer_back_vent_{side}', (.105, .018, .022), (s * .095, BACK_Y - .010, .585),
        M['gun'], bevel=.006, rot=(.22, 0, 0))
    box(f'seer_back_vent_glow_{side}', (.078, .008, .008), (s * .095, BACK_Y - .002, .585),
        M['blue'], bevel=.002, rot=(.22, 0, 0))

# ---- 双腿 + 钟形脚
for s, side in ((-1, 'l'), (1, 'r')):
    x = s * .116
    cyl(f'seer_leg_{side}', .031, .30, (x, 0., .245), M['steel'], verts=24)
    for k in range(5):
        torus(f'seer_leg_{side}_rib_{k}', .036, .007, (x, 0., .135 + k * .05), M['gun'],
              major=24, minor=8)
    cyl(f'seer_leg_{side}_hip', .045, .04, (x, 0., .398), M['gun_dark'], verts=24, bevel=.006)
    lathe(f'seer_foot_{side}', [(.004, .092), (.012, .115), (.032, .122),
                               (.055, .102), (.072, .072), (.086, .058),
                               (.094, .056)], M['body'], cx=x, cy=-.004, verts=48)
    torus(f'seer_foot_{side}_gold', .112, .013, (x, -.004, .038), M['gold'],
          major=48, minor=10)
    torus(f'seer_foot_{side}_rim', .060, .010, (x, -.004, .088), M['gold_d'],
          major=40, minor=8)
    sphere(f'seer_foot_{side}_bolt', .016, (x, -.112, .052), M['steel_l'], segs=20, rings=10)
    # 脚底一圈黑色垫片
    cyl(f'seer_foot_{side}_sole', .095, .008, (x, -.004, .004), M['gun_dark'], verts=48)

# ================================================================ 预览
def setup_render(campos, target, path, lens=70):
    scene = bpy.context.scene
    world = bpy.data.worlds.new('w')
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.035, .042, .055, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = .55

    ground = bpy.data.meshes.new('floor')
    ground.from_pydata([(-4, -4, 0), (4, -4, 0), (4, 4, 0), (-4, 4, 0)], [], [(0, 1, 2, 3)])
    go = bpy.data.objects.new('floor', ground)
    bpy.context.collection.objects.link(go)
    gm = material('seer_floor', (.10, .11, .13), .42, .10)
    go.data.materials.append(gm)

    for name, loc, energy, size, col in (
        ('key', (2.2, -2.8, 2.6), 420, 2.4, (1., .96, .90)),
        ('rim', (-2.4, 2.4, 2.2), 320, 2.0, (.55, .78, 1.)),
        ('fill', (-1.4, -2.8, 1.0), 120, 2.5, (.85, .90, 1.)),
    ):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy, ld.size, ld.color = energy, size, col
        ob = bpy.data.objects.new(name, ld)
        bpy.context.collection.objects.link(ob)
        ob.location = loc
        ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()

    cam_data = bpy.data.cameras.new('cam')
    cam_data.lens = lens
    cam = bpy.data.objects.new('cam', cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = campos
    cam.rotation_euler = (Vector(target) - Vector(campos)).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = 900, 1100
    scene.view_settings.view_transform = 'Standard'
    scene.render.filepath = str(Path(path).resolve())
    bpy.ops.render.render(write_still=True)


if GLB:
    out = Path(GLB).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(out), export_format='GLB', export_apply=True, export_lights=False)
    print('exported', out, len(bpy.data.objects), 'objects')
if RENDER:
    setup_render((1.35, -2.55, 1.28), (0., 0., .60), RENDER, lens=75)
    print('rendered', RENDER)
if RENDER_BACK:
    setup_render((-1.15, 2.55, 1.30), (0., 0., .62), RENDER_BACK, lens=75)
    print('rendered', RENDER_BACK)
