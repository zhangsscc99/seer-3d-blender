import {
  AbstractMesh,
  AssetContainer,
  Color3,
  LoadAssetContainerAsync,
  PBRMaterial,
  Scene,
  TransformNode,
  Vector3,
} from '@babylonjs/core';
import '@babylonjs/loaders/glTF';

export type PropName = string;

interface Proto {
  container: AssetContainer;
  size: Vector3;
  offset: Vector3;
  count: number;
}

const protos = new Map<PropName, Proto>();

export interface LoadOptions {
  emissive?: number;
}

export async function loadProp(scene: Scene, name: PropName, opts: LoadOptions = {}) {
  const container = await LoadAssetContainerAsync(`/models/${name}.glb`, scene);
  for (const m of container.meshes) m.receiveShadows = true;
  if (opts.emissive) {
    for (const mat of container.materials) {
      if (!(mat instanceof PBRMaterial)) continue;
      mat.emissiveTexture = mat.albedoTexture;
      mat.emissiveColor = new Color3(opts.emissive, opts.emissive, opts.emissive);
    }
  }
  protos.set(name, { container, size: Vector3.Zero(), offset: Vector3.Zero(), count: 0 });
}

export interface SpawnOptions {
  height?: number;
  width?: number;
  rotY?: number;
  scale?: number;
}

export function spawn(
  scene: Scene,
  name: PropName,
  pos: Vector3,
  opts: SpawnOptions = {},
): { node: TransformNode; meshes: AbstractMesh[]; height: number } {
  const proto = protos.get(name);
  if (!proto) throw new Error(`prop not loaded: ${name}`);
  const wrapper = new TransformNode(`${name}_${proto.count}`, scene);
  const entries = proto.container.instantiateModelsToScene((n) => `${n}_${proto.count}`, false, {
    doNotInstantiate: false,
  });
  const root = entries.rootNodes[0] as TransformNode;
  root.parent = wrapper;

  if (proto.count === 0) {
    root.computeWorldMatrix(true);
    const { min, max } = root.getHierarchyBoundingVectors(true);
    proto.size = max.subtract(min);
    proto.offset = new Vector3(-(min.x + max.x) / 2, -min.y, -(min.z + max.z) / 2);
  }
  proto.count++;

  root.position.copyFrom(proto.offset);
  let s = opts.scale ?? 1;
  if (opts.height) s = opts.height / proto.size.y;
  else if (opts.width) s = opts.width / Math.max(proto.size.x, proto.size.z);
  wrapper.scaling.setAll(s);
  wrapper.position.copyFrom(pos);
  wrapper.rotation.y = opts.rotY ?? 0;

  const meshes = root.getChildMeshes(false);
  return { node: wrapper, meshes, height: proto.size.y * s };
}
