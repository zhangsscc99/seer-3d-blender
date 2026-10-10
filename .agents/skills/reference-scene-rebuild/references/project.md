# 本项目的具体约定

- 仓库根目录运行命令。Blender 默认 `/Applications/Blender.app/Contents/MacOS/Blender`，不可用时寻找已安装的 Blender。
- 原图：`微信图片_20261002145944_421_25.jpg`。模型源码：`blender/invention_room.py`；共享 NONO：`blender/nono.py`；HUD：`blender/make_hud.py` / `hud.png`。
- 导出：`Blender -b -P blender/invention_room.py -- --glb public/models/inv/invention_room.glb`。同时生成同名 `.json`；Blender 在 Python 异常时可能仍返回 0，需要检查日志中的 traceback 与 exported 标记。
- Babylon 映射为 Blender `(x,y,z)` → `(-x,z,-y)`。房间 x±9、y±7，高5。不要直接用 Blender 平面坐标写网页碰撞。
- `src/invention.ts` 导入 GLB，并按材质名调参数。角色部件前缀为 `nono0_`（左舱）、`nono1_`（中央）、`nono2_`（右管）；三者共享 v7。`holo_icon` / `holo_man` / `holo_scan` 会被编入投影旋转组。固定底座部件不要误用这些前缀。
- 元数据 `colliders:[{x,y,r}]` 由 `src/inventionMovement.ts` 映射。盒形障碍和台阶高度也在该文件。实际相机 Vector3 的 x/z 是访问器；坐标复制必须显式读取，不能 `{...position}`。
- 第一人称 `?scene=invention`；正交总览 `?scene=invention&ref=1`。端口先确认当前 Vite 服务，通常5174。总览隐藏屋顶/前窗，默认第一人称保留天空盒和完整室内。
- 同一分区重建前后尽量保持总览相机不变。总览是建模检查工具，第一人称是用户玩法要求，不可为了匹配原图改回第三人称。
- `.env` 与 `gen/raw` 不提交，不读取/输出密钥。当前目录可能有与项目无关的个人文件，只对已确认属于项目的路径做 git add。

## 已约定的区域

1. 左前 NONO 大舱：玻璃罩、分段环管、深色机械基座与外护沿。
2. 左后发光圆柱：顶部开口、中段竖灯槽、下部屏幕与装甲块。
3. 左后银色机械单元：横筒、宽斜切基座、中央圆形接口。
4. 左前全息装置：分瓣金属底座与蓝色角色投影。
5. 中央终端与台阶：厚圆角屏幕、连续背板、暗色两层台阶。
6. 地面：中央三瓣弧形标记、横向通道、盖板及短灯带。
7. 右后培养管：机械顶底座、左管内 NONO 上方的机械爪、前方控制台；被遮挡的右管内容不臆定为新角色。
8. 右前大机器：厚重弧形实体机壳、嵌入面板、圆鼓模块、前方独立小设备。

## 验证命令

```sh
node --test tests/invention-movement.test.mjs
npm run build
git diff --check
/Applications/Blender.app/Contents/MacOS/Blender -b -P .agents/skills/reference-scene-rebuild/scripts/check_scene.py -- --asset public/models/inv/invention_room.glb --metadata public/models/inv/invention_room.json --out renders/scene-check.json
```

`check_scene.py` 从导出资产重新导入，不能替代网页截图、渲染法线观察和设备专属间隙检查。默认只验证本发明室应有的三只 NONO，换场景时使用 `--nono-count 0`。
