# Claude 事实摘要后续实现审查（2026-10-07）

审查对象为 `33dc239d84549418f4ce76f70ba3a23180c0ce69`，对照 `1315b31` 后的代码与 2026-10-05 evidence 设计、计划、报告。当前目录没有更新的后续提交；本报告新建，旧文档和模型原始证据保持原样。

## 工程约定

适用技能优先；UI 先 ui-ux-pro-max 与 design-system，颜色/字体/时长走三层 token；配置化、窄接口单向依赖，yt-dlp 仅 ytdlp_service，LLM 仅 llm_service，视觉只读 scene。本轮仅审查后端与离线证据工具，不改 UI、用户 .env、数据库或模型资产，不发付费模型请求、不改预算台账。MIT 源及衍生证据保留原署名和 CC BY-NC-SA 4.0 非商业许可。

## 已确认并修复

1. **P1：auto 选事实管线时忽略 facts 专用分段配置。** `summarize_text` 只对显式 facts 使用较小分段；auto 仍会把至多 20000 字作为一次抽取输入，重现文档中已测得的过大分段风险。现统一两条事实路径的分段规则。事实分段数量超过上限时，auto 在任何 POST 前选择独立的 legacy 分段；显式 facts 明确报容量错误，不进行付费失败回退。
2. **P2：提示词与最终证据合同冲突。** 抽取提示还写“one contiguous run”，核查提示还写“lines array”，而合同允许非连续行号、实际发送 `[N]` 编号 text。现统一为选择可支持声明的编号原文行。
3. **P2：姓名归因接受不在原文中的完整名字。** 白空规范化会把 `Mira\nLiao`、`Mira  Liao` 或 tab 分隔的文字匹配成 `Mira Liao`，不符合逐字来源合同。改为原文精确子串查找，仍只允许同一 SourcePart；audit 重建同样使用精确匹配。
4. **P2：离线检查可误报成功。** 原 checker 未核验冻结 manifest/source/cleaned 哈希，实际清理和切分依赖当前生产代码；空 index、错误 posts、逆序证据和缺失 final checks 也会通过。现使用哈希核验后的冻结纯 codec 与 cleanup 函数，核验完整样本前缀、请求数量/顺序、输出与 audit 合同、证据原始顺序及模型元数据。输出预算 ceiling 也由错误的 24 改为实际台账值 49。`audit_contract_valid` 与 `semantic_entailment_proven` 分别报告，不把模型 flags 当作语义正确证明。
5. **P2：共享台账存在并发覆盖路径。** 原运行锁在各自报告目录，完成时写回整份旧台账；另一 caller 后续追加的请求可被覆盖。现统一到旧台账目录的 `.http-session-lock`，内部台账操作另有 `ledger.lock`；完成时重读并按 ordinal 更新当前记录。模拟交错测试验证其他记录和更新保留；真实 48 行未发现实际丢失，本轮不修改这些原件。
6. **P2：失败响应缺少可复查证据。** 原工具仅保存 HTTP 成功且 JSON 可解析的响应。现保存所有收到的响应状态、正文 SHA-256、白名单错误分类以及允许的正文/usage，并绑定 response 文件哈希；不存 headers、错误消息、密钥或 reasoning。HTTP 错误、无效 JSON、传输错误都保留预占且不自动重发。兼容生产适配器支持的 text blocks，忽略 reasoning blocks。
7. **P2：报告串轮、过度简化长文失败根因。** 更正见下节；保留原报告，在本新文档中明确更正数据和未验收范围。

## 更正旧报告的最终轮数据

旧报告未改写。以下均来自 `evidence-wide` 最终输出，而不是 `evidence-noncontig`：

| 样本 | 最终要点数 | 摘要字符数 | 最长要点字符数 | 可追溯事实数 |
| --- | --- | --- | --- | --- |
| zh-short | 5 | 270 | 53 | 11 |
| en-medium | 7 | 405 | 72 | 8 |
| en-long | 无最终结果 | — | — | 54（仅抽取阶段） |

旧报告的短文 6 点/396 字、中篇 6 点/424 字是串轮数据。最后的 `responses/48.json` 虽不闭合，但包含 18 个完整要点对象及第 19 个对象的完整文本（文本均为 56–141 字），在截断之前已经超过 7 点合同。因此长文问题同时包含数量/组织失控和输出截断；不能认为只增大 token 预算即可解决。语义覆盖、限定、归因和主题取舍仍未完成全量独立验收。

## 验证进度

- 基线后端：352 项通过。首次运行有 8 项 pytest 临时目录权限 setup error；在独立 basetemp 复跑后全部通过，无产品逻辑失败。
- 新增 3 项真实编排回归（只替换供应商 HTTP）：修复前 auto 两项失败、显式 facts 一项通过；修复后全部通过。
- 修复后管线 30 项、后端全量 355 项通过，保留既有 Starlette/httpx 弃用提示。
- 新增姓名反例：3 项修复前全失败，修复后通过；合同与管线合计 114 项通过。
- 新增 checker 反例：9 项修复前全失败、修复后全通过；所有测试只修改临时复制的证据。
- 加强后的 checker 只读复核真实原件通过，返回 11/8/54 事实，短/中 audit 合同完整，长文无最终 audit；预算仍 48/49。
- 预算工具 12 项回归修复前 10 项失败、2 项通过，修复后全部通过；新增 text blocks 兼容性测试修复前失败、修复后通过。预算工具与 checker 合计 22 项通过。
- **最终后端全量：380 项通过**，保留 1 条既有 Starlette/httpx 弃用提示；`git diff --check` 通过。未改前端，没有重复前端测试或将旧结果算成本轮验证。
- 两位独立 reviewer 复审了纯合同、选路及 checker 修复；未发现指定范围内新增的确认缺陷。本轮生产修复没有真实模型质量复测。

## 复查入口

加强后的只读核查结果保存为 [offline-check.json](offline-check.json)，与旧 `results/evidence-wide-offline-check.json` 区分，不覆盖旧输出。

```powershell
# 项目根目录，零网络只读复查冻结 evidence-wide；不要加 --write 覆盖/补写旧结果
.venv/Scripts/python.exe docs/acceptance-reports/2026-10-05-grounded-summary-evidence/scripts/check_evidence.py --phase evidence-wide

# 后端目录；为每次运行选择尚不存在的独立 basetemp
../.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider --basetemp E:/install_video/tmp/pytest-review-another-run
```

`evaluate.py --check-only` 比较的是**当前生产源码/提示词/runner**与旧冻结版本；本轮修复后预计失配，不能用它判断历史证据损坏。复查历史原件应使用上述 `check_evidence.py`。未来真实评测必须另建 phase、冻结当前字节并明确预算，不能复用旧结果作为新代码实测。

## 交付边界

`legacy` 仍为默认。当前修改没有新模型评测，不能把旧 phase 结果当作修复后实测。长文 compose 的截断及数量违约、逐项语义与原 14 条复合事实覆盖仍须区分于来源行号可追溯；后者不证明前者。代码修复处于工作区，尚未新建提交。原报告/设计/计划、冻结源码/payload/response/trace、共享台账均未改动；仅更新可执行评测工具，并新建本审查文档与测试。
