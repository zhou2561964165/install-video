# 工程约定（每次必须遵守）

> **Claude 接手先读**：[当前交接文档](docs/handoff-2026-10-10.md)（更新至2026-10-11）。用户指定后续开发统一在 `E:\install_video`；已有访问隔离/UI代码已迁回，当前分支 `feature/job-file-access-isolation-original-20261011`，沿用原配置、账号数据和本地模型。旧worktree只作历史/回滚参考；其运行服务尚未切换，先按交接核对。功能开发仍暂停，模型内容验收已跳过。本文件不覆盖最新用户指令与 `AGENTS.md`。

## 1. UI 设计必须用 skill
涉及 UI/视觉/交互（配色、字体、动效、无障碍、组件）时，先调用：
- `ui-ux-pro-max`（设计决策检索：`--design-system` / `--domain color|typography|ux` / `--stack`）
- `design-system`（三层 token：primitive→semantic→component）

## 2. skill 优先于计划
计划文档与 skill 指引冲突时，**以 skill 为准**。
例：ui-ux-pro-max「每屏最多动 1–2 个关键元素」> 计划里的常驻动画清单。

## 3. 代码不写死、保留扩展、避免大规模重构
- 颜色/字体/时长一律走 `:root` token，不散落硬编码。
- 新增能力数据驱动、可配置，不做写死导致后续要推倒重来的实现。

## 4. 解耦（单向依赖，改动隔离）
- 核心模块对外只暴露窄接口：后端 `ytdlp_service.py` 是唯一接触 yt-dlp 的层；前端视觉表现层只读 `scene` 状态，绝不修改下载状态、绝不 import 下载核心。
- 层与层、模块与模块通过稳定接口通信，禁止绕过接口直接依赖内部实现。
- 新增能力走接口隔离，扩展不触碰既有核心。

以上约定需写进所有文档（含现有文档），并每次照做。
