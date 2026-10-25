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
import { makeCollision } from './teleportMovement';
import { attachCompanions, preloadCompanions } from './companions';
import { createBackpack } from './backpack';

interface Terminal {
  x: number;
  y: number;
  ix: number;
  iy: number;
  r: number;
  scene: 'kelosi' | 'station' | 'invention' | 'power';
  label: string;
}

interface Meta {
  colliders: { x: number; y: number; r: number }[];
  lights: { x: number; y: number; z: number; color: number[]; power: number; range: number }[];
  walk: { minX: number; maxX: number; minY: number; maxY: number };
  room: { x: number; y: number; r: number };
  pad: { x: number; y: number; r: number };
  spawn: { x: number; y: number };
  terminals: Terminal[];
  portals: { x: number; y: number; z: number; r: number }[];
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

/** 传送舱为圆形房间：按“网格中心相对房间中心”的径向方向判定墙体朝向。 */
const ROOM_CENTER = toB(0, 0.4, 0);

function tuneMaterials() {
  for (const mat of scene.materials) {
    if (!(mat instanceof PBRMaterial)) continue;
    const n = mat.name;
    if (n === 'tp_silver') {
      mat.environmentIntensity = 1.1;
      mat.clearCoat.isEnabled = true;
      mat.clearCoat.intensity = 0.15;
      mat.clearCoat.roughness = 0.25;
    } else if (n === 'tp_brushed') {
      // 反射探针修好后地面才真正有金属反射。
      mat.metallic = 0.65;
      mat.roughness = 0.38;
      mat.environmentIntensity = 1.0;
    } else if (n === 'tp_silver_dark') {
      mat.environmentIntensity = 0.9;
    } else if (n === 'tp_bluegray' || n === 'tp_bluegray_dark') {
      mat.environmentIntensity = 0.85;
    } else if (n === 'tp_column') {
      mat.environmentIntensity = 1.2;
      mat.roughness = 0.22;
    } else if (n === 'tp_lens' || n === 'tp_hub') {
      mat.environmentIntensity = 1.0;
      mat.roughness = 0.38;
      mat.metallic = 0.15;
      // 凹槽内缺少环境光，给中心帽一点自发光避免死黑（参考图是灰蓝金属帽）。
      const hub = n === 'tp_hub';
      mat.emissiveColor = new Color3(hub ? 0.12 : 0.15, hub ? 0.14 : 0.18, hub ? 0.18 : 0.22);
      mat.emissiveIntensity = hub ? 1.0 : 1.0;
    } else if (n === 'tp_visor') {
      mat.environmentIntensity = 0.85;
      mat.clearCoat.isEnabled = true;
      mat.clearCoat.intensity = 0.05;
      mat.clearCoat.roughness = 0.35;
    } else if (n === 'tp_brass') {
      mat.environmentIntensity = 0.65;
      mat.roughness = 0.48;
      mat.metallic = 0.5;
    } else if (n === 'tp_cream' || n === 'tp_cream_light') {
      // 白墙保持哑光：探针里高亮的青色环会在光滑漆面上拉出细丝状伪影。
      mat.environmentIntensity = 0.6;
      mat.clearCoat.isEnabled = false;
    } else if (n === 'tp_glass') {
      mat.alpha = 0.46;
      mat.useAlphaFresnel = false;
      mat.albedoColor = new Color3(0.012, 0.028, 0.05);
      mat.metallic = 0;
      mat.roughness = 0.09;
      mat.backFaceCulling = true;
      mat.environmentIntensity = 0.85;
      mat.clearCoat.isEnabled = true;
      mat.clearCoat.intensity = 0.6;
      mat.clearCoat.roughness = 0.06;
    } else if (n === 'tp_glow_cyan') {
      mat.emissiveColor = new Color3(0.22, 0.85, 1);
      mat.emissiveIntensity = 2.3;
    } else if (n === 'tp_glow_pill') {
      mat.emissiveColor = new Color3(0.28, 0.9, 1);
      mat.emissiveIntensity = 3.6;
    } else if (n === 'tp_glow_green') {
      mat.emissiveColor = new Color3(0.2, 1, 0.45);
      mat.emissiveIntensity = 2.2;
    } else if (n === 'tp_starfield' || n === 'tp_chase' || n === 'tp_diaphragm') {
      // 只调自发光强度，保持贴图反照率（不要让发光材质变成纯黑壳）。
      mat.emissiveColor = Color3.White();
      mat.emissiveIntensity = n === 'tp_chase' ? 2.4
        : n === 'tp_diaphragm' ? 0.95 : 1.45;
      for (const t of [mat.emissiveTexture, mat.albedoTexture]) {
        if (t instanceof Texture) {
          t.wrapU = Texture.WRAP_ADDRESSMODE;
          t.wrapV = Texture.WRAP_ADDRESSMODE;
        }
      }
    } else if (n === 'tp_etch') {
      mat.emissiveColor = new Color3(0.55, 0.8, 1);
      mat.emissiveIntensity = 0.9;
      mat.environmentIntensity = 0.8;
    } else if (n === 'tp_hazard' || n === 'tp_vent' || n === 'tp_ribs') {
      mat.environmentIntensity = 0.8;
    }
  }
}

/** 只克隆真正的环体材质（每终端 2 个），避免给几十颗小灯各克隆一份。 */
function terminalMaterials(meshes: AbstractMesh[]) {
  return [0, 1, 2, 3].map((i) => {
    const owned: { mat: PBRMaterial; base: number }[] = [];
    for (const m of meshes) {
      if (!m.name.startsWith(`term_${i}_`) || !(m.material instanceof PBRMaterial)) continue;
      const src = m.material;
      const isRing = m.name.endsWith('_ring_glow') || m.name.endsWith('_portal');
      if (!isRing || (src.name !== 'tp_glow_cyan' && src.name !== 'tp_diaphragm')) continue;
      const own = src.clone(`${m.name}_mat`);
      m.material = own;
      owned.push({ mat: own, base: own.emissiveIntensity || 1 });
    }
    return owned;
  });
}

async function main() {
  hud.innerHTML = '<span style="font-size:22px;font-weight:700;letter-spacing:2px">传送舱 I</span><br>加载中…';
  const meta: Meta = await (await fetch('/models/teleport/teleport_room.json')).json();
  const [res] = await Promise.all([
    ImportMeshAsync('/models/teleport/teleport_room.glb', scene),
    refMode ? Promise.resolve() : loadProp(scene, 'player/seer_robot'),
    refMode ? Promise.resolve() : preloadCompanions(scene),
  ]);
  const meshes = res.meshes;
  // 必须在创建灯光前实例化，否则机器人网格拿不到光源列表。
  const player = refMode ? null : spawn(scene, 'player/seer_robot', toB(meta.spawn.x, meta.spawn.y, 0), { height: 1.25, rotY: Math.PI });
  const companions = player ? attachCompanions(scene, player.node, { playerHeight: 1.25 }) : null;
  for (const m of meshes) m.receiveShadows = true;
  tuneMaterials();
  const termMats = terminalMaterials(meshes);

  const hemi = new HemisphericLight('hemi', new Vector3(0, 1, 0.15), scene);
  hemi.diffuse = new Color3(0.82, 0.87, 0.96);
  hemi.groundColor = new Color3(0.26, 0.28, 0.33);
  hemi.intensity = 0.68;
  const key = new DirectionalLight('key', new Vector3(0.15, -1, 0.4).normalize(), scene);
  key.position = new Vector3(3, 12, -6);
  key.diffuse = new Color3(1, 0.96, 0.9);
  key.intensity = 1.55;
  // 大厅顶部的大范围柔光，补足弧形墙与顶棚。
  const fill = new PointLight('fill', new Vector3(0, 6.5, 2.2), scene);
  fill.diffuse = new Color3(0.92, 0.94, 1);
  fill.intensity = 14;
  fill.range = 26;
  let padLight: PointLight | null = null;
  let padLightDist = Infinity;
  for (const l of meta.lights) {
    const p = new PointLight('pl', toB(l.x, l.y, l.z), scene);
    p.diffuse = new Color3(l.color[0], l.color[1], l.color[2]);
    p.intensity = l.power / 3;
    p.range = l.range * 1.5;
    const d2 = (l.x - meta.pad.x) ** 2 + (l.y - meta.pad.y) ** 2;
    if (l.z < 1.5 && d2 < padLightDist) {
      padLightDist = d2;
      padLight = p;
    }
  }

  const shadow = new CascadedShadowGenerator(2048, key);
  shadow.numCascades = 2;
  shadow.shadowMaxZ = 30;
  shadow.autoCalcDepthBounds = true;
  shadow.usePercentageCloserFiltering = true;
  shadow.bias = 0.0008;
  shadow.normalBias = 0.02;
  shadow.darkness = 0.45;
  for (const m of meshes) {
    if (!m.name.startsWith('wall_arc') && m.getTotalVertices() > 0 && (m.material?.alpha ?? 1) >= 1) shadow.addShadowCaster(m);
  }

  // 参考视角：与 Blender 预览相机一致（campos 0.38,-8.63,4.98 / target -0.06,1.32,0.87 / lens 26.7）。
  const cam = new ArcRotateCamera('cam', 1.615, 1.179, 10.77, toB(-0.06, 1.32, 0.87), scene);
  cam.fovMode = Camera.FOVMODE_VERTICAL_FIXED;
  cam.fov = 0.7242;
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

  // 终端交互提示与淡出遮罩。
  const prompt = document.createElement('div');
  prompt.id = 'tp-prompt';
  prompt.style.cssText =
    'position:fixed;left:50%;bottom:56px;transform:translateX(-50%);display:none;padding:11px 22px;' +
    'background:rgba(5,14,22,.82);border:1px solid rgba(80,220,255,.5);border-radius:9px;' +
    'color:#dff6ff;font:15px/1.2 "PingFang SC","Microsoft YaHei",sans-serif;letter-spacing:1px;' +
    'box-shadow:0 0 18px rgba(40,180,230,.35);pointer-events:none;z-index:20;white-space:nowrap;';
  document.body.append(prompt);
  const fade = document.createElement('div');
  fade.style.cssText =
    'position:fixed;inset:0;background:#000;opacity:0;pointer-events:none;transition:opacity .45s ease;z-index:50;';
  document.body.append(fade);

  let navigating = false;
  const go = (id: Terminal['scene']) => {
    if (navigating) return;
    navigating = true;
    fade.style.opacity = '1';
    setTimeout(() => (location.href = `?scene=${id}`), 480);
  };

  const padPos = toB(meta.pad.x, meta.pad.y, 0);
  if (!refMode) {
    cam.fov = 0.92;
    cam.radius = 5.6;
    cam.beta = 1.02;
    cam.lowerRadiusLimit = 3.2;
    cam.upperRadiusLimit = 8.5;
    cam.lowerBetaLimit = 0.7;
    cam.upperBetaLimit = 1.35;
    cam.lowerAlphaLimit = Math.PI / 2 - 1.15;
    cam.upperAlphaLimit = Math.PI / 2 + 1.15;
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

  // 靠相机一侧的弧形墙段自动隐藏；用网格包围盒中心相对房间中心的径向方向。
  const tmp = new Vector3();
  const wallMeshes = meshes.filter((m) => m.name.startsWith('wall_arc'));
  const wallDirs = wallMeshes.map((m) => {
    m.computeWorldMatrix(true);
    const c = m.getBoundingInfo().boundingBox.centerWorld.clone();
    return new Vector3(c.x - ROOM_CENTER.x, 0, c.z - ROOM_CENTER.z).normalize();
  });
  scene.onBeforeRenderObservable.add(() => {
    tmp.copyFrom(cam.position).subtractInPlace(cam.target);
    tmp.y = 0;
    tmp.normalize();
    for (let i = 0; i < wallMeshes.length; i++) {
      wallMeshes[i].setEnabled(wallDirs[i].x * tmp.x + wallDirs[i].z * tmp.z <= 0.55);
    }
  });

  // 动态：跑灯环滚动、星云漂移、终端脉动、站上传送台增亮。
  const chaseMat = scene.getMaterialByName('tp_chase') as PBRMaterial | null;
  const starMat = scene.getMaterialByName('tp_starfield') as PBRMaterial | null;
  const glowMat = scene.getMaterialByName('tp_glow_cyan') as PBRMaterial | null;
  const chaseTex = chaseMat?.emissiveTexture instanceof Texture ? chaseMat.emissiveTexture : null;
  const starTex = starMat?.emissiveTexture instanceof Texture ? starMat.emissiveTexture : null;
  const chaseBase = chaseMat?.emissiveIntensity || 1.8;
  const starBase = starMat?.emissiveIntensity || 1.1;
  const glowBase = glowMat?.emissiveIntensity || 2.2;
  const padLightBase = padLight ? padLight.intensity : 0;
  let boost = 0;
  let nearIdx = -1;
  let t = 0;
  const terminalsB = meta.terminals.map((term) => ({ ix: -term.ix, iz: -term.iy, r: term.r }));
  scene.onBeforeRenderObservable.add(() => {
    const dt = Math.min(engine.getDeltaTime() / 1000, 0.05);
    t += dt;
    let wantBoost = 0;
    if (player) {
      const dx = player.node.position.x - padPos.x;
      const dz = player.node.position.z - padPos.z;
      if (dx * dx + dz * dz < meta.pad.r * meta.pad.r) wantBoost = 1;
    }
    boost += (wantBoost - boost) * Math.min(1, dt * 3);
    if (chaseTex) chaseTex.uOffset = (chaseTex.uOffset + dt * (0.06 + 0.26 * boost)) % 1;
    if (starTex) {
      starTex.uOffset = (starTex.uOffset + dt * 0.004) % 1;
      starTex.vOffset = (starTex.vOffset + dt * 0.003) % 1;
    }
    if (chaseMat) chaseMat.emissiveIntensity = chaseBase * (1 + 0.55 * boost);
    if (starMat) starMat.emissiveIntensity = starBase * (1 + 0.9 * boost);
    if (glowMat) glowMat.emissiveIntensity = glowBase * (0.9 + 0.1 * Math.sin(t * 2.2)) * (1 + 0.35 * boost);
    if (padLight) padLight.intensity = padLightBase * (1 + 0.9 * boost);
    nearIdx = -1;
    if (player) {
      let best = Infinity;
      terminalsB.forEach((term, i) => {
        const d = Math.hypot(player.node.position.x - term.ix, player.node.position.z - term.iz);
        if (d < term.r && d < best) {
          best = d;
          nearIdx = i;
        }
      });
    }
    termMats.forEach((list, i) => {
      const hot = i === nearIdx ? 1 : 0;
      const wave = 0.82 + 0.18 * Math.sin(t * 1.9 + i * 1.3);
      for (const o of list) o.mat.emissiveIntensity = o.base * (wave + 0.55 * hot + 0.25 * boost);
    });
    if (prompt) {
      const term = nearIdx >= 0 ? meta.terminals[nearIdx] : null;
      prompt.style.display = term ? 'block' : 'none';
      if (term) prompt.innerHTML = `按 <b style="color:#7fe9ff">E</b> 传送至 ${term.label}`;
    }
  });
  addEventListener('keydown', (e) => {
    if (e.code === 'KeyE' && nearIdx >= 0 && !navigating && !refMode) go(meta.terminals[nearIdx].scene);
  });

  // 反射探针：Babylon 9 不会自动渲染探针，因此等资源就绪后手动渲染一次，
  // 再把它挂成环境贴图并停止刷新。探针渲染时 environmentTexture 仍为空，
  // 不会出现“边渲染边采样自己”的 WebGL feedback loop。
  const probe = new ReflectionProbe('probe', 512, scene);
  probe.position = toB(meta.pad.x, meta.pad.y, 2.2);
  for (const m of meshes) if (!m.name.startsWith('pad_glass')) probe.renderList!.push(m);
  probe.cubeTexture.refreshRate = RenderTargetTexture.REFRESHRATE_RENDER_ONCE;
  scene.executeWhenReady(() => {
    probe.cubeTexture.render();
    // 场景会把 environmentTexture（这是个 RTT）重新加入渲染列表；显示禁用
    // 它的自动刷新，避免在采样自己的同时再次渲染。
    (probe.cubeTexture as unknown as { _shouldRender: () => boolean })._shouldRender = () => false;
    scene.environmentTexture = probe.cubeTexture;
    scene.environmentIntensity = 1.0;
  });

  const pipe = new DefaultRenderingPipeline('pipe', true, scene, [cam]);
  pipe.samples = 4;
  pipe.fxaaEnabled = true;
  pipe.bloomEnabled = true;
  pipe.bloomThreshold = 0.64;
  pipe.bloomWeight = 0.40;
  pipe.bloomKernel = 64;
  pipe.bloomScale = 0.55;
  pipe.sharpenEnabled = true;
  pipe.sharpen.edgeAmount = 0.08;
  pipe.imageProcessingEnabled = true;
  pipe.imageProcessing.toneMappingEnabled = true;
  pipe.imageProcessing.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
  pipe.imageProcessing.exposure = 1.07;
  pipe.imageProcessing.contrast = 1.14;
  pipe.imageProcessing.vignetteEnabled = true;
  pipe.imageProcessing.vignetteWeight = 0.18;
  pipe.imageProcessing.vignetteColor = new Color4(0.02, 0.02, 0.04, 0);
  try {
    const ssao = new SSAO2RenderingPipeline('ssao', scene, { ssaoRatio: 0.6, blurRatio: 1 }, [cam]);
    ssao.radius = 0.55;
    ssao.totalStrength = 0.35;
    ssao.samples = 12;
    ssao.maxZ = 40;
  } catch {
    /* 不支持时跳过 */
  }

  document.title = '赛尔号 · 传送舱 I';
  hud.innerHTML =
    '<span style="font-size:22px;font-weight:700;letter-spacing:2px;color:#8fe8ff">传送舱 I</span><br>' +
    (refMode
      ? '参考视角 · 拖动旋转 · 滚轮缩放'
      : '第三人称 · WASD 移动 · Shift 加速 · B 精灵背包 · 靠近终端按 E 传送');
  const sw = document.createElement('a');
  sw.className = 'invention-view-switch';
  sw.href = refMode ? '?scene=teleport' : '?scene=teleport&ref=1';
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
