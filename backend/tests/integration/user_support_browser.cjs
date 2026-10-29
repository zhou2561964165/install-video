/* Support tickets user side: the built user frontend against the real business app on one origin.
 * argv: origin evidenceDir email password playwrightModule chromiumPath
 * Only same-origin requests are allowed; no tokens, passwords or bodies are recorded. */
const fs = require('node:fs');
const path = require('node:path');
const [origin, evidence, email, password, playwrightModule, executablePath] = process.argv.slice(2);
const { chromium } = require(playwrightModule);
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, ok: Boolean(ok), detail: detail ?? null }); console.error('check', name, Boolean(ok)); };
const NOTE = '<script>window.__pwned=1</script>扣款了但会员没到账';

async function context(browser, width, height) {
  const ctx = await browser.newContext({ viewport: { width, height }, serviceWorkers: 'block' });
  const trace = { responses: [], pageErrors: [], blocked: [] };
  await ctx.route('**/*', route => {
    const url = new URL(route.request().url());
    if (['data:', 'blob:'].includes(url.protocol) || url.origin === origin) return route.continue();
    trace.blocked.push(url.origin);
    return route.abort('blockedbyclient');
  });
  const page = await ctx.newPage();
  page.setDefaultTimeout(30000);
  page.on('response', r => { const p = new URL(r.url()).pathname; if (p.startsWith('/api/')) trace.responses.push({ path: p, status: r.status() }); });
  page.on('pageerror', e => trace.pageErrors.push(String(e)));
  return { ctx, page, trace };
}
async function shot(page, name) { await page.screenshot({ path: path.join(evidence, name + '.png'), fullPage: true }); }
async function open(page) {
  for (let i = 0; i < 60; i++) { try { await page.goto(origin + '/'); return; } catch { await page.waitForTimeout(1000); } }
}
async function toSupport(page) {
  await page.getByRole('button', { name: '会员方案' }).click();
  await page.getByRole('button', { name: '联系客服' }).click();
}

(async () => {
  fs.mkdirSync(evidence, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath });
  const traces = {};
  try {
    // Guest: support asks to log in and sends no support request.
    const guest = await context(browser, 1440, 1000);
    await open(guest.page);
    await toSupport(guest.page);
    await guest.page.getByRole('button', { name: '登录后联系客服' }).waitFor();
    await shot(guest.page, 'guest-support');
    check('guest sees login prompt without support requests', !guest.trace.responses.some(r => r.path.startsWith('/api/support')));
    // F-UI-01: register validates locally; an invalid form sends no request.
    await guest.page.getByRole('button', { name: '返回会员方案' }).click();
    await guest.page.getByRole('button', { name: '登录', exact: true }).first().click();
    await guest.page.getByRole('button', { name: '注册', exact: true }).click();
    await guest.page.getByLabel('邮箱', { exact: true }).fill('invalid-email');
    await guest.page.getByLabel('密码', { exact: true }).fill('1');
    await guest.page.getByRole('button', { name: '立即注册' }).click();
    await guest.page.getByText('密码至少 8 位').waitFor();
    check('register: invalid email/password shown inline, no request sent',
      await guest.page.getByText('请输入有效的邮箱地址，例如 you@example.com').isVisible()
      && !guest.trace.responses.some(r => r.path === '/api/auth/register'));
    await shot(guest.page, 'guest-register-invalid');
    traces.guest = guest.trace;

    // F-UI-02: a parse result without formats explains why and offers a re-parse (parse response synthetic).
    const empty = await context(browser, 1440, 1000);
    let parses = 0;
    await empty.page.route('**/api/parse', route => { parses += 1; return route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ title: '合成直播回放', platform: 'synthetic', formats: [], subtitles: [] }) }); });
    await open(empty.page);
    await empty.page.getByRole('button', { name: '登录', exact: true }).first().click();
    await empty.page.getByLabel('邮箱', { exact: true }).fill(email);
    await empty.page.getByLabel('密码', { exact: true }).fill(password);
    await empty.page.getByRole('button', { name: '立即登录' }).click();
    await empty.page.getByRole('textbox', { name: '视频链接' }).fill('https://video.example.invalid/watch?v=empty');
    await empty.page.getByRole('button', { name: '解析', exact: true }).click();
    await empty.page.getByText('没有找到可下载的格式').waitFor();
    check('no formats: reason shown and download disabled', await empty.page.getByRole('button', { name: '下载', exact: true }).isDisabled());
    await shot(empty.page, 'desktop-empty-formats');
    await empty.page.getByRole('button', { name: '重新解析' }).click();
    await empty.page.waitForTimeout(500);
    check('no formats: 重新解析 parses the same link again', parses === 2, parses);
    traces.empty = empty.trace;

    for (const [label, width, height] of [['desktop', 1440, 1000], ['mobile', 360, 800]]) {
      const { page, trace } = await context(browser, width, height);
      await open(page);
      await page.getByRole('button', { name: '登录', exact: true }).first().click();
      await page.getByLabel('邮箱', { exact: true }).fill(email);
      await page.getByLabel('密码', { exact: true }).fill(password);
      const loggedIn = page.waitForResponse(r => new URL(r.url()).pathname === '/api/auth/login');
      await page.getByRole('button', { name: '立即登录' }).click();
      check(`${label}: login → 200`, (await loggedIn).status() === 200);
      const meta = page.waitForResponse(r => new URL(r.url()).pathname === '/api/support/meta');
      await toSupport(page);
      check(`${label}: support meta → 200`, (await meta).status() === 200);
      await page.getByRole('radio', { name: '会员付款后未到账' }).check();
      const submit = page.getByRole('button', { name: '提交问题' });
      check(`${label}: order required before submit`, await submit.isDisabled());
      if (label === 'desktop') {
        await page.getByRole('radio', { name: /订单 appeal01/ }).check();
        await page.getByLabel('补充说明（可选）').fill(NOTE);
        await shot(page, `${label}-support-form`);
        const posted = page.waitForResponse(r => new URL(r.url()).pathname === '/api/support/tickets' && r.request().method() === 'POST');
        await submit.click();
        check(`${label}: submit → 200`, (await posted).status() === 200);
        await page.getByRole('tab', { name: '我的工单', selected: true }).waitFor();
        await page.getByText('处理中').first().waitFor();
        const text = await page.locator('main').innerText();
        check(`${label}: my tickets shows the open ticket and the note as text`, text.includes('会员付款后未到账') && text.includes('<script>window.__pwned=1</script>'));
        check(`${label}: note did not execute`, await page.evaluate(() => window.__pwned === undefined));
        await shot(page, `${label}-support-tickets`);
        // The same order cannot be appealed twice while open.
        await page.getByRole('tab', { name: '提交问题' }).click();
        await page.getByRole('radio', { name: '会员付款后未到账' }).check();
        const reopened = await page.getByRole('radio', { name: /订单 appeal01/ }).count();
        if (reopened) {
          await page.getByRole('radio', { name: /订单 appeal01/ }).check();
          const again = page.waitForResponse(r => new URL(r.url()).pathname === '/api/support/tickets' && r.request().method() === 'POST');
          await page.getByRole('button', { name: '提交问题' }).click();
          check(`${label}: duplicate appeal refused with a readable error`, (await again).status() === 422 && await page.getByRole('alert').innerText().then(t => t.includes('已有处理中的工单')));
        } else check(`${label}: duplicate appeal refused with a readable error`, true, 'order no longer offered');
      } else {
        await page.getByRole('tab', { name: '我的工单' }).click();
        await page.getByText('处理中').first().waitFor();
        await shot(page, `${label}-support-tickets`);
        const width = await page.evaluate(() => document.documentElement.scrollWidth);
        check(`${label}: no horizontal page scroll`, width <= 360, width);
      }
      traces[label] = trace;
    }
    for (const [name, trace] of Object.entries(traces)) {
      const serverErrors = trace.responses.filter(r => r.status >= 500);
      check(`${name}: no 5xx`, serverErrors.length === 0, serverErrors);
      check(`${name}: no page errors`, trace.pageErrors.length === 0, trace.pageErrors);
      check(`${name}: no external requests`, trace.blocked.length === 0, [...new Set(trace.blocked)]);
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
  process.exit(failed.length ? 1 : 0);
})();
