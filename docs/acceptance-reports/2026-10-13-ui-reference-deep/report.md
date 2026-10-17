# 皮蛋 AI / DeepSeek 全站 UI 深度迭代

日期：2026-10-13。基线：`5dce877`与原有用户文档修改。本轮在既有皮蛋 AI 对照基础上修改现有表现层。

工程约定：UI先使用ui-ux-pro-max与design-system，skill优先于历史计划；颜色、字体、时长使用primitive→semantic→component token；成熟接口优先、能力配置化、窄接口与单向依赖。仅ytdlp_service.py接触yt-dlp，视觉只读scene派生表现；保护用户修改、账号/env、本地模型与全部原始验收证据。

## 参考与实际改动

复用[原分析](../../ui-refactor-pidanai.md)和[深度分析](../../ui-refactor-pidanai-deep.md)，并实际浏览[皮蛋 AI](https://pidanai.com/)与[DeepSeek](https://www.deepseek.com/)。参考其留白、圆润标题、玻璃胶囊控件、淡色背景与几何底纹，保留本项目产品名称、信息结构及功能。

- 浅色默认；深色/自动、登录、入口、视频工作台及角色菜单使用同一语义。新增浮动玻璃导航、宽输入卡、圆润大标题与胶囊页签，当前功能文案按来源能力与短中篇总结范围表述。
- token集中`frontend/src/styles/tokens.css`；`global.css`保留基础组件，`reference.css`集中参考表现。取消外部字体请求，使用系统字体及回退。
- 复用已有PIXI 6.5同一舞台/ticker；背景收敛为五色软光斑与少量光尘，静态点阵由CSS实现。配置、低档减量、reduced-motion、后台暂停与幂等销毁保留/补齐。未增加第二个产品canvas、RAF、WebGL上下文或运行依赖。
- 独立审查发现并修复暗色时长角标失读、320px导航空间、resize顺序及脱离stage后的GPU资源释放问题。下载/字幕/认证API与状态编排未改。

## 实际验证

| 检查 | 结果与范围 |
| --- | --- |
| `npm test` | 最终19文件、171项通过；包含背景ticker/销毁生命周期回归 |
| `npm run build` | 成功，138 modules；既有大于500k bundle警告仍在，主JS约810kB |
| Edge/Playwright UI回归 | 17项通过；1440/768/390/320px、浅/深主题、无横向溢出或导航碰撞、登录/解析、键盘页签、字幕、复制/TXT、返回URL与焦点、减弱动效 |
| 正常动效与舞台 | 原生Edge headless实际WebGL和本地Live2D加载，Enter开菜单/Escape关闭、390px canvas resize通过；无pageerror |
| 独立代码审查 | 复审无遗留Critical/Important；审查方只读，浏览器及测试由root执行 |
| 本地服务 | 用户授权加载现有.env启动后端；8000 OpenAPI200，5173前端200 |

首轮UI脚本曾使用简写页签名“字幕”，与现有正式名称“字幕文本”不匹配；改用真实可访问名称后完成17项检查。该选择器修正没有修改产品页签或语义。初轮170项为清理补测前结果，最终以171项为准。

所有浏览器API均拦截为本地模拟数据，模拟邮箱不是新增真实账号；摘要/字幕/下载的业务内容只用于检查界面。本轮开发验收模型POST上限0、平台提取/媒体下载上限0，实际均0；不使用或重开历史预算，旧raw/freeze/ledger/评分原字节保持。

## 截图与证据

- [浅色入口](entry-light-desktop.png)、[浅色登录](auth-light-desktop.png)、[浅色工作台](workspace-light-desktop.png)
- [深色工作台](workspace-dark-desktop.png)、[手机入口](entry-light-mobile.png)、[手机工作台](workspace-light-mobile.png)
- [17项浏览器结果](ui-check-result.json)、[正常动效/舞台结果](stage-check-result.json)

浏览器脚本保留于本机`.planning/ui-reference-deep-20261013/`，复用本机已安装的Playwright与Edge，没有给产品增加测试运行依赖。

本轮是本地UI交付与服务启动；未推送或部署。桌面浏览器模拟宽度不等于真手机，未做新FPS/真实低GPU性能测量；模拟摘要不提供新的语义质量结论，长文暂停与已有精度缺陷仍按原报告保留。
