"""超能 NONO 跟随伙伴 —— 在 NONO v7 造型上增加蓝色光晕、悬浮光环与平衡激光翼。

正面朝 Blender -Y；导出独立 GLB + 透明背景背包图标。

用法:
  Blender -b -P blender/super_nono.py -- \
      --glb public/models/player/super_nono.glb \
      --icon public/ui/pets/super_nono.png [--samples 24] [--no-render]
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pets  # noqa: E402
from nono import build_nono  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


GLB = Path(arg('--glb', 'public/models/player/super_nono.glb')).resolve()
ICON = Path(arg('--icon', 'public/ui/pets/super_nono.png')).resolve()
SAMPLES = int(arg('--samples', '24'))
RENDER = '--no-render' not in argv

pets.SAMPLES = SAMPLES
pets.reset()

SCALE = .72
nono = build_nono(prefix='snono', scale=SCALE)

M_GLOW = pets.material('sn_glow', (.04, .45, .80), .28, 0., emit=(.30, .88, 1.), strength=4.2)
M_SOFT = pets.material('sn_soft', (.10, .55, .85), .32, 0., emit=(.35, .80, 1.), strength=1.6)
M_WHITE = pets.material('sn_white', (.80, .94, 1.), .30, 0., emit=(.80, .96, 1.), strength=1.2)

# 壳体与面罩提亮：超能形态整体发蓝光。
for mat_name, color, strength in [
    ('nono_shell', (.14, .62, .78), .40),
    ('nono_rim', (.62, .95, .98), .95),
    ('nono_eyes', (.45, .92, .98), 1.8),
]:
    mat = bpy.data.materials.get(mat_name)
    if mat and mat.use_nodes:
        bs = mat.node_tree.nodes.get('Principled BSDF')
        if bs:
            bs.inputs['Base Color'].default_value = (*color, 1)
            bs.inputs['Emission Color'].default_value = (*color, 1)
            bs.inputs['Emission Strength'].default_value = strength

# 悬浮光环
pets.torus('snono_halo', .285, .009, (0, 0, .075), M_GLOW, major=56, minor=8)
pets.torus('snono_top_ring', .165, .007, (0, 0, .325), M_SOFT, major=40, minor=6)
pets.torus('snono_bottom_ring', .205, .007, (0, 0, -.135), M_SOFT, major=44, minor=6)
# 上下各一对平衡激光翼
for sx in (-1, 1):
    pets.teardrop(f'snono_wing_top_{sx}', (sx * .05, 0, .315), (sx * .345, 0, .345),
                  .026, .010, M_SOFT, bulge=.55)
    pets.teardrop(f'snono_wing_bot_{sx}', (sx * .04, 0, -.12), (sx * .285, 0, -.185),
                  .026, .010, M_SOFT, bulge=.55)
    # 耳翼末端光点
    pets.sphere(f'snono_tip_{sx}', .023, (sx * .418, .058, .526), M_WHITE, segs=16, rings=8)

OBJS = list(nono) + list(pets.OBJS)
root = bpy.data.objects.new('super_nono_root', None)
bpy.context.collection.objects.link(root)
for o in OBJS:
    o.parent = root
    o.matrix_parent_inverse = root.matrix_world.inverted()

GLB.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='DESELECT')
root.select_set(True)
for o in OBJS:
    o.select_set(True)
bpy.context.view_layer.objects.active = root
bpy.ops.export_scene.gltf(filepath=str(GLB), export_format='GLB',
                          use_selection=True, export_apply=True, export_lights=False)
print('exported', GLB, len(OBJS), 'objects')

if RENDER:
    scene = pets.setup_studio(.66)
    ICON.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(ICON)
    bpy.ops.render.render(write_still=True)
    print('rendered', scene.render.filepath)
print('super nono done')
