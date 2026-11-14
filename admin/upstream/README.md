# Ant Design Pro 来源记录

- 上游仓库：<https://github.com/ant-design/ant-design-pro>
- 固定提交：`42f2cb1d303380909ea04c73b5e60679d09c321a`
- 上游版本：6.0.3
- 版权与许可：Alipay.inc，MIT；完整声明见 [../LICENSE](../LICENSE)。
- 原始包配置：[package.original.json](package.original.json)
- 复制文件清单：[copied-files.txt](copied-files.txt)
- 原始文件摘要：[original-files.sha256.json](original-files.sha256.json)

管理端在这些来源的基础上调整路由、登录、请求、权限和主题配置，使用 Umi Max 的布局与运行时扩展，以及 LoginForm、ProTable、ProDescriptions、Drawer 等组件。

本目录保存来源记录；项目使用的页面和配置位于 `src/`、`config/`。样式采用三层 token，模块通过窄接口单向依赖。
