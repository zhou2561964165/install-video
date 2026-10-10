# Compact 质量续收尾首阶段

工程约定：最新用户 AGENTS、Superpowers 调试/并行/TDD/独立审查/验证；UI 按需三层token，本阶段仅后端。配置化窄接口单向依赖、LLM/yt-dlp唯一服务层、scene只读，用户env/db/账号/旧raw冻结预算保留。新工作组硬26、root唯一真实caller、每POST前持久预占、全部失败和分类修复计数。

本阶段已关闭：**3 POST，供应商报告7,840 tokens，无final**。短文extract六事实来源校验通过；compose与一次format repair均返回主题conditions/consequences的完整标量字符串，旧normalizer仅接受数组，因invalid_theme_plan停止。未audit，中篇及长文未调用，原14essential全部未评。

核查协议整改在实测前已完成：新的compact最终一个摘要/有限点槽/条目内嵌真实四bool，程序管理S/P/check映射和引用；新增质量模块提供限定身份与主题primary诊断。原source/core/checks/final7/800/240保持，新模式compat默认、策略legacy默认保持，真实评测显式compact+default format1/semantic1/shared2。root当时1194后端全量通过，所有实际8模块和helper/原来源/rubric冻结一致后才调用。

独立checker已重放原始payload/feedback/normalization/quality/trace/public，严格transport metadata，确认3次和原失败未被包装为成功。当前受信任本地helpers初始化后，在任何模型POST及归档产品定义执行之前验证全部实际helper hash；没有声称具备独立bootstrap拦截任意helper自身顶层代码的更强机制。

## 已定位离线修复

对两份已存compose原件，已新增规范化将非空字符串原字面包为单元素tuple，精确空串转零项并记录；不按标点拆分、不剪字、不改ID或推断语义。空白-only、非法类型、超限仍拒绝；原数组不额外转换。Luna执行真实红绿，独立审查228项及root针对性112项通过，原件hash保持。prompt补明确JSON arrays、长度及point/theme topic同值。

独立还修复身份常规谓词句误报：“讲者认为条件成立并介绍操作”不能把“认为条件成立并”视为名字；未确认真姓名继续拒，完整源字面姓名仍绑定，不声称通用NER或归属证明。

## 有限续验收

[新独立续阶段](../2026-10-09-summary-quality-repaired/report.md)正常13/默认最坏19，计入同组已用3，最大组22≤26。为保留默认分类修复实测，把初步followup13估算调整为19，既有硬26不增，不续跑本阶段、不借旧余额、不另开工作组绕上限。续阶段需新full/review/freeze/check，全部首phase结果额外pin原件并绑定真实helper链。

存储层若os.replace临时WinError5，必须保留已经预占和原件、拒伪成功，不能重新发HTTP或重启phase；不改本阶段冻结helpers来隐藏错误。

只读复查：`.venv/Scripts/python.exe -B docs/acceptance-reports/2026-10-08-summary-quality-final/scripts/check_evidence.py`。关闭阶段不执行run。
