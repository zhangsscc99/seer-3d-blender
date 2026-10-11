/** 发明室地面行走：单位为米，XZ 是 Babylon 的水平面。 */
export interface Position2 { x: number; z: number }
export interface CircleObstacle extends Position2 { r: number }
export interface BoxObstacle { minX: number; maxX: number; minZ: number; maxZ: number }
export interface RoomCollision { circles: CircleObstacle[]; boxes: BoxObstacle[] }

export const PLAYER_RADIUS = 0.28;
export const EYE_HEIGHT = 1.45;

export function roomCollision(colliders: { x: number; y: number; r: number }[]): RoomCollision {
  return {
    // 台阶可走上去；只拦控制台和两侧护轨，不用大圆封死整个终端区。
    circles: colliders.filter((c) => !(Math.abs(c.x) < 0.01 && Math.abs(c.y - 5.6) < 0.01))
      .map((c) => ({ x: -c.x, z: -c.y, r: c.r })),
    boxes: [
      { minX: -1.5, maxX: 1.5, minZ: -6.4, maxZ: -5.8 },
      { minX: -2.5, maxX: -2.0, minZ: -6.95, maxZ: -4.25 },
      { minX: 2.0, maxX: 2.5, minZ: -6.95, maxZ: -4.25 },
    ],
  };
}

export function canOccupy(x: number, z: number, collision: RoomCollision): boolean {
  if (Math.abs(x) > 8.6 - PLAYER_RADIUS || Math.abs(z) > 6.6 - PLAYER_RADIUS) return false;
  for (const c of collision.circles) {
    if (Math.hypot(x - c.x, z - c.z) < c.r + PLAYER_RADIUS) return false;
  }
  for (const b of collision.boxes) {
    const nearX = Math.max(b.minX, Math.min(x, b.maxX));
    const nearZ = Math.max(b.minZ, Math.min(z, b.maxZ));
    if (Math.hypot(x - nearX, z - nearZ) < PLAYER_RADIUS) return false;
  }
  return true;
}

export function moveInRoom(pos: Position2, dx: number, dz: number, collision: RoomCollision): Position2 {
  const next = { x: pos.x, z: pos.z };
  // 每一步小于身体半径，即使低帧率或冲刺也不能越过设备。
  const steps = Math.max(1, Math.ceil(Math.hypot(dx, dz) / 0.08));
  const sx = dx / steps;
  const sz = dz / steps;
  for (let i = 0; i < steps; i++) {
    if (canOccupy(next.x + sx, next.z + sz, collision)) {
      next.x += sx;
      next.z += sz;
    } else if (canOccupy(next.x + sx, next.z, collision)) next.x += sx;
    else if (canOccupy(next.x, next.z + sz, collision)) next.z += sz;
  }
  return next;
}

export function floorHeight(x: number, z: number): number {
  if (Math.abs(x) <= 2 && z >= -6.825 && z <= -4.875) return 0.28;
  if (Math.abs(x) <= 2.3 && z >= -6.85 && z <= -4.35) return 0.14;
  return 0;
}
