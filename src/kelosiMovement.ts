/** 克洛斯星高度场采样与开放地形碰撞。地面/高度场直接使用 Babylon (x, z)。 */
export interface KelosiHeightfield {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  cell: number;
  cols: number;
  rows: number;
  heights: number[];
}

export interface KelosiMeta {
  waterLevel: number;
  walk: { minX: number; maxX: number; minY: number; maxY: number };
  heightfield: KelosiHeightfield;
  colliders: { id?: string; x: number; y: number; r: number }[];
  boxes: { id?: string; minX: number; maxX: number; minY: number; maxY: number }[];
  /** 露出水面的踏脚石，供水面深度图烘出浅点。已使用 Babylon (x, z)。 */
  shallows?: { x: number; z: number; r: number }[];
}

export const PLAYER_R = 0.34;
export const WATER_DEPTH = 0.95;
export const MAX_SLOPE = 1.6;

const clamp = (v: number, a: number, b: number) => (v < a ? a : v > b ? b : v);

export function makeGround(meta: KelosiMeta): (x: number, z: number) => number {
  const hf = meta.heightfield;
  const { minX, minY, cell, cols, rows, heights } = hf;
  return (x: number, z: number) => {
    const gx = clamp((x - minX) / cell, 0, cols - 1);
    const gy = clamp((z - minY) / cell, 0, rows - 1);
    const c0 = Math.min(cols - 2, Math.floor(gx));
    const r0 = Math.min(rows - 2, Math.floor(gy));
    const fx = gx - c0;
    const fy = gy - r0;
    const i = r0 * cols + c0;
    const h00 = heights[i];
    const h10 = heights[i + 1];
    const h01 = heights[i + cols];
    const h11 = heights[i + cols + 1];
    const a = h00 + (h10 - h00) * fx;
    const b = h01 + (h11 - h01) * fx;
    return a + (b - a) * fy;
  };
}

interface Box {
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
}

function toBox(b: { minX: number; maxX: number; minY: number; maxY: number }, pad: number): Box {
  // 元数据中的 x 已是 Babylon x；minY/maxY 存的是 -Babylon z。
  return {
    minX: b.minX - pad,
    maxX: b.maxX + pad,
    minZ: -b.maxY - pad,
    maxZ: -b.minY + pad,
  };
}

export interface KelosiMovement {
  move(p: { x: number; z: number }, dx: number, dz: number): boolean;
  blocked(x: number, z: number): boolean;
  walkable(x: number, z: number, fromX?: number, fromZ?: number): boolean;
}

export function makeMovement(meta: KelosiMeta, ground: (x: number, z: number) => number): KelosiMovement {
  const circles = meta.colliders.map((c) => ({ x: c.x, z: -c.y, r: c.r }));
  const boxes = meta.boxes.map((b) => toBox(b, 0));
  const walk = toBox(meta.walk, 0);

  const blocked = (x: number, z: number) =>
    circles.some((c) => Math.hypot(x - c.x, z - c.z) < c.r + PLAYER_R - 1e-7) ||
    boxes.some(
      (b) =>
        x > b.minX - PLAYER_R &&
        x < b.maxX + PLAYER_R &&
        z > b.minZ - PLAYER_R &&
        z < b.maxZ + PLAYER_R,
    ) ||
    x < walk.minX + PLAYER_R ||
    x > walk.maxX - PLAYER_R ||
    z < walk.minZ + PLAYER_R ||
    z > walk.maxZ - PLAYER_R;

  const walkable = (x: number, z: number, fromX?: number, fromZ?: number) => {
    if (blocked(x, z)) return false;
    const h = ground(x, z);
    if (h < meta.waterLevel - WATER_DEPTH) return false;
    if (fromX !== undefined && fromZ !== undefined) {
      const run = Math.hypot(x - fromX, z - fromZ);
      if (run > 1e-7 && Math.abs(h - ground(fromX, fromZ)) / run > MAX_SLOPE) return false;
    }
    return true;
  };

  const move = (p: { x: number; z: number }, dx: number, dz: number) => {
    const total = Math.hypot(dx, dz);
    const steps = Math.max(1, Math.ceil(total / 0.08));
    let moved = false;
    for (let step = 0; step < steps; step++) {
      const previousX = p.x;
      const previousZ = p.z;
      p.x += dx / steps;
      p.z += dz / steps;

      for (let pass = 0; pass < 12; pass++) {
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

      if (!walkable(p.x, p.z, previousX, previousZ)) {
        p.x = previousX;
        p.z = previousZ;
      } else if (Math.hypot(p.x - previousX, p.z - previousZ) > 1e-7) {
        moved = true;
      }
    }
    return moved;
  };

  return { move, blocked, walkable };
}
