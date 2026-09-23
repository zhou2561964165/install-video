# 万能视频下载网站

粘贴任意平台视频链接 → 解析 → 选清晰度 → 下载到本地。依托 yt-dlp 覆盖数千站点，前端是「lolimeow」紫罗兰浅/深主题 + 玻璃拟态卡片（PIXI 舞台 + Live2D 白角色，含程序化待机动画），移动端可用。

## 工程约定（每次遵守）

> 与根目录 `CLAUDE.md` 一致（最高优先级）。

1. **UI 必须用 skill**：配色/字体/动效/无障碍/组件先调用 `ui-ux-pro-max` + `design-system`。
2. **skill 优先于计划**：冲突时以 skill 为准（如「每屏最多动 1–2 个关键元素」> 常驻动画清单）。
3. **不写死、保留扩展**：颜色/字体/时长走 `:root` token；新增能力数据驱动、可配置，避免大规模重构。
4. **解耦**：核心模块对外只暴露窄接口（后端 `ytdlp_service.py` 唯一接触 yt-dlp；前端视觉层只读 `scene`、不改下载状态、不 import 下载核心）；层与模块通过稳定接口通信，扩展不触碰既有核心。

## 架构

```
[前端 React/Vite + PIXI + Live2D]  ⇄ HTTP/JSON  ⇄  [FastAPI 后端]
                                                       │
                                          yt-dlp 服务层（线程池 + SQLite 任务状态）
```

- 后端：`backend/` — FastAPI + yt-dlp(Python API) + SQLModel/SQLite。直链下载与服务端下载自动切换，服务端产物 TTL 自动清理。
- 前端：`frontend/` — React 18 + Vite + PIXI v6 + pixi-live2d-display。单一 PIXI 管线，场景状态机驱动，WebGL 缺失/低端机自动降级。

详细设计见 `docs/design.md`，需求见 `docs/requirements.md`，后续扩展见 `docs/superpowers/plans/2026-09-21-extension-plan.md`，第二阶段视觉升级见 `docs/superpowers/plans/2026-09-22-phase2-cinematic-visual.md`。

## 环境要求

- Python 3.12
- Node.js 18+
- **ffmpeg**（合并高清视频/音频流必需；缺少时服务端下载会报 `ffmpeg_missing`）

## 快速启动

### 1. 后端

```bash
# 建虚拟环境并装依赖
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows；Linux/macOS 用 source .venv/bin/activate
pip install -r requirements.txt

# 安装 ffmpeg（合并视频/音频流必需）
#   Windows: powershell -ExecutionPolicy Bypass -File scripts/install_ffmpeg.ps1
#   Linux:   bash scripts/install_ffmpeg.sh
#   或系统安装后确保 ffmpeg 在 PATH 上

# 启动（默认 http://127.0.0.1:8000）
uvicorn app.main:app --reload --port 8000
```

### 2. 前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173，/api 由 Vite 代理转发到 8000
```

浏览器打开 `http://localhost:5173`，粘贴一个视频链接即可走完「解析 → 选清晰度 → 下载」。

## 配置（环境变量）

后端所有可调参数都在 `backend/app/config.py`，均可通过环境变量覆盖，均有合理默认值：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `FFMPEG_PATH` | `ffmpeg` | ffmpeg 可执行文件路径 |
| `MAX_CONCURRENT` | `3` | 并发下载数上限 |
| `TEMP_DIR` | `<backend>/tmp` | 服务端下载临时目录（TTL 自动清理） |
| `MAX_FILE_SIZE` | `2147483648` | 单文件大小上限（字节，默认 2GB） |
| `TTL_SECONDS` | `3600` | 服务端产物保留时长（秒） |
| `DB_URL` | `sqlite:///<backend>/jobs.db` | SQLite 连接串（可换 PostgreSQL） |
| `RATE_LIMIT` | `30` | 每 IP 每窗口请求上限 |
| `RATE_LIMIT_WINDOW` | `60` | 限流窗口（秒） |

默认路径（`TEMP_DIR` / `DB_URL`）已锚定到后端目录，与启动时的工作目录无关。

## 验证

### 自动化测试

```bash
# 后端（pytest，32 项）
cd backend && .venv/Scripts/python -m pytest

# 前端（vitest，32 项）
cd frontend && npm test
```

### 手工冒烟（端到端主链路）

1. 按「快速启动」起后端与前端。
2. 前端粘贴 `https://www.youtube.com/watch?v=dQw4w9WgXcQ`，点「解析」→ 应出现标题、时长与多档清晰度。
3. 选一档清晰度点「下载」：
   - 直链可用 → 浏览器直接保存；
   - 否则落到服务端下载（轮询进度到 `done`）→ 点「保存文件」。
4. 后端接口可直接验证（curl）：

```bash
curl -X POST http://127.0.0.1:8000/api/parse \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

## 署名与授权

Live2D 角色「白」—— 人物绘制：煎果饼子txy · 建模：逐尾鲨。模型遵循作者使用规则：**非商用、不二传二改**（见 `frontend/README.md`）。
