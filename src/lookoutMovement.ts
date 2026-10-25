/** Blender floor coordinates map to Babylon (-x, -y) in the ground plane. */
export interface LookoutCollisionMeta {
  colliders: { x: number; y: number; r: number }[];
  boxes: { minX: number; maxX: number; minY: number; maxY: number }[];
  walk: { minX: number; maxX: number; minY: number; maxY: number };
}
export const PLAYER_R = 0.32;

interface Box {
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
}

function toBox(b: { minX: number; maxX: number; minY: number; maxY: number }, pad: number): Box {
  return {
    minX: -b.maxX - pad,
    maxX: -b.minX + pad,
    minZ: -b.maxY - pad,
    maxZ: -b.minY + pad,
  };
}

export function makeCollision(meta: LookoutCollisionMeta) {
  const circles = meta.colliders.map((c) => ({ x: -c.x, z: -c.y, r: c.r }));
  const boxes = meta.boxes.map((b) => toBox(b, 0));
  const walk = toBox(meta.walk, 0);
  const blocked = (x: number, z: number) =>
    circles.some((c) => Math.hypot(x - c.x, z - c.z) < c.r + PLAYER_R - 1e-7) ||
    boxes.some((b) => x > b.minX - PLAYER_R && x < b.maxX + PLAYER_R && z > b.minZ - PLAYER_R && z < b.maxZ + PLAYER_R) ||
    x < walk.minX + PLAYER_R || x > walk.maxX - PLAYER_R || z < walk.minZ + PLAYER_R || z > walk.maxZ - PLAYER_R;

  return (p: { x: number; z: number }, dx: number, dz: number) => {
    const steps = Math.max(1, Math.ceil(Math.hypot(dx, dz) / 0.08));
    for (let i = 0; i < steps; i++) {
      const previousX = p.x;
      const previousZ = p.z;
      p.x += dx / steps;
      p.z += dz / steps;
      for (let pass = 0; pass < 16; pass++) {
        for (const c of circles) {
          const ox = p.x - c.x;
          const oz = p.z - c.z;
          const d = Math.hypot(ox, oz);
          const min = c.r + PLAYER_R + 1e-5;
          if (d < min) {
            p.x = c.x + (d > 1e-9 ? ox / d : 1) * min;
            p.z = c.z + (d > 1e-9 ? oz / d : 0) * min;
          }
        }
        for (const b of boxes) {
          const minX = b.minX - PLAYER_R;
          const maxX = b.maxX + PLAYER_R;
          const minZ = b.minZ - PLAYER_R;
          const maxZ = b.maxZ + PLAYER_R;
          if (p.x <= minX || p.x >= maxX || p.z <= minZ || p.z >= maxZ) continue;
          const left = p.x - minX;
          const right = maxX - p.x;
          const down = p.z - minZ;
          const up = maxZ - p.z;
          const m = Math.min(left, right, down, up);
          if (m === left) p.x = minX;
          else if (m === right) p.x = maxX;
          else if (m === down) p.z = minZ;
          else p.z = maxZ;
        }
        p.x = Math.min(walk.maxX - PLAYER_R, Math.max(walk.minX + PLAYER_R, p.x));
        p.z = Math.min(walk.maxZ - PLAYER_R, Math.max(walk.minZ + PLAYER_R, p.z));
      }
      if (blocked(p.x, p.z)) {
        p.x = previousX;
        p.z = previousZ;
      }
    }
  };
}
