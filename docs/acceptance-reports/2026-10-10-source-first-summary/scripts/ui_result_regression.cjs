// Real owned browser regression for clearing a previous summary after failure.
const fs = require('node:fs');
const path = require('node:path');
function control(target, value) {
  const tmp = target + '.regression-tmp';
  fs.writeFileSync(tmp, JSON.stringify(value));
  fs.renameSync(tmp, target);
}
async function main() {
  const [readyPath, packagePath, executablePath] = process.argv.slice(2);
  const ready = JSON.parse(fs.readFileSync(readyPath, 'utf8'));
  const { chromium } = require(packagePath);
  const evidence = { real_vendor_posts: 0, model_semantics_tested: false, page_errors: 0, responses: [] };
  let browser;
  try {
    browser = await chromium.launch({ headless: true, executablePath });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const allowed = new Set([new URL(ready.frontend).origin, new URL(ready.source).origin]);
    await context.route('**/*', route => {
      const u = new URL(route.request().url());
      return allowed.has(u.origin) || ['data:', 'blob:'].includes(u.protocol) ? route.continue() : route.abort();
    });
    const page = await context.newPage();
    page.on('pageerror', () => evidence.page_errors++);
    page.on('response', response => {
      const p = new URL(response.url()).pathname;
      if (['/api/parse', '/api/summary'].includes(p)) evidence.responses.push({ path: p, status: response.status() });
    });
    await page.goto(ready.frontend + ready.session_path, { waitUntil: 'networkidle' });
    await page.getByRole('textbox', { name: '视频链接', exact: true }).fill(ready.source + '/en-medium.html');
    await page.getByRole('button', { name: '解析', exact: true }).click();
    const generate = page.getByRole('button', { name: '生成总结', exact: true });
    await generate.waitFor({ timeout: 45000 });
    await generate.click();
    await page.getByTestId('summary-result').waitFor({ timeout: 45000 });
    evidence.success_visible = await page.getByTestId('summary-result').isVisible();
    control(ready.control, { mode: 'http_503' });
    await page.waitForTimeout(300);
    await generate.click();
    await page.locator('.video-insights__status [role="alert"]').waitFor({ timeout: 45000 });
    evidence.previous_summary_hidden_after_failure = await page.getByTestId('summary-result').count() === 0;
    evidence.error_visible = Boolean(await page.locator('.video-insights__status [role="alert"]').innerText());
    evidence.action_reenabled = await generate.isEnabled();
    await page.screenshot({ path: path.join(ready.work, 'summary-after-failure.png') });
    evidence.passed = evidence.success_visible && evidence.previous_summary_hidden_after_failure &&
      evidence.error_visible && evidence.action_reenabled && evidence.page_errors === 0;
    await context.close();
  } catch (error) {
    evidence.passed = false;
    evidence.error_class = error.name;
  } finally {
    if (browser) await browser.close();
    fs.writeFileSync(path.join(ready.work, 'ui-regression.json'), JSON.stringify(evidence, null, 2));
    control(ready.control, { mode: 'healthy', stop: true, evidence });
  }
  console.log(JSON.stringify(evidence));
  if (!evidence.passed) process.exitCode = 1;
}
main().catch(error => { console.error(error.name); process.exitCode = 1; });
