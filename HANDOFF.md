# 赛尔号 3D 网页游戏 · 交接文档

目标:用 Babylon.js 做一个接近 3A 画质的网页版 3D 赛尔号,优先使用已有资产。用户要求全程使用简体中文沟通。

## 1. 技术栈与运行

- Vite + TypeScript + Babylon.js 9(`@babylonjs/core`、`loaders`、`materials`)
- 开发:`npm run dev`(或 `npx vite --port 5173`),打开 http://localhost:5173
- 构建:`npm run build`(含 `tsc --noEmit`)
- 场景路由:`?scene=kelosi | station | invention`,由 `src/main.ts` 分发并生成右上角导航
- 调试相机:`?cam=alpha,beta,radius,tx,ty,tz`;发明室另有 `?ref=1`(与参考图对齐的固定视角,并隐藏玩家)
- 密钥:`.env` 里的 `HUNYUAN_3D_API_KEY`(已 gitignore,不要提交、不要打印)

## 2. 已完成的三个场景

| 场景 | 文件 | 资产来源 | 状态 |
|---|---|---|---|
| 克洛斯星 | `src/kelosi.ts`、`src/terrain.ts`、`src/props.ts` | 混元 3D 生成,`public/models/hy/*` | 完成,可玩(机器人 WASD,Shift 加速) |
| 赛尔号空间站 | `src/station.ts` | Kenney Space Station Kit(CC0),`public/models/ks/*` | 完成,模块化网格 + 剖切墙 |
| 发明室 I | `src/invention.ts` | Blender 程序化建模,`public/models/inv/invention_room.glb` + `.json` | **进行中**,相似度约 6/10 |

通用:玩家模型 `hy/robot`,`props.ts` 的 `loadProp` / `spawn` 负责加载与归一化;后处理为 DefaultRenderingPipeline(Bloom、ACES、FXAA、锐化、暗角)+ SSAO2 + CascadedShadowGenerator。

## 3. 资产流水线

- `gen/assets.json` + `scripts/hunyuan-gen.mjs`:批量调用混元 3D,输出 `gen/raw/<name>/model.glb`(并发上限 3,PBR 每个任务 40 积分)
- `scripts/build-hy.mjs`:压缩为 `public/models/hy/*.glb`(减面、webp 纹理)
- `scripts/build-ks.mjs`:Kenney GLB 转 `public/models/ks/*`
- `scripts/build-assets.mjs`:旧的 Meshy 管线,依赖 /tmp 临时文件,基本弃用
- `blender/invention_room.py`:发明室 Blender 脚本;`blender/make_hud.py` 生成 `blender/hud.png`(HUD 屏纹理)

## 4. 发明室 I(当前工作)

**用户需求**:复刻参考图 `refs/invention_room.png`(明亮银灰金属实验室 + 青色自发光)。先用 Blender 建模再放进 Web 场景;材质要非常好;要用子代理反复截图与参考图对比,再改进。

### 重新导出模型
```
/Applications/Blender.app/Contents/MacOS/Blender -b -P blender/invention_room.py -- \
  --glb public/models/inv/invention_room.glb --render renders/x.png --cam ref --samples 32
```
(`--cam ref|front|right`;Blender 路径以本机为准。)脚本同时输出 `.json`:`colliders`、`lights`、`animated` 锚点。

### 关键坑:坐标映射
glTF 导入 Babylon 后,Blender `(x, y, z)` 对应 Babylon `(-x, z, -y)`(绕 Y 旋转了 180°)。`src/invention.ts` 里的 `toB`、碰撞体、玩家出生点、相机、侧墙隐藏的法线都按此映射写。不要按直觉用 `(x, z, y)`。可在浏览器里用 `window.__scene` 检查物体实际世界坐标。

### 对象命名约定(Web 端靠前缀识别)
- 墙:`wall_left/right/back/front`、`left_panel*`、`trim_*`、`glow_*`、`pipe_*`、`back_panel*`;相机一侧的墙会被自动隐藏,`front` 永远隐藏
- 动画:`drone{i}_*` 上下浮动,`holo_icon/holo_man/holo_scan` 旋转
- 材质名:`floor_tile`、`steel`、`steel_light`、`wall_panel`、`glass`、`glass_tube`、`glow_cyan`、`hud_screen`、`holo_body` 等,Web 端会按名字改参数

### 当前对比结果(上一轮子代理,相似度约 6/10)
布局已对上:左前孵化舱 + 兔子、后墙 HUD 屏 + 平台、右后两根玻璃管、地面圆 + 椭圆轨道。

待修(按优先级):
1. **右前弧形大机器**不对:现在是 3 个横躺胶囊 + 小桌。应改成只露一角的圆弧分段大机器,带 2–3 块发光蓝色面板和深蓝圆形嵌入,拉丝金属(metallic 0.8,roughness 0.35)。
2. **六边形全息底座**:应低矮(高约 0.05–0.1)深灰,只在上方有淡蓝半透明光柱;孵化舱下加一个深约 0.1 的六边形凹坑。
3. **左后矮机器**应是两台:带青色发光顶环的分层圆柱,以及银色圆柱顶 + 发光环底座的机械单元。
4. **玻璃管**里补悬浮机械爪和小精灵;底座加读数面板。
5. 补**后墙粗电缆**(竖直,直径约 0.15);小无人机改成**带蓝翼**的,不是白球。
6. 平台改 **2 层**深灰台阶;HUD 内容改为线框 + 数据风格(改 `blender/make_hud.py`)。
7. 地面轨道做成**凹进去的细灯带 + 小圆点**,线宽减半;地砖更大块、缝更细。
8. 整体仍偏暗、泛光偏重:继续微调 `src/invention.ts` 里的 hemi/key 强度、exposure、bloom,目标是亮而柔、无硬阴影。上一次调整(地面哑光、玻璃 alpha 0.18、泛光下调)**还没截图复核**。

### 验证流程(循环做)
1. 改 `blender/invention_room.py` → 重新导出 GLB
2. 启动 dev server,Playwright 打开 `http://localhost:5173/?scene=invention&ref=1`,等 8 秒后截图(截图保存在 `~/`,偶尔超时,重试即可)
3. 起子代理,让它读 `refs/invention_room.png` 和新截图,输出相似度、差异和带数值的修改清单(子代理看的是图片描述,别指望像素级)
4. 按清单继续改,直到相似度 ≥ 8/10

## 5. 其他待办 / 想法

- 发明室:给玻璃/全息做更好的折射感;地面做平面反射;模型按材质合并以降低 draw call(目前约 421 个网格,122k 三角面,3.2MB)
- 空间站传送门做成可交互,在场景间切换
- 机器人绑骨骼动画(Meshy rigging)
- 克洛斯星水面反射升级

## 6. 仓库状态

最近提交 `b410020`:加入发明室场景、Blender 脚本、GLB。之后若有未提交改动,以 `git status` 为准。`gen/raw` 与 `.env` 被 gitignore。
