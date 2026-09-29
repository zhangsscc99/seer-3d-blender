import {
  ArcRotateCamera,
  CascadedShadowGenerator,
  Color3,
  Color4,
  DefaultRenderingPipeline,
  DirectionalLight,
  DynamicTexture,
  Engine,
  HemisphericLight,
  ImageProcessingConfiguration,
  Mesh,
  MeshBuilder,
  PBRMaterial,
  PointLight,
  ReflectionProbe,
  RenderTargetTexture,
  Scene,
  SSAO2RenderingPipeline,
  StandardMaterial,
  Texture,
  TransformNode,
  Vector3,
} from '@babylonjs/core';
import {
  createTerrain,
  heightAt,
  pitDistance,
  riverCenter,
  waterLevel,
} from './terrain';
import { loadProp, spawn, PropName } from './props';

const canvas = document.getElementById('app') as HTMLCanvasElement;
const engine = new Engine(canvas, true, { antialias: true, powerPreference: 'high-performance' });
engine.setHardwareScalingLevel(1 / Math.min(window.devicePixelRatio, 2));
const scene = new Scene(engine);
scene.clearColor = new Color4(0.95, 0.42, 0.22, 1);
scene.fogMode = Scene.FOGMODE_EXP2;
scene.fogColor = new Color3(0.98, 0.55, 0.32);
scene.fogDensity = 0.0055;

let seed = 20260930;
const rnd = () => {
  seed = (seed * 1664525 + 1013904223) >>> 0;
  return seed / 4294967296;
};
const range = (a: number, b: number) => a + rnd() * (b - a);

function createSky() {
  const tex = new DynamicTexture('skyTex', { width: 16, height: 512 }, scene, true);
  const ctx = tex.getContext() as CanvasRenderingContext2D;
  const g = ctx.createLinearGradient(0, 0, 0, 512);
  g.addColorStop(0.0, '#b3261e');
  g.addColorStop(0.35, '#e8541f');
  g.addColorStop(0.55, '#ff8a3d');
  g.addColorStop(0.62, '#ffc06a');
  g.addColorStop(0.66, '#ff9a4a');
  g.addColorStop(1.0, '#c9552a');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 16, 512);
  tex.update();
  const mat = new StandardMaterial('skyMat', scene);
  mat.backFaceCulling = false;
  mat.disableLighting = true;
  mat.emissiveTexture = tex;
  mat.fogEnabled = false;
  const sky = MeshBuilder.CreateSphere('sky', { diameter: 900, segments: 32 }, scene);
  sky.material = mat;
  sky.infiniteDistance = true;
  sky.isPickable = false;
  return sky;
}

function createWaterNormal() {
  const N = 256;
  const tex = new DynamicTexture('waterN', { width: N, height: N }, scene, true);
  const ctx = tex.getContext() as CanvasRenderingContext2D;
  const img = ctx.createImageData(N, N);
  const h = (u: number, v: number) => {
    const a = Math.PI * 2;
    return (
      Math.sin(u * a * 3 + Math.sin(v * a * 2) * 1.2) * 0.5 +
      Math.sin(v * a * 4 - u * a * 2) * 0.3 +
      Math.sin((u + v) * a * 6) * 0.2
    );
  };
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const u = x / N;
      const v = y / N;
      const e = 1 / N;
      const dx = (h(u + e, v) - h(u - e, v)) * 6;
      const dy = (h(u, v + e) - h(u, v - e)) * 6;
      const len = Math.hypot(dx, dy, 1);
      const i = (y * N + x) * 4;
      img.data[i] = ((-dx / len) * 0.5 + 0.5) * 255;
      img.data[i + 1] = ((-dy / len) * 0.5 + 0.5) * 255;
      img.data[i + 2] = (1 / len * 0.5 + 0.5) * 255;
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  tex.update();
  tex.wrapU = Texture.WRAP_ADDRESSMODE;
  tex.wrapV = Texture.WRAP_ADDRESSMODE;
  return tex;
}

function createRiver() {
  const w = MeshBuilder.CreateGround('river', { width: 240, height: 14, subdivisions: 1 }, scene);
  w.position.set(0, waterLevel(), riverCenter(0));
  const n = createWaterNormal();
  n.uScale = 30;
  n.vScale = 2;
  const mat = new PBRMaterial('waterMat', scene);
  mat.albedoColor = new Color3(0.1, 0.62, 0.95);
  mat.metallic = 0;
  mat.roughness = 0.08;
  mat.alpha = 0.78;
  mat.bumpTexture = n;
  mat.bumpTexture.level = 0.7;
  mat.emissiveColor = new Color3(0.02, 0.18, 0.32);
  mat.transparencyMode = PBRMaterial.PBRMATERIAL_ALPHABLEND;
  mat.backFaceCulling = false;
  w.material = mat;
  scene.onBeforeRenderObservable.add(() => {
    const t = performance.now() * 0.00006;
    n.uOffset = t * 3;
    n.vOffset = t;
  });
  w.isPickable = false;
  return w;
}

function createPortal(x: number, z: number) {
  const y = heightAt(x, z);
  const root = new TransformNode('portal', scene);
  root.position.set(x, y + 0.15, z);
  const base = MeshBuilder.CreateCylinder('portalBase', { diameter: 7, height: 0.3, tessellation: 48 }, scene);
  const bm = new PBRMaterial('portalBaseMat', scene);
  bm.albedoColor = new Color3(0.62, 0.66, 0.72);
  bm.metallic = 0.9;
  bm.roughness = 0.35;
  base.material = bm;
  base.parent = root;
  base.position.y = 0.15;
  const ring = MeshBuilder.CreateTorus('portalRing', { diameter: 6.2, thickness: 0.35, tessellation: 64 }, scene);
  ring.material = bm;
  ring.parent = root;
  ring.position.y = 0.4;
  const disc = MeshBuilder.CreateDisc('portalDisc', { radius: 2.9, tessellation: 64 }, scene);
  const dm = new PBRMaterial('portalDiscMat', scene);
  dm.albedoColor = new Color3(0.4, 0.85, 1);
  dm.emissiveColor = new Color3(0.35, 0.85, 1.3);
  dm.alpha = 0.85;
  dm.disableLighting = true;
  disc.material = dm;
  disc.parent = root;
  disc.rotation.x = Math.PI / 2;
  disc.position.y = 0.42;
  const light = new PointLight('portalLight', new Vector3(x, y + 2.5, z), scene);
  light.diffuse = new Color3(0.4, 0.85, 1);
  light.intensity = 12;
  light.range = 22;
  scene.onBeforeRenderObservable.add(() => {
    const t = performance.now() * 0.002;
    dm.emissiveColor = new Color3(0.3, 0.75 + Math.sin(t) * 0.1, 1.2 + Math.sin(t * 1.3) * 0.2);
    light.intensity = 11 + Math.sin(t * 1.7) * 2;
  });
  return { root, meshes: [base, ring] };
}

const hud = document.getElementById('hud') as HTMLElement;
const setStatus = (t: string) => (hud.textContent = t);

async function main() {
  setStatus('克洛斯星 · 加载中…');
  const sky = createSky();

  const sun = new DirectionalLight('sun', new Vector3(-0.55, -0.75, 0.35).normalize(), scene);
  sun.position = new Vector3(60, 80, -40);
  sun.diffuse = new Color3(1, 0.82, 0.6);
  sun.specular = new Color3(1, 0.85, 0.7);
  sun.intensity = 3.2;
  const hemi = new HemisphericLight('hemi', new Vector3(0, 1, 0), scene);
  hemi.diffuse = new Color3(1, 0.72, 0.5);
  hemi.groundColor = new Color3(0.35, 0.22, 0.3);
  hemi.intensity = 0.7;

  const probe = new ReflectionProbe('probe', 128, scene);
  probe.renderList!.push(sky);
  probe.refreshRate = RenderTargetTexture.REFRESHRATE_RENDER_ONCE;
  scene.environmentTexture = probe.cubeTexture;
  scene.environmentIntensity = 0.9;

  const terrain = await createTerrain(scene);
  createRiver();

  const names: PropName[] = [
    'cloud_flower', 'cloud_blue_small', 'grass', 'amberleaf_sentinel', 'amethyst_tendril',
    'cotton_candy_pig', 'emerald_canopy', 'gold_bar', 'gold_pile', 'stone_wall',
    'stump', 'verdant_tendrils', 'whispered_petals',
  ];
  await Promise.all(names.map((n) => loadProp(scene, n)));

  const casters: Mesh[] = [];
  const place = (
    name: PropName,
    x: number,
    z: number,
    opts: Parameters<typeof spawn>[3] = {},
    lift = 0,
  ) => {
    const y = heightAt(x, z) + lift;
    const r = spawn(scene, name, new Vector3(x, y, z), { rotY: rnd() * Math.PI * 2, ...opts });
    for (const m of r.meshes) casters.push(m as Mesh);
    return r;
  };

  const onLand = (x: number, z: number) =>
    pitDistance(x, z) > 1.12 && Math.abs(z - riverCenter(x)) > 5.5 && Math.hypot(x, z - 5) < 78;

  const scatter = (
    name: PropName,
    count: number,
    box: [number, number, number, number],
    size: [number, number],
    by: 'height' | 'width' = 'height',
  ) => {
    let placed = 0;
    for (let tries = 0; placed < count && tries < count * 30; tries++) {
      const x = range(box[0], box[1]);
      const z = range(box[2], box[3]);
      if (!onLand(x, z)) continue;
      const s = range(size[0], size[1]);
      place(name, x, z, by === 'height' ? { height: s } : { width: s });
      placed++;
    }
  };

  // 右侧草地高台
  scatter('emerald_canopy', 8, [26, 70, -20, 22], [5, 8]);
  scatter('amberleaf_sentinel', 6, [28, 70, -20, 24], [4.5, 7]);
  scatter('grass', 70, [22, 72, -22, 26], [1.4, 2.6], 'width');
  scatter('cloud_blue_small', 26, [22, 72, -22, 26], [1.4, 2.4], 'width');
  scatter('cloud_flower', 22, [22, 72, -22, 26], [1.0, 1.9]);
  scatter('stump', 5, [24, 60, -18, 22], [1.6, 2.6]);

  // 左侧粉色岩丘
  scatter('whispered_petals', 20, [-72, -20, -22, 26], [1.6, 3.2]);
  scatter('verdant_tendrils', 16, [-72, -20, -22, 26], [2.2, 4.4]);
  scatter('amethyst_tendril', 12, [-70, -22, -20, 26], [3, 6]);
  scatter('stone_wall', 8, [-70, -24, -20, 24], [3, 6], 'width');
  scatter('cloud_blue_small', 10, [-70, -22, -20, 24], [1.2, 2.2], 'width');

  // 河对岸
  scatter('emerald_canopy', 9, [-60, 60, 40, 72], [5, 9]);
  scatter('amberleaf_sentinel', 6, [-60, 60, 40, 72], [4.5, 7.5]);
  scatter('grass', 50, [-60, 60, 38, 72], [1.4, 2.6], 'width');
  scatter('cloud_flower', 18, [-60, 60, 38, 72], [1.0, 1.9]);
  scatter('amethyst_tendril', 8, [-60, 60, 40, 72], [3, 6]);

  // 靠近后方
  scatter('grass', 24, [-60, 60, -60, -24], [1.4, 2.4], 'width');
  scatter('stone_wall', 8, [-65, 65, -70, -26], [3, 6], 'width');
  scatter('stump', 3, [-40, 40, -60, -28], [1.6, 2.6]);

  // 凹坑边缘岩石
  for (let i = 0; i < 26; i++) {
    const a = (i / 26) * Math.PI * 2 + rnd() * 0.2;
    const d = 1.16 + rnd() * 0.05;
    const x = Math.cos(a) * 24 * d;
    const z = 2 + Math.sin(a) * 19 * d;
    if (Math.abs(z - riverCenter(x)) < 6) continue;
    place('stone_wall', x, z, { width: range(3, 5.5) });
  }

  // 坑底
  for (let i = 0; i < 6; i++) {
    const a = rnd() * Math.PI * 2;
    const d = range(0.35, 0.8);
    place('gold_pile', Math.cos(a) * 24 * d, 2 + Math.sin(a) * 19 * d, { width: range(1.6, 2.6) });
  }
  for (let i = 0; i < 8; i++) {
    const a = rnd() * Math.PI * 2;
    const d = range(0.5, 0.85);
    place('stone_wall', Math.cos(a) * 24 * d, 2 + Math.sin(a) * 19 * d, { width: range(1.6, 3) });
  }

  // 河中发光金矿
  const glowLights: PointLight[] = [];
  const gold: [number, number][] = [[6, 0], [10, 1.4], [8, -1.6], [-22, 0.5], [-26, -1]];
  for (const [gx, off] of gold) {
    const gz = riverCenter(gx) + off;
    place('gold_bar', gx, gz, { width: range(3.2, 4.4) }, 0);
    place('gold_pile', gx + 2.2, gz + 0.8, { width: range(2.2, 3) }, 0);
    const l = new PointLight(`gold${gx}`, new Vector3(gx, waterLevel() + 2.2, gz), scene);
    l.diffuse = new Color3(1, 0.85, 0.35);
    l.intensity = 9;
    l.range = 16;
    glowLights.push(l);
  }

  const portal = createPortal(34, -4);
  for (const m of portal.meshes) casters.push(m as Mesh);

  // 玩家
  const player = place('cotton_candy_pig', 0, 9, { height: 1.5 });
  const cam = new ArcRotateCamera('cam', -Math.PI / 2, 1.0, 15, new Vector3(0, 1, 9), scene);
  cam.lowerRadiusLimit = 5;
  cam.upperRadiusLimit = 32;
  cam.lowerBetaLimit = 0.35;
  cam.upperBetaLimit = 1.45;
  cam.wheelPrecision = 30;
  cam.panningSensibility = 0;
  cam.minZ = 0.1;
  cam.maxZ = 900;
  const dbg = new URLSearchParams(location.search).get('cam');
  const debugCam = !!dbg;
  if (dbg) {
    const [a, b, r, tx, ty, tz] = dbg.split(',').map(Number);
    cam.alpha = a;
    cam.beta = b;
    cam.radius = r;
    cam.target.set(tx, ty, tz);
    cam.upperRadiusLimit = 400;
    cam.lowerBetaLimit = 0.02;
    cam.upperBetaLimit = 3;
  }
  cam.attachControl(canvas, true);
  cam.inputs.removeByType('ArcRotateCameraKeyboardMoveInput');

  const shadow = new CascadedShadowGenerator(2048, sun);
  shadow.numCascades = 3;
  shadow.lambda = 0.75;
  shadow.shadowMaxZ = 130;
  shadow.autoCalcDepthBounds = true;
  shadow.usePercentageCloserFiltering = true;
  shadow.filteringQuality = 1;
  shadow.bias = 0.0008;
  shadow.normalBias = 0.02;
  shadow.stabilizeCascades = true;
  shadow.darkness = 0.25;
  for (const m of casters) shadow.addShadowCaster(m);
  terrain.receiveShadows = true;

  const pipe = new DefaultRenderingPipeline('pipe', true, scene, [cam]);
  pipe.samples = 4;
  pipe.fxaaEnabled = true;
  pipe.bloomEnabled = true;
  pipe.bloomThreshold = 0.75;
  pipe.bloomWeight = 0.45;
  pipe.bloomKernel = 64;
  pipe.bloomScale = 0.6;
  pipe.sharpenEnabled = true;
  pipe.sharpen.edgeAmount = 0.25;
  pipe.imageProcessingEnabled = true;
  pipe.imageProcessing.toneMappingEnabled = true;
  pipe.imageProcessing.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
  pipe.imageProcessing.exposure = 1.1;
  pipe.imageProcessing.contrast = 1.25;
  pipe.imageProcessing.vignetteEnabled = true;
  pipe.imageProcessing.vignetteWeight = 2.2;
  pipe.imageProcessing.vignetteColor = new Color4(0.25, 0.05, 0.02, 0);

  try {
    const ssao = new SSAO2RenderingPipeline('ssao', scene, { ssaoRatio: 0.6, blurRatio: 1 }, [cam]);
    ssao.radius = 2.5;
    ssao.totalStrength = 0.9;
    ssao.expensiveBlur = false;
    ssao.samples = 12;
    ssao.maxZ = 90;
  } catch {
    /* 不支持时跳过 */
  }

  const keys = new Set<string>();
  addEventListener('keydown', (e) => keys.add(e.code));
  addEventListener('keyup', (e) => keys.delete(e.code));
  addEventListener('blur', () => keys.clear());

  const pos = player.node.position;
  let heading = 0;
  let hopT = 0;
  const camTarget = new Vector3(pos.x, pos.y + 1.2, pos.z);

  scene.onBeforeRenderObservable.add(() => {
    const dt = Math.min(engine.getDeltaTime() / 1000, 0.05);
    let fx = 0;
    let fz = 0;
    if (keys.has('KeyW') || keys.has('ArrowUp')) fz += 1;
    if (keys.has('KeyS') || keys.has('ArrowDown')) fz -= 1;
    if (keys.has('KeyD') || keys.has('ArrowRight')) fx += 1;
    if (keys.has('KeyA') || keys.has('ArrowLeft')) fx -= 1;
    const moving = fx !== 0 || fz !== 0;

    if (moving) {
      const forward = cam.getTarget().subtract(cam.position);
      forward.y = 0;
      forward.normalize();
      const right = new Vector3(forward.z, 0, -forward.x);
      const dir = forward.scale(fz).add(right.scale(fx)).normalize();
      const inWater = Math.abs(pos.z - riverCenter(pos.x)) < 4;
      const speed = (keys.has('ShiftLeft') ? 22 : 12) * (inWater ? 0.6 : 1);
      const step = speed * dt;
      const tryMove = (dx: number, dz: number) => {
        const nx = pos.x + dx;
        const nz = pos.z + dz;
        if (Math.hypot(nx, nz - 5) > 84) return false;
        const dh = heightAt(nx, nz) - heightAt(pos.x, pos.z);
        if (dh / step > 1.6) return false;
        pos.x = nx;
        pos.z = nz;
        return true;
      };
      if (!tryMove(dir.x * step, dir.z * step)) {
        if (!tryMove(dir.x * step, 0)) tryMove(0, dir.z * step);
      }
      const target = Math.atan2(dir.x, dir.z);
      let diff = target - heading;
      diff = Math.atan2(Math.sin(diff), Math.cos(diff));
      heading += diff * Math.min(1, dt * 12);
      hopT += dt * (keys.has('ShiftLeft') ? 19 : 14);
    } else {
      hopT = 0;
    }
    const ground = heightAt(pos.x, pos.z);
    const hop = moving ? Math.abs(Math.sin(hopT)) * 0.35 : 0;
    pos.y = ground + hop;
    player.node.rotation.y = heading;

    if (!debugCam) {
      camTarget.x += (pos.x - camTarget.x) * Math.min(1, dt * 8);
      camTarget.y += (pos.y + 1.2 - camTarget.y) * Math.min(1, dt * 8);
      camTarget.z += (pos.z - camTarget.z) * Math.min(1, dt * 8);
      cam.target.copyFrom(camTarget);
    }

    if (!debugCam) {
      const clear = (beta: number) => {
        const sb = Math.sin(beta);
        const cx = cam.target.x + cam.radius * Math.cos(cam.alpha) * sb;
        const cz = cam.target.z + cam.radius * Math.sin(cam.alpha) * sb;
        const cy = cam.target.y + cam.radius * Math.cos(beta);
        return cy - (heightAt(cx, cz) + 1.4);
      };
      let b = cam.beta;
      for (let i = 0; i < 40 && clear(b) < 0 && b > 0.2; i++) b -= 0.04;
      cam.beta = b;
    }

    const t = performance.now() * 0.003;
    glowLights.forEach((l, i) => (l.intensity = 8.5 + Math.sin(t + i) * 1.5));
  });

  setStatus('克洛斯星 · WASD/方向键移动 · Shift 加速 · 拖动旋转视角 · 滚轮缩放');
  engine.runRenderLoop(() => scene.render());
  addEventListener('resize', () => engine.resize());
  (window as unknown as { __scene: Scene }).__scene = scene;
}

main().catch((e) => {
  console.error(e);
  setStatus(`加载失败: ${e?.message ?? e}`);
});
