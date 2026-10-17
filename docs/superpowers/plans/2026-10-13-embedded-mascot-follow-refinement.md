# 角色嵌入与跟随细化实施计划

> **For agentic workers:** 使用 superpowers:executing-plans 逐任务实施；用户已授权按最新方案开发，直接推进。

**Goal:** 角色在文档流专属区域内显示和交互；镜片缩小、标题倾斜加大，并在接近角色/控件时连续淡出。

**Architecture:** 复用单个 PIXI 6.5.10 舞台、区域 DOM 几何和 Pointer Events/CSS transition。局部 bounds/pivot 决定 contain 与拖动范围，PIXI Graphics mask 和 DOM 热区共同服从区域；跟随只读取表现层标记。

**Tech Stack:** React 18、PIXI 6.5.10、pixi-live2d-display、Vitest/Testing Library、现有 Playwright。

**Spec:** `docs/superpowers/specs/2026-10-13-embedded-mascot-follow-refinement-design.md`

## Global Constraints

- 工程约定：UI先用ui-ux-pro-max/design-system，skill优先于旧计划；primitive→semantic→component三层token；成熟方案优先、配置化、窄接口和单向依赖。
- 视觉只消费scene/DOM几何，不修改下载状态或依赖下载核心；仅ytdlp_service.py接触yt-dlp。
- 保护既有未提交改动、账号/env、本地模型、原历史报告/raw/freeze/账本。Live2D模型不上传。
- 默认`embedded`；旧自由拖动仅为显式配置。模型、mask、热区、滚动与拖动必须服从相同区域；无有效区域隐藏。
- 只恢复示例网站前的“试试”；不恢复其余装饰文案。
- 圆径`clamp(96px,13vw,190px)`、倾斜8deg/3deg、位移12px；隐藏140ms、恢复180ms；普通控件进入8px/退出16px。
- 只倾斜一个展示标题。镜片定位与缩放层分开；不新增RAF、ticker、逐帧碰撞或全document style监听。
- 验收预算：真实模型POST=0、平台提取=0、媒体下载=0；浏览器API全mock、外部请求阻断。
- 本轮在现有功能分支工作区开发，以当前文件快照记录差异，保留此前未提交UI；不自动提交/推送/部署。

## Review Focus

- 非中心本地bounds/pivot：完整模型与可点击区域都在容器内。
- 滚动/resize/场景切换期间拖动：旧位置及捕获不能留在视口压住正文。
- 模型加载失败/区域不可见：没有漂浮模型或虚假排除矩形。
- 快速穿越避让边缘：未缩放圆径与退出余量防止反复闪烁，原生指针及时恢复。
- 热区在uiRef外、晚到几何变化：模型拖动和菜单变化能刷新边界，镜片style不反馈观察器。

### Task 1: 区域内角色渲染与交互

**Files:** `frontend/src/pixi/mascotConfig.js`、`mascot.js`、两者现有测试。

**Interfaces:** 消费现有`getRegion()`和`interactionTarget`；布局使用bounds/pivot与配置模式，发布同一可见DOM热区；App仍只调用现有resize/scaleBy/scene方法。

- [x] 添加失败回归：contain、非对称bounds/pivot、区域内拖动/相对位置、无区域隐藏、mask与热区/捕获清理。
- [x] `npm test -- src/pixi/mascotConfig.test.js src/pixi/mascot.test.js`观察预期失败。
- [x] 实现embedded默认与free兼容、contain、Graphics mask、区域拖动与生命周期约束。
- [x] 同命令绿色；本轮文件快照差异和结果写入`.planning/ui-embedded-implementation-20261013/progress.md`。

### Task 2: 页面区域与镜片避让

**Files:** `EntryScene.jsx`、`App.jsx`、`PointerFollower.jsx`及新测试、`tokens.css`、`reference.css`、App相关测试；独立审查后增加`ExpressionMenu.jsx`与现有测试，补隐藏热区的可见后备回焦。

**Interfaces:** Task 1消费App提供的文档流区域；`data-follow-exclude="mascot"`只发布可用区域/热区给PointerFollower。普通控件依据指针接近带；角色依据未缩放圆形足迹。

- [x] 添加失败回归：唯一“试试”、可用角色区域、控件接近/退出余量、uiRef外角色足迹、隐藏/晚到热区、禁用/清理。
- [x] 执行对应Vitest，确认失败属于缺失行为。
- [x] 实现≥1180px独立角色列、较窄文档流区域、角色排除标记、三层token与分层transition。
- [x] 回归绿色；记录实现差异与检查结果。

### Task 3: 集成验收与文档同步

**Files:** 新本机Playwright验收脚本/日志；新增本轮report；更新当前README、design/requirements、前端说明、交接及方案实施状态。

**Interfaces:** 复用现有本地模型、mock API与阻断外部请求的浏览器工作流；历史证据不改。

- [x] 前端`npm test`和`npm run build`通过；不重跑无变化后端测试。
- [x] 1440/1024/390/320px下验证渲染/热区contain、滚动/拖动/菜单/缩放/场景切换、唯一文案、镜片尺寸/倾斜/避让；检查正常/暗色/混合、reduced-motion/断点恢复。
- [x] 新报告记录真实覆盖、局限、网络审计和0调用；模型截图仅本机保存。
- [x] 独立Agent审查本轮快照diff与最终文件；处理实质问题并执行覆盖检查。
- [x] 当前文档同步实现状态与测试范围；保留历史报告原字节。

最终结果：193项前端/build、12+6浏览器检查通过。三个审查问题在同一修复阶段经四项失败回归和63项相关检查/全套验证解决。当前实现、设备局限及静止回退决策见[验收报告](../../acceptance-reports/2026-10-13-embedded-mascot-refinement/report.md)。
