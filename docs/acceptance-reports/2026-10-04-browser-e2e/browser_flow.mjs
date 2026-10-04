/** Real browser actions and real app HTTP. No page.route(), API mocks or app-state injection. */
import { createRequire } from 'node:module';
import { existsSync, readdirSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash, randomBytes } from 'node:crypto';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../../..');
const args = process.argv.slice(2);
const option = (name, fallback) => { const i = args.indexOf(name); return i < 0 ? fallback : args[i + 1]; };
const base = option('--base-url', 'http://127.0.0.1:5185');
const videoURL = option('--video-url', 'http://127.0.0.1:8052/captioned.html');
const summaryOnly = args.includes('--summary-only');
const output = path.resolve(option('--output-dir', here));
const require = createRequire(import.meta.url);
let playwrightPath = process.env.PLAYWRIGHT_CORE_PATH;
if (!playwrightPath) {
  try { playwrightPath = require.resolve('playwright-core'); } catch {
    const npmCache = execFileSync('cmd.exe', ['/d', '/s', '/c', 'npm.cmd config get cache'], { encoding: 'utf8' }).trim();
    const directory = path.join(npmCache, '_npx');
    for (const item of existsSync(directory) ? readdirSync(directory) : []) {
      const candidate = path.join(directory, item, 'node_modules/playwright-core');
      if (existsSync(path.join(candidate, 'package.json'))) { playwrightPath = candidate; break; }
    }
  }
}
if (!playwrightPath) throw new Error('Set PLAYWRIGHT_CORE_PATH to an installed playwright-core package.');
const { chromium } = require(playwrightPath);
mkdirSync(output, { recursive: true });
const downloadsDir = path.join(root, '.planning/2026-10-04-platform-browser-summary/browser/saved');
mkdirSync(downloadsDir, { recursive: true });
const evidence = { generatedAt: new Date().toISOString(), base, videoURL, summaryOnly, browser: 'Microsoft Edge headless, WebGL disabled to exercise existing CSS fallback', appRoutesMocked: false, scopes: {}, checks: [], requests: [], errors: [] };
let browser;

function record(name, details = {}) { evidence.checks.push({ name, pass: true, ...details }); }
async function step(name, action) {
  try { await action(); console.log(`PASS ${name}`); } catch (err) {
    evidence.checks.push({ name, pass: false, error: String(err) });
    console.log(`FAIL ${name}: ${String(err).slice(0, 500)}`);
    throw err;
  }
}
async function checkpoint(page, viewport, scene) {
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
  const metrics = await page.evaluate(() => ({ width: innerWidth, documentWidth: document.documentElement.scrollWidth, bodyWidth: document.body.scrollWidth, cssFallback: Boolean(document.querySelector('.css-fallback')), overflowing: [...document.querySelectorAll('body *')].filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && (r.right > innerWidth + 1 || r.left < -1); }).slice(0, 10).map(el => ({ tag: el.tagName, class: el.className, width: el.getBoundingClientRect().width })) }));
  assert.equal(metrics.documentWidth <= metrics.width + 1, true, `Horizontal overflow: ${JSON.stringify(metrics)}`);
  assert.equal(metrics.cssFallback, true);
  record(`${viewport}: ${scene} fits viewport`, metrics);
  await page.screenshot({ path: path.join(output, `${viewport}-${scene}.png`), fullPage: scene !== 'entry' });
}
async function postControl(fail) {
  const r = await fetch('http://127.0.0.1:8053/fixture/control', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fail }) });
  assert.equal(r.status, 200);
}
async function parse(page, url) {
  await page.getByLabel('视频链接', { exact: true }).fill(url);
  const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/parse' && r.request().method() === 'POST');
  await page.getByRole('button', { name: '解析', exact: true }).click();
  const res = await response;
  assert.equal(res.status(), 200, `Parse ${url}: ${await res.text()}`);
  await page.getByTestId('selecting-scene').waitFor({ timeout: 120000 });
  const metadata = await res.json();
  const buttons = page.locator('.format-list button');
  assert.ok(await buttons.count() > 0);
  if (!summaryOnly) assert.equal(await buttons.count(), 2, 'Owned HLS master should expose720p and360p');
  await buttons.first().click();
  assert.equal(await buttons.first().getAttribute('aria-pressed'), 'true');
  return metadata;
}
async function insight(page, label, expectedStatus, testId) {
  const endpoint = label === '查看字幕' ? '/api/subtitle' : label === '翻译字幕' ? '/api/subtitle/translate' : '/api/summary';
  const result = page.waitForResponse(r => new URL(r.url()).pathname === endpoint && r.request().method() === 'POST', { timeout: 180000 });
  await page.getByRole('button', { name: label, exact: true }).click();
  const response = await result;
  assert.equal(response.status(), expectedStatus, `${endpoint}: ${await response.text()}`);
  if (testId) {
    const output = page.getByTestId(testId);
    await output.waitFor();
    assert.ok((await output.innerText()).length > 10);
  } else {
    await page.locator('.video-insights [role=alert]').waitFor();
    assert.equal(await page.getByTestId('selecting-scene').isVisible(), true);
    assert.equal(await page.getByRole('button', { name: '下载', exact: true }).isEnabled(), true);
  }
  return response.json();
}
async function serverDownload(page, viewport, label) {
  const selectedLabel = await page.locator('.format-list button[aria-pressed=true] .format-list__label').innerText();
  const expectedHeight = Number(selectedLabel.match(/(\d+)p/)?.[1]);
  await page.getByLabel('强制走服务器').check();
  const incoming = page.waitForEvent('download', { timeout: 120000 });
  const r = page.waitForResponse(response => new URL(response.url()).pathname === '/api/download' && response.request().method() === 'POST');
  await page.getByRole('button', { name: '下载', exact: true }).click();
  assert.equal((await r).status(), 200);
  const download = await incoming;
  assert.equal(await download.failure(), null);
  const save = path.join(downloadsDir, `${viewport}-${label}.mp4`);
  await download.saveAs(save);
  await page.getByTestId('done-scene').waitFor();
  const media = JSON.parse(execFileSync('ffprobe', ['-v', 'quiet', '-show_streams', '-show_format', '-of', 'json', save], { encoding: 'utf8' }));
  assert.ok(media.streams.some(s => s.codec_type === 'video' && s.codec_name === 'h264'));
  assert.ok(media.streams.some(s => s.codec_type === 'audio' && s.codec_name === 'aac'));
  assert.ok(Number(media.format.duration) >= 3);
  assert.equal(media.streams.find(s => s.codec_type === 'video').height, expectedHeight, 'Saved resolution must match the selected format');
  const sha256 = createHash('sha256').update(readFileSync(save)).digest('hex');
  record(`${viewport}: ${label} server download reaches browser file`, { selectedLabel, expectedHeight, fileAPI: new URL(download.url()).pathname, bytes: readFileSync(save).length, sha256, duration: media.format.duration, streams: media.streams.map(s => ({ type: s.codec_type, codec: s.codec_name, width: s.width, height: s.height })), suggestedFilename: download.suggestedFilename() });
  await checkpoint(page, viewport, `${label}-done`);
  await page.getByRole('button', { name: '继续下载', exact: true }).click();
  await page.getByTestId('entry-scene').waitFor();
}
async function runViewport(viewport) {
  const label = viewport.width === 375 ? 'mobile375' : 'desktop';
  const context = await browser.newContext({ viewport, acceptDownloads: true, reducedMotion: 'reduce' });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  page.on('pageerror', err => evidence.errors.push({ viewport: label, kind: 'pageerror', error: String(err) }));
  page.on('console', msg => { if (msg.type() === 'error' && !/status of (503|502|422|401)/.test(msg.text())) evidence.errors.push({ viewport: label, kind: 'console', error: msg.text().slice(0, 500) }); });
  page.on('response', response => { const u = new URL(response.url()); if (u.pathname.startsWith('/api/')) evidence.requests.push({ viewport: label, method: response.request().method(), path: u.pathname, status: response.status() }); });
  const email = `browser-${label}-${Date.now()}@example.com`;
  const password = `Owned-${randomBytes(10).toString('hex')}`;
  await step(`${label} register, logout, login and refresh`, async () => {
    await page.goto(base);
    await checkpoint(page, label, 'auth');
    await page.getByRole('button', { name: '注册', exact: true }).click();
    await page.getByLabel('邮箱', { exact: true }).fill(email);
    await page.getByLabel('密码', { exact: true }).fill(password);
    await page.getByRole('button', { name: '立即注册', exact: true }).click();
    await page.getByTestId('entry-scene').waitFor();
    await page.getByRole('button', { name: '退出', exact: true }).click();
    await page.getByTestId('auth-scene').waitFor();
    await page.getByLabel('邮箱', { exact: true }).fill(email);
    await page.getByLabel('密码', { exact: true }).fill(password);
    await page.getByRole('button', { name: '立即登录', exact: true }).click();
    await page.getByTestId('entry-scene').waitFor();
    await page.reload();
    await page.getByTestId('entry-scene').waitFor();
    await checkpoint(page, label, 'entry');
    record(`${label}: registration, login persistence and logout use real auth API`);
  });
  await step(`${label} parse and AI results`, async () => {
    const quotaBefore = await page.locator('.auth-bar__quota').innerText();
    const parsed = await parse(page, videoURL);
    record(`${label}: real yt-dlp parse and explicit format selection`, { parsed });
    await checkpoint(page, label, 'selecting');
    if (!summaryOnly) {
      const subtitle = await insight(page, '查看字幕', 200, 'subtitle-result');
      assert.ok(subtitle.text.includes('Recover after failures.'));
      const translation = await insight(page, '翻译字幕', 200, 'translation-result');
      assert.ok(translation.text.includes('失败后恢复'));
      record(`${label}: real subtitle HTTP parser and simulated upstream translation`);
    }
    const summary = await insight(page, '生成总结', 200, 'summary-result');
    assert.ok(summary.key_points.length > 0);
    record(`${label}: summary visible`, { summary });
    assert.equal(await page.locator('.auth-bar__quota').innerText(), quotaBefore);
    record(`${label}: AI requests do not consume download quota`);
    await checkpoint(page, label, 'summary');
  });
  if (!summaryOnly) {
    await step(`${label} captioned server download`, async () => serverDownload(page, label, 'captioned'));
    await step(`${label} no-caption error leaves download usable`, async () => {
      await parse(page, 'http://127.0.0.1:8052/no-captions.html');
      const lowerFormat = page.locator('.format-list button').last();
      await lowerFormat.click();
      assert.equal(await lowerFormat.getAttribute('aria-pressed'), 'true');
      assert.equal(await page.getByText('尚未检测到字幕。可以尝试读取内容；无可用字幕时会显示原因。').isVisible(), true);
      const data = await insight(page, '生成总结', 422);
      assert.equal(data.detail.error_type, 'subtitle_unavailable');
      record(`${label}: no-caption explicit summary attempt shows local error`, { errorType: data.detail.error_type });
      await checkpoint(page, label, 'no-caption');
      await serverDownload(page, label, 'no-caption');
    });
    await step(`${label} upstream AI outage leaves download usable`, async () => {
      await parse(page, videoURL);
      await postControl(true);
      try {
        const data = await insight(page, '生成总结', 502);
        assert.equal(data.detail.error_type, 'llm_error');
        record(`${label}: simulated upstream503 produces local AI error`, { errorType: data.detail.error_type });
        await checkpoint(page, label, 'ai-error');
        await serverDownload(page, label, 'ai-error');
      } finally { await postControl(false); }
    });
  }
  await page.getByRole('button', { name: '退出', exact: true }).click();
  await page.getByTestId('auth-scene').waitFor();
  await page.reload();
  await page.getByTestId('auth-scene').waitFor();
  record(`${label}: final logout persists after reload`);
  await context.close();
}
try {
  browser = await chromium.launch({ executablePath: option('--browser-executable', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'), headless: true, args: ['--disable-webgl', '--disable-gpu', '--no-first-run'] });
  evidence.scopes = { real: summaryOnly ? ['registration/login/JWT/auth restoration', 'Vite and application UI', 'FastAPI parse/summary and actual configured upstream', 'supplied video URL metadata and subtitle retrieval'] : ['registration/login/JWT/auth restoration', 'Vite and application UI', 'FastAPI parse/subtitle/translate/summary/download/job/file APIs', 'yt-dlp reads local HTTP HTML video, two-variant HLS and track', 'real HTTP VTT text parse', 'yt-dlp downloads H264/AAC generated owned media', 'browser file and ffprobe verification'], simulated: summaryOnly ? [] : ['LLM HTTP upstream deterministic completion and controlled503'], limitation: 'Local media is not evidence of public-platform compatibility. WebGL/Live2D model rendering is not exercised.' };
  const viewportChoice = option('--viewport', 'both');
  if (viewportChoice !== 'mobile') await runViewport({ width: 1440, height: 900 });
  if (viewportChoice !== 'desktop') await runViewport({ width: 375, height: 812 });
  assert.equal(evidence.errors.length, 0, JSON.stringify(evidence.errors));
  evidence.pass = true;
} catch (err) {
  evidence.pass = false;
  evidence.failure = String(err);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  writeFileSync(path.join(output, 'results.json'), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify({ pass: evidence.pass, checks: evidence.checks.length, errors: evidence.errors.length, results: path.join(output, 'results.json') }));
}
