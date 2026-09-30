import {
  Color3,
  Mesh,
  PBRMaterial,
  Scene,
  Texture,
  VertexData,
} from '@babylonjs/core';

export const WORLD_SIZE = 240;
export const RIVER_Z = 30;
export const PIT_CENTER = { x: 0, z: 0 };
export const PIT_RX = 30;
export const PIT_RZ = 21;
export const PIT_DEPTH = 5.5;
const PIT_STEPS = 3;

const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

const noise = (x: number, z: number) =>
  Math.sin(x * 0.21 + Math.cos(z * 0.17) * 1.7) * 0.5 +
  Math.sin(z * 0.27 - x * 0.11 + 1.3) * 0.35 +
  Math.sin((x + z) * 0.53) * 0.15;

const ridged = (x: number, z: number) => {
  const a = 1 - Math.abs(Math.sin(x * 0.06 + Math.sin(z * 0.05) * 2));
  const b = 1 - Math.abs(Math.sin(z * 0.08 + x * 0.03 + 1.7));
  return a * 0.6 + b * 0.4;
};

export function riverCenter(x: number) {
  return RIVER_Z + Math.sin(x * 0.07) * 2.5 + Math.sin(x * 0.19) * 0.8;
}

export function pitDistance(x: number, z: number) {
  const dx = (x - PIT_CENTER.x) / PIT_RX;
  const dz = (z - PIT_CENTER.z) / PIT_RZ;
  const wobble = 1 + Math.sin(Math.atan2(dz, dx) * 5) * 0.05 + Math.sin(Math.atan2(dz, dx) * 9) * 0.03;
  return Math.hypot(dx, dz) / wobble;
}

export function heightAt(x: number, z: number): number {
  let h = noise(x, z) * 0.35;

  const hillL = Math.exp(-(((x + 38) ** 2 + (z - 6) ** 2) / 110)) * 3.2;
  const hillL2 = Math.exp(-(((x + 30) ** 2 + (z - 20) ** 2) / 60)) * 2.2;
  h += hillL + hillL2;
  h += Math.exp(-(((x - 38) ** 2 + (z - 12) ** 2) / 220)) * 1.2;

  const d = pitDistance(x, z);
  const pit = 1 - smooth(0.74, 1.04, d);
  const t = pit * PIT_STEPS;
  const k = Math.min(Math.floor(t), PIT_STEPS - 1);
  const terraced = (k + smooth(0.45, 1, t - k)) / PIT_STEPS;
  h = h * (1 - pit) - PIT_DEPTH * terraced + noise(x * 2.3, z * 2.3) * 0.2 * pit;
  h += smooth(0.98, 1.06, d) * (1 - smooth(1.06, 1.2, d)) * 0.6;

  const rz = Math.abs(z - riverCenter(x));
  h -= 1.7 * (1 - smooth(2.6, 4.6, rz));

  const r = Math.hypot(x, z - 5);
  const m = smooth(58, 95, r);
  h += m * (16 + ridged(x, z) * 26);
  return h;
}

export function waterLevel() {
  return -0.7;
}

export async function createTerrain(scene: Scene): Promise<Mesh> {
  const segs = 260;
  const size = WORLD_SIZE;
  const positions: number[] = [];
  const colors: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];

  const pink = new Color3(1.0, 0.45, 0.62);
  const green = new Color3(0.36, 0.86, 0.26);
  const floor = new Color3(1.0, 0.5, 0.28);
  const cliff = new Color3(0.78, 0.5, 0.32);
  const rock = new Color3(0.6, 0.52, 0.5);
  const bank = new Color3(0.9, 0.7, 0.4);

  const mix = (a: Color3, b: Color3, t: number) =>
    new Color3(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t);

  for (let j = 0; j <= segs; j++) {
    for (let i = 0; i <= segs; i++) {
      const x = (i / segs - 0.5) * size;
      const z = (j / segs - 0.5) * size;
      const y = heightAt(x, z);
      positions.push(x, y, z);
      uvs.push(x / 11, z / 11);

      const d = pitDistance(x, z);
      const e = 0.6;
      const slope = Math.hypot(heightAt(x + e, z) - heightAt(x - e, z), heightAt(x, z + e) - heightAt(x, z - e)) / (2 * e);

      let c = x > 8 ? green : x < -14 ? pink : mix(pink, green, smooth(-14, 8, x));
      const inPit = 1 - smooth(0.9, 1.05, d);
      c = mix(c, floor, inPit);
      const band = 0.5 + 0.5 * Math.sin(y * 2.6 + noise(x, z) * 0.6);
      const layered = mix(cliff, new Color3(0.55, 0.32, 0.2), band * 0.6);
      c = mix(c, layered, smooth(0.45, 1.2, slope) * 0.9);
      const rz = Math.abs(z - riverCenter(x));
      c = mix(c, bank, (1 - smooth(2.4, 5.2, rz)) * 0.9);
      const mtn = smooth(60, 90, Math.hypot(x, z - 5));
      c = mix(c, rock, mtn * 0.8);
      const shade = 0.9 + noise(x * 1.7, z * 1.7) * 0.12;
      colors.push(c.r * shade, c.g * shade, c.b * shade, 1);
    }
  }
  const row = segs + 1;
  for (let j = 0; j < segs; j++) {
    for (let i = 0; i < segs; i++) {
      const a = j * row + i;
      indices.push(a, a + 1, a + row, a + 1, a + row + 1, a + row);
    }
  }

  const mesh = new Mesh('terrain', scene);
  const vd = new VertexData();
  vd.positions = positions;
  vd.indices = indices;
  vd.uvs = uvs;
  vd.colors = colors;
  const normals: number[] = [];
  VertexData.ComputeNormals(positions, indices, normals);
  vd.normals = normals;
  vd.applyToMesh(mesh);

  const mat = new PBRMaterial('terrainMat', scene);
  const tex = new Texture('/textures/detail.webp?v=2', scene);
  tex.anisotropicFilteringLevel = 8;
  mat.albedoTexture = tex;
  mat.albedoColor = new Color3(1, 1, 1);
  mat.metallic = 0;
  mat.roughness = 0.92;
  mesh.material = mat;
  mesh.receiveShadows = true;
  mesh.freezeWorldMatrix();
  return mesh;
}
