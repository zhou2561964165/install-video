// 下载编排配置：轮询/保存等常量集中于此，App 与 useDownload 共用，不散落魔法数字。
// 后端 /api 限流 30/60s，轮询间隔须 ≥2s 才安全。
export const POLL_MS = 3000;
// 来源直链的 Content-Disposition 不受应用控制；默认使用已有服务端文件命名。
export const DEFAULT_FORCE_SERVER = true;
