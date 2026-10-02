import {
  AbstractMesh,
  ArcRotateCamera,
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
  TransformNode,
  Vector3,
} from '@babylonjs/core';
import '@babylonjs/loaders/glTF';
import { loadProp, spawn } from './props';

const RX = 9;
const RY = 7;

interface Meta {
  colliders: { x: number; y: number; r: number }[];
  lights: { x: number; y: number; z: number; color: number[]; power: number; range: number }[];
  animated: Record<string, { x: number; y: number; z: number }>;
}

const canvas = document.getElementById('app') as HTMLCanvasElement;
const engine = new Engine(canvas, true, { antialias: true, powerPreference: 'high-performance' });
engine.setHardwareScalingLevel(1 / Math.min(window.devicePixelRatio, 2));
const scene = new Scene(engine);
scene.clearColor = new Color4(0.03, 0.05, 0.09, 1);

const hud = document.getElementById('hud') as HTMLElement;
const params = new URLSearchParams(location.search);
const refMode = params.has('ref');

const wallGroup = (name: string): 'left' | 'right' | 'front' | 'back' | null => {
  if (/^(wall_left|left_panel|trim_left|glow_left|pipe_left)/.test(name)) return 'left';
  if (/^(wall_right|right_panel|trim_right|glow_right|pipe_right)/.test(name)) return 'right';
  if (/^wall_front/.test(name)) return 'front';
  if (/^(wall_back|back_panel|trim_back|glow_back|pipe_back|pipe_clamp)/.test(name)) return 'back';
  return null;
};

async function main() {
  hud.innerHTML = '<span style="font-size:22px;font-weight:700;letter-spacing:2px">发明室 I</span><br>加载中…';

  const meta: Meta = await (await fetch('/models/inv/invention_room.json')).json();
  const res = await ImportMeshAsync('/models/inv/invention_room.glb', scene);
  const meshes = res.meshes;
  // 导入后世界坐标: Blender(x,y,z) -> Babylon(-x,z,-y)
  const toB = (x: number, y: number, z: number) => new Vector3(-x, z, -y);

  const walls: Record<string, AbstractMesh[]> = { left: [], right: [], front: [], back: [] };
  for (const m of meshes) {
    const g = wallGroup(m.name);
    if (g) walls[g].push(m);
    m.receiveShadows = true;
  }

  for (const mat of scene.materials) {
    const pm = mat as PBRMaterial;
    if (mat.name === 'floor_tile') {
      pm.roughness = 0.55;
      pm.environmentIntensity = 0.35;
      pm.albedoColor = new Color3(0.62, 0.66, 0.7);
    } else if (/^(steel|steel_light|wall_panel)$/.test(mat.name)) {
      pm.environmentIntensity = 0.6;
    } else if (mat.name === 'glass' || mat.name === 'glass_tube') {
      pm.alpha = 0.18;
      pm.roughness = 0.05;
    }
  }
  for (const m of meshes) if (/^glow_(left|right)/.test(m.name)) m.visibility = 0.25;

  // 悬浮机器人上下浮动、全息图旋转
  const bobbers: { node: TransformNode; base: number; phase: number }[] = [];
  for (const key of Object.keys(meta.animated)) {
    const c = meta.animated[key];
    const center = toB(c.x, c.y, c.z);
    const prefixes = key.startsWith('drone') ? [`${key}_`] : key === 'holo_icon' ? ['holo_icon', 'holo_man', 'holo_scan'] : [];
    if (!prefixes.length) continue;
    const node = new TransformNode(`anim_${key}`, scene);
    node.position.copyFrom(center);
    for (const m of meshes) if (prefixes.some((p) => m.name.startsWith(p))) m.setParent(node);
    if (key.startsWith('drone')) bobbers.push({ node, base: center.y, phase: Number(key.slice(5)) * 2.1 });
    else scene.onBeforeRenderObservable.add(() => (node.rotation.y += 0.012));
  }
  scene.onBeforeRenderObservable.add(() => {
    const t = performance.now() * 0.001;
    for (const b of bobbers) {
      b.node.position.y = b.base + Math.sin(t * 1.4 + b.phase) * 0.12;
      b.node.rotation.y = Math.sin(t * 0.6 + b.phase) * 0.4;
    }
  });

  // 灯光
  const hemi = new HemisphericLight('hemi', new Vector3(0.1, 1, -0.2), scene);
  hemi.diffuse = new Color3(0.75, 0.86, 1);
  hemi.groundColor = new Color3(0.6, 0.68, 0.8);
  hemi.intensity = 2.0;
  const key = new DirectionalLight('key', new Vector3(0.25, -0.9, 0.35).normalize(), scene);
  key.position = new Vector3(-8, 14, -8);
  key.diffuse = new Color3(0.85, 0.93, 1);
  key.intensity = 2.4;
  for (const l of meta.lights) {
    const p = new PointLight('pl', toB(l.x, l.y, l.z), scene);
    p.diffuse = new Color3(l.color[0], l.color[1], l.color[2]);
    p.intensity = l.power / 4;
    p.range = l.range * 1.4;
  }

  // 玩家
  await loadProp(scene, 'hy/robot');
  const player = spawn(scene, 'hy/robot', new Vector3(1.5, 0, 4.2), { height: 1.55 });
  player.node.setEnabled(!refMode);

  const casters = meshes.filter((m) => !wallGroup(m.name) && m.getTotalVertices() > 0);
  casters.push(...(player.meshes as AbstractMesh[]));
  const shadow = new CascadedShadowGenerator(2048, key);
  shadow.numCascades = 2;
  shadow.shadowMaxZ = 40;
  shadow.autoCalcDepthBounds = true;
  shadow.usePercentageCloserFiltering = true;
  shadow.bias = 0.0008;
  shadow.normalBias = 0.02;
  shadow.darkness = 0.5;
  for (const m of casters) shadow.addShadowCaster(m);

  const cam = new ArcRotateCamera('cam', 1.15, 1.12, 17, new Vector3(1.5, 1, 4.2), scene);
  cam.lowerRadiusLimit = 5;
  cam.upperRadiusLimit = 30;
  cam.lowerBetaLimit = 0.4;
  cam.upperBetaLimit = 1.4;
  cam.wheelPrecision = 30;
  cam.panningSensibility = 0;
  cam.minZ = 0.1;
  cam.maxZ = 200;
  const dbg = params.get('cam');
  let freeCam = false;
  if (refMode || dbg) {
    const [a, b, r, tx, ty, tz] = (dbg ?? '1.15,1.0,16.5,-0.2,1,-1.2').split(',').map(Number);
    cam.alpha = a;
    cam.beta = b;
    cam.radius = r;
    cam.target.set(tx, ty, tz);
    cam.upperRadiusLimit = 80;
    freeCam = true;
  }
  cam.attachControl(canvas, true);
  cam.inputs.removeByType('ArcRotateCameraKeyboardMoveInput');

  const probe = new ReflectionProbe('probe', 256, scene);
  probe.position = new Vector3(0, 2.5, 0);
  for (const m of meshes) probe.renderList!.push(m);
  probe.refreshRate = RenderTargetTexture.REFRESHRATE_RENDER_ONCE;
  scene.environmentTexture = probe.cubeTexture;
  scene.environmentIntensity = 1.1;
  for (const t of [800, 2500]) setTimeout(() => probe.cubeTexture.refreshRate = RenderTargetTexture.REFRESHRATE_RENDER_ONCE, t);

  const pipe = new DefaultRenderingPipeline('pipe', true, scene, [cam]);
  pipe.samples = 4;
  pipe.fxaaEnabled = true;
  pipe.bloomEnabled = true;
  pipe.bloomThreshold = 1.15;
  pipe.bloomWeight = 0.14;
  pipe.bloomKernel = 32;
  pipe.bloomScale = 0.5;
  pipe.sharpenEnabled = true;
  pipe.sharpen.edgeAmount = 0.2;
  pipe.imageProcessingEnabled = true;
  pipe.imageProcessing.toneMappingEnabled = true;
  pipe.imageProcessing.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
  pipe.imageProcessing.exposure = 1.2;
  pipe.imageProcessing.contrast = 1.12;
  pipe.imageProcessing.vignetteEnabled = true;
  pipe.imageProcessing.vignetteWeight = 1.2;
  pipe.imageProcessing.vignetteColor = new Color4(0, 0.02, 0.06, 0);
  try {
    const ssao = new SSAO2RenderingPipeline('ssao', scene, { ssaoRatio: 0.6, blurRatio: 1 }, [cam]);
    ssao.radius = 1.2;
    ssao.totalStrength = 0.8;
    ssao.samples = 12;
    ssao.maxZ = 60;
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
  const R = 0.5;
  const colliders = meta.colliders.map((c) => ({ x: -c.x, z: -c.y, r: c.r }));
  const walkable = (x: number, z: number) => {
    if (Math.abs(x) > RX - 0.9 || Math.abs(z) > RY - 0.9) return false;
    for (const c of colliders) if (Math.hypot(x - c.x, z - c.z) < c.r + R) return false;
    return true;
  };
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
      const step = (keys.has('ShiftLeft') ? 9 : 5) * dt;
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
    pos.y = moving ? Math.abs(Math.sin(performance.now() * 0.012)) * 0.08 : 0;

    if (!freeCam) {
      const k = Math.min(1, dt * 8);
      camTarget.x += (pos.x - camTarget.x) * k;
      camTarget.z += (pos.z - camTarget.z) * k;
      cam.target.copyFrom(camTarget);
    }

    tmp.copyFrom(cam.position).subtractInPlace(cam.target);
    tmp.y = 0;
    tmp.normalize();
    const normals: Record<string, [number, number]> = { left: [1, 0], right: [-1, 0], front: [0, 1], back: [0, -1] };
    for (const g of Object.keys(walls)) {
      const [nx, nz] = normals[g];
      const hide = g === 'front' || nx * tmp.x + nz * tmp.z > 0.45;
      for (const m of walls[g]) m.setEnabled(!hide);
    }
  });

  hud.innerHTML =
    '<span style="font-size:22px;font-weight:700;letter-spacing:2px;color:#9ff0ff">发明室 I</span><br>WASD 移动 · Shift 加速 · 拖动旋转 · 滚轮缩放';
  engine.runRenderLoop(() => scene.render());
  addEventListener('resize', () => engine.resize());
  (window as unknown as { __scene: Scene }).__scene = scene;
}

main().catch((e) => {
  console.error(e);
  hud.textContent = `加载失败: ${e?.message ?? e}`;
});

export {};
