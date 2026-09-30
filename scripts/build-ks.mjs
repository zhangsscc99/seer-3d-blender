import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import fs from 'node:fs';
import path from 'node:path';

const SRC = path.resolve('assets-src/kenney-space-station-kit/glb');
const OUT = path.resolve('public/models/ks');
fs.mkdirSync(OUT, { recursive: true });
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
for (const f of fs.readdirSync(SRC).filter((f) => f.endsWith('.glb'))) {
  const doc = await io.read(path.join(SRC, f));
  await io.write(path.join(OUT, f), doc);
}
console.log(`${fs.readdirSync(OUT).length} models -> ${OUT}`);
