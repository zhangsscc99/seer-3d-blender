import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import { makeCollision, PLAYER_R } from '../src/lookoutMovement.ts';

const meta = JSON.parse(readFileSync(new URL('../public/models/lookout/lookout_deck.json', import.meta.url)));
const move = makeCollision(meta);

function inside(p) {
  for (const c of meta.colliders) {
    if (Math.hypot(p.x + c.x, p.z + c.y) < c.r + PLAYER_R - 1e-6) return `circle ${c.x},${c.y}`;
  }
  for (const b of meta.boxes) {
    const minX = -b.maxX - PLAYER_R;
    const maxX = -b.minX + PLAYER_R;
    const minZ = -b.maxY - PLAYER_R;
    const maxZ = -b.minY + PLAYER_R;
    if (p.x > minX && p.x < maxX && p.z > minZ && p.z < maxZ) return `box ${JSON.stringify(b)}`;
  }
  const w = meta.walk;
  if (p.x < -w.maxX + PLAYER_R - 1e-6 || p.x > -w.minX - PLAYER_R + 1e-6) return 'walk x';
  if (p.z < -w.maxY + PLAYER_R - 1e-6 || p.z > -w.minY - PLAYER_R + 1e-6) return 'walk z';
  return '';
}

const spawn = () => new Vector3(-meta.spawn.x, 0, -meta.spawn.y);

test('lookout spawn stands on the open walkway', () => {
  const p = spawn();
  assert.equal(inside(p), '');
});

test('a straight run cannot enter the central dais or leave the deck', () => {
  const p = spawn();
  move(p, 0, -12);
  assert.equal(inside(p), '');
  assert.ok(p.z > -meta.walk.maxY, 'dais or back edge should stop the run');
  const side = spawn();
  move(side, -20, 0);
  assert.equal(inside(side), '');
  assert.ok(side.x > -meta.walk.maxX, 'left lip should hold the player');
});

test('the aisle between the rails stays walkable', () => {
  const p = spawn();
  move(p, 0.35, 0.8);
  assert.equal(inside(p), '');
  assert.ok(Math.abs(p.x) < 0.7, 'the step should remain between the rails');
});
