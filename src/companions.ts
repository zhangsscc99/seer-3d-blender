import { AbstractMesh, Scene, TransformNode, Vector3 } from '@babylonjs/core';
import { loadProp, spawn } from './props';

export type PetId = 'bubu' | 'huohou' | 'yiyou' | 'mika';

export interface PetDef {
  id: PetId;
  name: string;
  element: string;
  height: number;
  icon: string;
}

export const PETS: PetDef[] = [
  { id: 'bubu', name: '布布种子', element: '草系', height: 0.60, icon: '/ui/pets/bubu.png' },
  { id: 'huohou', name: '小火猴', element: '火系', height: 0.64, icon: '/ui/pets/huohou.png' },
  { id: 'yiyou', name: '伊优', element: '水系', height: 0.60, icon: '/ui/pets/yiyou.png' },
  { id: 'mika', name: '米咔', element: '光系', height: 0.66, icon: '/ui/pets/mika.png' },
];

export const NONO_MODEL = 'player/super_nono';
const STORE_KEY = 'seer.followPet';

export interface CompanionOptions {
  playerHeight?: number;
  groundAt?: (x: number, z: number) => number;
}

interface PetInstance {
  def: PetDef;
  node: TransformNode;
  meshes: AbstractMesh[];
  baseScale: Vector3;
}

export interface Companions {
  readonly current: PetId;
  readonly meshes: AbstractMesh[];
  readonly petNodes: TransformNode[];
  readonly nonoNode: TransformNode;
  setPet(id: PetId, persist?: boolean): void;
  update(dt: number): void;
}

export function savedPet(): PetId {
  try {
    const v = localStorage.getItem(STORE_KEY);
    if (PETS.some((p) => p.id === v)) return v as PetId;
  } catch {
    /* 隐私模式等 */
  }
  return 'bubu';
}

export async function preloadCompanions(scene: Scene) {
  await Promise.all([
    ...PETS.map((p) => loadProp(scene, `player/pets/${p.id}`)),
    loadProp(scene, NONO_MODEL),
  ]);
}

const forwardOf = (rotY: number) => new Vector3(Math.sin(rotY), 0, Math.cos(rotY));
const rightOf = (rotY: number) => new Vector3(Math.cos(rotY), 0, -Math.sin(rotY));

export function attachCompanions(
  scene: Scene,
  player: TransformNode,
  opts: CompanionOptions = {},
): Companions {
  const groundAt = opts.groundAt ?? (() => 0);
  const playerHeight = opts.playerHeight ?? 1.25;
  // 各场景机器人高度不同，伙伴按玩家比例缩放，保证视觉大小一致。
  const petScale = playerHeight / 1.25;
  const instances = new Map<PetId, PetInstance>();
  const allMeshes: AbstractMesh[] = [];

  const make = (id: PetId, height: number) => {
    const r = spawn(scene, `player/pets/${id}`, player.position.clone(), { height });
    r.node.setEnabled(false);
    const inst: PetInstance = {
      def: PETS.find((p) => p.id === id)!,
      node: r.node,
      meshes: r.meshes,
      baseScale: r.node.scaling.clone(),
    };
    instances.set(id, inst);
    allMeshes.push(...r.meshes);
    return inst;
  };
  for (const def of PETS) make(def.id, def.height * petScale);

  const nono = spawn(scene, NONO_MODEL, player.position.clone(), { height: 0.56 * petScale });
  allMeshes.push(...nono.meshes);

  const halo = nono.meshes.find((m) => m.name.includes('snono_halo'));
  const tips = nono.meshes.filter((m) => m.name.includes('snono_tip'));
  const haloBase = halo ? halo.scaling.clone() : null;
  const tipBase = tips.map((m) => m.scaling.clone());

  let current = savedPet();
  let pop = 0;
  let petHeading = player.rotation.y;
  let nonoHeading = player.rotation.y;
  let hop = 0;

  interface TrailPoint {
    x: number;
    z: number;
    d: number;
  }
  const trail: TrailPoint[] = [];
  let trailTotal = 0;
  let lastPlayerX = player.position.x;
  let lastPlayerZ = player.position.z;

  const recordTrail = (x: number, z: number) => {
    const last = trail[trail.length - 1];
    if (!last) {
      trail.push({ x, z, d: 0 });
      return;
    }
    const seg = Math.hypot(x - last.x, z - last.z);
    if (seg < 0.04) return;
    trailTotal += seg;
    trail.push({ x, z, d: trailTotal });
    while (trail.length > 2 && trailTotal - trail[1].d > 8) trail.shift();
  };

  const pointBehind = (dist: number) => {
    if (!trail.length) return { x: player.position.x, z: player.position.z };
    const target = trailTotal - dist;
    for (let i = trail.length - 1; i > 0; i--) {
      const a = trail[i - 1];
      const b = trail[i];
      if (a.d <= target) {
        const t = (target - a.d) / Math.max(1e-5, b.d - a.d);
        return { x: a.x + (b.x - a.x) * t, z: a.z + (b.z - a.z) * t };
      }
    }
    return { x: trail[0].x, z: trail[0].z };
  };

  const desiredPet = () => {
    const r = rightOf(player.rotation.y);
    if (trailTotal < 1.05) {
      // 玩家还没走动过：站在背后偏右，避免被身体挡住。
      const f = forwardOf(player.rotation.y);
      const p = player.position;
      return { x: p.x - f.x * 0.62 + r.x * 0.92, z: p.z - f.z * 0.62 + r.z * 0.92 };
    }
    const behind = pointBehind(0.85);
    return { x: behind.x + r.x * 0.95, z: behind.z + r.z * 0.95 };
  };

  const desiredNono = () => {
    const f = forwardOf(player.rotation.y);
    const r = rightOf(player.rotation.y);
    const p = player.position;
    return {
      x: p.x + r.x * 0.62 - f.x * 0.12,
      z: p.z + r.z * 0.62 - f.z * 0.12,
      y: groundAt(p.x, p.z) + playerHeight * 1.05 + 0.22,
    };
  };

  const snapPet = (inst: PetInstance) => {
    const d = desiredPet();
    inst.node.position.x = d.x;
    inst.node.position.z = d.z;
    inst.node.position.y = groundAt(d.x, d.z);
    inst.node.rotation.y = player.rotation.y;
    petHeading = player.rotation.y;
  };

  const setPet = (id: PetId, persist = true) => {
    const inst = instances.get(id);
    if (!inst) return;
    for (const [k, v] of instances) v.node.setEnabled(k === id);
    current = id;
    pop = 0;
    snapPet(inst);
    const s = inst.baseScale;
    inst.node.scaling.set(s.x * 0.55, s.y * 0.55, s.z * 0.55);
    if (persist) {
      try {
        localStorage.setItem(STORE_KEY, id);
      } catch {
        /* ignore */
      }
    }
  };

  if (!trail.length) recordTrail(player.position.x, player.position.z);
  setPet(current, false);

  const d0 = desiredNono();
  nono.node.position.set(d0.x, d0.y, d0.z);
  nono.node.rotation.y = player.rotation.y;

  const update = (dtRaw: number) => {
    const dt = Math.min(Math.max(dtRaw, 0), 0.05);
    const p = player.position;
    const t = performance.now() * 0.001;
    recordTrail(p.x, p.z);
    const playerSpeed = Math.hypot(p.x - lastPlayerX, p.z - lastPlayerZ) / Math.max(dt, 1e-4);
    lastPlayerX = p.x;
    lastPlayerZ = p.z;

    // ---- 宠物：沿玩家走过的轨迹尾随，避免直接穿墙
    const active = instances.get(current)!;
    const d = desiredPet();
    const node = active.node;
    const k = 1 - Math.exp(-dt * 5.5);
    const px = node.position.x + (d.x - node.position.x) * k;
    const pz = node.position.z + (d.z - node.position.z) * k;
    if (Math.hypot(px - p.x, pz - p.z) > 2.7) {
      node.position.x = d.x;
      node.position.z = d.z;
    } else {
      node.position.x = px;
      node.position.z = pz;
    }
    const petGround = groundAt(node.position.x, node.position.z);
    const petSpeed = Math.hypot(px - node.position.x, pz - node.position.z) / Math.max(dt, 1e-4);
    const moving = playerSpeed > 0.25 || petSpeed > 0.8;
    hop += dt * (moving ? 11 : 3.2);
    node.position.y = petGround + (moving ? Math.abs(Math.sin(hop)) * 0.045 : (Math.sin(hop) + 1) * 0.008);

    const faceTarget = moving ? player.rotation.y : Math.atan2(p.x - node.position.x, p.z - node.position.z);
    let diff = faceTarget - petHeading;
    diff = Math.atan2(Math.sin(diff), Math.cos(diff));
    petHeading += diff * Math.min(1, dt * 9);
    node.rotation.y = petHeading;
    node.rotation.z = moving ? Math.sin(hop * 0.5) * 0.05 : 0;

    if (pop < 1) {
      pop = Math.min(1, pop + dt * 4);
      const e = 1 - Math.pow(1 - pop, 3);
      const s = active.baseScale;
      node.scaling.set(s.x * (0.55 + 0.45 * e), s.y * (0.55 + 0.45 * e), s.z * (0.55 + 0.45 * e));
    } else {
      node.scaling.copyFrom(active.baseScale);
    }

    // ---- 超能 NONO：右上方悬浮跟随
    const nd = desiredNono();
    const nk = 1 - Math.exp(-dt * 4.2);
    nono.node.position.x += (nd.x - nono.node.position.x) * nk;
    nono.node.position.z += (nd.z - nono.node.position.z) * nk;
    nono.node.position.y += (nd.y + Math.sin(t * 2.1) * 0.06 - nono.node.position.y) * Math.min(1, dt * 5);
    let ndiff = player.rotation.y - nonoHeading;
    ndiff = Math.atan2(Math.sin(ndiff), Math.cos(ndiff));
    nonoHeading += ndiff * Math.min(1, dt * 3.5);
    nono.node.rotation.y = nonoHeading;
    nono.node.rotation.z = Math.sin(t * 1.6) * 0.045;
    const pulse = 1 + Math.sin(t * 2.6) * 0.035;
    if (halo && haloBase) halo.scaling.set(haloBase.x * pulse, haloBase.y, haloBase.z * pulse);
    for (let i = 0; i < tips.length; i++) {
      const b = tipBase[i];
      const s = 1 + Math.sin(t * 3.1 + i * 1.7) * 0.16;
      tips[i].scaling.set(b.x * s, b.y * s, b.z * s);
    }
  };

  scene.onBeforeRenderObservable.add(() => {
    update(scene.getEngine().getDeltaTime() / 1000);
  });

  const api: Companions = {
    get current() {
      return current;
    },
    get meshes() {
      return allMeshes;
    },
    get petNodes() {
      return PETS.map((p) => instances.get(p.id)!.node);
    },
    get nonoNode() {
      return nono.node;
    },
    setPet,
    update,
  };
  (window as unknown as { __companions?: Companions }).__companions = api;
  return api;
}
