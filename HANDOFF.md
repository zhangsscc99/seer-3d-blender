# 赛尔号 3D 网页游戏 · 交接文档

目标:用 Babylon.js 做一个接近 3A 画质的网页版 3D 赛尔号,优先使用已有资产。用户要求全程使用简体中文沟通。

## 新场景：动力室 I（2026-10-11，独立于发明室）

- 参考图 `refs/power_room.png`（1024×465）；放大裁切在 `renders/power_ref/`。用户选定：复刻 + **第三人称**机器人行走、全部 Blender 程序化、三种动态（火焰流动、灯条扫光、玻璃管能量流动）、先精修反应堆。
- 文件：`blender/power_reactor.py`（反应堆，可单独审核，`build_reactor(prefix, origin, scale)`）、`blender/power_room.py`（房间，复用反应堆）、`blender/make_power_textures.py`（生成 `flame/grate/energy_blue/energy_orange/screen_ui.png`）、`src/power.ts`、路由 `?scene=power`（`src/main.ts` 仅加一条分支与导航按钮）。发明室文件未改动。
- 导出：`python3 blender/make_power_textures.py`，然后 `Blender -b -P blender/power_room.py -- --glb public/models/power/power_room.glb`（可选 `--render x.png --samples 16 --campos 0,-6.4,6.6 --target 0,0.9,1.0 --lens 18`）。反应堆审核：`Blender -b -P blender/power_reactor.py -- --out renders/reactor_vN`。
- 坐标仍是 Blender `(x,y,z)` → Babylon `(-x,z,-y)`。反应堆在 (0,3.5)、缩放 1.15；格栅走道 x±2.1、y −2.0…1.6，前方为地坑。元数据 `power_room.json`：`colliders` 圆、`walk` 走道矩形（Blender 坐标）、`spawn`(0,−1.0)、`lights`。网页端圆形推出 + 走道夹取，可沿设备滑行。
- 命名约定：`wall_left/right/back*`（朝相机一侧自动隐藏）、`strip_cyan|red_<灯名>_<序号>`（每根克隆材质做扫光）、`flame_core` + 材质 `pw_flame`（UV 滚动 + 闪烁）、`energy_blue/orange`（UV 流动）。材质统一 `pw_*` 前缀，在 `tuneMaterials` 中按名调参。
- `?scene=power&ref=1` 为参考视角（与 Blender 预览相机一致，水平 FOV 90°）。截图迭代记录：`renders/reactor_v1…v5`（子代理第 4 轮认为可导入）、`renders/power_v1b/v2/v3.png`（Blender 房间）、`renders/power_web_v1…v7.png`（网页参考视角）、`renders/power_web_tp.png`（第三人称）。
- 注意：混元机器人必须在创建灯光之前 `spawn`，否则网格没有光源会全黑；其金属度在本场景压到 0.25。
- 已验证：`check_scene.py --nono-count 0` 无问题（330 网格、约 14 万三角面）、`npm run build`、`node --test tests/`、`git diff --check`、网页无错误、第三人称四向碰撞。
- 剩余差异（未获用户验收）：左右机组造型仍偏方块、缺少参考里更复杂的分层壳体和扶手形细节；玻璃管后端外壳为推测补建；墙面细节与线缆较少；格栅下层管道在参考视角里只露出一部分。

## 区域 1：左前 NONO 大舱（2026-10-10）

用户要求按区域逐一修改，本轮仅重建左前大舱。上一保存点为 `c22384b`，以下尺寸覆盖此前 NONO 左舱记录；区域 2–8 尚未进入本轮修改。

- `blender/invention_room.py` 大舱分成半椭球玻璃罩、后侧金属脊、宽舱口边框、双层分段环管、深色机身、折线灯路、五根液压筒及六边形宽护沿；移除扩建范围内的左侧旧占位柜。
- 位置 Blender `(-6.3,-0.8)`，最大高度约 4.32m，外沿碰撞半径 2.64m。NONO 共享 v7 几何不变；舱内实例 scale=1.42、锚点 z=2.8674，其余两只不变。总览相机及其他区域模型不变。
- 已导出生产 GLB / JSON。六项移动测试、生产构建、网页无错误检查通过；总览两轮截图和第一人称转向检查完成。几何检查验证环形边框外向法线、顶点有限、NONO 在完整上下悬浮幅度内处于玻璃椭球内且高于甲板。
- `renders/pod_region1/before.png` / `after.png` 是相同总览视角前后截图；`first_person.png` 是实际玩家眼高。`invention_pod.blend` 是完整可编辑场景，选中了大舱部件；`geometry_check.json` 保存几何检查数据。
- 整体构图仍与原图有差异（原图左右设备被画面裁切更多）；本轮保留相机以便逐区比较。当前为待用户检视的区域 1 结果，不应宣称原图完全复刻或继续擅自修改区域 2。

## 当前保存点（2026-10-10）

用户要求先提交当前版本，再按原图从左到右列差异，后续逐项修改。此保存点包含 NONO v7、第一人称、天空盒及此前房间改动；功能检查通过不代表整体美术相似度已获用户认可。当前任务只保存和对比，不继续改模型。

## 第一人称与天空盒更新（2026-10-04）

用户新要求：发明室主角相机改为第一人称，并做好天空盒。现已完成：

- 默认 `?scene=invention` 是第一人称：眼高1.45m，出生 Babylon `(0,1.45,4.6)`，WASD移动、Shift快走、鼠标锁定查看；不支持锁定时按住画面拖动，Esc释放。普通模式不加载可见主角模型，不剖切侧墙。镜头无强制晃动，仰俯不影响水平移动。
- `?scene=invention&ref=1` 仍是美术对比用的正交总览；`?cam=...` 是旧调试总览。右下角可在第一人称/总览切换。**给用户预览第一人称时链接不能带 ref=1。**
- `src/inventionFirstPerson.ts` 实现输入/视角，`src/inventionMovement.ts` 实现碰撞与两层台阶高度。修正旧出生点卡入全息底座，补小控制台碰撞。移动显式读取 Vector3 的 x/z，不能对它使用 object spread。
- `src/inventionEnvironment.ts` 是本地程序天空：星场、微弱星云、带海陆云层/日夜面/大气边的行星，无限远不随行走平移。另含替代前墙的观景窗、顶棚、中央天窗、灯条；总览时隐藏新增室内构件。无需外部图片或网络资产。
- 验证：`npm run build` 通过；`node --test tests/invention-movement.test.mjs` 六项通过（出生点、舱体/控制台防穿透、台阶、墙边滑动、真实 Babylon Vector3）。网页键盘事件、拖动转向、鼠标锁定降级反馈与渲染已检查；内嵌浏览器本次走拖动降级。子代理复核碰撞与真实室内/窗外截图。仍有已有的 bundle 大小提示。
- 截图：`renders/invention_first_person.png`、`renders/invention_space_window.png`、合并预览 `renders/invention_fps_preview.png`。

## 最新进度（2026-10-04，NONO 重新建模）

用户明确反馈 v2 NONO 仍不像，要求重新参照原图三处，在 Blender 做好后再导入。**v2 的通过记录已被用户否定，不要当作当前验收结果。**

- 当前使用 **v7**：`blender/nono.py` 生成圆顶机壳、深蓝黑拱形面罩、短粗双竖眼、后侧扁平裙翼、薄叶片 V 耳翼。保留 v1–v6 过程资产，最终独立 `.blend` / `.glb` / 三视图 / 三实例姿态在 `renders/nono_v7/`。
- 新增原图三处裁切 `renders/nono_reference/`，并排对照 `renders/nono_v7/comparison.png`，网页实景 `renders/nono_scene_v7.png`，过程说明 `renders/NONO_REVIEW.md`。
- 子代理重新独立看原图和新模型，指出旧版厚额头、尖三角脸、眼槽过长、底托不足。最终 v7 经六张 Blender 图复核后再导入，没有再发现必须先返工的明确几何问题；不再用主观百分数当作验收。
- 恰有三只：左舱 `nono0`、中央 `nono1`、右管 `nono2`。共享13部件模型，运行时按前缀动画；`nono0` 锚点 z=1.35、scale=1.06，耳尖在完整悬浮幅度内仍位于玻璃半球内。中央与左舱各有不同侧倾/转向。
- 修正了面罩/耳翼朝内法线，焊接叶片端点；检查无退化面、封闭外向壳体，面罩朝前。生产构建、GLB 三实例/锚点、网页无错误检查通过；保留既有大包体提示。
- 本轮和此前房间修改已纳入 2026-10-10 保存点。不要恢复旧兔子、白球无人机、小鸟，或旧 `drone` / `bird` 动画分组。
- 此前已改右前弧形设备、两层台阶、完整 UV HUD、较大地砖与横向轨道、低全息底座、机械爪与读数面板，修复玻璃罩切割坐标。`?ref=1` 使用正交正面构图。房间整体还需精修，下面原差异清单属于历史参考。

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
| 动力室 I | `src/power.ts` | Blender 程序化建模,`public/models/power/power_room.glb` + `.json` | 首版可玩（第三人称），待用户验收 |

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
- 动画:`nono{i}_*` 上下浮动,`holo_icon/holo_man/holo_scan` 旋转
- 材质名:`floor_tile`、`steel`、`steel_light`、`wall_panel`、`glass`、`glass_tube`、`glow_cyan`、`hud_screen`、`holo_body` 等,Web 端会按名字改参数

### 历史对比结果（NONO 专项与本轮模型修改之前）
布局已对上:左前孵化舱（现已替换为 NONO）、后墙 HUD 屏 + 平台、右后两根玻璃管、地面圆 + 椭圆轨道。

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
