/** Blender floor coordinates map to Babylon (-x, -y) in the ground plane. */
export interface PowerCollisionMeta {
  colliders: { x: number; y: number; r: number }[];
  walk: { minX: number; maxX: number; minY: number; maxY: number };
}
export const PLAYER_R = 0.32;

export function makeCollision(meta: PowerCollisionMeta) {
  const circles = meta.colliders.map((c) => ({ x: -c.x, z: -c.y, r: c.r }));
  const w = meta.walk;
  const box = { minX: -w.maxX, maxX: -w.minX, minZ: -w.maxY, maxZ: -w.minY };
  // 小步前进后把位置推出圆形障碍并夹回走道，碰到圆弧时自然沿切线滑行。
  return (p: { x: number; z: number }, dx: number, dz: number) => {
    const steps = Math.max(1, Math.ceil(Math.hypot(dx, dz) / 0.08));
    for (let i = 0; i < steps; i++) {
      const previousX = p.x;
      const previousZ = p.z;
      p.x += dx / steps;
      p.z += dz / steps;
      // A clamp or a second machine can push the player back into an earlier
      // obstacle. Resolve the complete constraint set before accepting the step.
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
        p.x = Math.min(box.maxX - PLAYER_R, Math.max(box.minX + PLAYER_R, p.x));
        p.z = Math.min(box.maxZ - PLAYER_R, Math.max(box.minZ + PLAYER_R, p.z));
      }
      if (circles.some(c => Math.hypot(p.x-c.x, p.z-c.z) < c.r+PLAYER_R-1e-7)) {
        p.x = previousX;
        p.z = previousZ;
      }
    }
  };
}
