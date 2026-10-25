import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import { makeCollision, PLAYER_R } from '../src/teleportMovement.ts';
const meta = JSON.parse(readFileSync(new URL('../public/models/teleport/teleport_room.json', import.meta.url)));
const move = makeCollision(meta);
const room = { x: -meta.room.x, z: -meta.room.y, r: meta.room.r };
const pad = { x: -meta.pad.x, z: -meta.pad.y, r: meta.pad.r };

function free(p, label = '') {
  for (const c of meta.colliders)
    assert.ok(Math.hypot(p.x + c.x, p.z + c.y) >= c.r + PLAYER_R - 1e-6, `${label} inside collider ${JSON.stringify(c)} at ${p.x},${p.z}`);
  assert.ok(Math.hypot(p.x - room.x, p.z - room.z) <= room.r - PLAYER_R + 1e-6, `${label} outside room at ${p.x},${p.z}`);
  assert.ok(p.x >= -meta.walk.maxX + PLAYER_R - 1e-6 && p.x <= -meta.walk.minX - PLAYER_R + 1e-6, `${label} walk x`);
  assert.ok(p.z >= -meta.walk.maxY + PLAYER_R - 1e-6 && p.z <= -meta.walk.minY - PLAYER_R + 1e-6, `${label} walk z`);
}
const spawn = () => new Vector3(-meta.spawn.x, 0, -meta.spawn.y);

test('teleport metadata declares room, pad and four real portals', () => {
  assert.equal(meta.terminals.length, 4);
  assert.equal(meta.portals.length, 4);
  const ids = new Set(['kelosi', 'station', 'invention', 'power']);
  for (const t of meta.terminals) {
    assert.ok(ids.has(t.scene), `unexpected scene ${t.scene}`);
    assert.ok(t.label && t.label.length > 0);
    assert.ok(Math.hypot(t.ix - t.x, t.iy - t.y) > t.r * 0.9, 'interaction point should sit in front of terminal collider');
  }
  assert.ok(meta.room.r > meta.pad.r && meta.pad.r > 1);
});

test('teleport spawn is clear and the central pad is walkable', () => {
  const p = spawn();
  free(p, 'spawn');
  move(p, pad.x - p.x, pad.z - p.z);
  free(p, 'pad approach');
  assert.ok(Math.hypot(p.x - pad.x, p.z - pad.z) <= pad.r, 'player should reach the pad centre');
});

test('all four terminals are reachable from the pad', () => {
  for (const t of meta.terminals) {
    const p = new Vector3(pad.x, 0, pad.z);
    const ix = -t.ix;
    const iz = -t.iy;
    move(p, ix - p.x, iz - p.z);
    free(p, t.scene);
    assert.ok(Math.hypot(p.x - ix, p.z - iz) < 0.6, `${t.scene}: stopped short of interaction point`);
    // interaction point must still be within the trigger radius measured from the anchor
    assert.ok(Math.hypot(p.x - ix, p.z - iz) < t.r);
  }
});

test('circular wall stops long moves and permits sliding without penetration', () => {
  const dirs = [];
  for (let i = 0; i < 12; i++) dirs.push([Math.cos((i * Math.PI) / 6), Math.sin((i * Math.PI) / 6)]);
  for (const [dx, dz] of dirs) {
    const p = spawn();
    for (let i = 0; i < 300; i++) {
      move(p, dx * 0.04, dz * 0.04);
      free(p, 'sweep');
    }
  }
  // push straight into the back wall, then slide sideways along it
  const p = spawn();
  move(p, 0, -20);
  free(p, 'wall stop');
  const z0 = p.z;
  move(p, 1.2, 0);
  free(p, 'wall slide');
  assert.ok(p.x > 0.3, 'should slide along the curved wall');
  assert.ok(Math.abs(p.z - z0) < 0.6, 'slide should stay near the wall');
});

test('terminal colliders cannot be tunnelled through', () => {
  for (const t of meta.terminals) {
    const p = new Vector3(pad.x, 0, pad.z);
    move(p, -t.x - p.x, -t.y - p.z); // aim straight at the terminal centre
    free(p, 'terminal');
    const c = meta.colliders.find((k) => Math.hypot(k.x - t.x, k.y - t.y) < 1e-6);
    assert.ok(c, 'terminal should have a matching collider');
    assert.ok(Math.hypot(p.x + t.x, p.z + t.y) >= c.r + PLAYER_R - 1e-6);
  }
});
