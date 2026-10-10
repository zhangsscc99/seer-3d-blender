import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { Vector3 } from '@babylonjs/core/Maths/math.vector.js';
import { roomCollision, canOccupy, moveInRoom, floorHeight, EYE_HEIGHT } from '../src/inventionMovement.ts';

const metadata = JSON.parse(readFileSync(new URL('../public/models/inv/invention_room.json', import.meta.url)));
const collision = roomCollision(metadata.colliders);

test('spawn is free and the former hologram-overlapping spawn is rejected', () => {
  assert.equal(canOccupy(0, 4.6, collision), true);
  assert.equal(canOccupy(1.5, 4.2, collision), false);
});

test('a long move cannot tunnel into or through the incubation chamber', () => {
  const position = moveInRoom({ x: 2.5, z: 0.8 }, 6, 0, collision);
  // 新大舱包含外护沿：6.3 - 2.64 - 0.28 = 3.38m。
  assert.ok(position.x <= 3.38 && position.x >= 3.30);
  assert.equal(canOccupy(position.x, position.z, collision), true);
});

test('containment glass and its small console block movement', () => {
  const glass = moveInRoom({ x: -4.7, z: -3 }, 0, -5, collision);
  assert.ok(glass.z > -3.73);
  const console = moveInRoom({ x: -3.35, z: -3 }, 0, -4, collision);
  assert.ok(console.z >= -3.4 && console.z < -3.3);
});

test('walking reaches both steps before the console, rather than an oversized circle', () => {
  assert.equal(floorHeight(0, -4.5), 0.14);
  assert.equal(floorHeight(0, -5.1), 0.28);
  const firstStep = moveInRoom({ x: 0, z: -3 }, 0, -1.5, collision);
  assert.ok(firstStep.z < -4.4);
  const stop = moveInRoom(firstStep, 0, -4, collision);
  assert.ok(stop.z <= -5.3 && stop.z >= -5.52);
  assert.equal(EYE_HEIGHT + floorHeight(stop.x, stop.z), 1.73);
});

test('walls retain space for the body and wall pipes, with sliding along boundaries', () => {
  const stop = moveInRoom({ x: 0, z: 5 }, 0, 20, collision);
  assert.ok(stop.z <= 6.32);
  const slide = moveInRoom({ x: 0, z: 6.3 }, 1, 1, collision);
  assert.ok(slide.x > 0.9 && slide.z <= 6.32);
});

// Babylon 使用访问器保存 x/z，实际相机坐标并非普通对象。
test('camera Vector3 coordinates remain finite on the first movement', () => {
  const position = moveInRoom(new Vector3(0, EYE_HEIGHT, 4.6), 0, -0.15, collision);
  assert.ok(Number.isFinite(position.x) && Number.isFinite(position.z));
  assert.equal(position.x, 0);
  assert.ok(Math.abs(position.z - 4.45) < 1e-8);
});
