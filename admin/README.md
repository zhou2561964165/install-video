# 管理后台

基于 Ant Design Pro、Umi Max 和 TypeScript 的管理前端，与用户工作台分别构建。日常入口包括概览、用户管理、支付订单、客服工单和下载记录；操作记录及系统诊断位于高级管理。

## 环境与启动

使用 Node.js 22+，在本目录执行：

```powershell
npm ci --ignore-scripts
npm run setup
npm run dev
```

开发服务默认使用 4174 端口，默认关闭 mock。管理 API 是独立的 ASGI 应用 `app.admin_main:app`，仅支持 PostgreSQL；普通用户 API `app.main:app` 和默认 SQLite 启动方式不提供管理登录。

连接真实后台前，需完成 PostgreSQL 迁移到 `mc_0016`、配置独立运行角色与 `DB_URL`，并设置后端 `ADMIN_COOKIE_PATH`、至少 32 字节的 `ADMIN_CSRF_SECRET` 及 `ADMIN_ALLOWED_ORIGINS`。后者填写浏览器访问管理页面的准确 origin。配置规则见 [后端管理配置](../backend/app/admin/config.py)。本机 HTTP 开发仅在 loopback origin 下可设 `ADMIN_COOKIE_SECURE=false`；公网使用 HTTPS 和安全 Cookie。

例如将已配置的独立管理 API 运行在 8001 端口，再由前端开发服务代理：

```powershell
# 在项目根目录、已准备后端管理环境配置的终端中执行
uv run --env-file backend/.env uvicorn app.admin_main:app --app-dir backend --host 127.0.0.1 --port 8001
```

```powershell
# 在另一终端的 admin 目录中执行
$env:ADMIN_DEV_PROXY_TARGET='http://127.0.0.1:8001'
npm run dev
```

## 配置

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `ADMIN_ROUTE_BASE` | `/` | Umi hash 路由基址 |
| `ADMIN_PUBLIC_PATH` | `/admin/` | 静态资源路径前缀 |
| `ADMIN_API_BASE` | `/api/admin/v1` | 同源管理 API 前缀 |
| `ADMIN_DEV_PROXY_TARGET` | 空 | 可选开发代理目标 origin |
| `ADMIN_MOCK` | `false` | 仅开发环境的字面值 `true` 启用模拟数据 |

例如部署到 `/demo/admin/#/users` 时，设置 `ADMIN_PUBLIC_PATH=/demo/admin/`、`ADMIN_API_BASE=/demo/api/admin/v1`，hash 路由基址保持 `/`。管理 API 前缀只接受同源路径。配置中不放入密码或服务端密钥。

## 会话与操作权限

管理端使用后端 HttpOnly Cookie 和内存中的 CSRF Token。登录后读取会话及服务端能力信息，菜单与操作按钮按权限展示；服务端仍逐次验证权限。会话过期或返回 401 时清理前端会话状态并跳转登录。

用户列表和详情中的会员控制支持永久启用、指定未来到期时间、停用及恢复自动管理。写入需要 `memberships:write` 权限和服务端 `membership_control_write.ready=true`，并提交原因、预期版本和幂等键。管理员设置优先于付款会员规则，不修改订单、退款或订阅事实。

账号启停、支付金额显示和支付补发核实各自受权限及服务端能力控制。写请求发生网络错误或 5xx 时不会自动重试，应先核对操作记录和实际状态。

首个管理员须先注册用户账号，再由运维在后端的受限环境执行：

```text
python -m app.admin_grant grant --user-id <已确认的账号ID> --role admin --reason "经账号所有者确认授予管理员权限"
```

默认只预演，核对目标后附加 `--apply` 才写入。`ADMIN_CLI_DB_URL` 只用于运维 CLI。支付补发核实需单独配置 `ADMIN_STRIPE_READ_KEY` 受限只读密钥。

## 构建与接口类型

```powershell
npm run build
```

生产构建强制关闭 mock，静态产物位于 `dist/`。反向代理需提供同源管理 API，并设置准确的 Cookie Path 和 Origin；管理 HTML 应禁用缓存。

接口类型来自版本 `1.0.0-proposal.20261029.1` 的本地 OpenAPI 契约，包含 24 个操作。类型生成器位于 `tools/codegen/`，使用独立锁文件；需要重新生成时先在该目录执行 `npm ci --ignore-scripts`，再回到管理端目录执行 `npm run codegen`。生成器校验契约的固定 SHA-256，不发起远程请求。

## 开发模拟数据

`npm run dev:mock` 启用模拟服务，页面持续显示模拟模式提示。模拟账号及场景说明通过 `GET /__admin_mock/help` 查看；数据、会话和 CSRF 均与真实后端分离。场景包括正常、空列表、无权限、服务不可用、限流及会话过期。模拟模式不连接真实数据库、媒体、模型或支付服务，不能作为真实后端验收结果。

## 上游与许可

管理端基于 [Ant Design Pro 6.0.3](https://github.com/ant-design/ant-design-pro) 的固定提交 `42f2cb1d303380909ea04c73b5e60679d09c321a`，使用其 Umi Max 配置、布局及组件组合。来源清单见 [upstream/README.md](upstream/README.md)，版权与完整 MIT 许可见 [LICENSE](LICENSE)。

样式采用 primitive → semantic → component 三层 token，界面与业务通过窄接口单向依赖。
