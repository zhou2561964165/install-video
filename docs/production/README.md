# PostgreSQL 生产运行说明

本地启动默认沿用 SQLite。PostgreSQL 18 模式需要独立 API、source broker、下载 worker、计费 worker、清理器和管理 API；源码与默认配置本身不构成可直接运行的生产部署包。

## 配置与前置条件

- 用 Alembic 升级到源码唯一 head `mc_0016`，为迁移身份和各运行职责分配独立数据库角色；运行身份不使用数据库超级用户或迁移凭据。
- 计费角色处理通知时需要对 `app.billingevent` 行锁；除SELECT/INSERT外须具备窄范围 `UPDATE(id)`。部署者可为自己的计费角色执行 `GRANT UPDATE (id) ON TABLE app.billingevent TO billing_runtime_role;`（替换角色名），随后用该实际LOGIN在事务内执行零行`SELECT id FROM app.billingevent LIMIT 0 FOR UPDATE`并回滚。无须授表级UPDATE或outcome列UPDATE；id列授权仍允许修改主键，应按真实权限评估。
- API 仅在 `PG_BUSINESS_ENABLED=true`、迁移版本、媒体目录、持久化计费配置及 `SOURCE_BROKER_SOCKET` 检查通过后启动。`BILLING_INBOX_MODE=durable`；支付环境必须显式区分测试/正式模式，并固定账户命名空间。
- `MEDIA_ROOT` 使用绝对路径；媒体发布、目录遍历、磁盘空间、清理权限和挂载选项必须由真实运行身份核对。
- broker 使用本机受限 UNIX socket。Linux 来源子进程须通过独立 UID、网络命名空间、受限出口代理及防火墙预检；不向子进程传入数据库、LLM 或支付凭据。
- B站受控下载支持已验证的普通 AAC/DASH 双轨。没有所需轨道或无法验证画质时拒绝；不会回退到旧的不受控来源路径。平台可用性仍取决于网络与会话。
- `faster-whisper` 为可选依赖。仅安装默认依赖不提供本地转写；模型服务和支付也需分别配置。

完整环境校验见 `backend/app/config.py`、`backend/app/db.py`；各运行入口和隔离检查应由部署者结合自己的服务账户、网络、路径与资源限制配置。不要把生产配置或凭据提交到仓库。

## 切换与恢复

1. 原库停写前完成副本导出、演练导入、`verify_snapshot` 和二次导入幂等检查。发现孤立外键等异常时停止，由数据所有者决定处理方式，保留原库。
2. 维护期间业务 API 和支付通知返回 503，允许供应商重投；停止旧任务创建并等待在途任务。
3. 正式导入和只读验收通过后，持久化写入承诺标记，再开放 API 和后台写进程。
4. 标记前可按完整回执恢复旧环境。标记后新写入可能已发生，必须前向修复，不能直接指回旧 SQLite。
5. 切换后检查真实角色权限、任务提交 readiness、通知入库、服务日志、内存与 OOM，并完成登录和客服跨端验收。

迁移工具位于 `tools/production_db_*.py`。演练库、备份与临时副本的清理须核对名称、所有者、内容摘要及成功回执，不能批量清理不明数据库或历史证据。

## 管理端与首个管理员

管理前端使用独立 HttpOnly 会话和内存 CSRF。接口契约见 [admin-api-v1.openapi.yaml](admin-api-v1.openapi.yaml)，构建参数见 [管理端说明](../../admin/README.md)。子路径示例 `/demo/admin/` 使用 `ADMIN_PUBLIC_PATH=/demo/admin/`、`ADMIN_API_BASE=/demo/api/admin/v1`，hash 路由 base 保持 `/`。反向代理需同时配置准确的 Cookie Path 和 Origin，并对管理 HTML 禁用缓存。

支付的 `STRIPE_PUBLIC_ORIGIN` 使用站点origin，不含子路径。子路径部署还须将根路径的三种`membership=success/cancel/return`回跳精确重定向到项目子路径，保留普通根入口。云端Webhook配置独立的端点签名密钥，不能复用本机CLI监听密钥。测试模式的未付款Checkout过期通知可验证真实通知入库/消费；它不等同于付款成功、退款或会员开通验收。

由账号本人先注册，再由运维在服务器查明该账号 ID，使用独立受限的运维环境运行：

```text
python -m app.admin_grant grant --user-id <已确认的账号ID> --role admin --reason "经账号所有者确认授予首个管理员权限"
```

默认只预演。核对目标后附加 `--apply` 才写入；真实变更写入审计。`ADMIN_CLI_DB_URL` 仅交给运维 CLI，不能传给 Web 服务。没有“首个注册用户自动成为管理员”的机制。

补发核实只接受 `ADMIN_STRIPE_READ_KEY` 受限只读密钥，未配置时显示未就绪；不得用主支付密钥替代，也不能把 mock 或构建通过视为真实支付验收。

## 验证范围

本仓库保留产品测试源码。部分生产阶段测试依赖运维方单独提供的隔离 PostgreSQL、Linux 网络身份和私有验收 runner，部分默认测试路径对应原开发机；仅克隆仓库不能直接重跑所有阶段验收。管理端契约测试可用 `ADMIN_CONTRACT_PATH` 指向本仓库的 YAML。生产运行不依赖这些测试 runner，也不要为通过测试接入真实来源或支付服务。

工程约定：按适用技能执行；UI 用 primitive→semantic→component 三层 token；只有 `ytdlp_service.py` 接触 yt-dlp；模块通过窄接口单向依赖；不做无关重构。

## 管理员会员控制

后台日常入口为概览、用户管理、支付订单、客服工单和下载记录；操作记录及系统诊断在高级管理。原深链接仍可访问。

管理员会员设置优先于付款记录：可永久启用、指定独立的未来到期时间、停用或恢复自动。指定期限结束后权益失效，必须再次设置或恢复自动；不会自动回到付款权益。无手动设置时，沿用付款会员已启用且未到期的规则。页面以中文显示管理方式、有效期和实际生效原因。

手动控制不改付款状态、流水、订阅或退款事实，支付通知不能覆盖管理员设置。手动管理期间关闭新购买入口，已有通知继续处理。免费功能与账号登录保持可用。只有admin拥有`memberships:write`及`membership_control_write`能力，viewer只读；写操作要求实时会话、Origin/CSRF、原因、预期控制版本和独立幂等键。操作记录与控制修改同事务保存。

迁移`mc_0016`父版本为`t1_0015`，新增控制表和幂等操作表，不回填付款历史。Alembic必须传明确`b3b_runtime_roles`及其子集`mc_admin_roles`；只给管理角色控制表写入及幂等表SELECT/INSERT，其余运行角色只读控制表。新schema与六服务代码须在同一项目维护窗口协调更新，先备份、演练及真实运行角色探针，不能运行新代码配旧schema或回切旧SQLite。
