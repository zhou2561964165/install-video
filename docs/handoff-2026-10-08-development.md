# 当前交接：开发账号与自主有限验收（2026-10-08）

<!-- DOCUMENT_ARCHIVE_NOTICE -->
> **历史文档阅读说明：** 本页保留原阶段设计、任务和当时的验证结果。当前实现以[设计文档](design.md)和[需求/实施状态](requirements.md)为准，当前任务与预算见[自适应交接](handoff-2026-10-09-adaptive.md)。文中的“当前、下一步、待实现、等待授权”表示记录当时，不能据此重复已完成工作或重开关闭phase；仍未实现的能力以当前说明和代码为准。

> 后续当前状态见[摘要模块化交接](handoff-2026-10-08-normalized.md)：后端965项、三纯模块/分类有限重试、独立新工作组25POST。本文保留原开发账号和旧3POST工作组快照，不将其无重试/唯一扩展规则套到后续已授权整改。

已按用户更新的全局AGENTS和现有项目文档接续，不再重复询问开发/有限模型预算授权。轻量用注册lightweight_general/Luna Max，中高复杂度用sol_specialist/Sol High，主agent模型不改。完整实况见[当前报告](acceptance-reports/2026-10-08-grounded-summary-prefix/report.md)。

## 工程约定

技能优先；UI先ui-ux-pro-max/design-system与三层token；配置化、窄接口单向依赖，避免大规模重构；LLM仅llm_service/yt-dlp仅ytdlp_service，视觉只读scene，不改下载状态或import核心。原.env/db/模型与历史原件保持，默认legacy/n+2，无自动失败重试/隐藏付费回退。MIT来源及衍生评测保留署名与CC BY-NC-SA4.0非商业/同方式共享要求。用户持续授权优先于旧“等待授权”段落，预算每轮有硬上限。

## 已交付

- 已有manual-test@example.com配置不限下载额度，local backend/dev-quota-policy.json按显式ID热读，gitignored；其他账号继续有限，统计不清空。没有新建live账号/改密码/表迁移。
- quota me API显式unlimited与null limit/remaining；AuthBar显示下载额度不限，保留既有token样式/退出，不修改下载scene/core。
- 前缀codec允许仅unused尾槽省略或null，所有有效事实/点、未知键/hole/source/type/duplicate守护和最终边界保持。
- 独立新prefix入口/严格typed transport与完整raw/source/trace/plan绑定、发前预占/共享单caller/首次错误停均离线验证及review通过。
- root稳定后端855 passed/1既有warning，前端84 passed/build成功；原DB7账号/hash保持，me认证GET200使用原DB副本校验。Playwright受限/超时，未声称浏览器整体通过。

## 真实质量与预算

本次持续授权组上限26、最多一个13POST扩展：首contracts1POST未用尾null被冻结合同拒绝；追加prefix2POST，extract6facts通过但compose.summary为str而非声明数组，未audit。合计3POST/5869供应商tokens，两个失败phase关闭，唯一扩展已用，余额不用。本组不能继续新增付费phase或把失败改成功；不能通过建立新账号绕额度。

所有新14essential为not_evaluated，没有final；最近前轮真实评分仍短中7full/1partial、长6未评。来源字面/hash/结构/checks都不证明语义质量完成。默认legacy保持，代码未新建提交。

## 接续只读检查

```powershell
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-08-grounded-summary-prefix/scripts/check_evidence.py
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-08-grounded-summary-prefix/scripts/evaluate.py --check-only
```

不要对本轮调用--run/--freeze/--write覆盖文件。源修改后check-only失配是预期，不修改历史provenance。下一步先复审私有summary声明协议、用已存str错误与正常fixture离线验证，保持所有来源和硬边界；真实下一轮必须在明确的新有限工作范围内记录预算，不能无上限循环。

本机quota政策可删除指定ID撤销或更换已有user ID，无需账号迁移。留意政策文件不入git；只有用户自行正常登录自己的现有账号，服务便按当前政策返回不限状态，凭据从未保存到交付文档。
