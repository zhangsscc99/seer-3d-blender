import {
  AbstractMesh,
  Color3,
  Mesh,
  MeshBuilder,
  PBRMaterial,
  Scene,
  ShaderMaterial,
  Vector3,
} from '@babylonjs/core';

/** A stationary celestial background and the room's enclosed observation side. */
export function createInventionEnvironment(scene: Scene): {
  meshes: AbstractMesh[];
  setInspectionMode: (enabled: boolean) => void;
} {
  const meshes: AbstractMesh[] = [];
  const interior: AbstractMesh[] = [];

  // Every detail is evaluated from a direction, so neither the stars nor the
  // distant planet moves when the player walks. There are no downloaded assets.
  const skyMaterial = new ShaderMaterial('invention_space_material', scene, {
    vertexSource: `
      precision highp float;
      attribute vec3 position;
      uniform mat4 worldViewProjection;
      varying vec3 vDirection;
      void main() {
        vDirection = position;
        gl_Position = worldViewProjection * vec4(position, 1.0);
        gl_Position.z = gl_Position.w * 0.999999;
      }
    `,
    fragmentSource: `
      precision highp float;
      varying vec3 vDirection;
      const float PI = 3.14159265359;

      float hash(vec3 p) {
        p = fract(p * 0.1031);
        p += dot(p, p.yzx + 33.33);
        return fract((p.x + p.y) * p.z);
      }
      float noise(vec3 p) {
        vec3 i = floor(p);
        vec3 f = fract(p);
        f = f * f * (3.0 - 2.0 * f);
        return mix(mix(mix(hash(i), hash(i + vec3(1, 0, 0)), f.x),
                       mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
                   mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x),
                       mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y), f.z);
      }
      float terrain(vec3 p) {
        float n = 0.5 * noise(p);
        n += 0.25 * noise(p * 2.03 + 4.7);
        n += 0.125 * noise(p * 4.09 + 9.2);
        n += 0.0625 * noise(p * 8.17 + 1.4);
        return n / 0.9375;
      }
      vec3 stars(vec2 uv, vec2 grid, float threshold, float seed) {
        vec2 cell = floor(uv * grid);
        vec2 local = fract(uv * grid);
        float chance = hash(vec3(cell, seed));
        if (chance < threshold) return vec3(0.0);
        vec2 center = vec2(hash(vec3(cell, seed + 3.0)), hash(vec3(cell, seed + 7.0)));
        center = 0.25 + center * 0.5;
        float magnitude = hash(vec3(cell, seed + 11.0));
        float radius = mix(0.045, 0.14, magnitude * magnitude);
        float d = length(local - center);
        float aa = max(length(fwidth(uv * grid)) * 0.43, 0.012);
        float core = 1.0 - smoothstep(radius - aa, radius + aa, d);
        float halo = exp(-d * d / (radius * radius * 5.0)) * 0.08;
        vec3 tint = mix(vec3(0.62, 0.76, 1.0), vec3(1.0, 0.88, 0.7), magnitude);
        return tint * (core + halo) * mix(0.26, 1.2, magnitude);
      }
      void main() {
        vec3 direction = normalize(vDirection);
        vec2 uv = vec2(atan(direction.z, direction.x) / (2.0 * PI) + 0.5,
                       asin(clamp(direction.y, -1.0, 1.0)) / PI + 0.5);
        vec3 color = mix(vec3(0.0025, 0.005, 0.014), vec3(0.008, 0.017, 0.042),
                         clamp(direction.y * 0.4 + 0.5, 0.0, 1.0));
        float belt = exp(-pow(dot(direction, normalize(vec3(0.48, 0.78, -0.35))) * 3.8, 2.0));
        float wisps = terrain(direction * 3.0 + 12.0);
        float nebula = belt * smoothstep(0.32, 0.75, wisps);
        color += mix(vec3(0.016, 0.021, 0.048), vec3(0.035, 0.019, 0.045), wisps) * nebula;
        color += stars(uv, vec2(650.0, 325.0), 0.9975, 2.0);
        color += stars(uv, vec2(320.0, 160.0), 0.994, 17.0);

        // Ray/sphere intersection gives a genuinely curved terminator and a
        // continuous atmospheric limb, rather than a flat disc or sprite.
        vec3 center = normalize(vec3(0.23, 0.10, 1.0)) * 6.0;
        float radius = 0.88;
        float along = dot(direction, center);
        float distanceSq = dot(center, center) - along * along;
        float discriminant = radius * radius - distanceSq;
        vec3 sun = normalize(vec3(-0.65, 0.50, -0.62));
        if (along > 0.0 && discriminant > 0.0) {
          vec3 point = direction * (along - sqrt(discriminant));
          vec3 normal = normalize(point - center);
          float sunlight = dot(normal, sun);
          float day = smoothstep(-0.08, 0.16, sunlight);
          float lambert = max(sunlight, 0.0);
          float continent = terrain(normal * 4.3 + vec3(3.7, 1.1, 9.4));
          float land = smoothstep(0.48, 0.56, continent);
          vec3 ocean = mix(vec3(0.008, 0.035, 0.12), vec3(0.014, 0.15, 0.26), continent);
          vec3 ground = mix(vec3(0.055, 0.15, 0.13), vec3(0.21, 0.27, 0.18), continent);
          vec3 surface = mix(ocean, ground, land);
          float clouds = smoothstep(0.53, 0.69, terrain(normal * 8.0 + vec3(11.0, 3.0, 2.0)));
          clouds *= smoothstep(0.24, 0.72, noise(normal * 3.0 - 5.0));
          surface = mix(surface, vec3(0.74, 0.82, 0.9), clouds * 0.9);
          float polar = smoothstep(0.83, 0.98, abs(normal.y) + (continent - 0.5) * 0.12);
          surface = mix(surface, vec3(0.69, 0.78, 0.84), polar);
          float rim = pow(1.0 - max(dot(normal, -direction), 0.0), 3.4);
          color = surface * (0.025 + day * (0.14 + lambert * 1.05));
          color += vec3(0.055, 0.25, 0.55) * rim * (0.08 + day * 0.8);
          float spec = pow(max(dot(reflect(-sun, normal), -direction), 0.0), 45.0);
          color += vec3(0.28, 0.4, 0.5) * spec * (1.0 - land) * day * 0.32;
        } else if (along > 0.0) {
          float edge = max(sqrt(max(distanceSq, 0.0)) - radius, 0.0);
          float atmosphere = exp(-edge / 0.017) * smoothstep(0.0, 0.018, edge + 0.002);
          vec3 limbNormal = normalize(direction * along - center);
          float litEdge = smoothstep(-0.2, 0.7, dot(limbNormal, sun));
          color += vec3(0.035, 0.20, 0.43) * atmosphere * (0.18 + litEdge * 0.82);
        }
        gl_FragColor = vec4(color, 1.0);
      }
    `,
  }, { attributes: ['position'], uniforms: ['worldViewProjection'] });
  skyMaterial.backFaceCulling = false;
  skyMaterial.disableDepthWrite = true;
  skyMaterial.fogEnabled = false;
  const sky = MeshBuilder.CreateSphere('invention_space_sky', {
    diameter: 150, segments: 32, sideOrientation: Mesh.BACKSIDE,
  }, scene);
  sky.material = skyMaterial;
  sky.infiniteDistance = true;
  sky.isPickable = false;
  sky.applyFog = false;
  sky.alwaysSelectAsActiveMesh = true;
  sky.metadata = { inventionEnvironment: 'sky' };
  meshes.push(sky);

  const metal = (name: string, color: Color3, metallic: number, roughness: number) => {
    const material = new PBRMaterial(name, scene);
    material.albedoColor = color;
    material.metallic = metallic;
    material.roughness = roughness;
    material.environmentIntensity = 0.45;
    return material;
  };
  const silver = metal('invention_window_silver', new Color3(0.48, 0.56, 0.64), 0.62, 0.34);
  const panel = metal('invention_ceiling_panel', new Color3(0.32, 0.39, 0.47), 0.38, 0.65);
  const graphite = metal('invention_window_gasket', new Color3(0.027, 0.049, 0.069), 0.3, 0.5);
  const trim = metal('invention_window_edge', new Color3(0.64, 0.73, 0.79), 0.72, 0.26);
  const light = metal('invention_ceiling_light', new Color3(0.65, 0.83, 0.88), 0, 0.4);
  light.unlit = true;
  light.emissiveColor = new Color3(0.46, 0.78, 0.88);

  const remember = (mesh: Mesh, material: PBRMaterial) => {
    mesh.material = material;
    mesh.isPickable = false;
    mesh.receiveShadows = true;
    mesh.metadata = { inventionEnvironment: 'interior' };
    meshes.push(mesh);
    interior.push(mesh);
    return mesh;
  };
  const box = (name: string, size: [number, number, number], position: [number, number, number], material: PBRMaterial) => {
    const mesh = MeshBuilder.CreateBox(`invention_${name}`, { width: size[0], height: size[1], depth: size[2] }, scene);
    mesh.position.set(...position);
    return remember(mesh, material);
  };

  // The room-facing rim projects into the cabin. The actual aperture remains
  // clear: no alpha sorting, screen overlay, or opaque fake glass blocks space.
  box('window_lower_wall', [18.4, 1.14, 0.46], [0, 0.57, 7.13], panel);
  box('window_header', [18.4, 0.53, 0.5], [0, 4.735, 7.13], silver);
  for (const side of [-1, 1]) {
    box(`window_pillar_${side}`, [1.7, 3.36, 0.5], [side * 8.35, 2.8, 7.13], silver);
    box(`window_pillar_inset_${side}`, [0.38, 2.62, 0.04], [side * 8.36, 2.8, 6.86], graphite);
    box(`window_pillar_light_${side}`, [0.045, 1.85, 0.05], [side * 8.36, 2.8, 6.83], light);
  }
  box('window_sill', [15.1, 0.17, 0.7], [0, 1.14, 6.99], silver);
  box('window_sill_edge', [14.84, 0.045, 0.035], [0, 1.245, 6.75], light);
  box('window_top_gasket', [15.05, 0.095, 0.11], [0, 4.43, 6.84], graphite);
  box('window_bottom_gasket', [15.05, 0.065, 0.1], [0, 1.265, 7.00], graphite);
  for (const x of [-7.48, -2.56, 2.56, 7.48]) {
    box(`window_mullion_${x}`, [0.12, 3.18, 0.23], [x, 2.855, 7.0], graphite);
    box(`window_mullion_face_${x}`, [0.052, 3.18, 0.035], [x, 2.855, 6.875], trim);
  }
  for (const x of [-6.2, -3.1, 0, 3.1, 6.2]) {
    box(`window_lower_inset_${x}`, [2.74, 0.54, 0.035], [x, 0.54, 6.887], silver);
    box(`window_lower_groove_${x}`, [2.38, 0.025, 0.04], [x, 0.63, 6.863], graphite);
  }

  // A real ceiling closes the first-person room. A restrained central skylight
  // also reveals stars overhead without turning the whole cabin into a dome.
  for (const side of [-1, 1]) {
    box(`ceiling_side_${side}`, [7.1, 0.2, 14.4], [side * 5.55, 5.09, 0], panel);
    box(`ceiling_end_${side}`, [4.0, 0.2, 4.75], [0, 5.09, side * 4.825], panel);
    box(`skylight_long_frame_${side}`, [0.16, 0.24, 4.95], [side * 2, 5.01, 0], silver);
    box(`skylight_end_frame_${side}`, [4.0, 0.24, 0.16], [0, 5.01, side * 2.42], silver);
    box(`skylight_light_${side}`, [0.045, 0.035, 4.65], [side * 1.89, 4.88, 0], light);
    box(`ceiling_long_rail_${side}`, [0.28, 0.14, 13.9], [side * 5.98, 4.94, 0], graphite);
    box(`ceiling_long_light_${side}`, [0.09, 0.045, 12.7], [side * 5.98, 4.85, 0], light);
    for (const z of [-5.25, -2.8, 0, 2.8, 5.25]) {
      box(`ceiling_panel_seam_${side}_${z}`, [6.78, 0.025, 0.035], [side * 5.55, 4.978, z], graphite);
    }
  }
  box('skylight_crossbar', [4.0, 0.13, 0.1], [0, 5.0, 0], trim);
  for (const z of [-6.65, 6.65]) {
    box(`ceiling_crossbeam_${z}`, [17.8, 0.16, 0.24], [0, 4.9, z], silver);
    box(`ceiling_crossbeam_light_${z}`, [13.9, 0.035, 0.045], [0, 4.80, z], light);
  }
  // Two short diagonal braces connect the observation bulkhead to the roof.
  for (const side of [-1, 1]) {
    const brace = MeshBuilder.CreateTube(`invention_window_brace_${side}`, {
      path: [new Vector3(side * 8.1, 3.92, 6.73), new Vector3(side * 7.25, 4.84, 6.73)],
      radius: 0.085, tessellation: 8, cap: Mesh.CAP_ALL,
    }, scene);
    remember(brace, trim);
  }

  return {
    meshes,
    setInspectionMode(enabled: boolean) {
      for (const mesh of interior) mesh.setEnabled(!enabled);
    },
  };
}
