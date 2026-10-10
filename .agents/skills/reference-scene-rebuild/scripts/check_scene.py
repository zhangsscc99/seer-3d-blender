"""在 Blender 中重新导入生产 GLB，检查有限几何、NONO 实例与元数据。"""
import argparse
import json
import math
import sys
from pathlib import Path
import bpy

parser = argparse.ArgumentParser()
parser.add_argument('--asset', required=True)
parser.add_argument('--metadata', required=True)
parser.add_argument('--out', required=True)
parser.add_argument('--nono-count', type=int, default=3)
args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(Path(args.asset).resolve()))
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
issues = []
if not meshes:
    issues.append('GLB has no meshes')
for o in meshes:
    for vertex in o.data.vertices:
        if not all(math.isfinite(c) for c in o.matrix_world @ vertex.co):
            issues.append(f'{o.name}: nonfinite world vertex')
            break
metadata = json.loads(Path(args.metadata).read_text())
for i, obstacle in enumerate(metadata['colliders']):
    if not all(math.isfinite(obstacle[key]) for key in ('x','y','r')) or obstacle['r'] <= 0:
        issues.append(f'collider {i}: invalid circle')
for name, anchor in metadata['animated'].items():
    if not all(math.isfinite(anchor[key]) for key in ('x','y','z')):
        issues.append(f'{name}: invalid animation anchor')
instances = {}
for i in range(args.nono_count):
    key = f'nono{i}'
    instances[key] = len([o for o in meshes if o.name.startswith(key+'_')])
    if instances[key] == 0 or key not in metadata['animated']:
        issues.append(f'{key}: missing geometry or animation anchor')
report = {'asset':args.asset, 'mesh_count':len(meshes),
          'vertices':sum(len(o.data.vertices) for o in meshes),
          'triangles':sum(max(0,len(p.vertices)-2) for o in meshes for p in o.data.polygons),
          'nono_parts':instances, 'collider_count':len(metadata['colliders']), 'issues':issues}
out = Path(args.out)
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,indent=2)+'\n')
print('SCENE_CHECK',json.dumps(report))
if issues:
    raise RuntimeError('; '.join(issues))
