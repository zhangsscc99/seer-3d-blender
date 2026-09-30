import { NodeIO } from '@gltf-transform/core';
import { EXTMeshoptCompression, EXTTextureWebP } from '@gltf-transform/extensions';
import { weld, simplify, prune, dedup, compactPrimitive } from '@gltf-transform/functions';
import { MeshoptSimplifier } from 'meshoptimizer';
import sharp from 'sharp';
import fs from 'node:fs';
import path from 'node:path';

const GLB_DIR = process.env.GLB_DIR ?? '/tmp/seer_glb';
const TEX_DIR = process.env.TEX_DIR ?? '/tmp/seer_raw';
const OUT_DIR = path.resolve('public/models');

const TARGET_TRIS = {
  cloud_ground: 60000,
  grass: 7000,
  cloud_blue_small: 7000,
  cloud_flower: 10000,
  verdant_tendrils: 8000,
  whispered_petals: 10000,
  amethyst_tendril: 12000,
  gold_bar: 12000,
  gold_pile: 12000,
  stone_wall: 15000,
  default: 30000,
};
const TEX_SIZE = { cloud_ground: 2048, default: 1024 };

await MeshoptSimplifier.ready;
fs.mkdirSync(OUT_DIR, { recursive: true });

const io = new NodeIO().registerExtensions([EXTMeshoptCompression, EXTTextureWebP]);

const names = fs
  .readdirSync(TEX_DIR, { withFileTypes: true })
  .filter((d) => d.isDirectory())
  .map((d) => d.name);

const webp = (input, size, quality = 88) =>
  sharp(input).resize(size, size, { fit: 'inside' }).webp({ quality }).toBuffer();

async function buildOrm(dir, size) {
  const rough = await sharp(path.join(dir, 'model_roughness.png'))
    .resize(size, size, { fit: 'fill' })
    .greyscale()
    .raw()
    .toBuffer();
  const metal = await sharp(path.join(dir, 'model_metallic.png'))
    .resize(size, size, { fit: 'fill' })
    .greyscale()
    .raw()
    .toBuffer();
  const px = size * size;
  const out = Buffer.alloc(px * 3);
  for (let i = 0; i < px; i++) {
    out[i * 3] = 255;
    out[i * 3 + 1] = rough[i];
    out[i * 3 + 2] = metal[i];
  }
  return sharp(out, { raw: { width: size, height: size, channels: 3 } })
    .webp({ quality: 90 })
    .toBuffer();
}

for (const name of names) {
  const dir = path.join(TEX_DIR, name);
  const src = path.join(GLB_DIR, `${name}.glb`);
  if (!fs.existsSync(src)) {
    console.warn(`skip ${name}: no glb`);
    continue;
  }
  const size = TEX_SIZE[name] ?? TEX_SIZE.default;
  const doc = await io.read(src);
  const root = doc.getRoot();

  for (const m of root.listMaterials()) m.dispose();
  for (const t of root.listTextures()) t.dispose();
  for (const ext of root.listExtensionsUsed()) {
    if (ext.extensionName === 'KHR_materials_unlit') ext.dispose();
  }
  doc.createExtension(EXTTextureWebP).setRequired(true);

  const tex = (label, buf) =>
    doc.createTexture(label).setImage(new Uint8Array(buf)).setMimeType('image/webp');

  const base = tex('baseColor', await webp(path.join(dir, 'model_basecolor.png'), size));
  const normal = tex('normal', await webp(path.join(dir, 'model_normal.png'), size, 92));
  const orm = tex('orm', await buildOrm(dir, size));
  const emis = tex('emissive', await webp(path.join(dir, 'model_emission.png'), Math.min(size, 512)));

  const mat = doc
    .createMaterial(name)
    .setBaseColorTexture(base)
    .setNormalTexture(normal)
    .setMetallicRoughnessTexture(orm)
    .setOcclusionTexture(orm)
    .setEmissiveTexture(emis)
    .setEmissiveFactor([1, 1, 1])
    .setMetallicFactor(1)
    .setRoughnessFactor(1)
    .setDoubleSided(false);

  let tris = 0;
  for (const mesh of root.listMeshes()) {
    for (const p of mesh.listPrimitives()) {
      p.setMaterial(mat);
      const idx = p.getIndices();
      tris += idx ? idx.getCount() / 3 : p.getAttribute('POSITION').getCount() / 3;
    }
  }

  const target = TARGET_TRIS[name] ?? TARGET_TRIS.default;
  const ratio = Math.min(1, target / tris);
  await doc.transform(
    weld(),
    ratio < 1 ? simplify({ simplifier: MeshoptSimplifier, ratio, error: ratio < 0.01 ? 0.3 : 0.02 }) : (d) => d,
    dedup(),
    prune(),
  );

  for (const mesh of root.listMeshes()) {
    for (const p of mesh.listPrimitives()) {
      const idx = p.getIndices();
      const pos = p.getAttribute('POSITION');
      if (!idx || !pos) continue;
      const cur = idx.getCount() / 3;
      if (cur <= target * 1.3) continue;
      const [next] = MeshoptSimplifier.simplifySloppy(
        new Uint32Array(idx.getArray()),
        new Float32Array(pos.getArray()),
        3,
        null,
        target * 3,
        0.5,
      );
      idx.setArray(next);
      compactPrimitive(p);
    }
  }
  await doc.transform(prune());

  const out = path.join(OUT_DIR, `${name}.glb`);
  await io.write(out, doc);
  const kb = (fs.statSync(out).size / 1024).toFixed(0);
  console.log(`${name}: ${Math.round(tris)} tris -> ratio ${ratio.toFixed(3)}, ${kb} KB`);
}

const groundTex = path.join(TEX_DIR, 'cloud_ground', 'model_basecolor.png');
const texOut = path.resolve('public/textures');
fs.mkdirSync(texOut, { recursive: true });
await sharp(groundTex)
  .resize(1024, 1024, { fit: 'fill' })
  .greyscale()
  .normalise()
  .blur(1.2)
  .linear(0.16, 214)
  .webp({ quality: 85 })
  .toFile(path.join(texOut, 'detail.webp'));
console.log('detail texture written');
