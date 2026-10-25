import {
  AbstractMesh,
  ArcRotateCamera,
  Camera,
  CascadedShadowGenerator,
  Color3,
  Color4,
  DefaultRenderingPipeline,
  DirectionalLight,
  Engine,
  HemisphericLight,
  ImageProcessingConfiguration,
  ImportMeshAsync,
  PBRMaterial,
  PointLight,
  ReflectionProbe,
  RenderTargetTexture,
  Scene,
  SSAO2RenderingPipeline,
  Texture,
  Vector3,
} from '@babylonjs/core';
import '@babylonjs/loaders/glTF';
import { loadProp, spawn } from './props';
import { makeCollision } from './powerMovement';
import { attachCompanions, preloadCompanions } from './companions';
import { createBackpack } from './backpack';

interface Meta {
  colliders: { x: number; y: number; r: number }[];
  lights: { x: number; y: number; z: number; color: number[]; power: number; range: number }[];
  walk: { minX: number; maxX: number; minY: number; maxY: number };
  spawn: { x: number; y: number };
}

const canvas = document.getElementById('app') as HTMLCanvasElement;
const engine = new Engine(canvas, true, { antialias: true, powerPreference: 'high-performance' });
engine.setHardwareScalingLevel(1 / Math.min(window.devicePixelRatio, 2));
const scene = new Scene(engine);
scene.clearColor = new Color4(0.02, 0.03, 0.05, 1);

const hud = document.getElementById('hud') as HTMLElement;
const params = new URLSearchParams(location.search);
const refMode = params.has('ref');
const dbg = params.get('cam');
// Blender(x,y,z) -> Babylon(-x,z,-y)
const toB = (x: number, y: number, z: number) => new Vector3(-x, z, -y);

const wallGroup = (name: string): 'left' | 'right' | 'back' | null => {
  if (name.startsWith('wall_left')) return 'left';
  if (name.startsWith('wall_right')) return 'right';
  if (name.startsWith('wall_back')) return 'back';
  return null;
};

function tuneMaterials() {
  for (const mat of scene.materials) {
    if (!(mat instanceof PBRMaterial)) continue;
    const n = mat.name;
    if (n === 'pw_cream' || n === 'pw_cream_light') {
      mat.environmentIntensity = 0.55;
      mat.clearCoat.isEnabled = true;
      mat.clearCoat.intensity = 0.35;
      mat.clearCoat.roughness = 0.25;
    } else if (n === 'pw_brass') {
      mat.environmentIntensity = 1.6;
      mat.roughness = 0.3;
      mat.emissiveColor = new Color3(0.16, 0.08, 0.03);
    } else if (n === 'pw_grate') {
      mat.environmentIntensity = 0.4;
    } else if (n === 'pw_glass') {
      mat.alpha = 0.30;
      mat.useAlphaFresnel = true;
      mat.useLinearAlphaFresnel = true;
      mat.albedoColor = new Color3(0.10, 0.14, 0.19);
      mat.metallic = 0.65;
      mat.roughness = 0.04;
      mat.subSurface.isRefractionEnabled = false;
      mat.backFaceCulling = false;
      mat.environmentIntensity = 1.5;
    } else if (n === 'pw_flame') {
      // 只保留自发光，避免反照率被灯光照亮后冲淡橙色。
      mat.albedoTexture = null;
      mat.albedoColor = Color3.Black();
      mat.emissiveIntensity = 1.1;
    } else if (n === 'pw_glow_cyan' || n === 'pw_glow_red') {
      mat.emissiveIntensity = 2.0;
      mat.emissiveColor = n === 'pw_glow_cyan' ? new Color3(0.08, 0.72, 1) : new Color3(1, 0.1, 0.06);
    } else if (n === 'pw_glow_orange') {
      mat.emissiveColor = new Color3(1, 0.5, 0.15);
      mat.emissiveIntensity = 1.2;
    } else if (n === 'pw_energy_blue' || n === 'pw_energy_orange') {
      mat.emissiveIntensity = 1.6;
    } else if (n === 'pw_screen_ui' || n === 'pw_window') {
      mat.emissiveIntensity = 1.1;
    } else if (n === 'pw_jamb') {
      mat.emissiveIntensity = 0.6;
    } else if (n === 'pw_wall' || n === 'pw_wall_dark') {
      mat.environmentIntensity = 0.8;
    }
  }
}

/** 动画：火焰流动 + 闪烁、横纹灯扫光、能量棒流动。 */
function animate(meshes: AbstractMesh[], coreLights: PointLight[]) {
  const mat = (name: string) => scene.getMaterialByName(name) as PBRMaterial | null;
  const flame = mat('pw_flame');
  const blue = mat('pw_energy_blue');
  const orange = mat('pw_energy_orange');
  const scrolled = [flame, blue, orange].flatMap((m) =>
    m ? [m.emissiveTexture, m.albedoTexture].filter((t): t is Texture => t instanceof Texture) : [],
  );
  const base = new Map(coreLights.map((l) => [l, l.intensity]));
  // 每根灯条独立材质，按序号做依次亮起的扫光。
  const strips = meshes
    .map((m) => ({ m, hit: /^strip_(cyan|red)_(.+)_(\d+)$/.exec(m.name) }))
    .filter((s) => s.hit && s.m.material)
    .map(({ m, hit }) => {
      const own = (m.material as PBRMaterial).clone(`${m.name}_mat`);
      m.material = own;
      return { own, k: Number(hit![3]), lamp: hit![2], red: hit![1] === 'red', base: own.emissiveIntensity || 1 };
    });
  scene.onBeforeRenderObservable.add(() => {
    const t = performance.now() * 0.001;
    for (const tex of scrolled) {
      const isFlame = tex === flame?.emissiveTexture || tex === flame?.albedoTexture;
      tex.vOffset = (isFlame ? -t * 0.12 : t * (tex === blue?.emissiveTexture || tex === blue?.albedoTexture ? 0.45 : -0.32)) % 1;
      if (isFlame) tex.uOffset = Math.sin(t * 0.3) * 0.04;
    }
    const flicker = 0.88 + 0.07 * Math.sin(t * 7.3) + 0.05 * Math.sin(t * 12.9 + 1.3);
    if (flame) flame.emissiveIntensity = 1.1 * (0.9 + 0.1 * flicker);
    for (const [l, i] of base) l.intensity = i * flicker;
    for (const s of strips) {
      const phase = (s.lamp.length % 3) * 0.7;
      const wave = s.red ? 0.5 + 0.5 * Math.sin(t * 2.2 + phase) : Math.max(0, Math.cos((t * 1.6 + phase - s.k * 0.32) % 3.2));
      s.own.emissiveIntensity = s.base * (0.45 + 0.55 * wave);
    }
  });
}


async function main() {
  hud.innerHTML = '<span style="font-size:22px;font-weight:700;letter-spacing:2px">动力室 I</span><br>加载中…';
  const meta: Meta = await (await fetch('/models/power/power_room.json')).json();
  const [res] = await Promise.all([
    ImportMeshAsync('/models/power/power_room.glb', scene),
    refMode ? Promise.resolve() : loadProp(scene, 'player/seer_robot'),
    refMode ? Promise.resolve() : preloadCompanions(scene),
  ]);
  const meshes = res.meshes;
  const walls: Record<string, AbstractMesh[]> = { left: [], right: [], back: [] };
  for (const m of meshes) {
    const g = wallGroup(m.name);
    if (g) walls[g].push(m);
    m.receiveShadows = true;
  }
  tuneMaterials();
  // 必须在创建灯光前实例化，否则机器人网格拿不到光源列表。
  const player = refMode ? null : spawn(scene, 'player/seer_robot', toB(meta.spawn.x, meta.spawn.y, 0), { height: 1.25, rotY: Math.PI });
  // 伙伴也要在灯光创建前实例化。
  const companions = player ? attachCompanions(scene, player.node, { playerHeight: 1.25 }) : null;

  const hemi = new HemisphericLight('hemi', new Vector3(0, 1, 0.2), scene);
  hemi.diffuse = new Color3(0.78, 0.84, 0.95);
  hemi.groundColor = new Color3(0.32, 0.28, 0.25);
  hemi.intensity = 1.3;
  const key = new DirectionalLight('key', new Vector3(0.2, -1, 0.45).normalize(), scene);
  key.position = new Vector3(-4, 12, -8);
  key.diffuse = new Color3(1, 0.95, 0.88);
  key.intensity = 1.6;
  const coreLights: PointLight[] = [];
  for (const l of meta.lights) {
    const p = new PointLight('pl', toB(l.x, l.y, l.z), scene);
    p.diffuse = new Color3(l.color[0], l.color[1], l.color[2]);
    p.intensity = l.power / 5;
    p.range = l.range * 1.3;
    if (l.power >= 30) coreLights.push(p);
  }
  animate(meshes, coreLights);

  const shadow = new CascadedShadowGenerator(2048, key);
  shadow.numCascades = 2;
  shadow.shadowMaxZ = 30;
  shadow.autoCalcDepthBounds = true;
  shadow.usePercentageCloserFiltering = true;
  shadow.bias = 0.0008;
  shadow.normalBias = 0.02;
  shadow.darkness = 0.45;
  for (const m of meshes) if (!wallGroup(m.name) && m.getTotalVertices() > 0 && (m.material?.alpha ?? 1) >= 1) shadow.addShadowCaster(m);

  // 参考视角：原图为 16:9，垂直视场约 48.9°（旧参考图两侧有黑边，不能按整幅宽度算水平视场）。
  const cam = new ArcRotateCamera('cam', Math.PI / 2, 0.92, 9.2, toB(0, 0.9, 1.0), scene);
  cam.fovMode = Camera.FOVMODE_VERTICAL_FIXED;
  cam.fov = 0.854;
  cam.minZ = 0.1;
  cam.maxZ = 200;
  cam.wheelPrecision = 40;
  cam.panningSensibility = 0;
  cam.inputs.removeByType('ArcRotateCameraKeyboardMoveInput');
  const values = dbg?.split(',').map(Number);
  if (values?.length === 6 && values.every(Number.isFinite)) {
    const [a, b, r, tx, ty, tz] = values;
    cam.alpha = a;
    cam.beta = b;
    cam.radius = r;
    cam.target.set(tx, ty, tz);
  }
  cam.attachControl(canvas, true);

  if (!refMode) {
    cam.fov = 0.95;
    cam.radius = 5.2;
    cam.beta = 0.88;
    cam.lowerRadiusLimit = 3;
    cam.upperRadiusLimit = 10;
    cam.lowerBetaLimit = 0.45;
    cam.upperBetaLimit = 1.35;
    if (!player) throw new Error('robot not spawned');
    for (const m of player.meshes) {
      shadow.addShadowCaster(m);
    }
    if (companions) for (const m of companions.meshes) shadow.addShadowCaster(m);
    if (companions) createBackpack(companions);
    const pos = player.node.position;
    const move = makeCollision(meta);
    const keys = new Set<string>();
    addEventListener('keydown', (e) => keys.add(e.code));
    addEventListener('keyup', (e) => keys.delete(e.code));
    addEventListener('blur', () => keys.clear());
    let heading = Math.PI;
    let hop = 0;
    const camTarget = pos.add(new Vector3(0, 1, 0));
    scene.onBeforeRenderObservable.add(() => {
      const dt = Math.min(engine.getDeltaTime() / 1000, 0.05);
      const fz = (keys.has('KeyW') || keys.has('ArrowUp') ? 1 : 0) - (keys.has('KeyS') || keys.has('ArrowDown') ? 1 : 0);
      const fx = (keys.has('KeyD') || keys.has('ArrowRight') ? 1 : 0) - (keys.has('KeyA') || keys.has('ArrowLeft') ? 1 : 0);
      const fast = keys.has('ShiftLeft') || keys.has('ShiftRight');
      if (fx || fz) {
        const fwd = cam.getTarget().subtract(cam.position);
        fwd.y = 0;
        fwd.normalize();
        const dir = fwd.scale(fz).add(new Vector3(fwd.z, 0, -fwd.x).scale(fx)).normalize();
        const step = (fast ? 4.2 : 2.6) * dt;
        move(pos, dir.x * step, dir.z * step);
        const diff = Math.atan2(Math.sin(Math.atan2(dir.x, dir.z) - heading), Math.cos(Math.atan2(dir.x, dir.z) - heading));
        heading += diff * Math.min(1, dt * 12);
        hop += dt * (fast ? 17 : 13);
      } else hop = 0;
      pos.y = Math.abs(Math.sin(hop)) * 0.08;
      player.node.rotation.y = heading;
      camTarget.x += (pos.x - camTarget.x) * Math.min(1, dt * 8);
      camTarget.y += (pos.y + 1.0 - camTarget.y) * Math.min(1, dt * 8);
      camTarget.z += (pos.z - camTarget.z) * Math.min(1, dt * 8);
      if (!dbg) cam.target.copyFrom(camTarget);
    });
  }

  // 朝向相机一侧的墙自动隐藏，避免遮挡设备。
  const tmp = new Vector3();
  const normals: Record<string, [number, number]> = { left: [1, 0], right: [-1, 0], back: [0, -1] };
  scene.onBeforeRenderObservable.add(() => {
    tmp.copyFrom(cam.position).subtractInPlace(cam.target);
    tmp.y = 0;
    tmp.normalize();
    for (const [g, list] of Object.entries(walls)) {
      const [nx, nz] = normals[g];
      const hide = nx * tmp.x + nz * tmp.z > 0.55;
      for (const m of list) m.setEnabled(!hide);
    }
  });

  const probe = new ReflectionProbe('probe', 256, scene);
  probe.position = new Vector3(0, 2.2, -1);
  for (const m of meshes) if (!m.name.startsWith('flame')) probe.renderList!.push(m);
  probe.refreshRate = RenderTargetTexture.REFRESHRATE_RENDER_ONCE;
  scene.environmentTexture = probe.cubeTexture;
  scene.environmentIntensity = 1.0;
  setTimeout(() => (probe.cubeTexture.refreshRate = RenderTargetTexture.REFRESHRATE_RENDER_ONCE), 1500);

  const pipe = new DefaultRenderingPipeline('pipe', true, scene, [cam]);
  pipe.samples = 4;
  pipe.fxaaEnabled = true;
  pipe.bloomEnabled = true;
  pipe.bloomThreshold = 0.75;
  pipe.bloomWeight = 0.3;
  pipe.bloomKernel = 48;
  pipe.bloomScale = 0.5;
  pipe.sharpenEnabled = true;
  pipe.sharpen.edgeAmount = 0.2;
  pipe.imageProcessingEnabled = true;
  pipe.imageProcessing.toneMappingEnabled = true;
  pipe.imageProcessing.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
  pipe.imageProcessing.exposure = 1.15;
  pipe.imageProcessing.contrast = 1.12;
  pipe.imageProcessing.vignetteEnabled = true;
  pipe.imageProcessing.vignetteWeight = 1.2;
  pipe.imageProcessing.vignetteColor = new Color4(0.02, 0.02, 0.04, 0);
  try {
    const ssao = new SSAO2RenderingPipeline('ssao', scene, { ssaoRatio: 0.6, blurRatio: 1 }, [cam]);
    ssao.radius = 0.6;
    ssao.totalStrength = 0.7;
    ssao.samples = 12;
    ssao.maxZ = 40;
  } catch {
    /* 不支持时跳过 */
  }

  document.title = '赛尔号 · 动力室 I';
  hud.innerHTML = '<span style="font-size:22px;font-weight:700;letter-spacing:2px;color:#ffd38a">动力室 I</span><br>' +
    (refMode ? '参考视角 · 拖动旋转 · 滚轮缩放' : '第三人称 · WASD 移动 · Shift 加速 · B 精灵背包 · 拖动旋转视角');
  const sw = document.createElement('a');
  sw.className = 'invention-view-switch';
  sw.href = refMode ? '?scene=power' : '?scene=power&ref=1';
  sw.textContent = refMode ? '进入第三人称 →' : '参考视角';
  document.body.append(sw);
  engine.runRenderLoop(() => scene.render());
  addEventListener('resize', () => engine.resize());
  (window as unknown as { __scene: Scene }).__scene = scene;
}

main().catch((e) => {
  console.error(e);
  hud.textContent = `加载失败: ${e?.message ?? e}`;
});

export {};
