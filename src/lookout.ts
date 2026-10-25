import {
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
  Vector3,
} from '@babylonjs/core';
import '@babylonjs/loaders/glTF';
import { loadProp, spawn } from './props';
import { makeCollision } from './lookoutMovement';
import { attachCompanions, preloadCompanions } from './companions';
import { createBackpack } from './backpack';

interface Meta {
  colliders: { x: number; y: number; r: number }[];
  boxes: { minX: number; maxX: number; minY: number; maxY: number }[];
  lights: { x: number; y: number; z: number; color: number[]; power: number; range: number }[];
  walk: { minX: number; maxX: number; minY: number; maxY: number };
  spawn: { x: number; y: number };
}

const canvas = document.getElementById('app') as HTMLCanvasElement;
const engine = new Engine(canvas, true, { antialias: true, powerPreference: 'high-performance' });
engine.setHardwareScalingLevel(1 / Math.min(window.devicePixelRatio, 2));
const scene = new Scene(engine);
scene.clearColor = new Color4(0.01, 0.015, 0.03, 1);

const hud = document.getElementById('hud') as HTMLElement;
const params = new URLSearchParams(location.search);
const refMode = params.has('ref');
const dbg = params.get('cam');
const toB = (x: number, y: number, z: number) => new Vector3(-x, z, -y);

function tuneMaterials() {
  for (const mat of scene.materials) {
    if (!(mat instanceof PBRMaterial)) continue;
    const n = mat.name;
    if (n === 'lo_white' || n === 'lo_panel') {
      mat.metallic = 0.12;
      mat.roughness = 0.5;
      mat.environmentIntensity = 0.45;
    } else if (n === 'lo_silver') {
      mat.environmentIntensity = 0.75;
    } else if (n === 'lo_dark') {
      mat.environmentIntensity = 0.7;
    } else if (n === 'lo_window') {
      mat.alpha = 0.18;
      mat.albedoColor = new Color3(0.01, 0.015, 0.02);
      mat.roughness = 0.08;
      mat.backFaceCulling = false;
    } else if (n === 'lo_glass') {
      mat.alpha = 0.22;
      mat.useAlphaFresnel = true;
      mat.albedoColor = new Color3(0.02, 0.05, 0.08);
      mat.roughness = 0.06;
      mat.backFaceCulling = false;
      mat.environmentIntensity = 1.3;
    } else if (n === 'lo_glow_cyan') {
      mat.emissiveColor = new Color3(0.28, 0.9, 1);
      mat.emissiveIntensity = 1.45;
    } else if (n === 'lo_glow_red') {
      mat.emissiveColor = new Color3(1, 0.18, 0.12);
      mat.emissiveIntensity = 0.35;
    } else if (n === 'lo_sky') {
      mat.albedoColor = Color3.Black();
      mat.emissiveIntensity = 1.7;
      mat.backFaceCulling = false;
    } else if (n === 'lo_badge') {
      mat.albedoColor = Color3.Black();
      mat.emissiveIntensity = 1.8;
    }
  }
}

async function main() {
  hud.innerHTML = '<span style="font-size:22px;font-weight:700;letter-spacing:2px">瞭望露台 I</span><br>加载中…';
  const meta: Meta = await (await fetch('/models/lookout/lookout_deck.json')).json();
  const [res] = await Promise.all([
    ImportMeshAsync('/models/lookout/lookout_deck.glb', scene),
    refMode ? Promise.resolve() : loadProp(scene, 'player/seer_robot'),
    refMode ? Promise.resolve() : preloadCompanions(scene),
  ]);
  const meshes = res.meshes;
  const player = refMode ? null : spawn(scene, 'player/seer_robot', toB(meta.spawn.x, meta.spawn.y, 0), { height: 1.25, rotY: Math.PI });
  const companions = player ? attachCompanions(scene, player.node, { playerHeight: 1.25 }) : null;
  for (const m of meshes) m.receiveShadows = true;
  tuneMaterials();

  const hemi = new HemisphericLight('hemi', new Vector3(0, 1, 0.2), scene);
  hemi.diffuse = new Color3(0.75, 0.82, 0.95);
  hemi.groundColor = new Color3(0.16, 0.18, 0.24);
  hemi.intensity = 0.85;
  const key = new DirectionalLight('key', new Vector3(0.2, -1, 0.35).normalize(), scene);
  key.position = new Vector3(-2, 14, 8);
  key.diffuse = new Color3(0.9, 0.94, 1);
  key.intensity = 1.35;
  for (const l of meta.lights) {
    const p = new PointLight('pl', toB(l.x, l.y, l.z), scene);
    p.diffuse = new Color3(l.color[0], l.color[1], l.color[2]);
    p.intensity = l.power / 6;
    p.range = l.range * 1.4;
  }

  const shadow = new CascadedShadowGenerator(2048, key);
  shadow.numCascades = 2;
  shadow.shadowMaxZ = 40;
  shadow.autoCalcDepthBounds = true;
  shadow.usePercentageCloserFiltering = true;
  shadow.bias = 0.0008;
  shadow.normalBias = 0.02;
  shadow.darkness = 0.4;
  for (const m of meshes) {
    if (m.name.startsWith('sky_') || m.name.startsWith('pod_glass') || m.name.startsWith('mini_dome')) continue;
    if (m.getTotalVertices() > 0 && (m.material?.alpha ?? 1) >= 1) shadow.addShadowCaster(m);
  }

  // 与 Blender 预览相机一致：位置 (0,-9.4,4.6) 看向 (0,1.5,1.15)，镜头 18mm。
  // 重做后抬高机位，让八边形窗和舰体甲板按参考图入画。镜头 20mm。
  const cam = new ArcRotateCamera('cam', Math.PI / 2, 1.182, 10.54, toB(0, 1.15, 1.4), scene);
  cam.fovMode = Camera.FOVMODE_VERTICAL_FIXED;
  cam.fov = 0.937;
  cam.minZ = 0.08;
  cam.maxZ = 200;
  cam.wheelPrecision = 30;
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
    cam.radius = 6.2;
    cam.beta = 1.12;
    cam.lowerRadiusLimit = 3.4;
    cam.upperRadiusLimit = 12;
    cam.lowerBetaLimit = 0.65;
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
        const step = (fast ? 4.4 : 2.7) * dt;
        move(pos, dir.x * step, dir.z * step);
        const aim = Math.atan2(dir.x, dir.z);
        const diff = Math.atan2(Math.sin(aim - heading), Math.cos(aim - heading));
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

  const pilots = meshes.filter((m) => m.name.startsWith('pilot_'));
  const pilotBase = pilots.map((m) => m.position.clone());
  let t = 0;
  scene.onBeforeRenderObservable.add(() => {
    t += Math.min(engine.getDeltaTime() / 1000, 0.05);
    const bob = Math.sin(t * 1.6) * 0.03;
    pilots.forEach((m, i) => {
      m.position.y = pilotBase[i].y + bob;
    });
  });

  const probe = new ReflectionProbe('probe', 256, scene);
  probe.position = new Vector3(0, 2.2, 2);
  for (const m of meshes) if (!m.name.startsWith('sky_') && !m.name.startsWith('pod_glass')) probe.renderList!.push(m);
  probe.refreshRate = RenderTargetTexture.REFRESHRATE_RENDER_ONCE;
  scene.environmentTexture = probe.cubeTexture;
  scene.environmentIntensity = 0.85;

  const pipe = new DefaultRenderingPipeline('pipe', true, scene, [cam]);
  pipe.samples = 4;
  pipe.fxaaEnabled = true;
  pipe.bloomEnabled = true;
  pipe.bloomThreshold = 0.7;
  pipe.bloomWeight = 0.32;
  pipe.bloomKernel = 48;
  pipe.bloomScale = 0.5;
  pipe.sharpenEnabled = true;
  pipe.sharpen.edgeAmount = 0.18;
  pipe.imageProcessingEnabled = true;
  pipe.imageProcessing.toneMappingEnabled = true;
  pipe.imageProcessing.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
  pipe.imageProcessing.exposure = 1.05;
  pipe.imageProcessing.contrast = 1.08;
  pipe.imageProcessing.vignetteEnabled = true;
  pipe.imageProcessing.vignetteWeight = 0.9;
  pipe.imageProcessing.vignetteColor = new Color4(0.01, 0.01, 0.03, 0);
  try {
    const ssao = new SSAO2RenderingPipeline('ssao', scene, { ssaoRatio: 0.6, blurRatio: 1 }, [cam]);
    ssao.radius = 0.7;
    ssao.totalStrength = 0.55;
    ssao.samples = 12;
    ssao.maxZ = 50;
  } catch {
    /* 不支持时跳过 */
  }

  document.title = '赛尔号 · 瞭望露台 I';
  hud.innerHTML =
    '<span style="font-size:22px;font-weight:700;letter-spacing:2px;color:#d7f6ff">瞭望露台 I</span><br>' +
    (refMode ? '参考视角 · 拖动旋转 · 滚轮缩放' : '第三人称 · WASD 移动 · Shift 加速 · B 精灵背包');
  const sw = document.createElement('a');
  sw.className = 'invention-view-switch';
  sw.href = refMode ? '?scene=lookout' : '?scene=lookout&ref=1';
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
