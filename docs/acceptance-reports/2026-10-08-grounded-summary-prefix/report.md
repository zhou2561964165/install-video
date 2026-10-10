# 开发账号不限额度与有限前缀续验收（2026-10-08）

用户已明确开发期授权无需再逐轮询问，可必要地有限扩预算；随后更新全局AGENTS，轻量子任务实际使用lightweight_general/Luna Max，中高复杂度使用sol_specialist/Sol High，主agent模型保持。当前开发账号能力已交付，但总结质量目标没有完成。

## 工程约定

技能优先；UI先ui-ux-pro-max/design-system与primitive → semantic → component三层token，颜色/字体/时长走token；能力配置化、窄接口单向依赖，避免大规模重构。LLM仅llm_service.py、yt-dlp仅ytdlp_service.py、视觉只读scene，不修改下载状态或导入核心。用户.env/原数据库/模型资产及历史raw/freeze/台账保持；默认legacy、n+2、无自动失败重试/隐藏付费回退。MIT来源及衍生评测保留署名、CC BY-NC-SA4.0非商业及同方式共享要求，见[原许可](../2026-10-04-natural-subtitle-quality/corpus/LICENSE.md)。

## 现有开发账号

沿用已有 `manual-test@example.com`，通过本机 `backend/dev-quota-policy.json` 的显式user ID配置不限**下载**额度；该文件已精确加入.gitignore，不发布本机账号政策。没有新建live账号、重置密码、修改User/Quota表或清空历史使用量。原数据库仍为7账号且文件hash保持。

新增quota_policy独立模块，每次读取本地政策、支持DEV_QUOTA_POLICY_FILE覆盖；不存在/坏JSON/重复字段/错误类型/重复ID/星号通配均保持有限额度。豁免仅跳过额度耗尽检查，使用量继续累计；撤销配置立即回到原quota行/default限制。正常用户、鉴权、每IP限流和下载核心保持。

me API不限状态为 `unlimited=true, limit=null, remaining=null`，used/date保持；普通账号仍原整数上限和余量。AuthBar使用原样式和token，显示“下载额度不限”，不将null误判为耗尽，用一个完整role=status/aria-atomic状态；邮箱/退出/未知quota处理保持。

本机用原数据库只读备份启动隔离API预览，正常签名认证的GET /api/auth/me为200，返回选定现有ID/不限/used0。没有打印或保存认证token；原DB文件hash保持。此证明不代表取消供应商/Codex账户限制，不限下载也不表示模型计费/服务器资源无限。

## 代码及验证

- 后端额度：真实临时数据库/API红25失败→相关48通过；UI真实组件红8失败→11通过，各自独立审查通过。backend唯一Minor本机policy应gitignore已由root处理。
- 用户更新规则后，新小范围前缀修复与审查使用注册Luna Max，新评测集成与跨层审查使用注册Sol High；不虚构模型切换、不改主模型，不固定人为并发数。先前独立语义agent因宿主usage limit中止，已保留其实际offline-check，不伪称完成评分。
- 稳定root后端完整测试 **855 passed、1既有Starlette弃用提示（59.77秒）**。最初835属于checker实际payload校验修复前/进行中状态，后续855才为最终记录。
- 前端完整测试 **84 passed**，生产build成功。保留既有jsdom不支持navigation的输出噪声和799.72KB bundle/500KB advisory；未擅自升级依赖或重构下载hook。
- 真实Playwright验证尝试未形成完整成功结果：工具禁止newContext；组件harness经历CJS直接导入/HTML编码诊断，最后tools/call在300秒超时。只声明组件单测、build和真实认证API通过，不冒充浏览器/真机/真实登录E2E成功。浏览器返回连接元数据不保存进报告。

```powershell
# backend目录
../.venv/Scripts/python.exe -B -m pytest tests -q -p no:cacheprovider --basetemp E:/install_video/tmp/dev-quota-prefix-reviewed-20261008
# frontend目录
npm test
npm run build
```

## 两轮真实验收与有限扩预算

当前工作组总硬上限26POST，先13、最多因已定位且离线验证的修复追加一次13。每phase独立冻结/台账、root唯一caller串行、发前持久预占，错误即停；不用旧余额，不重启失败phase。本轮无需再询问许可，依据用户当前指令和根AGENTS第5条。

| Phase | 预占/上限 | 真实结果 | 供应商报告tokens |
| --- | --- | --- | --- |
| organization-contracts | 1/13 | extract完整6事实对象，省略未用尾部null槽，冻结严格合同invalid_fields；没有任何final | 1686 |
| organization-prefix | 2/13 | 前缀extract通过6事实；compose完整JSON的summary为字符串而非逐声明text/fact_ids数组，invalid_fields，无audit/final | 4183 |

组累计 **3 POST、5869供应商报告tokens**；HTTP全部200且finish_reason=stop，但不是3份有效总结。唯一追加phase已使用并关闭，两个phase剩余额度均不使用。本组当前不再发起付费阶段，未扩大26硬上限。

前缀修订仅允许连续有效槽后省略或null空尾槽；不构造/删非空事实，不扩大12facts/7points/最终7声明800字符、每point240字符；旧pure parser与冻结文件保持。独立AST/窄probe确认原parse_facts/parse_candidate/parse_composition/parse_audit/_object/_parse_fact本体不变；过去14/1600候选/600point修订余量不是本次放宽。

新organization-prefix checker预执行验证9实际runner/checker链、三源码快照/rubric/manifest/所有source/baseline，复用类型敏感raw→trace→audit规划绑定；独立review发现actual payload model/max_tokens/temp/options未与freeze核对，20反例红→绿修复并复审通过，模型执行前已绑定当前实际payload。根全量/freeze/check-only对应修复后的代码。

## 独立证据与语义范围

[授权](results/budget-authorization.json)、[冻结provenance](results/organization-prefix-provenance.json)、[独立台账](results/request-ledger.json)、[准确诊断](results/organization-prefix-failure-diagnosis.json)、[源码/测试交付记录](results/code-delivery.json)、[offline-check](results/organization-prefix-offline-check.json)、[独立证据复核](results/organization-prefix-evidence-review.json)、[语义范围记录](results/organization-prefix-semantic-review.json)完整保留。

新checker确认raw绑定和6事实字面来源，compose received不能算validated。没有任何最终summary/key_points，原14essential全部not_evaluated、missing0仅表示未评分，不表示通过；可选精度与组织也没有最终文字可评。前轮final短中7完整/1部分、长6未评仍是最近已交付输出的语义记录，不能拿它当本轮结果。

当前总结路径仍不能稳定遵守私有生成合同，字符串摘要缺逐声明引用不能靠随意挂ID挽救。后续应先简化/明确私有声明生成协议并离线验证实际失败原件，不能持续扩额度、删事实或截字换通过。默认legacy未推广，当前新增代码/证据未新建提交。
