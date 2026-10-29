/* Admin M1 + support tickets real-browser integration: the built admin frontend against the real admin backend.
 * argv: origin evidenceDir email password playwrightModule chromiumPath viewerEmail viewerPassword reissueTicket
 * Only same-origin requests are allowed; no cookies, CSRF, passwords or bodies are recorded. */
const fs = require('node:fs');
const path = require('node:path');
const [origin, evidence, email, password, playwrightModule, executablePath, viewerEmail, viewerPassword, reissueTicket] = process.argv.slice(2);
const { chromium } = require(playwrightModule);
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, ok: Boolean(ok), detail: detail ?? null }); console.error('check', name, Boolean(ok)); };

async function context(browser, width, height) {
  const ctx = await browser.newContext({ viewport: { width, height }, serviceWorkers: 'block' });
  const trace = { responses: [], console: [], pageErrors: [], blocked: [] };
  await ctx.route('**/*', route => {
    const url = new URL(route.request().url());
    if (['data:', 'blob:'].includes(url.protocol) || url.origin === origin) return route.continue();
    trace.blocked.push(route.request().url());
    return route.abort('blockedbyclient');
  });
  const page = await ctx.newPage();
  page.setDefaultTimeout(20000);
  page.on('response', r => { if (r.url().includes('/api/admin/v1/')) trace.responses.push({ path: new URL(r.url()).pathname.replace('/api/admin/v1', ''), status: r.status() }); });
  page.on('console', m => { if (m.type() === 'error') trace.console.push(m.text()); else console.error('page', m.text()); });
  page.on('pageerror', e => trace.pageErrors.push(String(e)));
  return { ctx, page, trace };
}

async function waitApi(page, suffix, status = 200) {
  const response = await page.waitForResponse(r => new URL(r.url()).pathname === '/api/admin/v1' + suffix.split('?')[0]);
  return response.status() === status;
}

async function shot(page, name) { await page.screenshot({ path: path.join(evidence, name + '.png'), fullPage: true }); }

async function login(page, who = email, secret = password) {
  for (let i = 0; i < 60; i++) {  // the server may still be starting
    try { await page.goto(`${origin}/admin/#/login`); break; } catch { await page.waitForTimeout(1000); }
  }
  await page.getByLabel('邮箱', { exact: true }).fill(who);
  await page.getByLabel('密码', { exact: true }).fill(secret);
  const loggedIn = page.waitForResponse(r => r.url().endsWith('/api/admin/v1/auth/login'));
  await page.getByRole('button', { name: /登\s*录/, exact: true }).click();
  return (await loggedIn).status();
}

async function visit(page, hash, api, name) {
  const done = waitApi(page, api);
  await page.goto(`${origin}/admin/#${hash}`);
  check(`${name}: ${api} 200`, await done);
  await page.waitForLoadState('networkidle');
  await shot(page, name);
  return page.locator('body').innerText();
}

(async () => {
  fs.mkdirSync(evidence, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath });
  const traces = {};
  try {
    const desktop = await context(browser, 1440, 1000);
    const p = desktop.page;
    // A wrong password first: unified failure, no session.
    for (let i = 0; i < 60; i++) { try { await p.goto(`${origin}/admin/#/login`); break; } catch { await p.waitForTimeout(1000); } }
    await p.getByLabel('邮箱', { exact: true }).fill(email);
    await p.getByLabel('密码', { exact: true }).fill('definitely-wrong');
    const bad = p.waitForResponse(r => r.url().endsWith('/api/admin/v1/auth/login'));
    await p.getByRole('button', { name: /登\s*录/, exact: true }).click();
    check('wrong password → 401', (await bad).status() === 401);
    check('login → 200', (await login(p)) === 200);
    await p.waitForResponse(r => r.url().endsWith('/api/admin/v1/meta') && r.status() === 200);
    await shot(p, 'desktop-after-login');
    let text = await visit(p, '/overview', '/overview', 'desktop-overview');
    check('overview shows content', text.length > 50);
    await visit(p, '/users', '/users', 'desktop-users');
    text = await visit(p, '/users/syn-paid-unfulfilled', '/users/syn-paid-unfulfilled', 'desktop-user-detail');
    check('user detail shows the email', text.includes('paid-unfulfilled@example.invalid'));
    await visit(p, '/memberships', '/memberships', 'desktop-memberships');
    await visit(p, '/billing', '/billing/checkouts', 'desktop-billing');
    await visit(p, '/jobs', '/jobs', 'desktop-jobs');
    text = await visit(p, '/jobs/job-v2-failed', '/jobs/job-v2-failed', 'desktop-job-detail');
    check('job detail never shows raw error text', !text.includes('must never be shown'));
    await visit(p, '/audit', '/audit/logs', 'desktop-audit');
    await visit(p, '/system', '/system/status', 'desktop-system');
    // Support: priority tickets first; verify with the synthetic reader, then the reviewed re-issue.
    console.error('step support');
    await visit(p, '/support', '/support/tickets', 'desktop-support-list');
    const rows = await p.locator('.ant-table-tbody tr.ant-table-row').allInnerTexts();
    // Default view: open tickets only, priority first (the closed login ticket is filtered out).
    check('support list: open tickets, priority first', rows.length === 3 && rows[0].includes('优先') && rows[1].includes('优先') && rows[2].includes('普通') && !rows.some(r => r.includes('已解决')), rows);
    text = await visit(p, `/support/${reissueTicket}`, `/support/tickets/${reissueTicket}`, 'desktop-support-detail');
    check('support detail renders user note as text', text.includes('<b>synthetic note</b>'));
    const verified = p.waitForResponse(r => r.url().endsWith(`/support/tickets/${reissueTicket}/verify-payment`));
    await p.getByRole('button', { name: '向支付平台核实付款' }).click();
    check('verify payment → 200', (await verified).status() === 200);
    await p.getByText('在有效期内').waitFor();
    const reissued = p.waitForResponse(r => r.url().endsWith(`/support/tickets/${reissueTicket}/reissue`));
    await p.getByRole('button', { name: '审核通过并补发会员' }).click();
    await shot(p, 'desktop-support-confirm');
    await p.getByRole('dialog').getByRole('button', { name: '确认补发' }).click();
    const reissueResponse = await reissued;
    check('re-issue → 200 with idempotency key', reissueResponse.status() === 200 && Boolean(reissueResponse.request().headers()['idempotency-key']));
    await p.getByText('已为您补发 30 天会员，请刷新会员页查看').first().waitFor();
    await p.getByRole('dialog').waitFor({ state: 'hidden' });
    check('closed ticket offers no further actions', await p.getByRole('button', { name: '审核通过并补发会员' }).count() === 0);
    await p.waitForLoadState('networkidle');
    await shot(p, 'desktop-support-reissued');
    text = await p.locator('body').innerText();
    check('ticket resolved with the automatic reply', text.includes('已解决') && text.includes('已补发会员'));
    // Same-origin cookie + CSRF from the page itself (what the frontend does), and backend facts rules.
    console.error('step api-evaluate');
    const api = await p.evaluate(async (reissueTicket) => {
      const limit = () => AbortSignal.timeout(15000);
      const step = (name) => console.log('api ' + name);
      const get = async u => { step(u); const r = await fetch('/api/admin/v1' + u, { credentials: 'include', signal: limit() }); return [r.status, await r.json()]; };
      const [, me] = await get('/auth/me');
      const [, ambiguous] = await get('/billing/payments/pi_syn_ambiguous');
      const [, unfulfilled] = await get('/billing/checkouts?state=paid&fulfilled=false');
      const [, credited] = await get('/users/syn-paid-unfulfilled');
      step('second reissue');
      const again = await fetch('/api/admin/v1/support/tickets/' + reissueTicket + '/reissue', { method: 'POST', credentials: 'include',
        signal: limit(), headers: { 'X-CSRF-Token': me.csrf_token, 'Idempotency-Key': 'integration-second-reissue-key' } });
      const againBody = await again.json();
      step('patch');
      const patch = await fetch('/api/admin/v1/users/syn-free/access', { method: 'PATCH', credentials: 'include', signal: limit(),
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': me.csrf_token, 'Idempotency-Key': 'integration-k1' },
        body: JSON.stringify({ enabled: false, reason: 'integration check of the closed endpoint', expected_revision: '0' }) });
      step('logout');
      const logout = await fetch('/api/admin/v1/auth/logout', { method: 'POST', credentials: 'include', signal: limit(), headers: { 'X-CSRF-Token': me.csrf_token } });
      step('after');
      const after = await fetch('/api/admin/v1/auth/me', { credentials: 'include', signal: limit() });
      return { permissions: me.permissions, capabilities: me.capabilities, facts: ambiguous.facts_state, money: ambiguous.money,
               unfulfilled: unfulfilled.items.map(i => i.id), patch: patch.status, logout: logout.status, after: after.status,
               credited: credited.membership.effective, second: again.status, secondType: againBody.detail && againBody.detail.error_type };
    }, reissueTicket);
    check('M1 permissions are read-only', !api.permissions.includes('users:access:write') && api.permissions.includes('users:read'), api.permissions);
    check('capabilities closed', !api.capabilities.account_access_write.ready && !api.capabilities.billing_amounts.ready);
    check('ambiguous payment', api.facts === 'ambiguous' && api.money === null, api);
    // co-paid-unfulfilled was re-issued above, so only the legacy paid-but-unfulfilled checkout remains listed.
    check('paid but unfulfilled checkout listed (re-issued one now fulfilled)', api.unfulfilled.includes('co-legacy') && !api.unfulfilled.includes('co-paid-unfulfilled'), api.unfulfilled);
    check('closed M2 endpoint → 503', api.patch === 503);
    check('re-issued user now has an effective membership', api.credited === true, api);
    check('second re-issue of the same order refused', api.second === 409 && ['already_reissued', 'ticket_closed'].includes(api.secondType), api);
    check('admin holds support permissions incl. re-issue', ['support:read', 'support:write', 'support:reissue'].every(x => api.permissions.includes(x)), api.permissions);
    check('logout → 204 then session gone', api.logout === 204 && api.after === 401);
    // The API logout bypassed the frontend's in-memory session: a full reload makes it bootstrap again.
    const back = waitApi(p, '/auth/me', 401);
    await p.goto(`${origin}/admin/?after-logout=1#/users`);
    check('after logout protected page asks to log in', await back);
    await p.getByLabel('邮箱', { exact: true }).waitFor();
    await shot(p, 'desktop-after-logout');
    traces.desktop = desktop.trace;

    const mobile = await context(browser, 360, 800);
    check('mobile login → 200', (await login(mobile.page)) === 200);
    await mobile.page.waitForResponse(r => r.url().endsWith('/api/admin/v1/meta') && r.status() === 200);
    await visit(mobile.page, '/overview', '/overview', 'mobile-overview');
    await visit(mobile.page, '/users', '/users', 'mobile-users');
    const width = await mobile.page.evaluate(() => document.documentElement.scrollWidth);
    check('mobile has no horizontal page scroll', width <= 360, width);
    // ADMIN-UI-01: page titles must not be truncated by the subtitle at 360px.
    const titleFits = async () => mobile.page.evaluate(() => [...document.querySelectorAll('.ant-page-header-heading-title, .ant-page-header-heading-sub-title')]
      .map(el => ({ text: el.textContent, client: el.clientWidth, scroll: el.scrollWidth })));
    let titles = await titleFits();
    check('mobile users title and subtitle not truncated', titles.length >= 2 && titles.every(t => t.scroll <= t.client), titles);
    await visit(mobile.page, '/overview', '/overview', 'mobile-overview-title');
    titles = await titleFits();
    check('mobile overview title and subtitle not truncated', titles.length >= 2 && titles.every(t => t.scroll <= t.client), titles);
    await visit(mobile.page, '/support', '/support/tickets', 'mobile-support-list');
    await visit(mobile.page, `/support/${reissueTicket}`, `/support/tickets/${reissueTicket}`, 'mobile-support-detail');
    const supportWidth = await mobile.page.evaluate(() => document.documentElement.scrollWidth);
    check('mobile support detail has no horizontal page scroll', supportWidth <= 360, supportWidth);
    traces.mobile = mobile.trace;

    // A viewer reads tickets but gets no write controls (and the server refuses writes anyway).
    const viewer = await context(browser, 1440, 1000);
    check('viewer login → 200', (await login(viewer.page, viewerEmail, viewerPassword)) === 200);
    await viewer.page.waitForResponse(r => r.url().endsWith('/api/admin/v1/meta') && r.status() === 200);
    text = await visit(viewer.page, '/support/tk-vip-other', '/support/tickets/tk-vip-other', 'viewer-support-detail');
    check('viewer sees the ticket', text.includes('其他问题'));
    check('viewer has no write buttons', await viewer.page.getByRole('button', { name: /回复并结单|驳回并结单|审核通过并补发会员|向支付平台核实付款/ }).count() === 0);
    traces.viewer = viewer.trace;

    for (const [name, trace] of Object.entries(traces)) {
      const serverErrors = trace.responses.filter(r => r.status >= 500 && r.path !== '/users/syn-free/access');
      check(`${name}: no 5xx`, serverErrors.length === 0, serverErrors);
      check(`${name}: no page errors`, trace.pageErrors.length === 0, trace.pageErrors);
      const unexpected = trace.console.filter(t => !/401|403|503|Unauthorized|Failed to load resource/.test(t));
      check(`${name}: no unexpected console errors`, unexpected.length === 0, unexpected);
      check(`${name}: no external requests`, trace.blocked.length === 0, trace.blocked);
    }
  } catch (error) {
    console.error('script error', String(error && error.stack || error));
    check('script completed', false, String(error && error.stack || error));
  } finally {
    fs.writeFileSync(path.join(evidence, 'results.json'), JSON.stringify({ origin, checks, traces }, null, 2));
    await Promise.race([browser.close(), new Promise(resolve => setTimeout(resolve, 15000))]);
  }
  const failed = checks.filter(c => !c.ok);
  console.log(JSON.stringify({ total: checks.length, failed }));
  // Leftover waits (e.g. response listeners) must not keep the process alive after the verdict.
  process.exit(failed.length ? 1 : 0);
})();
