# 开发模拟服务

仅 `NODE_ENV=development` 且 `ADMIN_MOCK=true` 时加载 `admin.ts`。`fixtures.ts` 提供合成数据，`engine.ts` 模拟独立的会话、CSRF、权限、分页和错误响应。业务页面不直接导入模拟数据，生产构建不加载模拟控制接口。

`GET /__admin_mock/help` 提供模拟账号与场景说明。使用有效模拟会话向 `POST /__admin_mock/scenario` 提交场景名，可切换 `normal`、`empty`、`forbidden`、`unavailable`、`rate-limited`、`meta-unavailable` 或 `expired`。会话过期场景需要重新登录。

模拟账号及密码仅用于开发演示，页面持续显示模拟模式提示。模拟服务不访问真实后端、数据库、媒体、模型或支付服务；模拟结果不能代替真实后端验收。

界面复用三层样式 token，通过窄接口保持单向依赖。
