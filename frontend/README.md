# 视频处理工作台前端

使用 React 18、JavaScript / JSX 和 Vite。包括公开首页、注册登录、视频解析与格式选择、任务进度、字幕及内容工具、会员方案。

## 本地运行

要求 Node.js 20.19+（20.x）或 22.12+，后端默认运行在 `http://127.0.0.1:8000`。

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

访问 <http://127.0.0.1:5173>。开发服务器将 `/api` 转发至后端；需要覆盖地址时，在启动前设置：

```powershell
$env:VITE_PROXY_TARGET = "http://127.0.0.1:8000"
```

## 构建

```powershell
npm run build
```

产物为 `dist/`。子路径部署可使用 `npm run build -- --base=/demo/`；服务器需配置匹配的静态路径与 API 转发。`npm run preview` 只用于静态预览。

## 代码组织

- `components/`：页面与界面组件。
- `hooks/`：身份、下载、会员和内容处理请求。
- `state/`：场景状态及功能配置。
- `api.js`：服务端请求封装。
- `styles/`：样式 token 与页面样式。
- `pixi/`：可选装饰层，与下载业务隔离。

Live2D 模型包不随仓库发布；手机端禁用装饰模型，缺少资源时核心功能仍可使用。权限以服务端校验为准。

安装、模型接口、语音转写和支付配置见[项目 README](../README.md)。
