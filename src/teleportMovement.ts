/** Blender floor coordinates map to Babylon (-x, -y) in the ground plane. */
export interface TeleportCollisionMeta {
  colliders: { x: number; y: number; r: number }[];
  walk: { minX: number; maxX: number; minY: number; maxY: number };
  room?: { x: number; y: number; r: number };
}
export const PLAYER_R = 0.32;

export function makeCollision(meta: TeleportCollisionMeta) {
  const circles = meta.colliders.map((c) => ({ x: -c.x, z: -c.y, r: c.r }));
  const w = meta.walk;
  const box = { minX: -w.maxX, maxX: -w.minX, minZ: -w.maxY, maxZ: -w.minY };
  const room = meta.room ? { x: -meta.room.x, z: -meta.room.y, r: meta.room.r } : null;
  const roomLimit = room ? room.r - PLAYER_R : 0;
  // 小步前进后把位置推出圆形障碍、拉回圆厅边界，碰到弧面时自然沿切线滑行。
  return (p: { x: number; z: number }, dx: number, dz: number) => {
    const steps = Math.max(1, Math.ceil(Math.hypot(dx, dz) / 0.08));
    for (let i = 0; i < steps; i++) {
      const previousX = p.x;
      const previousZ = p.z;
      p.x += dx / steps;
      p.z += dz / steps;
      // A clamp or a second obstacle can push the player back into an earlier
      // one. Resolve the complete constraint set before accepting the step.
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
        if (room) {
          const ox = p.x - room.x;
          const oz = p.z - room.z;
          const d = Math.hypot(ox, oz);
          if (d > roomLimit) {
            p.x = room.x + (d > 1e-9 ? ox / d : 1) * roomLimit;
            p.z = room.z + (d > 1e-9 ? oz / d : 0) * roomLimit;
          }
        }
        p.x = Math.min(box.maxX - PLAYER_R, Math.max(box.minX + PLAYER_R, p.x));
        p.z = Math.min(box.maxZ - PLAYER_R, Math.max(box.minZ + PLAYER_R, p.z));
      }
      const blocked =
        circles.some((c) => Math.hypot(p.x - c.x, p.z - c.z) < c.r + PLAYER_R - 1e-7) ||
        (room !== null && Math.hypot(p.x - room.x, p.z - room.z) > roomLimit + 1e-7);
      if (blocked) {
        p.x = previousX;
        p.z = previousZ;
      }
    }
  };
}
