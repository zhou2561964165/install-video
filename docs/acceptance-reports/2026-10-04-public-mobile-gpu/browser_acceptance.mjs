/** Actual UI/HTTP/file evidence. No route mocks, app state writes or paid LLM calls. */
import { createRequire } from 'node:module';
import { existsSync, readdirSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { createHash, randomBytes } from 'node:crypto';
import assert from 'node:assert/strict';
import { parseArgs } from 'node:util';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../../..');
const { values: options } = parseArgs({ options: { 'output-dir': { type: 'string' }, 'check-output-dir': { type: 'boolean', default: false } } });
const output = path.resolve(options['output-dir'] || path.join(root, '.planning/2026-10-04-public-mobile-gpu', `${Date.now()}-${randomBytes(3).toString('hex')}`, 'evidence'));
if (existsSync(output) && readdirSync(output).length) throw new Error('--output-dir must be new or empty; existing evidence will not be overwritten');
if (options['check-output-dir']) {
  console.log(JSON.stringify({ output_dir: output, valid: true, offline: true }));
  process.exit(0);
}
mkdirSync(output, { recursive: true });
const require = createRequire(import.meta.url);
let installed = process.env.PLAYWRIGHT_CORE_PATH;
if (!installed) {
  try { installed = require.resolve('playwright-core'); } catch {
    const cache = execFileSync('cmd.exe', ['/d', '/s', '/c', 'npm.cmd config get cache'], { encoding: 'utf8' }).trim();
    for (const item of readdirSync(path.join(cache, '_npx'))) {
      const candidate = path.join(cache, '_npx', item, 'node_modules/playwright-core');
      if (existsSync(path.join(candidate, 'package.json'))) { installed = candidate; break; }
    }
  }
}
if (!installed) throw new Error('Set PLAYWRIGHT_CORE_PATH to an existing playwright-core package');
const { chromium } = require(installed);
const savedDir = path.join(root, '.planning/2026-10-04-public-mobile-gpu', `${Date.now()}-${randomBytes(3).toString('hex')}`, 'saved');
mkdirSync(savedDir, { recursive: true });
const evidence = { generatedAt: new Date().toISOString(), publicSource: 'https://archive.org/details/youtube-6k-kbg3_Drc', license: 'CC BY 3.0', appRoutesMocked: false, llmCalls: 0, checks: [], requests: [], errors: [], gpu: [] };
const record = (name, detail = {}) => evidence.checks.push({ name, pass: true, ...detail });
let browser;
function observe(page, scope) {
  page.on('pageerror', error => evidence.errors.push({ scope, kind: 'pageerror', error: String(error) }));
  page.on('console', msg => { if (['error', 'warning'].includes(msg.type())) evidence.errors.push({ scope, kind: msg.type(), error: msg.text().slice(0, 1000) }); });
  page.on('response', response => { const u = new URL(response.url()); if (u.pathname.startsWith('/api/') || u.pathname.startsWith('/live2d/')) evidence.requests.push({ scope, method: response.request().method(), path: u.pathname, status: response.status() }); });
}
async function register(page) {
  await page.goto('http://127.0.0.1:5187', { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.getByTestId('auth-scene').waitFor();
  await page.getByRole('button', { name: '注册', exact: true }).click();
  await page.getByLabel('邮箱', { exact: true }).fill(`acceptance-${Date.now()}-${randomBytes(3).toString('hex')}@example.com`);
  await page.getByLabel('密码', { exact: true }).fill(`Owned-${randomBytes(12).toString('hex')}`);
  await page.getByRole('button', { name: '立即注册', exact: true }).click();
  await page.getByTestId('entry-scene').waitFor();
}
async function layout(page, name) {
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
  const metrics = await page.evaluate(() => ({ width: innerWidth, documentWidth: document.documentElement.scrollWidth, cssFallback: Boolean(document.querySelector('.css-fallback')) }));
  assert.ok(metrics.documentWidth <= metrics.width + 1, JSON.stringify(metrics));
  record(`${name} layout fits375px`, metrics);
  await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
}
async function publicMobile() {
  browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true, args: ['--disable-webgl', '--disable-gpu', '--no-first-run'] });
  const context = await browser.newContext({ viewport: { width: 375, height: 812 }, acceptDownloads: true, reducedMotion: 'reduce', isMobile: true, hasTouch: true });
  const page = await context.newPage(); page.setDefaultTimeout(30000); observe(page, 'public-mobile375');
  await register(page); record('real registration at375px'); await layout(page, 'mobile-entry');
  await page.getByLabel('视频链接', { exact: true }).fill(evidence.publicSource);
  const incomingParse = page.waitForResponse(r => new URL(r.url()).pathname === '/api/parse' && r.request().method() === 'POST', { timeout: 150000 });
  await page.getByRole('button', { name: '解析', exact: true }).click();
  const parsed = await incomingParse; assert.equal(parsed.status(), 200, await parsed.text());
  const metadata = await parsed.json(); record('public Archive real parse200', { metadata });
  await page.getByTestId('selecting-scene').waitFor();
  const buttons = page.locator('.format-list button'); assert.ok(await buttons.count());
  // Lowest listed video keeps the acceptance download bounded and explicitly selected.
  await buttons.last().click();
  const selectedLabel = await page.locator('.format-list button[aria-pressed=true] .format-list__label').innerText();
  const expectedHeight = Number(selectedLabel.match(/(\d+)p/)?.[1]) || null;
  record('available public format selected explicitly', { selectedLabel, expectedHeight, resolutionKnownBeforeDownload: Boolean(expectedHeight) });
  await page.getByLabel('强制走服务器').check(); await layout(page, 'mobile-selecting');
  const incomingFile = page.waitForEvent('download', { timeout: 240000 });
  const incomingJob = page.waitForResponse(r => new URL(r.url()).pathname === '/api/download' && r.request().method() === 'POST');
  await page.getByRole('button', { name: '下载', exact: true }).click();
  const submitted = await incomingJob; assert.equal(submitted.status(), 200, await submitted.text());
  record('public download submission200', { job: await submitted.json() });
  const file = await incomingFile; assert.equal(await file.failure(), null);
  const saved = path.join(savedDir, `archive-mobile375${path.extname(file.suggestedFilename()) || '.bin'}`); await file.saveAs(saved);
  await page.getByTestId('done-scene').waitFor();
  const media = JSON.parse(execFileSync('ffprobe', ['-v', 'quiet', '-show_streams', '-show_format', '-of', 'json', saved], { encoding: 'utf8' }));
  const video = media.streams.find(s => s.codec_type === 'video');
  assert.ok(video.height > 0);
  if (expectedHeight) assert.equal(video.height, expectedHeight);
  assert.ok(Math.abs(Number(media.format.duration) - metadata.duration) < 2, 'Complete saved duration must match public source');
  assert.ok(media.streams.some(s => s.codec_type === 'audio'));
  const bytes = readFileSync(saved); assert.ok(bytes.length > 1000);
  record('public server download reaches actual browser saved file', { selectedLabel, expectedHeight, fileAPI: new URL(file.url()).pathname, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex'), duration: media.format.duration, container: media.format.format_name, streams: media.streams.map(s => ({ type: s.codec_type, codec: s.codec_name, width: s.width, height: s.height })), suggestedFilename: file.suggestedFilename() });
  await layout(page, 'mobile-done');
  assert.equal(evidence.requests.filter(r => ['/api/summary', '/api/subtitle/translate'].includes(r.path)).length, 0);
  record('no AI API called in download acceptance');
  await context.close(); await browser.close(); browser = null;
}
async function gpuProbe(label, args, viewport) {
  browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true, args: ['--no-first-run', ...args] });
  const context = await browser.newContext({ viewport, reducedMotion: 'reduce' });
  const page = await context.newPage(); page.setDefaultTimeout(30000); observe(page, label);
  const session = await context.newCDPSession(page); let systemInfo;
  try { const cdp = await browser.newBrowserCDPSession(); systemInfo = await cdp.send('SystemInfo.getInfo'); await cdp.detach(); } catch (e) { systemInfo = { error: String(e) }; }
  await register(page);
  const started = Date.now();
  // Existing preloader visibility is observed, never forcibly hidden or altered.
  try { await page.locator('.preloader').waitFor({ state: 'hidden', timeout: 90000 }); } catch {}
  await page.waitForTimeout(3000);
  const state = await page.evaluate(() => {
    const canvas = document.querySelector('.stage canvas');
    const gl = canvas?.getContext('webgl2') || canvas?.getContext('webgl') || canvas?.getContext('experimental-webgl');
    const debug = gl?.getExtension('WEBGL_debug_renderer_info');
    const textures = window.PIXI ? Object.entries(window.PIXI.utils.BaseTextureCache).filter(([key]) => /texture_00/.test(key)).map(([key, base]) => ({ key, valid: base.valid, width: base.width, height: base.height, residentContexts: Object.keys(base._glTextures || {}) })) : [];
    return { cssFallback: Boolean(document.querySelector('.css-fallback')), canvas: canvas ? { width: canvas.width, height: canvas.height } : null, preloaderVisible: Boolean(document.querySelector('.preloader')), renderer: gl && debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : null, vendor: gl && debug ? gl.getParameter(debug.UNMASKED_VENDOR_WEBGL) : null, maxTextureSize: gl?.getParameter(gl.MAX_TEXTURE_SIZE) || null, textures, live2dCore: Boolean(window.Live2DCubismCore), hardwareConcurrency: navigator.hardwareConcurrency, deviceMemory: navigator.deviceMemory, userAgent: navigator.userAgent };
  });
  const capture = { label, args, viewport, waitedMilliseconds: Date.now() - started, ...state, gpuDevices: systemInfo.gpu?.devices || [], gpuFeatureStatus: systemInfo.gpu?.featureStatus || {}, visualReviewRequired: true };
  evidence.gpu.push(capture);
  await page.screenshot({ path: path.join(output, `${label}.png`), fullPage: false });
  await session.detach(); await context.close(); await browser.close(); browser = null;
  console.log(`GPU ${label}: ${JSON.stringify({ renderer: state.renderer, maxTextureSize: state.maxTextureSize, preloaderVisible: state.preloaderVisible, textures: state.textures })}`);
}
try {
  await publicMobile();
  await gpuProbe('gpu-default-desktop', [], { width: 1440, height: 900 });
  await gpuProbe('gpu-default-mobile375', [], { width: 375, height: 812 });
  evidence.downloadPass = true;
} catch (error) {
  evidence.failure = String(error); process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  evidence.gpuRenderingPass = evidence.gpu.length === 2 && evidence.gpu.every(x => !x.cssFallback && !x.preloaderVisible && x.textures.some(t => t.valid && t.width <= x.maxTextureSize && t.height <= x.maxTextureSize && t.residentContexts.length));
  if (!evidence.gpuRenderingPass) process.exitCode = 1;
  writeFileSync(path.join(output, 'results.json'), JSON.stringify(evidence, null, 2), { flag: 'wx' });
  console.log(JSON.stringify({ downloadPass: evidence.downloadPass, gpuRenderingPass: evidence.gpuRenderingPass, checks: evidence.checks.length, errors: evidence.errors.length }));
}
