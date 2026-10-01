# 交接文档 · 万能视频下载网站（当前：v2 账号 + 每用户额度，前后端均已接入）

> 交接时间：2026-09-24 · HEAD `62118c4` · **活跃任务：前端接 v2（登录/注册强制门 + 额度余量）——代码完成 + 单测 55/55 全绿；浏览器手动联调未做（见 §1.4）**
> 本文写给**下一位接手者**（人或 AI）。所有命令、数字、结论均来自**实测**，如实标注验证程度，不夸大、不隐瞒。

---

## 0. 30 秒上手

**这是什么**：一个「粘贴链接 → 解析 → 选清晰度 → 下载」的全流程视频下载网站。
- 后端：FastAPI + yt-dlp + SQLite（进程内直接调 yt-dlp Python API）。
- 前端：React 18.3 + Vite + PIXI 6.5.10 + pixi-live2d-display 0.4.0，Live2D 角色「白」，深色液态玻璃 + 樱花粉辉光主题。

**跑起来（3 条命令）**：

```bash
# 后端（端口 8000；uv 管理的 .venv 在仓库根目录）
cd backend && uv run uvicorn app.main:app --reload --port 8000

# 前端（端口 5173；dev server 已配 Vite 代理 /api → localhost:8000）
cd frontend && npm run dev
```

浏览器打开 `http://localhost:5173`（若端口被占，Vite 自动 +1，看终端实际地址）。首屏是**登录/注册门**（强制登录、无「游客继续」）：注册/登录后进入下载流程，顶部账号条显示「今日剩余 X/Y」。

**验证跑通（2 条命令，均全绿——已实测）**：

```bash
cd frontend && npm test                                   # 55/55 通过（本次实测）
cd backend && uv run python -m pytest -q        # 46/46 通过（后端未动）
```

> 首次换机器需：`uv sync`（仓库根目录，uv 依据 pyproject.toml 建 .venv）；前端 `cd frontend && npm install`。

---

## 1. 当前活跃任务（先读这个）

**任务**：v2 账号体系 + 每用户额度，**后端 + 前端均已接入（2026-09-24）**。
- 后端（已完成）：注册/登录 JWT + 每用户每日额度，46/46 全绿。
- 前端（本次完成）：登录/注册**强制门** + 顶部账号条额度余量，55/55 全绿；**浏览器手动联调未做**。

- **计划文件**：`.planning/2026-09-24-v2-account-quota/`（`task_plan.md` 阶段+决策 / `progress.md` 会话日志 / `findings.md` 侦察事实）；前端计划 `C:\Users\zxk\.claude\plans\floofy-shimmying-naur.md`。
- **依据文档**：`docs/superpowers/plans/2026-09-21-extension-plan.md` §3.1（已标记「已实现」）、`docs/design.md` §6/§9/§12、`docs/requirements.md` §7/§8。

### 1.1 阶段进度（如实）

| 阶段 | 状态 |
| --- | --- |
| 会话 1：侦察 + 计划初始化 | ✅ 完成（读遍后端源码 + 扩展计划，产出 3 个计划文件） |
| 阶段 1 数据模型 + 配置 | ✅ 完成（`models.py` 加 User/Quota/Job.user_id + `config.py` 加 4 环境变量） |
| 阶段 2 认证服务 + 路由 | ✅ 完成（`services/auth.py` + `routes/auth.py` + `schemas.py` + 新依赖 pyjwt） |
| 阶段 3 额度接入下载 | ✅ 完成（`services/quota.py` + `download.py` 路由层检查） |
| 阶段 4 测试 | ✅ 完成（`test_auth.py` 8 条 + `test_quota.py` 5 条，后端 46/46 全绿） |
| 阶段 5 文档同步 | ✅ 完成（requirements/design/extension-plan/handoff 四处） |
| 会话 7 前端接 v2 | ✅ 代码完成 + 单测 55/55（登录/注册强制门 + 额度余量；**手动联调未做**） |

> v2 前后端均已落地：后端 `46 passed`（既有 33 + 新增 13），前端 `55 passed`（原 44 + 本次新增 11）。

### 1.2 约束红线（不可破）

1. **下载核心永不被触碰**：`services/ytdlp_service.py` 不加账号/额度职责；`services/jobs.py` 线程池不感知用户。
2. **后端公开访问现状**：`/api/parse`、`/api/download` 无 token 仍可用（匿名走每 IP 限流）。⚠️ 产品方向已变：匿名下载**后续取消、改必须登录**，后端收紧留作后续任务（本次未动后端）；前端已做强制登录门（不提供匿名入口）。
3. **契约向后兼容**：`schemas.py` 新字段用可选/默认值，旧前端不因缺字段报错。
4. **错误类型向前兼容**：只复用既有 `error_type`（`quota` / `login_required`），不改 9 类语义。
5. **配置不硬编码**：secret / 额度上限 / 过期时长 / 迭代次数全进 `config.py` 环境变量。
6. **测试不删改**：既有 pytest 33 条保持全绿，新增测试独立成文件。

### 1.3 已定设计决策（计划阶段拍板，勿再问）

- 鉴权 = **JWT（pyjwt，HS256）**，Bearer token；session cookie 方案暂不采用。
- 密码哈希 = **stdlib `hashlib.pbkdf2_hmac`**（零新依赖，不引入 bcrypt/passlib）。
- **匿名保留**：额度只作用于已登录用户，匿名下载仍走每 IP 限流。
- 额度 = **每日额度**（UTC 日期粒度），提交即扣，直链与服务端下载同计；失败退款留作后续。
- 额度检查放**路由层**（`download.py`），不进 `jobs.py` 线程池。
- 额度超限复用 `error_type="quota"`（前端 `ERROR_SCENES.quota` 已覆盖，零新增错误类型）。
- 唯一新依赖 = **`pyjwt`**。
- [2026-09-24 前端] 登录门 = **强制登录**（无「游客继续」），未登录先登录/注册才能下载。
- [2026-09-24 前端] 额度余量 = **顶部账号条**（`今日剩余 X/Y`，用完显示「额度已用完」）。
- [2026-09-24 前端] 登录持久化 = **localStorage**（key `auth_token`），刷新自动恢复。
- [2026-09-24 前端] 额度刷新 = App 层 `useEffect` 监听 `state.download`（提交成功）与 `state.error`（`quota`）→ `refreshQuota()`，`useDownload.js` 零改动。

### 1.4 前端 v2 验证程度（如实）

- ✅ 单测 55/55 全绿（`api.test.js` auth 边界、`App.test.jsx` 强制门、`AuthScene.test.jsx` 表单）。
- ⚠️ **未做浏览器手动联调**：登录/注册真实请求、额度递减、刷新保持登录、退出，均未在真实前后端联调下验证过（只靠单测 mock）。接手后建议先跑一遍 §6 手工验收第 1 条。

---

## 2. 架构与解耦铁律

### 2.1 数据流

```
[前端 React/Vite :5173]  ⇄ /api（Vite 代理） ⇄  [FastAPI :8000]
                                                    │
                          ┌─────────────────────────┼──────────────────┐
                          │ ytdlp_service.py        │  线程池 + 并发上限  │
                          │ extract_info / download │  任务状态落 SQLite │
                          └─────────────────────────┼──────────────────┘
                                                    │
                                              临时目录 TTL 自动清理
```

### 2.2 解耦边界（单向依赖，改动隔离——违反会破坏扩展性）

- **后端**：`backend/app/services/ytdlp_service.py` 是**唯一**接触 `yt_dlp` 的层；其余模块只依赖它的接口（`extract_info` / `download` / 进度回调），**不得直接 import `yt_dlp`**。
- **前端**：视觉表现层（`pixi/`、`components/`）**只读** `scene` 状态，**绝不修改下载状态、绝不 import 下载核心**；下载核心也不依赖视觉层。
- **数据驱动、不写死**：颜色/字体/时长走 `:root` token；模型/表情/道具/特效走 `frontend/src/pixi/mascotConfig.js`。

### 2.3 工程约定（最高优先级，与根 CLAUDE.md 一致）

1. UI 必用 skill（`ui-ux-pro-max` 主 + `design-system`）；涉及 UI 前**先调 skill，再写代码**。
2. skill 优先于计划（冲突以 skill 为准）。
3. 不写死、保留扩展，避免大规模重构。
4. 解耦（见 2.2）。
5. 每完成一个 Task **停下等用户指示**，不自动推进下一个 Task。

---

## 3. 前端 token 体系（pidanai 重构成果，已提交）

三层 token：primitive → semantic → component，单一切换开关 `[data-theme]`（写在 `<html>` 上）。

**深色为默认**（`:root` = 深色签名）；`[data-theme='light']` 为显式浅色覆盖块；`[data-theme='dark']` 继承默认；`[data-theme='auto']` 由 `@media (prefers-color-scheme)` 解析。`App.jsx` 的 `useState` 默认 `'dark'`，三档数组 `THEMES = [{v:'light'},{v:'dark'},{v:'auto'}]`。

### 3.1 关键 token 值（evaluate_script 实测读数）

| token | 深色 | 说明 |
| --- | --- | --- |
| `--surface` | `#0a0a0f`（ink-900） | 基底 |
| `--surface-glass` | `color-mix(in srgb, #fff 6%, transparent)` | 玻璃面（浅色档为 72% 白） |
| `--accent` | `#d6336c` | 品牌樱花粉·主按钮（白字 4.6:1） |
| `--accent-hover` | `#bd2a5b` | 深一档 |
| `--accent-pink` | `#ff6cae` | 折射粉（辉光/PIXI 粒子） |
| `--accent-lilac` | `#996fff` | 折射紫 |
| `--refract-cyan` | `#47a9ff` | 折射青 |
| `--refract-violet` | `#996fff` | 折射紫 |
| `--refract-pink` | `#ff6cae` | 折射粉 |
| `--refract-mint` | `#53ddb8` | 折射薄荷 |
| `--refract-warm` | `#ffc062` | 折射暖橙 |
| `--fs-display` | `clamp(40px, 8vw, 104px)` | 超大展示字号 |

折射五色**跨主题恒定**（hex，不随浅/深变化）；品牌粉 `--accent` 也跨主题恒定。

### 3.2 PIXI `hex()` 约束（重要坑）

`pixi/theme.js` 的 `hex()` 用 `parseInt(hex,16)`，非 hex 输入回退**白色**。因此 `--accent` 系列 token **必须解析为 hex**，**不能**是 `rgba()`/`color-mix()`。PIXI 消费的 token 与 CSS 消费的 token 分属两条线，改值时两侧同步（theme.js fallback 与 global.css `:root` 一致）。

---

## 4. 玻璃系统（pidanai 重构成果，已提交）

- 玻璃配方统一 token：`--glass-blur:18px` / `--glass-saturate:1.16` / `--glass-filter: blur(18px) saturate(1.16)`。
- 所有 `backdrop-filter`（含 `-webkit-` 孪生行）统一引用 `var(--glass-filter)`。
- `body` 背景 = 深色底 + 折射双光斑 + 樱花粉辉光（角色身后）。

### 4.1 backdrop-filter 祖先破坏（必须逐模块巡检）

`opacity<1` / `transform` / `filter` / `overflow:hidden` 任一出现在玻璃元素**祖先**上，会**静默破坏** `backdrop-filter`。改任何玻璃面，先检查祖先链（巡检法：chrome-devtools 读 `getComputedStyle(el).backdropFilter` + 逐祖先查这四项）。

---

## 5. 文件地图（改哪，看哪）

### 前端 `frontend/src/`

| 文件 | 职责 |
| --- | --- |
| `App.jsx` | 场景装配：登录门（gate/authed 分支）、三档主题、角色点击开菜单、scene→表情/特效 |
| `styles/global.css` | **三层 token + 全部组件样式（视觉层唯一真源）** |
| `pixi/theme.js` | PIXI 颜色读 `:root` 语义 token |
| `pixi/mascotConfig.js` | **数据单一来源**：`MODELS`/`IDLE`/`EXPRESSIONS`/`SCALE` |
| `pixi/mascot.js` | Live2D 创建/待机/`setExpression`/`scaleBy` |
| `pixi/background.js` | 折射光点/背景 |
| `components/ui/ExpressionMenu.jsx` | 换装菜单 |
| `components/ui/Preloader.jsx` | 加载层 |
| `components/{Entry,Selecting,Downloading,Done,Error}Scene.jsx` | 各下载场景 |
| `components/AuthScene.jsx` | 登录/注册整屏门（强制，无游客继续） |
| `components/ui/AuthBar.jsx` | 顶部账号条（邮箱 + 额度 + 退出） |
| `api.js` | 后端接口封装（前端唯一接后端的边界）：含 auth token 边界 + `register/login/getMe` |
| `lib/videoAdapter.js` / `lib/saveFile.js` | parse 归一化 / 浏览器原生保存 |
| `hooks/useDownload.js` | 下载编排（发起 + 轮询 + 自动保存） |
| `hooks/useAuth.js` | 登录态三态 `loading/gate/authed` + localStorage 持久化 + 额度刷新 |
| `state/sceneMachine.js` | 场景状态机 + `ERROR_SCENES` 9 类文案 |
| `state/downloadConfig.js` | `POLL_MS` 配置 |

### 后端 `backend/app/`

| 文件 | 职责 | v2 状态 |
| --- | --- | --- |
| `services/ytdlp_service.py` | **唯一**接触 yt-dlp 的层 | ❌ 未动（红线） |
| `services/jobs.py` | 线程池 + 任务生命周期 + 临时文件清理 | ❌ 未动（红线） |
| `config.py` | 全部配置（env 覆盖） | ✅ 加 JWT/额度 4 变量 |
| `routes/parse.py` / `download.py` | HTTP 路由 | ✅ `download.py` 注入可选鉴权 + 额度检查 |
| `models.py` | SQLModel `Job` + `User` + `Quota` | ✅ 加 User/Quota + Job.user_id |
| `db.py` | SQLite 引擎/会话 | ✅ `init_db` 未改（create_all 自动建新表） |
| `schemas.py` | Pydantic 请求/响应 | ✅ 加 auth 相关 6 个 schema |
| `main.py` | 入口 + 限流中间件 | ✅ include auth_router |
| `services/auth.py` | 密码哈希（pbkdf2）+ JWT + 鉴权依赖 | ✅ 新增 |
| `services/quota.py` | 每用户每日额度（查/扣） | ✅ 新增 |
| `routes/auth.py` | `POST /api/auth/register·login`、`GET /api/auth/me` | ✅ 新增 |
| `tests/test_auth.py` / `tests/test_quota.py` | v2 测试（8+5 条） | ✅ 新增 |

---

## 6. 如何验证改动

```bash
cd frontend && npm test                                   # 前端必跑（55/55）
cd backend && uv run python -m pytest -q        # 后端必跑（46/46）
```

**手工验收清单**（动到以下任一项就跑）：
1. **登录/额度（本次新增，尚未联调）**：首屏登录门 → 注册新号 → 进入下载流程 → 账号条「今日剩余 10/10」→ 下载一次递减 → 刷新仍登录 → 退出回登录门。
2. 起前后端 → 打开 `:5173` → 登录后模型正常显示（非黑屏）。
3. 点角色 → 弹菜单 → 点「变大/变小」等比缩放、点表情变 `is-active`。
4. 主题三档切换（浅/深/自动）→ 玻璃卡、token、文字色随档切换。
5. 登录后粘贴真实链接跑「解析 → 选清晰度 → 下载」全流程。

---

## 7. 坑（务必先读，别再踩）

1. **venv 在仓库根目录** `E:/install_video/.venv`，**不是** `backend/.venv`，由 `uv sync` 管理。后端命令用 `uv run ...`（自动用该 venv）。
2. **ffmpeg**：默认 `ffmpeg_path="ffmpeg"`（走 PATH）；本机靠环境变量 `FFMPEG_PATH` 指定。换机器报 `ffmpeg_missing` 先设 `FFMPEG_PATH`。可 env 覆盖：`MAX_CONCURRENT`(3)、`TEMP_DIR`(backend/tmp)、`MAX_FILE_SIZE`(2GB)、`TTL_SECONDS`(3600)、`RATE_LIMIT`(30)。`ytdlp_service.py` 有 `FFMPEG_MIN_HEIGHT=1080` 阈值：仅 ≥1080p 提供 ffmpeg 合并，低清档只用渐进式直链、无直链跳过该档（720/480/360 可能不出现属预期）。
3. **16K 纹理**：`白.16384/texture_00.png` 是 16384×16384（约 1GB GPU 纹理），超过部分 GPU 的 `MAX_TEXTURE_SIZE` 会黑屏。开发机已实测可加载；移动端需征得作者许可压缩（属「二改」）。
4. **授权状态**：Live2D「白」已获作者授权，页脚署名已去除。「二改」（纹理压缩/模型改动）是否在授权范围内仍建议确认后再动。
5. **WebGL canvas 读不到像素**：PIXI 默认 `preserveDrawingBuffer:false`。测模型尺寸用临时 `window.__mascot` 钩子，实测后删。
6. **edle 只有单个特效**：`edle.motion3.json` 是单个「星光闪烁」循环，非旧注释所写 5 个。
7. **YouTube 间歇性风控**：部分视频报 `Sign in to confirm you're not a bot`（`login_required`/网络错误），属风控非 bug。真实链路验证应预期偶发失败。
8. **backdrop-filter 祖先破坏**：`opacity<1`/`transform`/`filter`/`overflow:hidden` 出现在祖先会静默破坏玻璃效果（§4.1）。
9. **PIXI `hex()` 只吃 hex**：`--accent*` 系列 token 必须 hex，不能 `rgba`/`color-mix`，否则 PIXI 侧回退白色（§3.2）。
10. **Vitest 两条「Not implemented: navigation」告警是既有的**：来自 `useDownload.js` 的 `window.location.assign` 与 `saveFile` 的 `a.click()` 在 jsdom 不支持，**非测试失败**（55/55 仍全绿）。
11. **SQLite 建表**：新表靠 `init_db()` 的 `create_all` 自动建，无需迁移工具；但已有 `jobs.db` 上**已有表不会被 ALTER**——v2 已给 `Job` 加 `user_id` 列、新增 `user`/`quota` 表，**换到旧库需删 `backend/jobs.db` 重建**（开发期直接删即可）。
12. **App.test.jsx 已 mock `useAuth`**：加登录门后 `App` 首屏不再是 EntryScene。凡在 App.test 测下载流程，必须让 `vi.mock('./hooks/useAuth.js')` 返回 `status:'authed'`（已配好）；测「未登录」用 `status:'gate'`。改 App 结构时别漏这条 mock。
13. **登录 token 两处要一致**：localStorage key `auth_token`（持久）+ `api.js` 模块级 `authToken`（运行时，刷新后靠 `useAuth.init()` 从 localStorage 恢复并 `setAuthToken`）。改 token 流程时两处同步。

---

## 8. Git 状态（如实）

- **HEAD `62118c4`**（pidanai UI 重构 + 下载编排解耦 + 扩展指南/交接文档，已提交）。
- 前序 `7ac05a4`（后端解析接口补元数据 + 格式档位精化，已提交）。
- **工作区有大量未提交改动**：v2 后端（`config.py`/`models.py`/`main.py`/`schemas.py`/`routes/download.py`/`requirements.txt` 改，新增 `routes/auth.py`、`services/auth.py`、`services/quota.py`、`tests/test_auth.py`、`tests/test_quota.py`）与 v2 前端（`App.jsx`/`api.js`/`styles/global.css` 改，新增 `hooks/useAuth.js`、`components/AuthScene.jsx`、`components/ui/AuthBar.jsx`、`components/AuthScene.test.jsx`，改 `api.test.js`/`App.test.jsx`）——**均未提交**。
- **`??` 勿提交**：根目录参考截图（`blog-home.png` / `ui-1280.png` / `ui-entry-light.png` + `pidanai-desktop-full` / `pidanai-desktop` / `pidanai-mobile-375x812` / `pidanai-mobile` / `pidanai-tablet-768x1024`，共 8 张）、`docs/package-lock.json`、`uv.lock`、`.planning/`（计划文件属工作记忆，是否入库由你定）。

---

## 9. 下一步

**v2 账号 + 每用户额度已前后端全部落地**（后端 46/46、前端 55/55 全绿）。剩余与可选：
- **手动联调验证**（建议先做）：起前后端，跑一遍 §6 手工验收第 1 条（本次只做了单测，未做真实浏览器联调）。
- **后端强制登录（收紧匿名）**：产品方向已定「匿名下载取消、改必须登录」。下一步把 `/api/parse`、`/api/download` 改为必须 token（`get_current_user` 替代 `get_current_user_optional`），同步调整 `test_quota.py` 里「匿名绕过」相关用例。前端已就位，无需再动。
- **v3 视频总结 / 字幕翻译**（LLM）、**v4 付费**（会员/支付渠道）——见 `docs/requirements.md` §8 与 `docs/superpowers/plans/2026-09-21-extension-plan.md` §3.2/§3.3。

## 10. 更多设计细节

- **v2 计划**（阶段/决策/侦察事实）→ `.planning/2026-09-24-v2-account-quota/`（`task_plan.md` / `findings.md` / `progress.md`）；前端 v2 计划 → `C:\Users\zxk\.claude\plans\floofy-shimmying-naur.md`。
- 表情/道具/特效参数映射 → `docs/design.md` §14.8。
- 主题/token/待机动画 → `docs/design.md` §14.1–14.6（⚠️ §14 配色已由 pidanai 重构替代，当前 token/主题见 `docs/ui-refactor-pidanai.md` 与 `docs/ui-extension-guide.md`；§14.6 待机/§14.8 表情机制仍准）。
- 后端架构/数据模型/错误分类/扩展点 → `docs/design.md` §1–§9（§6 含 User/Quota 预留字段、§12 迭代路线）。
- pidanai 风格分析 → `docs/ui-refactor-pidanai.md`；深度分析 → `docs/ui-refactor-pidanai-deep.md`；扩展指南 → `docs/ui-extension-guide.md`。
- v2 实现方案依据 → `docs/superpowers/plans/2026-09-21-extension-plan.md` §3.1。
