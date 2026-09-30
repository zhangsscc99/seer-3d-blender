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
  PIT_DEPTH,
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

  const hy: Record<string, { emissive?: number }> = {
    pink_mound: {}, pink_root: {}, maneater: {}, crystal: { emissive: 0.9 }, lantern: { emissive: 0.35 },
    portal: { emissive: 0.4 }, worm: {}, vine: {}, cliff: {}, rock: {}, tree: {}, bush: {},
    grass: {}, blue_flower: { emissive: 0.3 }, mountain: {}, robot: {},
  };
  await Promise.all(Object.entries(hy).map(([n, o]) => loadProp(scene, `hy/${n}`, o)));

  const casters: Mesh[] = [];
  const place = (
    name: PropName,
    x: number,
    z: number,
    opts: Parameters<typeof spawn>[3] = {},
    lift = 0,
  ) => {
    const y = heightAt(x, z) + lift;
    const r = spawn(scene, `hy/${name}`, new Vector3(x, y, z), { rotY: rnd() * Math.PI * 2, ...opts });
    if (castShadows) for (const m of r.meshes) casters.push(m as Mesh);
    return r;
  };
  let castShadows = true;

  const onLand = (x: number, z: number) =>
    pitDistance(x, z) > 1.1 &&
    Math.abs(z - riverCenter(x)) > 5.5 &&
    Math.hypot(x, z - 5) < 76 &&
    Math.hypot(x - 38, z + 2) > 7;

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

  const glowLights: PointLight[] = [];
  const glowBase: number[] = [];
  const glow = (x: number, y: number, z: number, color: Color3, intensity: number, rangeM: number) => {
    const l = new PointLight(`glow${glowLights.length}`, new Vector3(x, y, z), scene);
    l.diffuse = color;
    l.intensity = intensity;
    l.range = rangeM;
    glowLights.push(l);
    glowBase.push(intensity);
    return l;
  };

  // 左侧粉色岩丘：肉质岩丘 + 蓝莓、触手根须、灯笼草
  const mounds: [number, number, number][] = [[-44, 4, 9], [-36, 14, 7], [-50, 18, 8], [-40, -10, 7.5], [-56, -4, 9]];
  for (const [x, z, w] of mounds) place('pink_mound', x, z, { width: w });
  for (let i = 0; i < 9; i++) {
    const a = rnd() * Math.PI * 2;
    const [mx, mz] = mounds[i % mounds.length];
    place('pink_root', mx + Math.cos(a) * 6, mz + Math.sin(a) * 6, { width: range(7, 11), rotY: a + Math.PI });
  }
  scatter('pink_root', 6, [-66, -32, -22, 24], [6, 10], 'width');
  const lanterns: [number, number][] = [[-33, 2], [-47, -14], [-30, 18]];
  for (const [x, z] of lanterns) {
    const r = place('lantern', x, z, { height: range(2.6, 3.4) });
    glow(x, heightAt(x, z) + r.height * 0.85, z, new Color3(1, 0.9, 0.4), 5, 9);
  }
  scatter('blue_flower', 18, [-70, -30, -22, 24], [1.2, 2]);
  scatter('rock', 6, [-70, -30, -24, 24], [2.5, 4], 'width');
  scatter('grass', 14, [-66, -32, -22, 24], [1.2, 1.8], 'width');

  // 右侧绿色草地：传送台、食人花、盘绕藤蔓、树与灌木
  const portalPos = new Vector3(38, 0, -2);
  const portal = place('portal', portalPos.x, portalPos.z, { width: 8, rotY: 0 });
  glow(portalPos.x, heightAt(portalPos.x, portalPos.z) + 2.5, portalPos.z, new Color3(0.4, 0.85, 1), 12, 20);
  void portal;
  place('maneater', 30, 12, { height: 3.2, rotY: -Math.PI * 0.75 });
  place('maneater', 36, 15, { height: 2.8, rotY: -Math.PI * 0.6 });
  const vines: [number, number][] = [[50, 20], [56, 14], [46, 24], [60, 22]];
  for (const [x, z] of vines) place('vine', x, z, { height: range(5, 7) });
  scatter('tree', 7, [40, 72, -26, 26], [7, 10]);
  scatter('bush', 14, [26, 70, -24, 26], [2.4, 3.8], 'width');
  scatter('grass', 60, [24, 72, -24, 26], [1.2, 2], 'width');
  scatter('blue_flower', 10, [26, 70, -22, 24], [1.2, 1.8]);
  scatter('rock', 5, [28, 70, -24, 24], [2.5, 4], 'width');

  // 凹坑：分层崖壁环绕，坑底岩石，崖壁探出的粉色虫子
  castShadows = false;
  for (let i = 0; i < 34; i++) {
    const a = (i / 34) * Math.PI * 2;
    const d = 0.8;
    const x = Math.cos(a) * 30 * d;
    const z = Math.sin(a) * 21 * d;
    if (Math.abs(z - riverCenter(x)) < 7) continue;
    place('cliff', x, z, { height: PIT_DEPTH * range(0.75, 0.95), rotY: -a + Math.PI / 2 }, -PIT_DEPTH - heightAt(x, z));
  }
  castShadows = true;
  for (let i = 0; i < 7; i++) {
    const a = rnd() * Math.PI * 2;
    const d = range(0.2, 0.6);
    place('rock', Math.cos(a) * 30 * d, Math.sin(a) * 21 * d, { width: range(1.8, 3.2) });
  }
  const wormA = Math.PI * 0.42;
  place('worm', Math.cos(wormA) * 30 * 0.8, Math.sin(wormA) * 21 * 0.8, { height: 3.5, rotY: -wormA - Math.PI / 2 });

  // 河中发光水晶
  const crystals: [number, number, number][] = [[4, 0, 3.6], [8, 1.5, 2.6], [6.5, -1.4, 2.2], [-20, 0.6, 3.2], [-24, -1, 2.4]];
  for (const [cx, off, h] of crystals) {
    const cz = riverCenter(cx) + off;
    place('crystal', cx, cz, { height: h }, -0.3);
    glow(cx, waterLevel() + 2.4, cz, new Color3(1, 0.88, 0.4), 8, 15);
  }

  // 河对岸
  scatter('tree', 10, [-64, 64, 40, 72], [7, 11]);
  scatter('bush', 16, [-64, 64, 38, 72], [2.4, 4], 'width');
  scatter('grass', 40, [-64, 64, 38, 72], [1.2, 2], 'width');
  scatter('pink_mound', 3, [-60, -20, 42, 70], [6, 9], 'width');
  scatter('maneater', 3, [0, 50, 40, 66], [2.6, 3.2]);

  // 靠近镜头的南侧
  scatter('grass', 26, [-64, 64, -66, -26], [1.2, 2], 'width');
  scatter('rock', 8, [-66, 66, -70, -28], [3, 5], 'width');
  scatter('bush', 8, [-60, 60, -66, -28], [2.4, 3.6], 'width');

  // 远景山峰
  castShadows = false;
  for (let i = 0; i < 16; i++) {
    const a = (i / 16) * Math.PI * 2 + rnd() * 0.15;
    const r = range(96, 110);
    const x = Math.cos(a) * r;
    const z = 5 + Math.sin(a) * r;
    place('mountain', x, z, { height: range(40, 60), rotY: rnd() * Math.PI * 2 }, -4);
  }
  castShadows = true;

  // 玩家
  const player = place('robot', 30, -12, { height: 1.9, rotY: 0 });
  const cam = new ArcRotateCamera('cam', -Math.PI / 2, 1.05, 16, new Vector3(30, 1, -12), scene);
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
    glowLights.forEach((l, i) => (l.intensity = glowBase[i] * (0.88 + Math.sin(t + i) * 0.12)));
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
