import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { weld, simplify, prune, dedup, textureCompress } from '@gltf-transform/functions';
import { MeshoptSimplifier } from 'meshoptimizer';
import sharp from 'sharp';
import fs from 'node:fs';
import path from 'node:path';

const RAW = path.resolve('gen/raw');
const OUT = path.resolve('public/models/hy');
const TARGET_TRIS = { mountain: 40000, cliff: 20000, portal: 20000, robot: 25000, default: 14000 };
const TEX = { mountain: 2048, robot: 2048, default: 1024 };

await MeshoptSimplifier.ready;
fs.mkdirSync(OUT, { recursive: true });
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);

const only = process.argv.slice(2);
const names = fs
  .readdirSync(RAW)
  .filter((n) => fs.existsSync(path.join(RAW, n, 'model.glb')))
  .filter((n) => !only.length || only.includes(n));

for (const name of names) {
  const doc = await io.read(path.join(RAW, name, 'model.glb'));
  const root = doc.getRoot();
  let tris = 0;
  for (const m of root.listMeshes())
    for (const p of m.listPrimitives()) {
      const idx = p.getIndices();
      tris += (idx ? idx.getCount() : p.getAttribute('POSITION').getCount()) / 3;
    }
  const target = TARGET_TRIS[name] ?? TARGET_TRIS.default;
  const ratio = Math.min(1, target / tris);
  const size = TEX[name] ?? TEX.default;

  await doc.transform(
    dedup(),
    weld(),
    ...(ratio < 1 ? [simplify({ simplifier: MeshoptSimplifier, ratio, error: 0.004 })] : []),
    textureCompress({ encoder: sharp, targetFormat: 'webp', resize: [size, size], quality: 88 }),
    prune(),
  );

  const out = path.join(OUT, `${name}.glb`);
  await io.write(out, doc);
  const mats = root.listMaterials().map((m) =>
    [m.getBaseColorTexture() && 'base', m.getNormalTexture() && 'normal', m.getMetallicRoughnessTexture() && 'mr', m.getEmissiveTexture() && 'emis']
      .filter(Boolean)
      .join('+'),
  );
  console.log(
    `${name}: ${Math.round(tris)} -> ~${Math.round(tris * ratio)} tris, ${(fs.statSync(out).size / 1024).toFixed(0)} KB, 材质[${mats.join(', ')}]`,
  );
}
