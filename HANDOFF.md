# 赛尔号 3D 网页游戏 · 交接文档

目标:用 Babylon.js 做一个接近 3A 画质的网页版 3D 赛尔号,优先使用已有资产。用户要求全程使用简体中文沟通。

## 克洛斯星重做：Blender 场景 + 核心地标（2026-10-25）

- 用户提供 2D 克洛斯星地图参考（橙红盆地、蓝色河流、粉色珊瑚、黄色晶体、绿色高台与传送阵、暗红远山），确认路线为**Blender 场景为主**、首版范围**场景 + 核心地标**、风格**明亮卡通 3D**；保留主角、宠物/NONO、背包、移动、场景路由与传送舱入口，不做皮皮/闪光波克尔、文字标签和完整原版 HUD。
- 文件：`blender/kelosi_scene.py`（程序化地形/河流/珊瑚/晶体/高台/传送阵/远山/植被/碰撞体与高度场导出）、`public/models/kelosi/kelosi_outdoor.glb` + `.json`、`src/kelosi.ts`、`src/kelosiMovement.ts`、`tests/kelosi-movement.test.mjs`。
- 地形：高度场 **188×161**、格距 1.2，范围 x±112 / y±96；可行走范围 x±92 / y±80。Blender `bp()` 输出 `(x, -z, y)`，经 glTF 后 Babylon 坐标为 `(x, y, z)`；高度场直接按 Babylon `(x, z)` 采样，元数据里的 `spawn.y` / 碰撞 `y` 存 `-z`。高度场是唯一权威，运行时双线性插值。
- 场景内容：河流使用自写 `ShaderMaterial`——高度场预烘 1024×256 深度图驱动水色/浅滩/岸线泡沫，三个世界坐标尺度的碎波法线 + 低频涌浪，三层夕阳天空反射、菲涅耳、太阳碎光，岸边泡沫只保留细碎水线与补丁（不再有几何白线/整圈白环）；踏脚石浅点也烘进深度图。另有左岸粉色分枝珊瑚群、近岸黄色发光晶簇、浅滩踏脚石、绿色高台（捕蝇草、银色/青色传送阵、旋转碎片）、右岸黄褐崖壁与粉色宝石、远景暗红山脊、外圈珊瑚/树木；出生海滩新增碎石、贝壳、浮木与贴岸草丛。70 个碰撞体 + 2 个盒型碰撞。
- 第三人称默认机位改为 `beta=1.30`、`radius=13`、目标 `player.y+1.4`，压低镜头让河对岸、高台、传送阵和远山进入画面，扩大后的场景更开阔。
- 运行时：`?scene=kelosi` 为默认场景，第三人称 ArcRotateCamera，WASD/方向键 + Shift 加速，镜头相对移动、地形跟随、深水减速、`B` 精灵背包；宠物与超能 NONO 跟随；`?ref=1` 固定参考视角。高度场/碰撞/坡度/深水逻辑在 `kelosiMovement.ts`，与渲染解耦。
- 调色：Blender/PBR 使用线性色，所有 sRGB 目标色经 `lin()` 转换，避免导出后发白；远山 `unlit` 保持平面剪影。
- 验证（2026-10-25）：`node --test tests/` **24 项通过**（其中克洛斯星 7 项：高度场、采样、出生点、碰撞/边界、深水与浅滩、出生→浅滩→高台→传送阵路线、坡度守卫）；`npm run build` 通过；`git diff --check` 通过；`check_scene.py --nono-count 0` 无问题（32 网格、245,673 顶点、309,517 三角面、70 碰撞体）。GLB **9.0 MB**，JSON 393 KB。浏览器实测 WASD/Shift 移动、深水阻挡、A 侧移正常，console 无脚本/WebGL 错误；水面相邻两帧约 11.5% 像素变化，确认动画在跑。
- 截图：`renders/kelosi_rebuild/43_default_final2.png`（最终默认第三人称）、`39_water_close3.png` / `42_ford_foam3.png`（水面近景与浅滩水线）、`33_overview2.png`（扩大后地图鸟瞰）、`asset_check.json`（GLB 检查）。
- 已知差距：水面仍是风格化着色而非物理水体，近景碎波主要靠法线贴图；浅滩水下沙洲只做颜色近似、没有真实折射/焦散；前景沙滩在极端俯视角下仍显空；三角面高于早期 25 万目标，后续可按材质合并减面。无头 Chromium（SwiftShader）约 3 fps，不代表真实 GPU 帧率，尚未在目标硬件上做帧时间基准。

## 主角替换：纯 Blender 重建经典赛尔机器人（2026-10-18）

- 用户最初要求「在网上找到赛尔机器人资源下载下来替换主角」。检索结果：Sketchfab 只有「赛尔号贾斯汀舰长」（人形，不是机器人）；Nexprint 有赛尔机器人但下载需登录；MakerWorld 被 Cloudflare 拦截；aigei 页面已失效。无合法可直接下载的官方机器人资产，用户选择**纯 Blender 程序化重建**，不使用第三方下载。
- 文件：`blender/seer_robot.py`（约 111 个网格的程序化模型 + GLB 导出 + Cycles 预览）、`blender/make_seer_textures.py`（生成面部贴图 `blender/seer_face.png`）、`public/models/player/seer_robot.glb`。
- 造型：近黑石墨色球形机身；正面大圆黑面窗 + 枪灰色带 10 颗螺栓的金属框；白色椭圆眼 + 各自中央的黑色竖瞳（贴图实现，避免网格眼）；机身两道接缝、两侧金色圆舷窗与小手、金色腰带 + 铆钉、倾斜的顶部压力阀（带 18 齿滚花）、背部暗色舱门 + 青色细光环；细密环肋钢腿与铃形脚。配色为低饱和金 + 枪灰 + 钢，青色仅作少量发光。
- 导出：`python3 blender/make_seer_textures.py`，然后
  `Blender -b -P blender/seer_robot.py -- --glb public/models/player/seer_robot.glb`。
  可选预览：加 `--render renders/seer_robot_front3.png --render-back renders/seer_robot_back3.png --samples 20`。
- 坐标：Blender 正面朝 **−Y**；经 glTF/Babylon 后模型局部正面为 **+Z**。五个场景原有 `rotY` 不变（动力室/传送舱/瞭望台 `π`，空间站 `0`，克洛斯星 `0`），第三人称镜头在背后时看到的仍是背面，行走时 `heading = atan2(dir.x, dir.z)` 让面窗朝向移动方向，已实测正确。
- 接线：`src/power.ts`、`src/teleport.ts`、`src/station.ts`、`src/lookout.ts` 的 `loadProp` / `spawn` 改为 `player/seer_robot`；`src/kelosi.ts` 的 `place()` 对含 `/` 的名字跳过 `hy/` 前缀，并预加载 `player/seer_robot`。旧的 `public/models/hy/robot.glb` 保留未删。
- 同时移除了动力室/传送舱/瞭望台里为混元机器人加的 `metallic=0.25, roughness=0.7` 全材质覆盖——新模型的枪灰/金/钢材质由 Blender 直接给出，覆盖会把金压成塑料色。只保留 `shadow.addShadowCaster`。
- 验证：`npm run build` 通过；`node --test tests/` **17 项通过**；Playwright 实测 `?scene=teleport` 按住 W 走到终端、提示「按 E 传送至 克洛斯星」、按 E 成功跳转克洛斯星；五个场景（teleport/power/station/lookout/kelosi）均正常加载新主角，背面、面窗与落地比例正常；console 无脚本错误（仅一次 favicon 404）。
- 资产规模：GLB **1.27 MB**，111 网格、10 材质、54,588 三角面、1 张贴图。
- 截图：`renders/seer_robot_front3.png` / `seer_robot_back3.png`（最终 Blender 预览）；游戏内 `renders/seer_web_teleport.png`、`seer_web_power.png`、`seer_web_station.png`、`seer_web_lookout.png`、`seer_web_kelosi.png`、`seer_web_face.png`。

## 跟随宠物 + 超能 NONO + 精灵背包（2026-10-19）

- 需求：带一只宠物跟随、超能 NONO 跟随；**四只宠物都要**，右下角背包可切换当前跟随宠物。没有可用的现成官方宠物模型（网上检索到的多为同人图/登录墙），因此四只宠物与超能 NONO 全部用 Blender 程序化建模。
- 新增文件：
  - `blender/pets.py`：布布种子 / 小火猴 / 伊优 / 米咔四只宠物的程序化建模、GLB 导出、透明背景 512² Cycles 图标渲染。导出：
    `Blender -b -P blender/pets.py -- --glb public/models/player/pets --icons public/ui/pets --samples 24`（可加 `--only bubu`）。
  - `blender/super_nono.py`：在 `blender/nono.py` 的 NONO v7 造型上做「超能形态」——壳体/面罩/眼部提亮为青蓝自发光，加悬浮光环、上下平衡激光翼、耳端光点；导出独立 GLB + 图标：
    `Blender -b -P blender/super_nono.py -- --glb public/models/player/super_nono.glb --icon public/ui/pets/super_nono.png --samples 24`。
  - `public/models/player/pets/{bubu,huohou,yiyou,mika}.glb`（约 0.5–0.6 MB/只）、`public/models/player/super_nono.glb`（约 0.35 MB）、`public/ui/pets/{bubu,huohou,yiyou,mika,super_nono}.png`。
- 造型：布布种子为绿色蛋形身体 + 奶油脸 + 叶帽 + 粉色花苞/花瓣手；小火猴为红色身体 + 奶油腹/脸 + 五簇火焰鬃毛 + 额前卷毛 + 三指火焰手 + 尾焰；伊优为蓝色海豹形 + 白腹/口鼻/额纹 + 耳鳍/臂鳍/背鳍/尾鳍；米咔为红色大耳 + 奶油脸 + 橙色额斑 + 粉腮 + 黑嘴吐舌。所有模型 Blender 正面朝 **−Y**，导出后 Babylon 局部正面 **+Z**，与主角一致。
- 运行时：
  - `src/companions.ts`：`preloadCompanions()` 一次并行加载 4 只宠物 + 超能 NONO；`attachCompanions(scene, playerNode, { playerHeight, groundAt })` 在场景里生成全部伙伴（只启用当前宠物）。
  - 宠物跟随采用**玩家轨迹尾随**：记录玩家最近 8m 的路径，宠物目标点为路径上 0.85–1.0m 处 + 当前朝向右侧 0.95m，避免直接穿墙；平滑跟随、移动时小跳/侧倾、静止时面向玩家；离玩家超过 2.7m 时直接吸附。`groundAt` 用于克洛斯星地形高度，其余场景为常量/空间站地板高度。
  - 超能 NONO 悬浮在玩家右上方（`playerHeight*1.05 + 0.22`），带上下浮动、轻微侧倾、光环缩放脉动与耳端光点闪烁。
  - 宠物与 NONO 的高度按 `playerHeight / 1.25` 缩放，保证在 1.7m/1.9m 主角的场景里比例一致。
  - 切换：`setPet(id)` 立即换模型（0.55→1 的弹出动画），写入 `localStorage['seer.followPet']`；跨场景/刷新保持选择。
  - `window.__companions` 暴露 `current / meshes / petNodes / nonoNode / setPet / update` 便于调试。
  - `src/backpack.ts`：右下角「精灵背包」按钮（位于原有「参考视角」链接上方，`right:18px; bottom:78px`），面板含四只宠物图标/名称/属性、当前选中高亮、超能 NONO「跟随中」状态；点击切换、`B` 开关、`Esc` 关闭、点击面板外关闭；按钮图标随当前宠物更新。参考视角（`?ref=1`）不创建背包与伙伴。
- 接线：`src/power.ts`、`src/teleport.ts`、`src/lookout.ts` 在 `Promise.all` 中预加载伙伴，并在创建灯光**之前**生成；`src/station.ts`、`src/kelosi.ts` 在主角之后生成。五个第三人称场景都把伙伴网格加入阴影投射，并在非参考模式创建背包。发明室 I 是第一人称 NONO 舱，未加入跟随伙伴。
- **顺带修复空间站地板高度**：空间站地板模型厚 1.2–1.3m，而主角原先生成在 y=0，实际陷入地板约 1.25m（只露出上半身）。本轮新增 `GROUND_Y = 1.25`，主角、伙伴、相机目标与行走高度都基于地板表面，视觉恢复正常。
- 验证：`npm run build` 通过；`node --test tests/` **17 项通过**；`git diff --check` 通过；Playwright 实测动力室打开背包（B）、切到小火猴、按 W 跟随时宠物保持在身后右侧、`localStorage` 持久化为 `huohou`，刷新后仍为米咔（测试写入）；teleport/station/lookout/kelosi 均能加载伙伴与背包，console 无脚本错误（仅 favicon 404）。截图：`renders/pets_backpack_power.png`、`renders/pets_huohou_power.png`、`renders/pets_bubu_kelosi.png`、`renders/pets_teleport.png`、`renders/pets_station.png`、`renders/pets_lookout.png`。
- 未做/限制：没有宠物战斗或技能，仅跟随与展示；宠物不做独立碰撞，靠轨迹跟随避免穿墙；超能 NONO 与宠物在镜头背后时看到的是背面（官方正脸需旋转镜头查看）。

## 新场景：瞭望露台 I（2026-10-18）

- 参考图 `refs/lookout_deck.png`。用户指出首版不像之后，按原图重做了剪影：更高的切角八边形观察窗（窗内带纹行星、顶部材质徽章、每边分开的青色灯条）、玻璃罐和圆头人偶、高台正面两侧青色格栅、白色舰体与近景厚唇、左侧朝向相机的大圆镜头、斜面上的红色横条、右侧穹顶、带防滚架和四轮的探测车、螺栓顶立罐、近景方壳加鳍片电机。
- 总览相机改为更接近原图的俯视：Blender `(0,-8.6,5.4)` 看向 `(0,1.15,1.4)`，镜头 20mm；网页 alpha π/2、beta 1.182、radius 10.54、垂直 fov 0.937。出生点改为 `(0,-1.55)`，两条细管不再做成横贯甲板的宽导轨。
- 重做前总览：`renders/lookout/before_rebuild.png`。当前总览：`renders/lookout/web_ref_v5.png`。第三人称走动：`web_tp_v3.png`。
- 仍未还原到原图的部分：窗框和设备还是方块/圆柱拼出来的，没有原图的倒角装甲和线缆；探测车的轮子从正面看仍像小圆柱；甲板是平面加两条纵梁，不是分层舰体；星云是程序贴图。不能当成已经还原。
- 文件：`blender/make_lookout_textures.py`（星云、行星、拱顶徽章）、`blender/lookout_deck.py`、`public/models/lookout/lookout_deck.glb` + `.json`、`src/lookout.ts`、`src/lookoutMovement.ts`、`tests/lookout-movement.test.mjs`。
- 导出：`python3 blender/make_lookout_textures.py`，然后
  `Blender -b -P blender/lookout_deck.py -- --glb public/models/lookout/lookout_deck.glb`。
  坐标仍是 Blender `(x,y,z)` → Babylon `(-x,z,-y)`。
- 布局（Blender 地面）：甲板约 x±7.1、y −5.3…5.3；高台碰撞盒 x±2.9、y 0.35…2.95；左镜头 `(-4.7,-2.4)`、红色斜面 `(-4.25,0.2)`、右穹顶 `(3.85,2.25)`、探测车 `(3.05,-0.85)`、立罐 `(5.2,-2.55)`、近景机组 y −4.2…−3.15。可行走范围 x±6.3、y −4.6…3.4。出生点 `(0,-1.55)`。
- 运行时：`?scene=lookout` 第三人称，`?scene=lookout&ref=1` 参考视角。舱内小人 `pilot_*` 轻微浮动。星空是内翻的 `sky_dome`。
- 验证：`node --test tests/lookout-movement.test.mjs` 3 项通过；`tsc --noEmit` 与 `git diff --check` 通过；`check_scene.py --nono-count 0` 无问题（126 网格、16,896 三角面）。网页参考视角无控制台错误。第三人称按住 W 曾从出生点走到约 `(0, 0.08, -0.03)`（`web_tp_v3.png`，早于最后一次设备位置调整）。
- 截图：`renders/lookout/web_ref_v5.png`；几何检查 `renders/lookout/scene-check.json`。`web_ref_v1.png` 到 `web_ref_v4.png` 是中间版本。

## 新场景：传送舱 I（2026-10-18）

- 参考图 `refs/teleport_room.png`（用户提供的传送舱 I 截图）。用户选定：**纯 Blender 程序化建模**（不使用混元）、**第三人称**机器人、中央传送台可走上去并增强灯环/星空、后墙 4 个终端真正传送。现有四个场景逻辑未改，只在 `src/main.ts` 增加路由与导航。
- 文件：`blender/make_teleport_textures.py`（警示条/肋条格栅/通风口/星云/跑灯环/终端环/拉丝金属）、`blender/teleport_room.py`（房间 + 元数据 + GLB/JSON 导出 + 可选 Cycles 预览）、`public/models/teleport/teleport_room.glb` + `.json`、`src/teleport.ts`、`src/teleportMovement.ts`、`tests/teleport-movement.test.mjs`。
- 导出与预览：`python3 blender/make_teleport_textures.py`，然后
  `Blender -b -P blender/teleport_room.py -- --glb public/models/teleport/teleport_room.glb --render renders/teleport_blender_final2.png --samples 16 --campos 0.38,-8.63,4.98 --target -0.06,1.32,0.87 --lens 26.7`（与网页 `?ref=1` 同构图）。
  调试可加 `--hide pad_glass` 等隐藏指定网格（逗号分隔）。坐标仍是 Blender `(x,y,z)` → Babylon `(-x,z,-y)`。
- 布局（Blender 地面坐标）：房间中心 `(0,0.4)`，可行走圆半径 **5.9**；传送台中心 `(0,0.5)`、玻璃穹顶半径 2.33 / 拱高 0.10；4 个终端在半径 5.0 的弧上，角度 50/77/103/130°，碰撞 `r=1.18`，交互点沿半径向内 1.7m、触发半径 1.4；5 根立柱在半径 5.05、碰撞 `r=0.55`；左侧座位舱中心 `polar(5.80,156°)`、碰撞 `r=0.98`；出生点 `(0,-4.0)`。元数据新增 `room`、`pad`、`terminals`、`portals`。
- **第一轮相似度返工（用户反馈「做得不太像」后）**：顶罩改为黑色底檐 + 斜置银框/灰色视窗 + 黄黑警示条 + 绿指示灯；终端圆环下移放大，重画 28 叶涡轮贴图并在外圈加 36 颗灯点、灰色镜面中心帽；立柱改为连续旋转体（`lathe`，下粗上收、顶部外扩到顶棚、正面青色胶囊灯）；墙面下半段改成浅灰白、通风格栅加高；左侧控制台改成贴墙内凹座位舱；传送台玻璃加厚变暗、辐条变细、去掉中心光核、收窄黄铜环；地面每个扇区增加斜向格栅。灯光功率整体下调并降低曝光，避免首版过曝。
- **第二轮相似度返工（用户要求「重新进行相似度返工」+ 多 subagent 审计）**：终端改为参考图的“蓝眼睛”结构——大直径灰蓝金属中心帽（`tp_lens` r .465 + `tp_hub` r .205 + 两圈细刻线）、帽外银色压圈，发光带收窄到贴图半径 0.70–0.93 并改成 12 段淡青分段（段缝加深），自发光/泛光重新配平；顶罩改成上宽下窄的梯形盾面（新增 `trap()` 网格工具），黑框+亮银内框+奶白面板，黑檐也改梯形并与视窗下缘贴合；黄黑警示条改成更细密的斜纹；立柱加粗到参考比例并改为偏蓝高光漆面；墙面上部通风格栅下移加宽，与立柱竖向对齐。传送台黄铜从亮金改为低饱和橄榄金（降低金属度/提高粗糙度），玻璃降低环境反射、压暗星云，辐条加粗增亮；地面拉丝贴图提亮。灯光改为更柔和的半球光 + 更强主光，ACES 曝光 1.07 / 对比 1.14，Bloom 0.40。白墙关闭 clearcoat 并降低环境反射强度，消除探针高亮环在漆面上拉出的青色细丝伪影。
- 终端映射（画面左→右，即 Blender x 负→正）：克洛斯星 `kelosi`、赛尔号空间站 `station`、发明室 I `invention`、动力室 I `power`。
- 交互：非参考模式靠近交互点（1.4m）时底部提示「按 E 传送至 …」，按 E 淡出后 `location.href='?scene=…'`；`navigating` 防重复；参考模式禁用。站在传送台半径内会平滑提升跑灯滚动、星云/发光强度与台面暖光（不切换场景）。
- 运行时：`src/teleport.ts` 以动力室为模板；`tp_*` 材质按名调参（含新增 `tp_lens`/`tp_hub`/`tp_visor`/`tp_glow_pill`/`tp_diaphragm`）；台面暖光按“离 `meta.pad` 中心最近的低位灯”识别，不再依赖功率阈值；每个终端的 `tp_glow_cyan` 与 `tp_diaphragm` 材质独立克隆做脉动与靠近增亮；弧形墙按「包围盒中心相对房间中心的径向方向」逐段隐藏；ReflectionProbe + Bloom/ACES/FXAA/锐化/暗角 + SSAO2（try/catch）。**反射探针在 Babylon 9 不会自动渲染**：等资源就绪后手动 `cubeTexture.render()` 一次，再改写 `_shouldRender=()=>false` 并挂成 `environmentTexture`，否则会形成“边渲染边采样自己”的 WebGL feedback loop（已实测 `FEEDBACK 0`）。`src/teleportMovement.ts` 在圆形障碍推出之外增加**圆形房间边界**，子步进 + 16 次约束迭代，失败退回，可沿弧墙滑行。
- 相机：参考视角与 Blender 相机严格对应（alpha 1.615、beta 1.179、radius 10.77、fov 0.7242、target `(0.06,0.87,-1.32)`）；第三人称 fov 0.92、radius 5.6、beta 1.02，alpha 限制 π/2±1.15、beta 0.7–1.35。
- 修复记录：星云底盘一直被 `backdrop_floor` 实体圆盘（顶面 z=-0.02，高于星云 z=-0.10）挡住，改为环形（内 6.2/外 7.3）后正常可见；当轮同时压低 `tp_starfield` 与玻璃透明度避免过曝，返工后又把运行时自发光提高、玻璃 alpha 定在 .46 以兼顾星云可见度。
- 验证（第二轮返工后）：`node --test tests/` **17 项通过**；`npm run build` 通过；`check_scene.py --nono-count 0` 无问题（**472 网格、169,664 三角面**，GLB 4.55 MB）；网页 `?scene=teleport&ref=1` 与第三人称截图正常；用 Playwright 实测按住 W 从出生点走到中央终端交互区，提示「按 E 传送至 赛尔号空间站」，按 E 后 URL 变为 `?scene=station` 且空间站场景加载成功（1111 网格）；console 无错误（仅一次热更新期间的瞬时 404，复测消失）。
- 截图：`renders/teleport_blender_v1…v24.png`、`teleport_blender_final2.png`（最终 Blender 预览）、`renders/teleport_web_v38_ref.png`（最终网页参考视角）、`teleport_web_v38_third.png`（第三人称）、`renders/teleport_compare_v38.png`（参考/Blender/网页三联对比）、`renders/web_v36_term_crop.png`、`web_v32_hood_crop.png`、`ref_term_one_zoom.png`、`ref_hood_zoom.png`、`ref_cols_zoom.png`；几何检查 `renders/teleport_scene_check.json`。
- 剩余差异（未获用户验收）：顶罩仍是简化的梯形盾面，参考图有更强的曲面转折和沿边银色包边；立柱比参考少分模线与配线细节；白墙为渐变弧面，参考图的装甲拼板更复杂；控制台座位舱为贴墙简化件；顶棚与背面为参考图看不见的合理补建。美术验收由用户判断。

## 动力室逐项修正（2026-10-11，本轮）

- 使用用户指定高清原图 `微信图片_20261010224246_449_25.jpg`；保留进入本轮时已有改动。按原有总览相机固定 1280×720 网页截图，未改变总览相机或第三人称玩法。
- 左侧：用闭合多边形实体重建低矮连续控制台、分层底壳、T 形检修面、圆鼻青灯和上下护沿；分离厚屏幕机头与键盘托盘；后柜增加终端、把手与红色连接件。
- 右侧：重做青灯/红灯机组护臂、前部斜向控制台、圆表刻度/指针及侧屏实体外壳；顶部补双铜线。大管改空心管箍、带螺栓/接缝的接口、实体承托架；透明深色材质采用边缘 Fresnel。
- 中央：减薄反应堆两道横肋，缩短右铜管落差并提升接口底座；替换黄色占位显示。格栅前方新增折线地坑护沿，仍禁止走入地坑。
- 屏幕统一修正完整 UV，并生成密集仪表纹理。通风口改低凹黑槽与横向银色短叶片，移除原竖立尖条。
- 源：`blender/power_room.py`、`blender/power_reactor.py`、`blender/make_power_textures.py`；导出 `public/models/power/power_room.glb` 与 JSON。运行时材质在 `src/power.ts`。
- 布局与碰撞：左灯中心移到 (-2.63,0.94)，左灯碰撞中心 (-2.4,0.95)、r=0.9；左前台碰撞中心 (-3.95,-1.9)、r=1.6。原走道/spawn 不变。提取 `src/powerMovement.ts`，修复多障碍推离后又被边界夹入设备的问题；迭代解约束，无法满足时退回上个合法位置。
- 验证：`node --test tests/` 九项通过（新增动力室出生、反应堆防穿透、地坑边界、六向滑动）；生产构建通过，仍有既有包体积提示。真实网页检查第三人称出生、WASD 输入、拖动转向和 console errors。
- 追溯：`renders/power_revision/before.png`、`pass1.png`、`after.png`、`third_person.png`、`third_person_side.png`；几何检查 `scene-check.json`。原图路径见上。
- 尚未宣称完整复刻：左右外壳仍比原图简化，原图的复杂连续曲率、墙面接缝/配线、金属细微反射尚有差异；参考单图遮挡的背面为合理补建。美术验收仍由用户判断。

## 新场景：动力室 I（2026-10-11，独立于发明室）

- 参考图 `refs/power_room.png`（1024×465）；放大裁切在 `renders/power_ref/`。用户选定：复刻 + **第三人称**机器人行走、全部 Blender 程序化、三种动态（火焰流动、灯条扫光、玻璃管能量流动）、先精修反应堆。
- 文件：`blender/power_reactor.py`（反应堆，可单独审核，`build_reactor(prefix, origin, scale)`）、`blender/power_room.py`（房间，复用反应堆）、`blender/make_power_textures.py`（生成 `flame/grate/energy_blue/energy_orange/screen_ui.png`）、`src/power.ts`、路由 `?scene=power`（`src/main.ts` 仅加一条分支与导航按钮）。发明室文件未改动。
- 导出：`python3 blender/make_power_textures.py`，然后 `Blender -b -P blender/power_room.py -- --glb public/models/power/power_room.glb`（可选 `--render x.png --samples 16 --campos 0,-6.4,6.6 --target 0,0.9,1.0 --lens 18`）。反应堆审核：`Blender -b -P blender/power_reactor.py -- --out renders/reactor_vN`。
- 坐标仍是 Blender `(x,y,z)` → Babylon `(-x,z,-y)`。反应堆在 (0,3.5)、缩放 1.15；格栅走道 x±2.1、y −2.0…1.6，前方为地坑。元数据 `power_room.json`：`colliders` 圆、`walk` 走道矩形（Blender 坐标）、`spawn`(0,−1.0)、`lights`。网页端圆形推出 + 走道夹取，可沿设备滑行。
- 命名约定：`wall_left/right/back*`（朝相机一侧自动隐藏）、`strip_cyan|red_<灯名>_<序号>`（每根克隆材质做扫光）、`flame_core` + 材质 `pw_flame`（UV 滚动 + 闪烁）、`energy_blue/orange`（UV 流动）。材质统一 `pw_*` 前缀，在 `tuneMaterials` 中按名调参。
- `?scene=power&ref=1` 为参考视角（与 Blender 预览相机一致，水平 FOV 90°）。截图迭代记录：`renders/reactor_v1…v5`（子代理第 4 轮认为可导入）、`renders/power_v1b/v2/v3.png`（Blender 房间）、`renders/power_web_v1…v7.png`（网页参考视角）、`renders/power_web_tp.png`（第三人称）。
- 注意：主角必须在创建灯光之前 `spawn`，否则网格没有光源会全黑。2026-10-18 起主角改为 Blender 重建的 `player/seer_robot`，原先对混元机器人压金属度的覆盖已移除。
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
- 场景路由:`?scene=kelosi | station | invention | power | teleport | lookout`,由 `src/main.ts` 分发并生成右上角导航
- 调试相机:`?cam=alpha,beta,radius,tx,ty,tz`;发明室另有 `?ref=1`(与参考图对齐的固定视角,并隐藏玩家)
- 密钥:`.env` 里的 `HUNYUAN_3D_API_KEY`(已 gitignore,不要提交、不要打印)

## 2. 已完成的三个场景

| 场景 | 文件 | 资产来源 | 状态 |
|---|---|---|---|
| 克洛斯星 | `src/kelosi.ts`、`src/terrain.ts`、`src/props.ts` | 混元 3D 生成,`public/models/hy/*` | 完成,可玩(机器人 WASD,Shift 加速) |
| 赛尔号空间站 | `src/station.ts` | Kenney Space Station Kit(CC0),`public/models/ks/*` | 完成,模块化网格 + 剖切墙 |
| 发明室 I | `src/invention.ts` | Blender 程序化建模,`public/models/inv/invention_room.glb` + `.json` | **进行中**,相似度约 6/10 |
| 动力室 I | `src/power.ts` | Blender 程序化建模,`public/models/power/power_room.glb` + `.json` | 首版可玩（第三人称），待用户验收 |
| 传送舱 I | `src/teleport.ts` | Blender 程序化建模,`public/models/teleport/teleport_room.glb` + `.json` | 可玩（第三人称 + 4 终端传送），相似度返工已完成，待用户验收 |
| 瞭望露台 I | `src/lookout.ts` | Blender 程序化建模,`public/models/lookout/lookout_deck.glb` + `.json` | 已按原图重做剪影，用户尚未验收 |

通用:玩家模型 `player/seer_robot`（Blender 程序化重建，见顶部章节），`props.ts` 的 `loadProp` / `spawn` 负责加载与归一化;后处理为 DefaultRenderingPipeline(Bloom、ACES、FXAA、锐化、暗角)+ SSAO2 + CascadedShadowGenerator。`hy/robot` 是旧混元模型，仍保留但已不被场景引用。

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
