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
  TransformNode,
  Vector3,
} from '@babylonjs/core';
import { loadProp, spawn } from './props';

const S = 4;
const FLIP = 0;

type Dir = 'N' | 'S' | 'E' | 'W';
const DV: Record<Dir, [number, number]> = { N: [0, 1], S: [0, -1], E: [1, 0], W: [-1, 0] };
const INWARD: Record<Dir, number> = {
  N: Math.PI + FLIP,
  S: 0 + FLIP,
  E: -Math.PI / 2 + FLIP,
  W: Math.PI / 2 + FLIP,
};
const DIRS: Dir[] = ['N', 'S', 'E', 'W'];

interface Zone {
  id: string;
  name: string;
  x: number;
  z: number;
  w: number;
  h: number;
  corridor?: boolean;
}

const zones: Zone[] = [
  { id: 'hub', name: '指挥中心', x: 8, z: 6, w: 8, h: 8 },
  { id: 'nav', name: '导航室', x: 8, z: 16, w: 8, h: 4 },
  { id: 'cargo', name: '货运舱', x: 7, z: 0, w: 10, h: 4 },
  { id: 'rest', name: '休息舱', x: 0, z: 6, w: 6, h: 8 },
  { id: 'launch', name: '发射平台', x: 18, z: 5, w: 6, h: 10 },
  { id: 'cn', name: '连接通道', x: 11, z: 14, w: 2, h: 2, corridor: true },
  { id: 'cs', name: '连接通道', x: 11, z: 4, w: 2, h: 2, corridor: true },
  { id: 'cw', name: '连接通道', x: 6, z: 9, w: 2, h: 2, corridor: true },
  { id: 'ce', name: '连接通道', x: 16, z: 9, w: 2, h: 2, corridor: true },
];

const cellZone = new Map<string, Zone>();
for (const z of zones)
  for (let i = 0; i < z.w; i++) for (let j = 0; j < z.h; j++) cellZone.set(`${z.x + i},${z.z + j}`, z);
const zoneAt = (cx: number, cz: number) => cellZone.get(`${cx},${cz}`);
const isFloor = (cx: number, cz: number) => cellZone.has(`${cx},${cz}`);
const worldFloor = (x: number, z: number) => isFloor(Math.floor(x / S), Math.floor(z / S));

const canvas = document.getElementById('app') as HTMLCanvasElement;
const engine = new Engine(canvas, true, { antialias: true, powerPreference: 'high-performance' });
engine.setHardwareScalingLevel(1 / Math.min(window.devicePixelRatio, 2));
const scene = new Scene(engine);
scene.clearColor = new Color4(0.02, 0.03, 0.07, 1);

let seed = 77123;
const rnd = () => {
  seed = (seed * 1664525 + 1013904223) >>> 0;
  return seed / 4294967296;
};

const hud = document.getElementById('hud') as HTMLElement;

function makeStarTexture() {
  const W = 2048;
  const H = 1024;
  const tex = new DynamicTexture('stars', { width: W, height: H }, scene, true);
  const ctx = tex.getContext() as CanvasRenderingContext2D;
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, '#04050e');
  g.addColorStop(0.5, '#0b1030');
  g.addColorStop(1, '#04050e');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  const blob = (x: number, y: number, r: number, c: string) => {
    const rg = ctx.createRadialGradient(x, y, 0, x, y, r);
    rg.addColorStop(0, c);
    rg.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = rg;
    ctx.fillRect(x - r, y - r, r * 2, r * 2);
  };
  for (let i = 0; i < 16; i++) {
    const c = ['rgba(120,60,200,0.22)', 'rgba(255,120,60,0.16)', 'rgba(60,140,255,0.2)'][i % 3];
    blob(rnd() * W, H * (0.25 + rnd() * 0.5), 140 + rnd() * 240, c);
  }
  for (let i = 0; i < 2600; i++) {
    const a = 0.3 + rnd() * 0.7;
    const r = rnd() < 0.05 ? 1.8 : rnd() < 0.3 ? 1.1 : 0.7;
    ctx.fillStyle = `rgba(${200 + rnd() * 55},${200 + rnd() * 55},255,${a})`;
    ctx.beginPath();
    ctx.arc(rnd() * W, rnd() * H, r, 0, Math.PI * 2);
    ctx.fill();
  }
  tex.update();
  return tex;
}

function makePlanetTexture() {
  const W = 1024;
  const H = 512;
  const tex = new DynamicTexture('planetTex', { width: W, height: H }, scene, true);
  const ctx = tex.getContext() as CanvasRenderingContext2D;
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, '#ffb060');
  g.addColorStop(0.3, '#ff6a3a');
  g.addColorStop(0.55, '#e83f4a');
  g.addColorStop(0.8, '#ff8a4a');
  g.addColorStop(1, '#ffc27a');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  for (let i = 0; i < 140; i++) {
    const x = rnd() * W;
    const y = rnd() * H;
    ctx.fillStyle = ['rgba(255,220,150,0.16)', 'rgba(150,40,60,0.18)', 'rgba(90,200,90,0.14)'][i % 3];
    ctx.beginPath();
    ctx.ellipse(x, y, 30 + rnd() * 110, 6 + rnd() * 22, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  tex.update();
  return tex;
}

function makeSky() {
  const mat = new StandardMaterial('starMat', scene);
  mat.backFaceCulling = false;
  mat.disableLighting = true;
  mat.emissiveTexture = makeStarTexture();
  const sky = MeshBuilder.CreateSphere('starSky', { diameter: 1800, segments: 32 }, scene);
  sky.material = mat;
  sky.infiniteDistance = true;
  sky.isPickable = false;

  const pm = new StandardMaterial('planetMat', scene);
  pm.disableLighting = true;
  pm.emissiveTexture = makePlanetTexture();
  pm.fogEnabled = false;
  const planet = MeshBuilder.CreateSphere('planet', { diameter: 340, segments: 48 }, scene);
  planet.material = pm;
  planet.position.set(-20, 40, 520);
  planet.isPickable = false;
  const halo = MeshBuilder.CreateSphere('halo', { diameter: 372, segments: 32 }, scene);
  const hm = new StandardMaterial('haloMat', scene);
  hm.disableLighting = true;
  hm.emissiveColor = new Color3(1, 0.45, 0.2);
  hm.alpha = 0.16;
  halo.material = hm;
  halo.position.copyFrom(planet.position);
  halo.isPickable = false;
  scene.onBeforeRenderObservable.add(() => (planet.rotation.y += 0.0004));
  return [sky, planet, halo];
}

async function main() {
  hud.textContent = '赛尔号空间站 · 加载中…';
  const skyMeshes = makeSky();

  const starLight = new DirectionalLight('starLight', new Vector3(0.25, -0.85, -0.5).normalize(), scene);
  starLight.position = new Vector3(20, 80, 120);
  starLight.diffuse = new Color3(1, 0.7, 0.5);
  starLight.intensity = 2.4;
  const hemi = new HemisphericLight('hemi', new Vector3(0, 1, 0), scene);
  hemi.diffuse = new Color3(0.55, 0.68, 1);
  hemi.groundColor = new Color3(0.2, 0.22, 0.34);
  hemi.intensity = 0.95;

  const probe = new ReflectionProbe('probe', 128, scene);
  for (const m of skyMeshes) probe.renderList!.push(m);
  probe.refreshRate = RenderTargetTexture.REFRESHRATE_RENDER_ONCE;
  scene.environmentTexture = probe.cubeTexture;
  scene.environmentIntensity = 1.1;

  const kit = [
    'floor', 'floor-detail', 'floor-panel', 'floor-panel-straight', 'wall', 'wall-window', 'wall-corner',
    'wall-door-wide', 'wall-door', 'structure', 'structure-barrier', 'pipe', 'pipe-bend', 'computer-system',
    'computer', 'computer-wide', 'chair-cushion-headrest', 'chair', 'display-wall-wide', 'display-wall',
    'bed-single', 'bed-double', 'table', 'table-large', 'container', 'container-tall', 'container-wide',
    'container-flat', 'skip', 'skip-rocks', 'rail', 'balcony-rail', 'wall-pillar', 'stairs',
  ];
  await Promise.all([
    ...kit.map((n) => loadProp(scene, `ks/${n}`, { nearest: true })),
    loadProp(scene, 'hy/robot'),
    loadProp(scene, 'hy/portal', { emissive: 0.4 }),
  ]);

  const casters: Mesh[] = [];
  const colliders: { x: number; z: number; r: number }[] = [];
  interface WallRec {
    node: TransformNode;
    nx: number;
    nz: number;
  }
  const walls: WallRec[] = [];

  const put = (name: string, x: number, z: number, rotY = 0, opts: { s?: number; y?: number; shadow?: boolean } = {}) => {
    const r = spawn(scene, `ks/${name}`, new Vector3(x * S, opts.y ?? 0, z * S), {
      scale: (opts.s ?? 1) * S,
      rotY,
    });
    if (opts.shadow !== false) for (const m of r.meshes) casters.push(m as Mesh);
    return r;
  };
  const atWall = (name: string, cx: number, cz: number, dir: Dir, inset = 0.3, opts: { s?: number; rot?: number } = {}) => {
    const [dx, dz] = DV[dir];
    const x = cx + 0.5 + dx * (0.5 - inset);
    const z = cz + 0.5 + dz * (0.5 - inset);
    return put(name, x, z, INWARD[dir] + (opts.rot ?? 0), { s: opts.s });
  };
  const block = (x: number, z: number, r: number) => colliders.push({ x: x * S, z: z * S, r: r * S });

  // 地面
  for (const [key, zone] of cellZone) {
    const [cx, cz] = key.split(',').map(Number);
    let name = 'floor';
    if (zone.id === 'hub') name = (cx + cz) % 2 === 0 ? 'floor-detail' : 'floor';
    else if (zone.corridor) name = 'floor-panel-straight';
    else if (zone.id === 'launch') name = 'floor-panel';
    put(name, cx + 0.5, cz + 0.5, 0, { shadow: false }).meshes.forEach((m) => (m.receiveShadows = true));
  }

  // 墙、窗、栏杆、门
  const windowed = (zone: Zone, dir: Dir) =>
    (zone.id === 'nav' && dir === 'N') ||
    (zone.id === 'rest' && dir === 'W') ||
    (zone.id === 'launch' && (dir === 'N' || dir === 'S')) ||
    (zone.id === 'hub' && false);
  for (const [key, zone] of cellZone) {
    const [cx, cz] = key.split(',').map(Number);
    for (const dir of DIRS) {
      const [dx, dz] = DV[dir];
      const nb = zoneAt(cx + dx, cz + dz);
      const ex = cx + 0.5 + dx * 0.5;
      const ez = cz + 0.5 + dz * 0.5;
      if (!nb) {
        let name = 'wall';
        if (zone.id === 'launch' && dir === 'E') name = 'rail';
        else if (windowed(zone, dir) && (dir === 'N' || dir === 'S' ? cx % 2 === 0 : cz % 2 === 0)) name = 'wall-window';
        const r = put(name, ex, ez, INWARD[dir], { shadow: name !== 'rail' });
        if (name !== 'rail') walls.push({ node: r.node, nx: dx, nz: dz });
      } else if (nb !== zone && (dir === 'N' || dir === 'E')) {
        put('wall-door-wide', ex, ez, INWARD[dir], { shadow: false });
      }
    }
  }
  // 外凸/内凹的墙角
  for (let vx = 0; vx <= 24; vx++) {
    for (let vz = 0; vz <= 20; vz++) {
      const f = [isFloor(vx - 1, vz - 1), isFloor(vx, vz - 1), isFloor(vx - 1, vz), isFloor(vx, vz)];
      const n = f.filter(Boolean).length;
      const diagonal = n === 2 && f[0] === f[3];
      if (n === 1 || n === 3 || diagonal) {
        const r = put('wall-corner', vx, vz, 0);
        const ox = f[0] || f[2] ? -1 : 1;
        const oz = f[0] || f[1] ? -1 : 1;
        walls.push({ node: r.node, nx: -ox * (n === 3 ? -1 : 1), nz: -oz * (n === 3 ? -1 : 1) });
      }
    }
  }

  // 指挥中心：全息星球
  const hc = new Vector3(12 * S, 0, 10 * S);
  const base = MeshBuilder.CreateCylinder('holoBase', { diameter: 5.4, height: 0.6, tessellation: 48 }, scene);
  const baseMat = new PBRMaterial('holoBaseMat', scene);
  baseMat.albedoColor = new Color3(0.28, 0.32, 0.42);
  baseMat.metallic = 0.85;
  baseMat.roughness = 0.35;
  base.material = baseMat;
  base.position.set(hc.x, 0.3, hc.z);
  casters.push(base);
  const baseRing = MeshBuilder.CreateTorus('holoRing', { diameter: 4.6, thickness: 0.14, tessellation: 64 }, scene);
  const glowCyan = new StandardMaterial('glowCyan', scene);
  glowCyan.disableLighting = true;
  glowCyan.emissiveColor = new Color3(0.3, 0.9, 1);
  baseRing.material = glowCyan;
  baseRing.position.set(hc.x, 0.62, hc.z);
  const beam = MeshBuilder.CreateCylinder('holoBeam', { diameterTop: 3.4, diameterBottom: 4, height: 2.6, tessellation: 40, cap: 0 }, scene);
  const beamMat = new StandardMaterial('beamMat', scene);
  beamMat.disableLighting = true;
  beamMat.emissiveColor = new Color3(0.25, 0.8, 1);
  beamMat.alpha = 0.12;
  beamMat.backFaceCulling = false;
  beam.material = beamMat;
  beam.position.set(hc.x, 1.9, hc.z);
  const holo = MeshBuilder.CreateSphere('holoPlanet', { diameter: 2.6, segments: 48 }, scene);
  const holoMat = new StandardMaterial('holoMat', scene);
  holoMat.disableLighting = true;
  holoMat.emissiveTexture = makePlanetTexture();
  holo.material = holoMat;
  holo.position.set(hc.x, 3.7, hc.z);
  const orbit = MeshBuilder.CreateTorus('holoOrbit', { diameter: 4.2, thickness: 0.05, tessellation: 80 }, scene);
  orbit.material = glowCyan;
  orbit.position.copyFrom(holo.position);
  orbit.rotation.z = 0.5;
  scene.onBeforeRenderObservable.add(() => {
    holo.rotation.y += 0.004;
    orbit.rotation.y += 0.01;
  });
  block(12, 10, 0.72);

  const pl = (x: number, y: number, z: number, c: Color3, i: number, r: number) => {
    const l = new PointLight(`pl_${x}_${z}`, new Vector3(x * S, y, z * S), scene);
    l.diffuse = c;
    l.intensity = i;
    l.range = r;
    return l;
  };
  pl(12, 5, 10, new Color3(0.4, 0.85, 1), 26, 26);

  for (const [px, pz] of [[8.7, 6.7], [15.3, 6.7], [8.7, 13.3], [15.3, 13.3]]) {
    put('structure', px, pz, 0, { s: 0.55 });
    block(px, pz, 0.35);
  }
  for (const cx of [9, 10, 13, 14]) atWall('display-wall-wide', cx, 13, 'N', 0.28);
  for (const cx of [9, 10, 13, 14]) atWall('computer', cx, 6, 'S', 0.3);
  for (const cz of [7, 12]) {
    atWall('computer-wide', 8, cz, 'W', 0.3);
    atWall('computer-wide', 15, cz, 'E', 0.3);
  }

  // 导航室
  for (const cx of [8, 9, 10, 13, 14, 15]) {
    atWall('computer-system', cx, 19, 'N', 0.36);
    put('chair-cushion-headrest', cx + 0.5, 18.1, Math.PI, {});
  }
  for (const cz of [17, 18]) {
    atWall('display-wall-wide', 8, cz, 'W', 0.28);
    atWall('display-wall-wide', 15, cz, 'E', 0.28);
  }
  pl(12, 4.5, 18, new Color3(1, 0.62, 0.3), 18, 22);

  // 休息舱
  for (const z of [6.8, 8.05, 9.3, 10.55, 11.8, 13.05]) {
    put('bed-single', 1.05, z - 0.2, Math.PI / 2);
    block(1.05, z - 0.2, 0.42);
  }
  put('table-large', 3.8, 9.5, 0);
  block(3.8, 9.5, 0.8);
  for (const [cx, cz, rot] of [[3.3, 8.7, 0], [4.3, 8.7, 0], [3.3, 10.3, Math.PI], [4.3, 10.3, Math.PI]] as const)
    put('chair', cx, cz, rot);
  atWall('container-tall', 5, 6, 'S', 0.3);
  atWall('container-tall', 4, 6, 'S', 0.3);
  atWall('container', 4, 13, 'N', 0.3);
  atWall('container', 5, 13, 'N', 0.3);
  pl(3, 4.5, 10, new Color3(1, 0.85, 0.65), 16, 20);

  // 货运舱
  const cargo: [string, number, number, number][] = [
    ['container-tall', 7.6, 0.7, 0], ['container-wide', 8.9, 0.7, 0], ['container', 10, 0.65, 0],
    ['container-tall', 7.6, 2.4, 0.3], ['container-wide', 8.9, 2.5, 0], ['skip', 9.3, 1.6, 0.6],
    ['container-tall', 15.4, 0.7, 0], ['container-wide', 14.1, 0.7, 0], ['container-flat', 13, 0.8, 0],
    ['skip-rocks', 15.2, 2.6, 0.5], ['container-tall', 15.4, 1.8, 0], ['container', 14.2, 2.7, 0.2],
  ];
  for (const [n, x, z, r] of cargo) {
    put(n, x, z, r);
    block(x, z, 0.42);
  }
  pl(12, 4.5, 2, new Color3(1, 0.75, 0.35), 18, 24);

  // 发射平台
  const portal = spawn(scene, 'hy/portal', new Vector3(21 * S, 0, 9.5 * S), { width: 10 });
  for (const m of portal.meshes) casters.push(m as Mesh);
  block(21, 9.5, 1.25);
  pl(21, 4, 9.5, new Color3(0.4, 0.85, 1), 24, 24);
  atWall('container', 18, 5, 'S', 0.3);
  atWall('container-tall', 19, 5, 'S', 0.3);
  atWall('container-wide', 18, 14, 'N', 0.3);

  // 走廊灯带
  const strip = new StandardMaterial('stripMat', scene);
  strip.disableLighting = true;
  strip.emissiveColor = new Color3(0.3, 0.85, 1);
  const addStrip = (x: number, z: number, w: number, d: number) => {
    const b = MeshBuilder.CreateBox('strip', { width: w * S, depth: d * S, height: 0.05 }, scene);
    b.material = strip;
    b.position.set(x * S, 0.32, z * S);
  };
  addStrip(11.12, 15, 0.06, 2);
  addStrip(12.88, 15, 0.06, 2);
  addStrip(11.12, 5, 0.06, 2);
  addStrip(12.88, 5, 0.06, 2);
  addStrip(7, 9.12, 2, 0.06);
  addStrip(7, 10.88, 2, 0.06);
  addStrip(17, 9.12, 2, 0.06);
  addStrip(17, 10.88, 2, 0.06);

  // 玩家
  const player = spawn(scene, 'hy/robot', new Vector3(12 * S, 0, 8 * S), { height: 1.7 });
  for (const m of player.meshes) casters.push(m as Mesh);

  const cam = new ArcRotateCamera('cam', -Math.PI / 2, 1.0, 17, new Vector3(12 * S, 1, 8 * S), scene);
  cam.lowerRadiusLimit = 6;
  cam.upperRadiusLimit = 34;
  cam.lowerBetaLimit = 0.4;
  cam.upperBetaLimit = 1.4;
  cam.wheelPrecision = 30;
  cam.panningSensibility = 0;
  cam.minZ = 0.1;
  cam.maxZ = 2500;
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

  const shadow = new CascadedShadowGenerator(2048, starLight);
  shadow.numCascades = 3;
  shadow.shadowMaxZ = 110;
  shadow.autoCalcDepthBounds = true;
  shadow.usePercentageCloserFiltering = true;
  shadow.bias = 0.001;
  shadow.normalBias = 0.02;
  shadow.stabilizeCascades = true;
  shadow.darkness = 0.35;
  for (const m of casters) shadow.addShadowCaster(m);

  const pipe = new DefaultRenderingPipeline('pipe', true, scene, [cam]);
  pipe.samples = 4;
  pipe.fxaaEnabled = true;
  pipe.bloomEnabled = true;
  pipe.bloomThreshold = 0.8;
  pipe.bloomWeight = 0.5;
  pipe.bloomKernel = 64;
  pipe.bloomScale = 0.6;
  pipe.sharpenEnabled = true;
  pipe.sharpen.edgeAmount = 0.2;
  pipe.imageProcessingEnabled = true;
  pipe.imageProcessing.toneMappingEnabled = true;
  pipe.imageProcessing.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
  pipe.imageProcessing.exposure = 1.05;
  pipe.imageProcessing.contrast = 1.18;
  pipe.imageProcessing.vignetteEnabled = true;
  pipe.imageProcessing.vignetteWeight = 1.6;
  pipe.imageProcessing.vignetteColor = new Color4(0, 0, 0.05, 0);
  try {
    const ssao = new SSAO2RenderingPipeline('ssao', scene, { ssaoRatio: 0.6, blurRatio: 1 }, [cam]);
    ssao.radius = 2;
    ssao.totalStrength = 0.9;
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
  const camTarget = new Vector3(pos.x, 1, pos.z);
  const R = 0.55;
  const walkable = (x: number, z: number) => {
    if (!(worldFloor(x - R, z - R) && worldFloor(x + R, z - R) && worldFloor(x - R, z + R) && worldFloor(x + R, z + R)))
      return false;
    for (const c of colliders) if (Math.hypot(x - c.x, z - c.z) < c.r + 0.4) return false;
    return true;
  };
  let lastZone = '';
  const tmp = new Vector3();

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
      const step = (keys.has('ShiftLeft') ? 17 : 9.5) * dt;
      if (walkable(pos.x + dir.x * step, pos.z + dir.z * step)) {
        pos.x += dir.x * step;
        pos.z += dir.z * step;
      } else if (walkable(pos.x + dir.x * step, pos.z)) pos.x += dir.x * step;
      else if (walkable(pos.x, pos.z + dir.z * step)) pos.z += dir.z * step;
      let diff = Math.atan2(dir.x, dir.z) - heading;
      diff = Math.atan2(Math.sin(diff), Math.cos(diff));
      heading += diff * Math.min(1, dt * 12);
    }
    player.node.rotation.y = heading;
    pos.y = moving ? Math.abs(Math.sin(performance.now() * 0.012)) * 0.12 : 0;

    if (!debugCam) {
      const k = Math.min(1, dt * 8);
      camTarget.x += (pos.x - camTarget.x) * k;
      camTarget.z += (pos.z - camTarget.z) * k;
      camTarget.y = 1.2;
      cam.target.copyFrom(camTarget);
    }

    const zn = zoneAt(Math.floor(pos.x / S), Math.floor(pos.z / S))?.name ?? '';
    if (zn && zn !== lastZone) {
      lastZone = zn;
      hud.textContent = `赛尔号空间站 · ${zn} · WASD 移动 · Shift 加速 · 拖动旋转 · 滚轮缩放`;
    }

    tmp.copyFrom(cam.position).subtractInPlace(pos);
    tmp.y = 0;
    tmp.normalize();
    for (const w of walls) {
      const wp = w.node.position;
      const near = Math.hypot(wp.x - pos.x, wp.z - pos.z) < 42;
      const facing = w.nx * tmp.x + w.nz * tmp.z;
      w.node.setEnabled(!(near && facing > 0.3 && !debugCam));
    }
  });

  hud.textContent = '赛尔号空间站 · WASD 移动 · Shift 加速 · 拖动旋转 · 滚轮缩放';
  engine.runRenderLoop(() => scene.render());
  addEventListener('resize', () => engine.resize());
  (window as unknown as { __scene: Scene }).__scene = scene;
}

main().catch((e) => {
  console.error(e);
  hud.textContent = `加载失败: ${e?.message ?? e}`;
});

export {};
