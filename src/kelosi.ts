import {
  ArcRotateCamera,
  Camera,
  CascadedShadowGenerator,
  Color3,
  Color4,
  DefaultRenderingPipeline,
  DirectionalLight,
  DynamicTexture,
  Engine,
  HemisphericLight,
  ImageProcessingConfiguration,
  ImportMeshAsync,
  Mesh,
  MeshBuilder,
  PBRMaterial,
  PointLight,
  ReflectionProbe,
  RenderTargetTexture,
  Scene,
  SSAO2RenderingPipeline,
  ShaderMaterial,
  StandardMaterial,
  Texture,
  TransformNode,
  Vector2,
  Vector3,
} from '@babylonjs/core';
import '@babylonjs/loaders/glTF';
import { loadProp, spawn } from './props';
import { attachCompanions, preloadCompanions } from './companions';
import { createBackpack } from './backpack';
import { KelosiMeta, makeGround, makeMovement } from './kelosiMovement';

const canvas = document.getElementById('app') as HTMLCanvasElement;
const engine = new Engine(canvas, true, { antialias: true, powerPreference: 'high-performance' });
engine.setHardwareScalingLevel(1 / Math.min(window.devicePixelRatio, 2));
const scene = new Scene(engine);
scene.clearColor = new Color4(1.0, 0.68, 0.40, 1);
scene.fogMode = Scene.FOGMODE_EXP2;
scene.fogColor = new Color3(0.95, 0.55, 0.34);
scene.fogDensity = 0.0026;

const hud = document.getElementById('hud') as HTMLElement;
const params = new URLSearchParams(location.search);
const refMode = params.has('ref');
const dbg = params.get('cam');
// 元数据里的点光照沿用 (x, -z, y) 的 Blender 风格坐标。
const toB = (x: number, y: number, z: number) => new Vector3(x, z, -y);

function createSky() {
  const tex = new DynamicTexture('skyTex', { width: 16, height: 512 }, scene, true);
  const ctx = tex.getContext() as CanvasRenderingContext2D;
  const g = ctx.createLinearGradient(0, 0, 0, 512);
  g.addColorStop(0.0, '#c53c43');
  g.addColorStop(0.28, '#e85a3f');
  g.addColorStop(0.52, '#ff8f4f');
  g.addColorStop(0.68, '#ffc270');
  g.addColorStop(0.76, '#ffe4a6');
  g.addColorStop(0.84, '#ffb66b');
  g.addColorStop(1.0, '#f08c52');
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
  // 可平铺的多倍频值噪声：比正弦条纹更接近自然水面的碎波，
  // 同时沿河道方向拉长，避免出现规则排列的高光斑点。
  const N = 512;
  const tex = new DynamicTexture('waterN', { width: N, height: N }, scene, true);
  const ctx = tex.getContext() as CanvasRenderingContext2D;
  const img = ctx.createImageData(N, N);
  const hash = (x: number, y: number) => {
    let h = Math.imul(x, 374761393) + Math.imul(y, 668265263);
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  };
  const smooth = (t: number) => t * t * (3 - 2 * t);
  const wrap = (v: number, p: number) => ((v % p) + p) % p;
  const noise = (x: number, y: number, px: number, py: number) => {
    const x0 = Math.floor(x);
    const y0 = Math.floor(y);
    const fx = smooth(x - x0);
    const fy = smooth(y - y0);
    const xa = wrap(x0, px);
    const xb = wrap(x0 + 1, px);
    const ya = wrap(y0, py);
    const yb = wrap(y0 + 1, py);
    const a = hash(xa, ya);
    const b = hash(xb, ya);
    const c = hash(xa, yb);
    const d = hash(xb, yb);
    return (a + (b - a) * fx) * (1 - fy) + (c + (d - c) * fx) * fy;
  };
  const height = new Float32Array(N * N);
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const u = x / N;
      const v = y / N;
      let sum = 0;
      let amp = 0.55;
      let f = 4;
      for (let o = 0; o < 4; o++) {
        // 只做极轻微的顺流拉长；拉得太长会让高光连成平行的“拉丝”。
        sum += amp * noise(u * f, v * f * 1.12, f, f * 1.12);
        amp *= 0.5;
        f *= 2;
      }
      height[y * N + x] = sum;
    }
  }
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const xl = height[y * N + ((x - 1 + N) % N)];
      const xr = height[y * N + ((x + 1) % N)];
      const yu = height[((y - 1 + N) % N) * N + x];
      const yd = height[((y + 1) % N) * N + x];
      const dx = (xr - xl) * 16;
      const dy = (yd - yu) * 16;
      const len = Math.hypot(dx, dy, 1);
      const i = (y * N + x) * 4;
      img.data[i] = ((-dx / len) * 0.5 + 0.5) * 255;
      img.data[i + 1] = ((-dy / len) * 0.5 + 0.5) * 255;
      img.data[i + 2] = ((1 / len) * 0.5 + 0.5) * 255;
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  tex.update();
  tex.wrapU = Texture.WRAP_ADDRESSMODE;
  tex.wrapV = Texture.WRAP_ADDRESSMODE;
  return tex;
}

/**
 * 把河床深度烘成一张贴图：让水体着色、浅滩透明感和岸线泡沫都由真实地形决定，
 * 而不是靠河心距离或几何泡沫条近似。R 通道存 0..MAX_DEPTH 的归一化深度。
 */
const WATER_MAX_DEPTH = 2.4;
function createWaterDepth(
  minX: number,
  minZ: number,
  maxX: number,
  maxZ: number,
  waterLevel: number,
  getGround: (x: number, z: number) => number,
  shallows: { x: number; z: number; r: number }[],
) {
  const W = 1024;
  const H = 256;
  const sstep = (a: number, b: number, v: number) => {
    const t = Math.max(0, Math.min(1, (v - a) / (b - a)));
    return t * t * (3 - 2 * t);
  };
  const tex = new DynamicTexture('waterDepth', { width: W, height: H }, scene, true);
  tex.hasAlpha = false;
  const ctx = tex.getContext() as CanvasRenderingContext2D;
  const img = ctx.createImageData(W, H);
  for (let y = 0; y < H; y++) {
    const z = minZ + ((y + 0.5) / H) * (maxZ - minZ);
    for (let x = 0; x < W; x++) {
      const wx = minX + ((x + 0.5) / W) * (maxX - minX);
      let depth = Math.max(0, Math.min(WATER_MAX_DEPTH, waterLevel - getGround(wx, z)));
      // 踏脚石顶面高出水面：把石顶烘成零深度，水线泡沫就会自然绕石一圈。
      for (const s of shallows) {
        const d = Math.hypot(wx - s.x, z - s.z);
        if (d < s.r + 0.9) depth *= 1 - sstep(s.r * 0.5, s.r + 0.85, d);
      }
      const i = (y * W + x) * 4;
      const v = Math.round((depth / WATER_MAX_DEPTH) * 255);
      img.data[i] = v;
      img.data[i + 1] = v;
      img.data[i + 2] = v;
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  tex.update();
  tex.wrapU = Texture.CLAMP_ADDRESSMODE;
  tex.wrapV = Texture.CLAMP_ADDRESSMODE;
  return tex;
}

interface RefCameraMeta {
  position: number[];
  target: number[];
  fov: number;
  fovMode?: string;
}

function arcFromReference(ref: RefCameraMeta) {
  const target = new Vector3(ref.target[0], ref.target[1], ref.target[2]);
  const offset = new Vector3(ref.position[0], ref.position[1], ref.position[2]).subtract(target);
  const radius = offset.length();
  return {
    target,
    radius,
    alpha: Math.atan2(offset.z, offset.x),
    beta: Math.acos(Math.max(-1, Math.min(1, offset.y / Math.max(radius, 1e-6)))),
  };
}

async function main() {
  document.title = '赛尔号 · 克洛斯星';
  hud.innerHTML = '<span style="font-size:22px;font-weight:700;letter-spacing:2px">克洛斯星</span><br>加载中…';

  const meta: KelosiMeta & { spawn: { x: number; y: number; heading?: number }; referenceCamera: RefCameraMeta } =
    await (await fetch('/models/kelosi/kelosi_outdoor.json')).json();
  const sky = createSky();
  const groundAt = makeGround(meta);

  const [res] = await Promise.all([
    ImportMeshAsync('/models/kelosi/kelosi_outdoor.glb', scene),
    refMode ? Promise.resolve() : loadProp(scene, 'player/seer_robot'),
    refMode ? Promise.resolve() : preloadCompanions(scene),
  ]);
  const meshes = res.meshes;
  for (const m of meshes) {
    m.receiveShadows = true;
    m.isPickable = false;
  }

  // ------------------------------------------------------------ 材质与光照
  const waterNormal = createWaterNormal();
  const pulsing: { mat: PBRMaterial; base: number; hz: number; amount: number }[] = [];

  for (const mat of scene.materials) {
    if (!(mat instanceof PBRMaterial)) continue;
    const n = mat.name;
    if (n === 'k_water') {
      // 水体在下面替换成带反射/折射和动态波浪的 WaterMaterial。
      continue;
    } else if (n === 'k_crystal_glow' || n === 'k_crystal_light') {
      mat.albedoColor = new Color3(n.endsWith('light') ? 1.0 : 0.92, 0.48, 0.025);
      mat.emissiveColor = new Color3(1.0, n.endsWith('light') ? 0.62 : 0.42, 0.02);
      mat.emissiveIntensity = n.endsWith('light') ? 1.25 : 0.95;
      mat.roughness = 0.24;
      mat.metallic = 0;
      pulsing.push({ mat, base: mat.emissiveIntensity, hz: n.endsWith('light') ? 0.52 : 0.42, amount: 0.28 });
    } else if (n === 'k_teleport_glow') {
      mat.albedoColor = new Color3(0.10, 0.65, 0.80);
      mat.emissiveColor = new Color3(0.18, 0.88, 1.0);
      mat.emissiveIntensity = 1.85;
      mat.roughness = 0.2;
      pulsing.push({ mat, base: 1.85, hz: 0.95, amount: 0.36 });
    } else if (n === 'k_portal_inner') {
      mat.albedoColor = new Color3(0.02, 0.18, 0.26);
      mat.emissiveColor = new Color3(0.06, 0.50, 0.68);
      mat.emissiveIntensity = 0.85;
      mat.roughness = 0.18;
      mat.metallic = 0.1;
    } else if (n === 'k_platform_white' || n === 'k_platform_silver') {
      mat.metallic = n.endsWith('silver') ? 0.52 : 0.12;
      mat.roughness = n.endsWith('silver') ? 0.32 : 0.48;
      mat.environmentIntensity = 0.9;
    } else if (n.startsWith('bg_mountain')) {
      mat.metallic = 0;
      mat.roughness = 0.96;
      mat.environmentIntensity = 0.1;
      mat.unlit = true;
    } else if (n.startsWith('k_')) {
      if ((mat.metallic ?? 0) > 0.4) mat.metallic = 0.1;
      if ((mat.roughness ?? 1) < 0.45) mat.roughness = 0.65;
      mat.environmentIntensity = Math.min(mat.environmentIntensity, 0.6);
    }
  }

  // 水体：自写水面着色器。河床深度由高度场烘成深度图，用来决定水色、
  // 浅滩透明感和岸线泡沫；碎波使用世界坐标的多尺度法线，避免网格 UV
  // 被拉成长条。比通用 WaterMaterial 的整场景 RTT 更快，也不会把
  // 暖色河岸反射成泥灰色。
  const waterMesh = meshes.find((m) => m.name === 'water_river' || m.material?.name === 'k_water') as Mesh | undefined;
  let water: ShaderMaterial | null = null;
  if (waterMesh) {
    waterMesh.computeWorldMatrix(true);
    const wb = waterMesh.getBoundingInfo().boundingBox;
    const depthTex = createWaterDepth(
      wb.minimumWorld.x,
      wb.minimumWorld.z,
      wb.maximumWorld.x,
      wb.maximumWorld.z,
      meta.waterLevel,
      groundAt,
      meta.shallows ?? [],
    );
    water = new ShaderMaterial(
      'k_water',
      scene,
      {
        vertexSource: `
          precision highp float;
          attribute vec3 position;
          uniform mat4 world;
          uniform mat4 worldViewProjection;
          varying vec3 vWorld;
          void main(void) {
            vec4 wp = world * vec4(position, 1.0);
            vWorld = wp.xyz;
            gl_Position = worldViewProjection * vec4(position, 1.0);
          }
        `,
        fragmentSource: `
          precision highp float;
          varying vec3 vWorld;
          uniform sampler2D uNormalTex;
          uniform sampler2D uDepthTex;
          uniform float uTime;
          uniform vec3 uCamPos;
          uniform vec3 uSunDir;
          uniform vec3 uSunColor;
          uniform vec3 uFogColor;
          uniform float uFogDensity;
          uniform vec2 uWaterMin;
          uniform vec2 uWaterSize;

          void main(void) {
            vec2 p = vWorld.xz;
            // 三个尺度的碎波，整体沿 +x 顺流漂移。
            vec2 f1 = p * 0.115 + vec2(-uTime * 0.085, uTime * 0.004);
            vec2 f2 = p * 0.285 + vec2(-uTime * 0.190, uTime * 0.012);
            vec2 f3 = p * 0.620 + vec2(-uTime * 0.340, uTime * 0.020);
            vec3 n1 = texture2D(uNormalTex, f1).xyz * 2.0 - 1.0;
            vec3 n2 = texture2D(uNormalTex, f2).xyz * 2.0 - 1.0;
            vec3 n3 = texture2D(uNormalTex, f3).xyz * 2.0 - 1.0;
            vec2 slope = n1.xy * 0.55 + n2.xy * 0.32 + n3.xy * 0.13;
            // 低频涌浪，让高光不会完全平铺成布纹。
            float swell = p.x * 0.22 + p.y * 0.41 + uTime * 0.85;
            vec3 N = normalize(vec3(
              slope.x * 0.42 + cos(swell) * 0.022,
              1.0,
              slope.y * 0.42 + sin(swell * 1.17) * 0.020
            ));

            vec3 V = normalize(uCamPos - vWorld);
            float ndv = clamp(dot(N, V), 0.0, 1.0);

            // 真实河床深度（由高度场预烘），并取深度梯度判断是否为真正的岸坡。
            vec2 duv = (p - uWaterMin) / uWaterSize;
            float depth = texture2D(uDepthTex, duv).r * 2.4;
            vec2 texel = 1.6 / uWaterSize;
            float dX = texture2D(uDepthTex, duv + vec2(texel.x, 0.0)).r - texture2D(uDepthTex, duv - vec2(texel.x, 0.0)).r;
            float dZ = texture2D(uDepthTex, duv + vec2(0.0, texel.y)).r - texture2D(uDepthTex, duv - vec2(0.0, texel.y)).r;
            // 约合米/米的河床坡度：平坦水下沙洲约 0.02，岸坡约 0.4。
            float grad = length(vec2(dX * 3.4, dZ * 4.5));

            vec3 bedTint = vec3(0.38, 0.31, 0.19);
            vec3 shallow = vec3(0.075, 0.345, 0.315);
            vec3 mid = vec3(0.018, 0.155, 0.205);
            vec3 deep = vec3(0.006, 0.065, 0.115);
            vec3 body = mix(bedTint, shallow, smoothstep(0.02, 0.55, depth));
            body = mix(body, mid, smoothstep(0.25, 0.90, depth));
            body = mix(body, deep, smoothstep(0.85, 1.75, depth));

            // 天空反射：地平线保留夕阳暖边，稍高的反射方向转为冷蓝灰，
            // 避免整条河变成和沙地一样的棕色。
            vec3 R = reflect(-V, N);
            float up = clamp(R.y, 0.0, 1.0);
            vec3 c0 = vec3(0.98, 0.62, 0.38);
            vec3 c1 = vec3(0.42, 0.44, 0.52);
            vec3 c2 = vec3(0.18, 0.31, 0.50);
            vec3 sky = mix(c0, c1, smoothstep(0.0, 0.22, up));
            sky = mix(sky, c2, smoothstep(0.22, 0.85, up));
            float fres = 0.02 + 0.98 * pow(1.0 - ndv, 5.0);
            // 反射再亮也要保留水体本色，否则远处会像一条灰白的沙路。
            vec3 col = mix(body, sky, clamp(fres * 1.10, 0.0, 0.58));

            // 太阳碎光：宽高光铺出光路，窄高光叠加噪声形成闪烁颗粒。
            vec3 L = normalize(-uSunDir);
            vec3 H = normalize(L + V);
            float sd = max(dot(N, H), 0.0);
            float glitter = smoothstep(0.35, 0.75, texture2D(uNormalTex, f2 * 1.7 + f3 * 0.6).r);
            float spec =
              pow(sd, 260.0) * (0.45 + 1.9 * glitter) +
              pow(sd, 42.0) * 0.045 +
              pow(sd, 9.0) * 0.014;
            col += uSunColor * spec;

            // 岸线泡沫：只保留浅水区边缘的一条碎沫，浅滩本身用青绿色透出来。
            float foamA = texture2D(uNormalTex, p * vec2(0.85, 1.05) + vec2(-uTime * 0.055, 0.0)).r;
            float foamB = texture2D(uNormalTex, p * vec2(2.20, 1.35) + vec2(-uTime * 0.110, 0.03)).g;
            float lace = foamA * 0.62 + foamB * 0.38;
            float shore = 1.0 - smoothstep(0.010, 0.14, depth);
            float slopeFoam = smoothstep(0.05, 0.28, grad);
            // 大尺度补丁遮罩，避免浅滩边缘连成一整圈几何白环。
            float patchMask = smoothstep(0.32, 0.60, texture2D(uNormalTex, p * 0.16 + vec2(-uTime * 0.01, 0.02)).g);
            float foam = shore * slopeFoam * smoothstep(0.48, 0.64, lace) * 0.55 * mix(0.05, 1.0, patchMask);
            // 水线处一条被噪声打断的细亮边。
            foam += exp(-depth * 55.0) * slopeFoam * smoothstep(0.34, 0.55, lace) * 0.45 * mix(0.15, 1.0, patchMask);
            foam = clamp(foam, 0.0, 1.0);
            col = mix(col, vec3(0.87, 0.94, 0.93), foam * 0.58);

            float dist = length(uCamPos - vWorld);
            float fog = 1.0 - exp(-uFogDensity * uFogDensity * dist * dist);
            col = mix(col, uFogColor, fog);
            gl_FragColor = vec4(col, 1.0);
          }
        `,
      },
      {
        attributes: ['position'],
        uniforms: [
          'world',
          'worldViewProjection',
          'uTime',
          'uCamPos',
          'uSunDir',
          'uSunColor',
          'uFogColor',
          'uFogDensity',
          'uWaterMin',
          'uWaterSize',
        ],
        samplers: ['uNormalTex', 'uDepthTex'],
      },
    );
    water.setTexture('uNormalTex', waterNormal);
    water.setTexture('uDepthTex', depthTex);
    water.setFloat('uTime', 0);
    water.setVector3('uCamPos', Vector3.Zero());
    water.setVector3('uSunDir', new Vector3(-0.42, -0.86, 0.32).normalize());
    water.setVector3('uSunColor', new Vector3(1.0, 0.93, 0.80));
    water.setVector3('uFogColor', new Vector3(scene.fogColor.r, scene.fogColor.g, scene.fogColor.b));
    water.setFloat('uFogDensity', scene.fogDensity);
    water.setVector2('uWaterMin', new Vector2(wb.minimumWorld.x, wb.minimumWorld.z));
    water.setVector2('uWaterSize', new Vector2(wb.maximumWorld.x - wb.minimumWorld.x, wb.maximumWorld.z - wb.minimumWorld.z));
    water.backFaceCulling = true;
    waterMesh.material = water;
    waterMesh.receiveShadows = false;
    waterMesh.renderingGroupId = 0;
    waterMesh.isPickable = false;
  }
  const hemi = new HemisphericLight('hemi', new Vector3(0, 1, 0.12), scene);
  hemi.diffuse = new Color3(0.72, 0.86, 1.0);
  hemi.groundColor = new Color3(0.80, 0.46, 0.30);
  hemi.intensity = 0.85;

  const sun = new DirectionalLight('sun', new Vector3(-0.42, -0.86, 0.32).normalize(), scene);
  sun.position = new Vector3(58, 96, -42);
  sun.diffuse = new Color3(1.0, 0.91, 0.77);
  sun.specular = new Color3(1.0, 0.92, 0.82);
  sun.intensity = 1.90;

  for (const l of (meta as unknown as { lights?: { x: number; y: number; z: number; color: number[]; power: number; range: number }[] }).lights ?? []) {
    const p = new PointLight('glow', toB(l.x, l.y, l.z), scene);
    p.diffuse = new Color3(l.color[0], l.color[1], l.color[2]);
    p.intensity = l.power / 5.5;
    p.range = l.range * 1.5;
  }

  const probe = new ReflectionProbe('probe', 128, scene);
  probe.renderList!.push(sky);
  probe.refreshRate = RenderTargetTexture.REFRESHRATE_RENDER_ONCE;
  scene.environmentTexture = probe.cubeTexture;
  scene.environmentIntensity = 0.45;

  const shadow = new CascadedShadowGenerator(2048, sun);
  shadow.numCascades = 3;
  shadow.lambda = 0.72;
  shadow.shadowMaxZ = 170;
  shadow.autoCalcDepthBounds = true;
  shadow.usePercentageCloserFiltering = true;
  shadow.filteringQuality = 1;
  shadow.bias = 0.0008;
  shadow.normalBias = 0.025;
  shadow.stabilizeCascades = true;
  shadow.darkness = 0.32;
  for (const m of meshes) {
    const n = m.name;
    const matName = m.material?.name ?? '';
    if (
      n === 'kelosi_terrain' ||
      n.startsWith('m_bg') ||
      n.includes('water') ||
      matName.startsWith('bg_') ||
      m.getTotalVertices() === 0
    ) {
      continue;
    }
    shadow.addShadowCaster(m);
  }

  // ------------------------------------------------------------ 玩家与相机
  const refCam = arcFromReference(meta.referenceCamera);
  const cam = new ArcRotateCamera('cam', refCam.alpha, refCam.beta, refCam.radius, refCam.target, scene);
  cam.fovMode = Camera.FOVMODE_VERTICAL_FIXED;
  cam.fov = meta.referenceCamera.fov;
  cam.minZ = 0.08;
  cam.maxZ = 900;
  cam.panningSensibility = 0;
  cam.wheelPrecision = 30;
  cam.inputs.removeByType('ArcRotateCameraKeyboardMoveInput');

  const debugCam = !!dbg;
  if (dbg) {
    const values = dbg.split(',').map(Number);
    if (values.length === 6 && values.every(Number.isFinite)) {
      const [a, b, r, tx, ty, tz] = values;
      cam.alpha = a;
      cam.beta = b;
      cam.radius = r;
      cam.target.set(tx, ty, tz);
      cam.lowerBetaLimit = 0.02;
      cam.upperBetaLimit = 3;
      cam.lowerRadiusLimit = 1;
      cam.upperRadiusLimit = 500;
    }
  }

  let player: ReturnType<typeof spawn> | null = null;
  if (!refMode) {
    const sx = meta.spawn.x;
    const sz = -meta.spawn.y;
    const sy = groundAt(sx, sz);
    player = spawn(scene, 'player/seer_robot', new Vector3(sx, sy, sz), {
      height: 1.9,
      rotY: meta.spawn.heading ?? Math.PI,
    });
    for (const m of player.meshes) shadow.addShadowCaster(m);

    const companions = attachCompanions(scene, player.node, { playerHeight: 1.9, groundAt });
    for (const m of companions.meshes) shadow.addShadowCaster(m);
    createBackpack(companions);

    if (!debugCam) {
      cam.alpha = Math.PI / 2;
      // 更低的机位让河对岸、台地和远山进入画面，扩大后的场景才显得开阔。
      cam.beta = 1.30;
      cam.radius = 13;
      cam.target.set(sx, sy + 1.4, sz);
      cam.attachControl(canvas, true);
    }
    cam.lowerRadiusLimit = 1;
    cam.upperRadiusLimit = 500;
    cam.lowerBetaLimit = 0.02;
    cam.upperBetaLimit = 1.42;

    // 角色补光：跟随相机一侧，避免深色机体在逆光下变成剪影。
    const playerFill = new PointLight('playerFill', new Vector3(0, 8, 30), scene);
    playerFill.diffuse = new Color3(1.0, 0.86, 0.70);
    playerFill.intensity = 40.0;
    playerFill.range = 13;

    const movement = makeMovement(meta, groundAt);
    const keys = new Set<string>();
    addEventListener('keydown', (e) => keys.add(e.code));
    addEventListener('keyup', (e) => keys.delete(e.code));
    addEventListener('blur', () => keys.clear());

    const pos = player.node.position;
    let heading = meta.spawn.heading ?? Math.PI;
    let hopT = 0;
    const camTarget = new Vector3(pos.x, pos.y + 1.4, pos.z);

    const attempt = (dx: number, dz: number) => {
      const bx = pos.x;
      const bz = pos.z;
      const full = movement.move(pos, dx, dz);
      if (full || Math.hypot(pos.x - bx, pos.z - bz) > Math.hypot(dx, dz) * 0.2) return;
      const ax = pos.x;
      const az = pos.z;
      const xOnly = movement.move(pos, dx, 0);
      if (xOnly || Math.hypot(pos.x - ax, pos.z - az) > 1e-5) return;
      movement.move(pos, 0, dz);
    };

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
        const inWater = groundAt(pos.x, pos.z) < 0.22;
        const speed = (keys.has('ShiftLeft') || keys.has('ShiftRight') ? 11.5 : 6.3) * (inWater ? 0.62 : 1);
        const step = speed * dt;
        attempt(dir.x * step, dir.z * step);
        const aim = Math.atan2(dir.x, dir.z);
        const diff = Math.atan2(Math.sin(aim - heading), Math.cos(aim - heading));
        heading += diff * Math.min(1, dt * 11);
        hopT += dt * (keys.has('ShiftLeft') ? 17 : 12.5);
      } else {
        hopT = 0;
      }

      const ground = groundAt(pos.x, pos.z);
      pos.y = ground + (moving ? Math.abs(Math.sin(hopT)) * 0.16 : 0);
      player!.node.rotation.y = heading;
      playerFill.position.set(
        pos.x + (cam.position.x - pos.x) * 0.34,
        pos.y + 2.8,
        pos.z + (cam.position.z - pos.z) * 0.34,
      );

      if (!debugCam) {
        camTarget.x += (pos.x - camTarget.x) * Math.min(1, dt * 8);
        camTarget.y += (pos.y + 1.4 - camTarget.y) * Math.min(1, dt * 8);
        camTarget.z += (pos.z - camTarget.z) * Math.min(1, dt * 8);
        cam.target.copyFrom(camTarget);

        const clear = (beta: number) => {
          const sb = Math.sin(beta);
          const cx = cam.target.x + cam.radius * Math.cos(cam.alpha) * sb;
          const cz = cam.target.z + cam.radius * Math.sin(cam.alpha) * sb;
          const cy = cam.target.y + cam.radius * Math.cos(beta);
          return cy - (groundAt(cx, cz) + 1.35);
        };
        let b = cam.beta;
        for (let i = 0; i < 40 && clear(b) < 0 && b > 0.22; i++) b -= 0.04;
        cam.beta = b;
      }
    });
  }

  // ------------------------------------------------------------ 水面与地标动画
  const ringNode = (scene.getTransformNodeByName('fx_teleport_ring') ??
    scene.getMeshByName('fx_teleport_ring')) as TransformNode | null;
  if (ringNode?.rotationQuaternion) ringNode.rotationQuaternion = null;

  let t = 0;
  scene.onBeforeRenderObservable.add(() => {
    const dt = Math.min(engine.getDeltaTime() / 1000, 0.05);
    t += dt;
    if (water) {
      water.setFloat('uTime', t);
      water.setVector3('uCamPos', cam.position);
    }
    for (const p of pulsing) {
      p.mat.emissiveIntensity = p.base * (1 + Math.sin(t * Math.PI * 2 * p.hz) * p.amount);
    }
    if (ringNode) ringNode.rotation.y += dt * 0.42;
  });

  // ------------------------------------------------------------ 后期
  const pipe = new DefaultRenderingPipeline('pipe', true, scene, [cam]);
  pipe.samples = 4;
  pipe.fxaaEnabled = true;
  pipe.bloomEnabled = true;
  pipe.bloomThreshold = 0.86;
  pipe.bloomWeight = 0.32;
  pipe.bloomKernel = 64;
  pipe.bloomScale = 0.55;
  pipe.sharpenEnabled = true;
  pipe.sharpen.edgeAmount = 0.18;
  pipe.imageProcessingEnabled = true;
  pipe.imageProcessing.toneMappingEnabled = true;
  pipe.imageProcessing.toneMappingType = ImageProcessingConfiguration.TONEMAPPING_ACES;
  pipe.imageProcessing.exposure = 0.98;
  pipe.imageProcessing.contrast = 1.12;
  pipe.imageProcessing.vignetteEnabled = false;

  try {
    const ssao = new SSAO2RenderingPipeline('ssao', scene, { ssaoRatio: 0.5, blurRatio: 0.9 }, [cam]);
    ssao.radius = 2.2;
    ssao.totalStrength = 0.48;
    ssao.expensiveBlur = false;
    ssao.samples = 10;
    ssao.maxZ = 85;
  } catch {
    /* 不支持时跳过 */
  }

  hud.innerHTML =
    '<span style="font-size:22px;font-weight:700;letter-spacing:2px">克洛斯星</span><br>' +
    (refMode
      ? '参考视角 · 固定机位 · 1280×720'
      : '第三人称 · WASD/方向键移动 · Shift 加速 · B 精灵背包 · 拖动旋转视角 · 滚轮缩放');
  const sw = document.createElement('a');
  sw.className = 'invention-view-switch';
  sw.href = refMode ? '?scene=kelosi' : '?scene=kelosi&ref=1';
  sw.textContent = refMode ? '进入第三人称 →' : '参考视角';
  document.body.append(sw);

  (window as unknown as { __kelosi?: unknown }).__kelosi = {
    ready: true,
    mode: refMode ? 'ref' : 'thirdperson',
    meta,
    groundAt,
    player: player?.node ?? null,
    camera: cam,
  };
  (window as unknown as { __scene: Scene }).__scene = scene;
  engine.runRenderLoop(() => scene.render());
  addEventListener('resize', () => engine.resize());
}

main().catch((e) => {
  console.error(e);
  hud.textContent = `加载失败: ${e?.message ?? e}`;
});

export {};
