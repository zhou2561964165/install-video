# Development mock boundary

Only explicit NODE_ENV=development plus ADMIN_MOCK=true loads admin.ts. fixtures.ts contains synthetic DTOs; engine.ts implements separate cookie/CSRF/permission/pagination/error simulation. Application pages never import them. Production never loads mock controls or falls back to fixtures.

GET /__admin_mock/help serves synthetic accounts and scenario instructions from mock source. POST /__admin_mock/scenario with a valid mock cookie accepts normal, empty, forbidden, unavailable, rate-limited, meta-unavailable or expired. Accounts/password are development demonstrations, not official template defaults or real credentials. The warning stays visible; M1 write/amount capabilities remain false.

This is local simulation, not backend security acceptance. UI follows existing ui-ux-pro-max/design-system tokens and narrow one-way interfaces. No mock accesses yt-dlp, a real backend, credentials, media, model or payment service.
