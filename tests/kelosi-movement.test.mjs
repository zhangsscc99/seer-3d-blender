import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import {
  makeGround,
  makeMovement,
  MAX_SLOPE,
  PLAYER_R,
  WATER_DEPTH,
} from '../src/kelosiMovement.ts';

const meta = JSON.parse(readFileSync(new URL('../public/models/kelosi/kelosi_outdoor.json', import.meta.url)));
const ground = makeGround(meta);
const move = makeMovement(meta, ground);
const hf = meta.heightfield;

const spawn = () => ({ x: meta.spawn.x, z: -meta.spawn.y });

function run(from, to, step = 0.25) {
  const p = { ...from };
  const distance = Math.hypot(to.x - from.x, to.z - from.z);
  const n = Math.max(1, Math.ceil(distance / step));
  for (let i = 0; i < n; i++) {
    move.move(p, (to.x - from.x) / n, (to.z - from.z) / n);
  }
  return p;
}

function route(points) {
  let p = { ...points[0] };
  for (let i = 1; i < points.length; i++) p = run(p, points[i]);
  return p;
}

test('heightfield is a finite row-major square grid with valid bounds', () => {
  assert.equal(hf.cols, Math.round((hf.maxX - hf.minX) / hf.cell) + 1);
  assert.equal(hf.rows, Math.round((hf.maxY - hf.minY) / hf.cell) + 1);
  assert.equal(hf.heights.length, hf.cols * hf.rows);
  assert.ok(hf.heights.every(Number.isFinite));
  assert.ok(hf.minX < hf.maxX && hf.minY < hf.maxY);
  assert.ok(hf.cell > 0);
});

test('heightfield sampler reproduces every sampled grid node', () => {
  for (let row = 0; row < hf.rows; row += 17) {
    for (let col = 0; col < hf.cols; col += 19) {
      const bx = hf.minX + col * hf.cell;
      const by = hf.minY + row * hf.cell;
      const expected = hf.heights[row * hf.cols + col];
      assert.ok(Math.abs(ground(bx, by) - expected) < 1e-6, `node ${col},${row}`);
    }
  }
});

test('spawn is open ground at the flattened start height', () => {
  const p = spawn();
  assert.equal(move.blocked(p.x, p.z), false);
  assert.equal(move.walkable(p.x, p.z), true);
  assert.ok(Math.abs(ground(p.x, p.z) - 2.05) < 0.02);
});

test('walk bounds and colliders contain the player', () => {
  const out = { ...spawn() };
  move.move(out, 0, 200);
  assert.ok(out.z <= -meta.walk.minY - PLAYER_R + 1e-6, 'north walk edge should hold');
  assert.ok(out.z >= -meta.walk.maxY - 1, 'player should stay on the map');

  const c = meta.colliders[0];
  const cx = c.x;
  const cz = -c.y;
  const p = { x: cx, z: cz + 3 };
  move.move(p, 0, -6);
  assert.ok(Math.hypot(p.x - cx, p.z - cz) >= c.r + PLAYER_R - 1e-4, 'circle should push out');
  assert.equal(move.blocked(p.x, p.z), false);
});

test('deep river water is not walkable, but the ford is', () => {
  const deepZ = 3.59;
  assert.ok(ground(0, deepZ) < meta.waterLevel - WATER_DEPTH);
  assert.equal(move.walkable(0, deepZ), false);

  const p = { x: 0, z: 9 };
  move.move(p, 0, -12);
  assert.ok(p.z > 3.0, 'deep water should stop a straight run');

  const ford = { x: 12, z: 7.3 };
  assert.ok(ground(ford.x, ford.z) > meta.waterLevel - WATER_DEPTH);
  assert.equal(move.walkable(ford.x, ford.z), true);
});

test('spawn -> ford -> east plateau -> portal platform route is traversable', () => {
  const points = [
    spawn(),
    { x: 12, z: 24 },
    { x: 12, z: 16 },
    { x: 12, z: 12 },
    { x: 12, z: 8 },
    { x: 12, z: 4 },
    { x: 12, z: 0 },
    { x: 12, z: -4 },
    { x: 12, z: -10 },
    { x: 30, z: -10 },
    { x: 34, z: -16 },
    { x: 34, z: -20 },
  ];
  const end = route(points);
  assert.ok(Math.abs(end.x - 34) < 1.6, `x=${end.x}`);
  assert.ok(Math.abs(end.z + 20) < 1.6, `z=${end.z}`);
  assert.ok(Math.abs(ground(end.x, end.z) - 5.02) < 0.05);
  assert.equal(move.blocked(end.x, end.z), false);
});

test('slope guard rejects a synthetic cliff', () => {
  const flatMeta = {
    ...meta,
    colliders: [],
    boxes: [],
    walk: { minX: -10, maxX: 10, minY: -10, maxY: 10 },
  };
  const cliff = makeMovement(flatMeta, (x) => (x > 0 ? 5 : 0));
  assert.equal(cliff.walkable(-0.1, 0, 0, 0), true);
  assert.equal(cliff.walkable(0.2, 0, 0, 0), false);
  assert.ok(MAX_SLOPE > 0);
});
