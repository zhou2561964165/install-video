// Owned headless browser only. No headers/storage dumps or real model calls.
const fs = require('node:fs');
const path = require('node:path');
function atomicJson(target, value) {
  const temporary = target + '.owned-tmp';
  fs.writeFileSync(temporary, JSON.stringify(value));
  fs.renameSync(temporary, target);
}

async function main() {
  const [readyPath, packagePath, executablePath] = process.argv.slice(2);
  const ready = JSON.parse(fs.readFileSync(readyPath, 'utf8'));
  const { chromium } = require(packagePath);
  const evidence = { real_vendor_posts: 0, model_quality_verified: false,
    password_login_tested: false, cases: [], page_error_count: 0, responses: [] };
  let browser;
  try {
    browser = await chromium.launch({ headless: true, executablePath });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    // Block unrelated origins in this owned browser context, including CDN assets.
    const allowed = new Set([new URL(ready.frontend).origin, new URL(ready.source).origin]);
    let externalBlocked = 0;
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      if (['data:', 'blob:'].includes(url.protocol) || allowed.has(url.origin)) return route.continue();
      externalBlocked += 1;
      return route.abort();
    });
    const page = await context.newPage();
    page.on('pageerror', () => { evidence.page_error_count += 1; });
    page.on('response', response => {
      const pathname = new URL(response.url()).pathname;
      if (['/api/parse', '/api/subtitle', '/api/summary'].includes(pathname)) {
        evidence.responses.push({ path: pathname, status: response.status() });
      }
    });
    await page.goto(ready.frontend + ready.session_path, { waitUntil: 'networkidle' });
    await page.getByRole('textbox', { name: '视频链接', exact: true }).waitFor();
    // Inspect rendered controls first; save only labels and roles, never storage.
    evidence.entry_controls = await page.locator('input[aria-label],button').evaluateAll(
      nodes => nodes.map(el => el.getAttribute('aria-label') || el.textContent.trim()).filter(Boolean));
    await page.getByRole('textbox', { name: '视频链接', exact: true }).fill(ready.source + '/en-medium.html');
    await page.getByRole('button', { name: '解析', exact: true }).click();
    await page.getByRole('button', { name: '生成总结', exact: true }).waitFor({ timeout: 45000 });
    evidence.cases.push({ case: 'medium_parse_controls', passed: true });
    await page.getByRole('button', { name: '查看字幕', exact: true }).click();
    await page.getByTestId('subtitle-result').waitFor({ timeout: 45000 });
    const source = fs.readFileSync(path.join(__dirname, '../../2026-10-04-natural-subtitle-quality/corpus/en-medium.txt'), 'utf8');
    const subtitle = await page.getByTestId('subtitle-result').locator('pre').innerText();
    evidence.cases.push({ case: 'medium_original_subtitle_render', passed: subtitle === source });
    await page.getByRole('button', { name: '生成总结', exact: true }).click();
    await page.getByTestId('summary-result').waitFor({ timeout: 45000 });
    const summary = await page.getByTestId('summary-result').locator('p').innerText();
    const points = await page.getByTestId('summary-result').locator('li').count();
    evidence.cases.push({ case: 'summary_fixture_render', passed:
      summary.includes('Controlled HTTP serialization fixture') && points === 1 });
    await page.screenshot({ path: path.join(ready.work, 'browser-summary.png'), fullPage: false });
    // Controlled local upstream fault; real app mapping and alert are exercised.
    atomicJson(ready.control, { mode: 'http_503' });
    await page.waitForTimeout(300);
    await page.getByRole('button', { name: '生成总结', exact: true }).click();
    await page.locator('.video-insights__status [role="alert"]').waitFor({ timeout: 45000 });
    const errorText = await page.locator('.video-insights__status [role="alert"]').innerText();
    evidence.cases.push({ case: 'upstream_error_alert_and_reenabled_action', passed:
      Boolean(errorText.trim()) && await page.getByRole('button', { name: '生成总结', exact: true }).isEnabled() });
    evidence.failed_summary_stale_result_visible = await page.getByTestId('summary-result').isVisible();
    await page.screenshot({ path: path.join(ready.work, 'browser-upstream-error.png'), fullPage: false });
    evidence.external_requests_blocked = externalBlocked;
    evidence.passed = evidence.cases.every(item => item.passed) && evidence.page_error_count === 0;
    await context.close();
  } catch (error) {
    evidence.passed = false;
    evidence.error_class = error.name;
    // Avoid arbitrary error text which can contain request credentials.
  } finally {
    if (browser) await browser.close();
    fs.writeFileSync(path.join(ready.work, 'browser-evidence.json'), JSON.stringify(evidence, null, 2));
    atomicJson(ready.control, { stop: true, mode: 'healthy', evidence });
  }
  console.log(JSON.stringify(evidence));
  if (!evidence.passed) process.exitCode = 1;
}
main().catch(error => { console.error(error.name); process.exitCode = 1; });
