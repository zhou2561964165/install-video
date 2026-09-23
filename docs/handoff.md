# 交接文档 · 万能视频下载网站

> 交接时间：2026-09-23
> 交接范围：第二阶段「lolimeow 主题重设计 + Live2D 完整版升级 + 表情/道具系统」的当前状态、遗留问题、下一步。
> 原则：**如实记录**——已完成的写「完成」，没验证的写「未验证」，有问题的写清楚问题，不夸大、不隐瞒。

---

## 1. 一句话现状

后端 v1 下载闭环（解析/清晰度/下载）**已稳定可用**；前端已完成三块工作：① lolimeow 紫罗兰主题重设计、② Live2D「白」升级为完整版 + 程序化待机动画、③ 表情/道具系统（阶段映射 + 随机道具 + 点击换装菜单）。**全部代码已写完、单测 35/35 通过，但都未 commit，且未在真实浏览器里逐屏实锤验证。**

---

## 2. Git 工作区状态（重要，未提交）

当前分支 `main`，最近一次提交 `e9d530a` 是**旧版霓虹主题**。以下改动全部还在工作区未提交：

**已修改（M，未提交）：**
- 文档：`README.md`、`docs/design.md`、`frontend/README.md`
- 主题/场景：`frontend/index.html`、`frontend/src/App.jsx`、`frontend/src/styles/global.css`、`frontend/src/components/{EntryScene,ErrorScene,SelectingScene}.jsx`、`frontend/src/components/ui/Bubble.jsx`
- PIXI：`frontend/src/pixi/background.js`、`frontend/src/pixi/mascot.js`、`frontend/src/pixi/mascotConfig.js`、`frontend/src/pixi/mascotConfig.test.js`、`frontend/src/fx/constants.js`

**已删除（D）：**
- 免费版模型 5 个文件（`白-免费版.*`，被完整版替换）
- `frontend/src/hooks/useModelSwitcher.js`（模型切换已删除）

**未跟踪（??）：**
- `blog-home.png` —— 用户博客首页截图（主题参考，勿提交进仓库）
- `frontend/src/pixi/theme.js` —— PIXI 颜色 token 单一来源（Task C 新增）
- `frontend/src/components/ui/ExpressionMenu.jsx` —— 换装/表情菜单（本次新增）
- `frontend/public/live2d/bai/` 下新模型文件：`白.moc3`、`白.model3.json`、`白.physics3.json`、`白.cdi3.json`、`白.16384/`、`edle.motion3.json`、`expressions/`（46 个）

---

## 3. 已完成的工作（代码层面）

### ① lolimeow 主题重设计（Task A/B/C，代码完成，未提交）

按参考站 `baomihuahua/lolimeow`（设计语言）+ `Misaka273/lolimeow-shiroki`（玻璃拟态/粒子）重做视觉。三层 token（primitive→semantic→component）、浅/深主题、玻璃拟态卡片、紫罗兰胶囊按钮、PIXI 配色收敛。见 `docs/design.md` §14.1–14.5。

### ② Live2D 完整版升级 + 待机动画（Task D，代码完成，未浏览器验证）

- 模型由免费版换成完整版 `白.moc3`（9.7MB，16K 纹理，42 组物理，46 表情，`edle.motion3.json`）。
- 删除 `hideParts`（免费版水印隐藏，死代码）。
- `startIdle()` 程序化待机：ticker 逐帧正弦驱动 `ParamAngleX/Y/Z + ParamBreath`（物理输入），参数名/振幅/频率进 `mascotConfig.js` 的 `IDLE`。
- **已删除此前的 3 处调试日志。**

### ③ 表情/道具系统（本次完成，代码完成，未浏览器验证）

- **阶段映射**（`EXPRESSIONS.stage`）：解析中→圈圈眼、选清晰度/下载中→煎蛋眼、完成→星星眼、出错→生气、入口→无。
- **随机道具**（`EXPRESSIONS.random`）：拿手柄/拿话筒/戳脸，每 ~20s 随机展示 ~4s。
- **点击换装菜单**（`EXPRESSIONS.menu` + `ExpressionMenu.jsx`）：发型（互斥）/ 衣服（互斥）/ 大小变（开关）/ 配饰（复选）。
- **模型切换已删除**：`cycleModel`/切换特效/`useModelSwitcher`/toast 全部移除。
- 技术方案：绕过单选 expression manager，直接 `coreModel.setParameterValueById(paramId, 1/0)`，支持多选并存。见 `docs/design.md` §14.8。

**验证状态**：`npm test` → **35/35 通过**（8 个测试文件，含新增 3 条表情配置断言）。输出里的 `Error: Not implemented: navigation` 是 jsdom 对 `window.location.assign` 的既有警告，不是失败。

---

## 4. 未验证（必须处理）

1. **待机动画是否真的在动，未在浏览器实锤。** 原因：Playwright 页面反复进入 Back-Forward Cache（控制台报 "Page entered Back-Forward Cache" / "vite server connection lost"），后台化后 `rAF`/`setTimeout` 冻结，采样 evaluate 直接挂起。**这是环境问题，不是代码 bug**——但结论仍是「没验证过」。
2. **表情/道具/换装菜单同样未在浏览器实锤**（阶段映射是否真的切换眼睛、随机道具是否出现、点击角色是否弹菜单、多选是否并存）。建议真机/真实浏览器手动过一遍，或换 headless 保持前台的验证方式。

---

## 5. 已知问题 / 阻塞

1. **16K 纹理兼容性**：`白.16384/texture_00.png` 是 16384×16384，超过多数移动端/部分桌面 GPU 的 `MAX_TEXTURE_SIZE`（常见 4096/8192），可能黑屏。压缩纹理属「二改」，需征得作者许可。
2. **`edle.motion3.json` 未接入**：它是星星/眼泪/生气装饰特效（11.9s 循环），不是呼吸，也未挂到 `model3.json` 的 `Motions`。当前闲置。
3. **未进菜单的 13 个表情闲置**：睫毛/眼镜颜色/头发颜色/头部装饰颜色/身体装饰颜色/创可贴×4/黑脸/血迹/哭/脸红。已在 `EXPRESSIONS` 注释与设计文档注明「加一行即暴露」。
4. **全部改动未提交**（§2）。

---

## 6. 下一步（无需决策，可直接做）

1. 真实浏览器手动验收（§4 两项）。
2. 决定 `edle.motion3.json` 是否接入、13 个闲置表情是否进菜单/随机池。
3. 提交（需你拍板 commit 时机与信息）。

---

## 7. 环境 / 命令速查

```bash
# 后端（端口 8000）
cd backend && .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# 前端（端口 5173）
cd frontend && npm run dev

# 前端测试（当前 35/35 通过）
cd frontend && npm test

# 后端测试
cd backend && .venv/Scripts/python -m pytest
```

---

## 8. 关键文件索引

| 文件 | 作用 |
| --- | --- |
| `docs/design.md` §14 | lolimeow 主题 + 待机动画 + 表情/道具系统（§14.8） |
| `frontend/src/pixi/mascotConfig.js` | `MODELS` + `IDLE` + `EXPRESSIONS`（数据驱动） |
| `frontend/src/pixi/mascot.js` | Live2D 创建/拖动/待机/`setExpression`/`setStageExpression`/`startRandomProps` |
| `frontend/src/components/ui/ExpressionMenu.jsx` | 换装/表情菜单（读 `EXPRESSIONS.menu`） |
| `frontend/src/pixi/theme.js` | PIXI 颜色读语义 token（未提交） |
| `frontend/src/styles/global.css` | 三层 token 与全部组件样式（含菜单样式） |
| `frontend/src/App.jsx` | 主题切换 + 角色点击开菜单 + scene→情绪眼接线 |
