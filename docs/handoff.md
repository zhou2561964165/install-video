# 交接文档 · 万能视频下载网站

> 交接时间：2026-09-23 · 当前 HEAD：`main` @ `7288888`
> 本文档写给**下一位接手者**（人或 AI），目标是「读一遍就能动手」。所有命令均已实测可跑，所有结论如实标注验证程度，不夸大、不隐瞒。

---

## 0. 先看这里（30 秒上手）

**这是什么**：一个「粘贴链接 → 解析 → 选清晰度 → 下载」的全流程视频下载网站。
- 后端：FastAPI + yt-dlp + SQLite（进程内直接调 yt-dlp Python API）。
- 前端：React 18 + Vite + PIXI（Live2D 角色「白」+ lolimeow 紫罗兰主题）。

**跑起来（3 条命令）**：

```bash
# 后端（端口 8000；venv 在仓库根目录，不是 backend/ 下）
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# 前端（端口 5173；dev server 已配 Vite 代理 /api → localhost:8000）
cd frontend && npm run dev
```

浏览器打开 `http://localhost:5173`。

**验证跑通（2 条命令，均全绿）**：

```bash
cd frontend && npm test                                   # 37/37 通过
cd backend && ../.venv/Scripts/python -m pytest -q        # 32/32 通过
```

> 首次换机器需：`python -m venv .venv`（根目录）→ `.venv/Scripts/pip install -r backend/requirements.txt`；前端 `cd frontend && npm install`。

---

## 1. 架构与铁律（改动前必读）

### 1.1 数据流

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

### 1.2 解耦边界（单向依赖，改动隔离——违反会破坏扩展性）

- **后端**：`backend/app/services/ytdlp_service.py` 是**唯一**接触 `yt_dlp` 的层；其余模块只依赖它的接口（`extract_info` / `download` / 进度回调），**不得直接 import `yt_dlp`**。
- **前端**：视觉表现层（`pixi/`、`fx/`、`components/`）**只读** `scene` 状态，**绝不修改下载状态、绝不 import 下载核心**；下载核心也不依赖视觉层。二者靠「场景状态」单向解耦。
- **数据驱动、不写死**：颜色/字体/时长走 `:root` token；模型/表情/道具/特效走 `frontend/src/pixi/mascotConfig.js`（`MODELS` / `IDLE` / `EXPRESSIONS`）。新增能力 = 加配置，不改渲染代码。

### 1.3 工程约定（最高优先级，与根 `CLAUDE.md` 一致）

1. **UI 必用 skill**：涉及配色/字体/动效/无障碍/组件，先调 `ui-ux-pro-max` + `design-system`。
2. **skill 优先于计划**：冲突时以 skill 为准。
3. **不写死、保留扩展**，避免大规模重构。
4. **解耦**（见 1.2）。

---

## 2. 当前状态（如实）

### 2.1 完成度

| 模块 | 状态 |
| --- | --- |
| 后端下载闭环（解析/清晰度/直链·服务端切换/下载） | ✅ 稳定可用 |
| lolimeow 主题 + 浅/深主题 | ✅ 完成 |
| Live2D「白」完整版 + 程序化待机动画 | ✅ 完成 |
| 表情/道具/装饰特效系统（46 表情全量） | ✅ 完成 |
| 模型切换功能 | ✅ 已删除（`cycleModel`/`useModelSwitcher`/toast） |

### 2.2 验证状态（如实区分「已验证 / 未验证」）

| 项 | 结果 |
| --- | --- |
| 前端单测 `npm test` | ✅ 37/37（8 个文件） |
| 后端单测 `pytest` | ✅ 32/32（9 个文件） |
| 模型加载（16K 纹理） | ✅ 浏览器实测 0 报错 |
| 点角色弹菜单（6 组）· 点表情切换 · edle 特效触发 | ✅ 浏览器实测通过 |
| **待机动画是否逐帧在动** | ⚠️ **未逐帧采样确认**（见 §5 坑 #4） |

### 2.3 Git

- `7288888`：接入 edle.motion3 装饰特效 + 13 表情进菜单（46 全量）+ favicon。
- `69a77f2`：lolimeow 主题 + Live2D 完整版 + 表情/道具系统。
- **未入库（`??`，勿提交）**：根目录 `blog-home.png` / `ui-1280.png` / `ui-entry-light.png`（参考截图）。

---

## 3. 关键文件地图（改哪，看哪）

### 前端 `frontend/src/`

| 文件 | 职责 | 改它注意 |
| --- | --- | --- |
| `App.jsx` | 场景装配：主题切换、角色点击开菜单、scene→表情/特效接线 | 视觉层只读 `scene`，不碰下载 |
| `pixi/mascotConfig.js` | **数据单一来源**：`MODELS`/`IDLE`/`EXPRESSIONS` | 加表情/道具/特效/模型都改这里 |
| `pixi/mascot.js` | Live2D 创建/拖动/待机/`setExpression`/`setStageExpression`+`setStageEffect`/`startRandomProps` | 特效走 `model.motion()`（`MotionPriority.IDLE`） |
| `pixi/background.js` | 粒子/极光背景 | 颜色读 `pixi/theme.js` |
| `pixi/theme.js` | PIXI 颜色读 `:root` 语义 token | 无 DOM 时用 fallback |
| `components/ui/ExpressionMenu.jsx` | 换装菜单（只读 `EXPRESSIONS.menu`） | 常驻挂载，`open` 只切 CSS 类 |
| `styles/global.css` | 三层 token + 全部组件样式 | 颜色一律 `var(--*)`，勿散落硬编码 |
| `api.js` | 后端接口封装 | 前端唯一接后端的边界 |

### 后端 `backend/app/`

| 文件 | 职责 | 改它注意 |
| --- | --- | --- |
| `services/ytdlp_service.py` | **唯一**接触 yt-dlp 的层 | 其它模块不得 import `yt_dlp` |
| `services/jobs.py` | 线程池 + 任务生命周期 + 临时文件清理 | 扩展队列在此换实现 |
| `config.py` | 全部配置（env 覆盖，见 §5 坑 #2） | 默认值已够用 |
| `routes/parse.py` / `download.py` | HTTP 路由 | 只管入参/出参 |
| `models.py` | SQLModel `Job`（预留 User/Quota） | — |
| `db.py` | SQLite 引擎/会话 | — |

---

## 4. 如何验证改动

```bash
# 前端（改前端必跑）
cd frontend && npm test

# 后端（改后端必跑）
cd backend && ../.venv/Scripts/python -m pytest -q
```

**手工验收清单**（动到以下任一项就跑一遍）：
1. 起前后端 → 打开 `:5173` → 模型正常显示（非黑屏）。
2. 点角色 → 弹 6 组菜单 → 换发型/衣服/戴耳机（多选并存）→ 点「脸红」变 `is-active`。
3. 粘贴真实链接跑「解析 → 选清晰度 → 下载」→ 眼睛依次 圈圈眼→煎蛋眼→煎蛋眼→星星眼；无效链接→生气 + edle 特效出现。
4. `prefers-reduced-motion` 下动画收敛、随机道具仍工作。

---

## 5. 坑（务必先读，别再踩）

1. **venv 在仓库根目录** `E:/install_video/.venv`，**不是** `backend/.venv`。后端命令必须 `cd backend && ../.venv/Scripts/python ...`。
2. **ffmpeg**：`config.py` 默认 `ffmpeg_path="ffmpeg"`（走 PATH）；本机 ffmpeg 在 WinGet 目录，靠环境变量 `FFMPEG_PATH` 指定。换机器若下载/合并报 `ffmpeg_missing`，先设 `FFMPEG_PATH` 或把 ffmpeg 加进 PATH。后端全部配置可 env 覆盖：`MAX_CONCURRENT`(3)、`TEMP_DIR`(backend/tmp)、`MAX_FILE_SIZE`(2GB)、`TTL_SECONDS`(3600)、`RATE_LIMIT`(30)。
3. **16K 纹理**：`白.16384/texture_00.png` 是 16384×16384（约 1GB GPU 纹理），超过多数移动端/部分桌面 GPU 的 `MAX_TEXTURE_SIZE`（常见 4096/8192）会黑屏。开发机显存充足已实测可加载；移动端兼容需征得作者许可压缩（属「二改」）。
4. **待机动画未逐帧实锤**：代码已写（ticker 正弦驱动），但没做过帧间对比确认「真的在动」。接手第一件事：真机看 5 秒确认。
5. **浏览器自动化验证会被 Back-Forward Cache 冻结**：此前 Playwright 页面后台化后 `rAF`/`setTimeout` 冻结，采样挂起。属环境问题非代码 bug；验证时保持页面前台，或真机手动。
6. **3 张参考截图勿提交**：根目录 `blog-home.png` / `ui-1280.png` / `ui-entry-light.png`。
7. **授权红线**：Live2D「白」遵循作者使用规则——**非商用、不二传二改**。任何纹理压缩/模型改动都属「二改」，需先征得作者许可。

---

## 6. 下一步

1. （唯一待办验证）待机动画真机看 5 秒，确认在动。
2. 后续方向由接手时确定。已预留扩展点（不碰下载核心）：账号/额度（`models.py` 预留 User/Quota）、视频总结/字幕翻译（独立模块）、付费。见 `docs/design.md` §9 / §12。

---

## 7. 更多设计细节

- 表情/道具/特效的完整参数映射、阶段映射、直接写参数方案 → `docs/design.md` §14.8。
- 主题/token/待机动画 → `docs/design.md` §14.1–14.6。
- 后端架构/数据模型/错误分类/扩展点 → `docs/design.md` §1–§9。
