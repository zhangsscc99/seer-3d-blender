import {
  AbstractMesh,
  ArcRotateCamera,
  CascadedShadowGenerator,
  Camera,
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
import { createFirstPersonCamera } from './inventionFirstPerson';
import { roomCollision } from './inventionMovement';
import { createInventionEnvironment } from './inventionEnvironment';

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
const dbg = params.get('cam');
const inspectionMode = refMode || !!dbg;

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
      pm.albedoColor = new Color3(0.56, 0.61, 0.66);
    } else if (/^(steel|steel_light|wall_panel)$/.test(mat.name)) {
      pm.environmentIntensity = 0.6;
    } else if (mat.name === 'nono_visor') {
      pm.environmentIntensity = 0.18;
      pm.roughness = 0.4;
    } else if (mat.name === 'nono_shell') {
      pm.environmentIntensity = 0.5;
    } else if (mat.name === 'glass' || mat.name === 'glass_tube') {
      pm.alpha = mat.name === 'glass' ? 0.22 : 0.09;
      pm.roughness = 0.05;
    }
  }
  for (const m of meshes) if (/^glow_(left|right)/.test(m.name)) m.visibility = 0.25;

  // 三个 NONO 轻微悬浮；前缀对应同一 Blender 模型的三个实例。
  const bobbers: { node: TransformNode; base: number; phase: number; amplitude: number }[] = [];
  for (const key of Object.keys(meta.animated)) {
    const c = meta.animated[key];
    const center = toB(c.x, c.y, c.z);
    const prefixes = key.startsWith('nono') ? [`${key}_`] : key === 'holo_icon' ? ['holo_icon', 'holo_man', 'holo_scan'] : [];
    if (!prefixes.length) continue;
    const node = new TransformNode(`anim_${key}`, scene);
    node.position.copyFrom(center);
    for (const m of meshes) if (prefixes.some((p) => m.name.startsWith(p))) m.setParent(node);
    if (key.startsWith('nono')) bobbers.push({ node, base: center.y, phase: Number(key.slice(4)) * 2.1, amplitude: key === 'nono1' ? 0.10 : 0.045 });
    else scene.onBeforeRenderObservable.add(() => (node.rotation.y += Math.min(engine.getDeltaTime() / 1000, 0.05) * 0.72));
  }
  scene.onBeforeRenderObservable.add(() => {
    const t = performance.now() * 0.001;
    for (const b of bobbers) {
      b.node.position.y = b.base + Math.sin(t * 1.4 + b.phase) * b.amplitude;
      b.node.rotation.y = Math.sin(t * 0.6 + b.phase) * 0.12;
    }
  });

  // 灯光
  const hemi = new HemisphericLight('hemi', new Vector3(0.1, 1, -0.2), scene);
  hemi.diffuse = new Color3(0.75, 0.86, 1);
  hemi.groundColor = new Color3(0.6, 0.68, 0.8);
  hemi.intensity = 1.65;
  const key = new DirectionalLight('key', new Vector3(0.25, -0.9, 0.35).normalize(), scene);
  key.position = new Vector3(-8, 14, -8);
  key.diffuse = new Color3(0.85, 0.93, 1);
  key.intensity = 2.0;
  for (const l of meta.lights) {
    const p = new PointLight('pl', toB(l.x, l.y, l.z), scene);
    p.diffuse = new Color3(l.color[0], l.color[1], l.color[2]);
    p.intensity = l.power / 4;
    p.range = l.range * 1.4;
  }

  const environment = createInventionEnvironment(scene);
  environment.setInspectionMode(inspectionMode);
  // 观景窗替代原来的整面前墙；室内模式不再剖切其余三面墙。
  for (const m of walls.front) m.setEnabled(false);

  const casters = meshes.filter((m) => !wallGroup(m.name) && m.getTotalVertices() > 0 && (m.material?.alpha ?? 1) >= 1);
  const shadow = new CascadedShadowGenerator(2048, key);
  shadow.numCascades = 2;
  shadow.shadowMaxZ = 40;
  shadow.autoCalcDepthBounds = true;
  shadow.usePercentageCloserFiltering = true;
  shadow.bias = 0.0008;
  shadow.normalBias = 0.02;
  shadow.darkness = 0.5;
  for (const m of casters) shadow.addShadowCaster(m);

  let cam: Camera;
  if (inspectionMode) {
    const orbit = new ArcRotateCamera('referenceCamera', Math.PI / 2, 1.04, 22, new Vector3(0, 2.3, -1), scene);
    orbit.lowerRadiusLimit = 5;
    orbit.upperRadiusLimit = 80;
    orbit.lowerBetaLimit = 0.4;
    orbit.upperBetaLimit = 1.4;
    orbit.wheelPrecision = 30;
    orbit.panningSensibility = 0;
    orbit.minZ = 0.1;
    orbit.maxZ = 2400;
    const values = dbg?.split(',').map(Number);
    if (values?.length === 6 && values.every(Number.isFinite)) {
      const [a, b, r, tx, ty, tz] = values;
      orbit.alpha = a;
      orbit.beta = Math.max(0.4, Math.min(1.4, b));
      orbit.radius = Math.max(5, Math.min(80, r));
      orbit.target.set(tx, ty, tz);
    }
    if (refMode && !dbg) {
      orbit.mode = Camera.ORTHOGRAPHIC_CAMERA;
      const fitReference = () => {
        const aspect = engine.getRenderWidth() / engine.getRenderHeight();
        const halfWidth = Math.max(8.5, 5.2 * aspect);
        orbit.orthoLeft = -halfWidth;
        orbit.orthoRight = halfWidth;
        orbit.orthoTop = halfWidth / aspect;
        orbit.orthoBottom = -halfWidth / aspect;
      };
      fitReference();
      engine.onResizeObservable.add(fitReference);
    }
    orbit.attachControl(canvas, true);
    orbit.inputs.removeByType('ArcRotateCameraKeyboardMoveInput');
    const tmp = new Vector3();
    scene.onBeforeRenderObservable.add(() => {
      tmp.copyFrom(orbit.position).subtractInPlace(orbit.target);
      tmp.y = 0;
      tmp.normalize();
      const normals: Record<string, [number, number]> = { left: [1, 0], right: [-1, 0], front: [0, 1], back: [0, -1] };
      for (const [group, groupMeshes] of Object.entries(walls)) {
        const [nx, nz] = normals[group];
        const hide = group === 'front' || nx * tmp.x + nz * tmp.z > 0.45;
        for (const m of groupMeshes) m.setEnabled(!hide);
      }
    });
    cam = orbit;
  } else {
    cam = createFirstPersonCamera(scene, canvas, roomCollision(meta.colliders));
  }
  scene.activeCamera = cam;

  const probe = new ReflectionProbe('probe', 256, scene);
  probe.position = new Vector3(0, 2.5, 0);
  for (const m of [...meshes, ...environment.meshes]) probe.renderList!.push(m);
  probe.refreshRate = RenderTargetTexture.REFRESHRATE_RENDER_ONCE;
  scene.environmentTexture = probe.cubeTexture;
  scene.environmentIntensity = 1.1;
  for (const t of [800, 2500]) setTimeout(() => probe.cubeTexture.refreshRate = RenderTargetTexture.REFRESHRATE_RENDER_ONCE, t);

  const pipe = new DefaultRenderingPipeline('pipe', true, scene, [cam]);
  pipe.samples = 4;
  pipe.fxaaEnabled = true;
  pipe.bloomEnabled = true;
  pipe.bloomThreshold = 1.15;
  pipe.bloomWeight = 0.08;
  pipe.bloomKernel = 32;
  pipe.bloomScale = 0.5;
  pipe.sharpenEnabled = true;
  pipe.sharpen.edgeAmount = 0.2;
  pipe.imageProcessingEnabled = true;
  pipe.imageProcessing.toneMappingEnabled = true;
  pipe.imageProcessing.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
  pipe.imageProcessing.exposure = 1.2;
  pipe.imageProcessing.contrast = 1.04;
  pipe.imageProcessing.vignetteEnabled = true;
  pipe.imageProcessing.vignetteWeight = 0.5;
  pipe.imageProcessing.vignetteColor = new Color4(0, 0.02, 0.06, 0);
  try {
    const ssao = new SSAO2RenderingPipeline('ssao', scene, { ssaoRatio: 0.6, blurRatio: 1 }, [cam]);
    ssao.radius = 0.55;
    ssao.totalStrength = 0.55;
    ssao.samples = 12;
    ssao.maxZ = 60;
  } catch {
    /* 不支持时跳过 */
  }

  document.title = '赛尔号 · 发明室 I';
  hud.innerHTML = '<span style="font-size:22px;font-weight:700;letter-spacing:2px;color:#9ff0ff">发明室 I</span><br>' +
    (inspectionMode ? '场景总览 · 拖动旋转 · 滚轮缩放' : '第一人称 · WASD 移动 · Shift 快走 · 鼠标查看');
  const viewSwitch = document.createElement('a');
  viewSwitch.className = 'invention-view-switch';
  viewSwitch.href = inspectionMode ? '?scene=invention' : '?scene=invention&ref=1';
  viewSwitch.textContent = inspectionMode ? '进入第一人称 →' : '场景总览';
  document.body.append(viewSwitch);
  engine.runRenderLoop(() => scene.render());
  addEventListener('resize', () => engine.resize());
  (window as unknown as { __scene: Scene }).__scene = scene;
}

main().catch((e) => {
  console.error(e);
  hud.textContent = `加载失败: ${e?.message ?? e}`;
});

export {};
