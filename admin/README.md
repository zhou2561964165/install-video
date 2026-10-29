# Independent management frontend


Derived from official Ant Design Pro **6.0.3**, commit `42f2cb1d303380909ea04c73b5e60679d09c321a`; provenance and preserved MIT license are in `upstream/` and `LICENSE`. This package reuses Umi Max layout/router/request/access/initialState, LoginForm, ProTable, ProDescriptions and Drawer. Ordinary frontend and backend remain separate packages.

The candidate targets local contract `1.0.0-proposal.20261028.3`, YAML SHA256 `5af2352ab3e5100f2bbd3044fa3e6d01c2e3beddb098b24e989905e8bae5a7e8`. **Mock success does not establish backend readiness, migrations, production authentication or deployment.** M1 is read only; account writes require a separate server feature plus permission.

Use Node >=22, independently in this directory:

```text
npm ci --ignore-scripts
npm run setup
npm run test:core
node tools/codegen/generate.mjs --check
node tools/codegen/check-mock-discovery.cjs
npm run tsc
npm run build
node tools/codegen/check-production.mjs
```

The type generator has an independent lock in `tools/codegen/`; run `npm ci --ignore-scripts` there if needed. `npm run codegen` regenerates checked-in wire types and 17 operation descriptors from the frozen local YAML. It refuses a changed contract hash and makes no remote request.

The mock-discovery check runs the installed Umi loader against the actual development configuration, without starting a server. Umi always scans its default mock glob; helper modules are explicitly excluded, and only mock/admin.ts is registered. The official Ant ConfigProvider is explicitly enabled so runtime theme tokens apply.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| ADMIN_ROUTE_BASE | / | Umi hash routing base; fragment routes remain /users. |
| ADMIN_PUBLIC_PATH | /admin/ | Static asset prefix. |
| ADMIN_API_BASE | /api/admin/v1 | Absolute same-origin management API prefix. |
| ADMIN_DEV_PROXY_TARGET | absent | Explicit optional development HTTP(S) origin; no implicit rewrite. |
| ADMIN_MOCK | false | Only literal true plus development enables mocks; production always disables them. |

For `/demo/admin/#/users`, set `ADMIN_PUBLIC_PATH=/demo/admin/` and `ADMIN_API_BASE=/demo/api/admin/v1`; hash stays `/users`. External origins, encoded/traversal paths and query-bearing prefixes are rejected. Cookie Path and allowed Origin are configured by the backend owner during authorized integration. No credentials belong in these settings.

## Authentication and data

Requests use withCredentials and the backend's HttpOnly cookie. No Bearer, localStorage credentials or persisted CSRF is used. Validated auth/me and real meta publish atomically into memory and official initialState. Metadata failures stay errors; no fabricated readiness or mock fallback occurs.

Every 401 clears permissions/meta/CSRF and redirects protected routes to a safe local login return path. Server expiration clears the session. Session versions reject late reads, bootstrap and 401s from replaced sessions. Errors retain safe local messages/request IDs, without raw backend payloads. Unconfirmed logout explicitly reports unknown server revocation.

Menus use permission strings; roles are display data. Optional account writes and amount displays require permission plus a known ready feature. The write adapter sends the caller's stable idempotency key and memory CSRF once, without retry. Network/5xx write outcomes are unknown and require manual checking.

Queries intersect contract schemas and server meta. Pagination follows the runtime ceiling (protocol maximum 1000). UTC/nulls remain explicit; decimal money/revisions/bytes remain strings. Unknown exponent stays unknown, negative quota shows excess and UTC day, future states remain neutral.

## Explicit development mock

`npm run dev` starts isolated port 4174 with mock disabled. `npm run dev:mock` explicitly starts its independent synthetic backend on 4174. Run service commands only in the task's authorized scope. The core implementation did not start either service.

A persistent warning identifies mock mode on every route. Login links to **GET /__admin_mock/help**, which serves the synthetic operator/viewer/limited accounts and demonstration password from mock source. These are distinct from official template defaults and real accounts. Operator has a write permission for guard demonstrations while M1 capability stays false; limited lacks jobs/billing/audit/system permissions.

Mock issues its separate HttpOnly admin_demo_session cookie, absolute 900-second expiry and memory CSRF. Logout validates CSRF and revokes it. All lists/details are synthetic, including future states, null history, huge decimals, negative quota, ambiguous facts and unknown worker samples. No real backend/DB, media, model or payment service is called.

With a valid mock cookie, POST /__admin_mock/scenario accepts {"scenario":"normal"}. Supported: normal, empty, forbidden, unavailable, rate-limited, meta-unavailable, expired. Restore normal with that endpoint, except expired revokes the session and requires login. Controls are development only and absent from production artifacts.

Fixture IDs: usr_demo_01–usr_demo_27, job_demo_1–job_demo_23, checkout_demo_1–checkout_demo_15, pi_demo_1–pi_demo_13. Lists implement filters, stable pagination (primary order plus ID ascending ties, NULLS LAST), runtime page caps/422, permission failures/403 and missing detail/404. Errors never become synthetic success.

Production script and configuration both disable mocks. Production excludes help/scenario controls, fixtures/accounts and warning, with no default proxy. check-production.mjs checks the artifact. Browser QA and real backend integration have separate evidence; unit tests/build imply neither.

UI follows existing ui-ux-pro-max/design-system decisions and primitive → semantic → component tokens. Narrow interfaces and one-way dependencies remain; only backend ytdlp_service.py accesses yt-dlp. Management displays import neither download core nor existing frontend/backend internals.
