# Official Ant Design Pro source record

- Repository: https://github.com/ant-design/ant-design-pro
- Commit: `42f2cb1d303380909ea04c73b5e60679d09c321a` (official master retrieved 2026-10-26)
- Upstream package: 6.0.3; MIT, copyright 2019-present Alipay.inc. Full notice preserved at ../LICENSE.
- Exact upstream package snapshot: package.original.json. Copied source list: copied-files.txt.
- Clone used for inspection: E:\install_video\.planning\2026-10-26-admin-frontend-execution\official-ant-design-pro.
- No upstream .git, .env, deployment scripts, model/media data, sample account store, or generated API clients copied.

## Reuse inventory

| Official source at pinned commit | Reuse in this scaffold / follow-up |
| --- | --- |
| config/config.ts + src/app.tsx | Umi Max plugins, initialState, built-in ProLayout runtime, route menu rendering and request configuration retained; demo state/remote origins removed. This is the official framework layout, not a custom layout/router. |
| config/routes.ts | Official typed-by-Umi route registry; M0 contains setup, login and wildcard 404 only. Business registry follows in M1. |
| src/pages/user/login/index.tsx | LoginForm + ProFormText/Password composition retained; social login, captcha, remember-me, demo accounts and fake success removed. Disabled until the separate cookie/CSRF adapter is implemented. |
| src/pages/table-list/index.tsx (imports 1–14; drawer around 320–342) | Genuine upstream ProTable + ProDescriptions + Drawer reference identified. Not copied as an active fake rules CRUD page. M1 will compose these public components with admin DTOs, pagination and detail drawers. |
| src/pages/profile/basic/index.tsx | Genuine upstream Descriptions reference identified; not copied because demo refund/customer data are unrelated. |
| src/requestErrorConfig.ts + src/access.ts | Official extension points retained. Demo success/data envelope and role==='admin' authorization removed. No permissions before M1 authentication; rejected requests stay rejected. |
| config/defaultSettings.ts | Built-in responsive ProLayout settings retained, external logo and theme editor removed. |
| src/pages/exception/404/index.tsx + src/loading.tsx | Official Result/Card and Skeleton compositions retained with local copy and centralized spacing. |
| config/config.ts antd configProvider / runtime antd hook | Official Ant theme API used; project primitive → semantic → component mapping in src/config/theme.ts. |

## Excluded upstream features

Welcome/demo dashboards, charts, chatbot, account organization pages, fake list and notice mocks, Stripe-like demo/refund forms, remote backgrounds/fonts/icons, Google Analytics, request recorder, remote API base, generated oneapi/OpenAPI plugins, public CNAME, Husky/deploy scripts, and unrelated test harness dependencies are absent. No remote OpenAPI generation runs during install/setup/build.

## Project conventions

UI follows the previously approved ui-ux-pro-max/design-system decisions and three-layer tokens. Keep interfaces narrow and dependencies one way. Only backend ytdlp_service may touch yt-dlp; this frontend imports no backend or download core. This base is not deployed or authenticated.
