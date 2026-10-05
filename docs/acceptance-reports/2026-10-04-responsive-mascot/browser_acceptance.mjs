/** Real browser/app/GPU, read-only PIXI introspection; no HTTP/app-state mocks. */
import { createRequire } from 'node:module';
import { existsSync, readdirSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { randomBytes, createHash } from 'node:crypto';
import { parseArgs } from 'node:util';
import assert from 'node:assert/strict';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../../..');
const { values: options } = parseArgs({ options: { 'output-dir': { type: 'string' }, 'check-output-dir': { type: 'boolean', default: false }, 'focus-only': { type: 'boolean', default: false }, 'gesture-only': { type: 'boolean', default: false } } });
const output = path.resolve(options['output-dir'] || path.join(root, '.planning/2026-10-04-responsive-mascot', `${Date.now()}-${randomBytes(3).toString('hex')}`, 'evidence'));
if (existsSync(output) && readdirSync(output).length) throw new Error('output-dir must be new or empty; frozen evidence will not be overwritten');
if (options['check-output-dir']) { console.log(JSON.stringify({ output_dir: output, valid: true, offline: true })); process.exit(0); }
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
if (!installed) throw new Error('An installed playwright-core package is required');
const { chromium } = require(installed);
const evidence = { generatedAt: new Date().toISOString(), httpMocks: false, appStateWrites: false, llmCalls: 0, physicalDeviceDebugChannel: 'adb not discovered on PATH; physical phone availability unknown', checks: [], requests: [], errors: [], failedRequests: [], captures: [] };
evidence.sourceSha256 = Object.fromEntries(['App.jsx', 'components/EntryScene.jsx', 'components/ui/ExpressionMenu.jsx', 'pixi/mascot.js', 'pixi/mascotConfig.js', 'pixi/stage.js', 'styles/global.css'].map(file => [file, createHash('sha256').update(readFileSync(path.join(root, 'frontend/src', file))).digest('hex')]));
const record = (name, detail = {}) => evidence.checks.push({ name, pass: true, ...detail });
const epsilon = 2;
let browser;
let activePage;
function observe(page, scope) {
  page.on('pageerror', error => evidence.errors.push({ scope, kind: 'pageerror', error: String(error) }));
  page.on('console', message => { if (['error', 'warning'].includes(message.type())) evidence.errors.push({ scope, kind: message.type(), error: message.text().slice(0, 1000), location: message.location() }); });
  page.on('requestfailed', request => evidence.failedRequests.push({ scope, url: request.url(), failure: request.failure() }));
  page.on('response', response => { const u = new URL(response.url()); if (u.pathname.startsWith('/api/') || u.pathname.startsWith('/live2d/')) evidence.requests.push({ scope, method: response.request().method(), path: u.pathname, status: response.status() }); });
}
async function register(page) {
  await page.goto('http://127.0.0.1:5188', { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.getByTestId('auth-scene').waitFor();
  await page.getByRole('button', { name: '注册', exact: true }).click();
  await page.getByLabel('邮箱', { exact: true }).fill(`responsive-${Date.now()}-${randomBytes(3).toString('hex')}@example.com`);
  await page.getByLabel('密码', { exact: true }).fill(`Owned-${randomBytes(12).toString('hex')}`);
  await page.getByRole('button', { name: '立即注册', exact: true }).click();
  await page.getByTestId('entry-scene').waitFor();
  await page.locator('.preloader').waitFor({ state: 'hidden', timeout: 90000 });
}
async function runtime(session) {
  const prototype = await session.send('Runtime.evaluate', { expression: 'window.PIXI.Application.prototype' });
  const objects = await session.send('Runtime.queryObjects', { prototypeObjectId: prototype.result.objectId });
  const result = await session.send('Runtime.callFunctionOn', { objectId: objects.objects.objectId, returnByValue: true,
    functionDeclaration: `function() { return this.filter(a => a.stage && a.view && a.view.isConnected).map(a => {
      const m = a.stage.children.find(child => child.internalModel);
      const rect = m?.getBounds();
      return { screen: { width: a.screen.width, height: a.screen.height }, model: m ? {
        visible: m.visible, x: m.x, y: m.y, scale: m.scale.x,
        bounds: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        local: { width: m.getLocalBounds().width, height: m.getLocalBounds().height }
      } : null };
    }); }` });
  await session.send('Runtime.releaseObject', { objectId: objects.objects.objectId });
  await session.send('Runtime.releaseObject', { objectId: prototype.result.objectId });
  assert.equal(result.result.value.length, 1, 'Exactly one active connected PIXI stage');
  return result.result.value[0];
}
async function geometry(page) {
  return page.evaluate(() => {
    const rect = element => { if (!element) return null; const r = element.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, right: r.right, bottom: r.bottom }; };
    const selectors = ['.landing-hero__content', '.landing-examples', '.landing-form', '[data-mascot-region]', '.mascot-menu-trigger', '.auth-bar', '.theme-switch'];
    return { width: innerWidth, height: innerHeight, documentWidth: document.documentElement.scrollWidth, scrollY,
      rects: Object.fromEntries(selectors.map(selector => [selector, rect([...document.querySelectorAll(selector)].find(el => el.getClientRects().length))])),
      chipHeights: [...document.querySelectorAll('.landing-examples__chip')].map(chip => chip.getBoundingClientRect().height) };
  });
}
function inside(bounds, region) {
  assert.ok(bounds.x >= region.x - epsilon && bounds.y >= region.y - epsilon &&
    bounds.x + bounds.width <= region.x + region.width + epsilon && bounds.y + bounds.height <= region.y + region.height + epsilon,
    JSON.stringify({ bounds, region }));
}
async function capture(page, session, label) {
  const g = await geometry(page), r = await runtime(session);
  assert.ok(g.documentWidth <= g.width + 1, JSON.stringify(g));
  evidence.captures.push({ label, geometry: g, runtime: r });
  await screenshot(page, `${label}.png`);
  return { g, r };
}
async function screenshot(page, filename) {
  // Actual current GPU frame. Optional remote font loading must not block capture.
  // This does not alter font CSS, network routes, app state or model visibility.
  const cdp = await page.context().newCDPSession(page);
  try {
    const frame = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
    writeFileSync(path.join(output, filename), Buffer.from(frame.data, 'base64'), { flag: 'wx' });
  } finally { await cdp.detach(); }
}
async function exercise(width, height) {
  const label = `gpu-${width}`;
  const context = await browser.newContext({ viewport: { width, height }, hasTouch: width <= 720, isMobile: width <= 720, reducedMotion: 'reduce' });
  const page = await context.newPage(); page.setDefaultTimeout(30000); observe(page, label);
  activePage = page;
  const session = await context.newCDPSession(page);
  await register(page); record(`${label} real registration and model ready`);
  const gpu = await page.evaluate(() => {
    const canvas = document.querySelector('.stage canvas');
    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
    const debug = gl.getExtension('WEBGL_debug_renderer_info');
    return { renderer: debug && gl.getParameter(debug.UNMASKED_RENDERER_WEBGL), maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE),
      textures: Object.entries(window.PIXI.utils.BaseTextureCache).filter(([key]) => /texture_00/.test(key)).map(([key, t]) => ({ key, width: t.width, height: t.height, valid: t.valid, residentContexts: Object.keys(t._glTextures || {}) })) };
  });
  assert.ok(/4050/.test(gpu.renderer), JSON.stringify(gpu));
  await capture(page, session, `${label}-entry-top`);
  await page.getByLabel('视频链接', { exact: true }).focus();
  const form = await page.locator('.landing-form').boundingBox();
  assert.ok(form.y >= 120, `Form is below fixed top controls: ${form.y}`);
  await page.getByRole('button', { name: 'bilibili.com', exact: true }).click();
  assert.match(await page.getByLabel('视频链接', { exact: true }).inputValue(), /bilibili/);
  record(`${label} example chip accessible and fills input`);
  if (width <= 720) {
    const g = await geometry(page);
    assert.ok(g.rects['[data-mascot-region]'].y >= g.rects['.landing-hero__content'].bottom - 1);
    assert.ok(g.chipHeights.every(h => h >= 44));
    record(`${label} dedicated region follows controls and chips >=44px`, g);
    await page.locator('[data-mascot-region]').scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
  }
  await page.waitForFunction(() => Object.values(window.PIXI.utils.BaseTextureCache).some(t => t.width === 16384 && t.valid && Object.keys(t._glTextures || {}).length), { timeout: 15000 });
  gpu.textures = await page.evaluate(() => Object.entries(window.PIXI.utils.BaseTextureCache).filter(([key]) => /texture_00/.test(key)).map(([key, t]) => ({ key, width: t.width, height: t.height, valid: t.valid, residentContexts: Object.keys(t._glTextures || {}) })));
  record(`${label} real RTX4050 16K texture resident`, gpu);
  let { g, r } = await capture(page, session, `${label}-whole-character`);
  assert.ok(r.model?.visible);
  inside(r.model.bounds, width <= 720 ? g.rects['[data-mascot-region]'] : { x: 0, y: 0, width, height });
  if (width > 720) assert.ok(r.model.bounds.y + r.model.bounds.height <= g.rects['.mascot-menu-trigger'].y, 'Desktop character clears separate footer entry');
  record(`${label} real model entirely within allocated area`, { bounds: r.model.bounds, region: g.rects['[data-mascot-region]'] });
  const b = r.model.bounds, center = { x: b.x + b.width / 2, y: b.y + b.height / 2 };
  if (width <= 720) await page.touchscreen.tap(center.x, center.y); else await page.mouse.click(center.x, center.y);
  await page.getByRole('dialog', { name: '角色换装' }).waitFor({ state: 'visible' });
  record(`${label} actual model tap opens menu`);
  await page.keyboard.press('Escape');
  await page.getByRole('dialog', { name: '角色换装' }).waitFor({ state: 'hidden' });
  await page.getByRole('button', { name: '角色换装', exact: true }).click();
  await page.getByRole('button', { name: '关闭菜单' }).waitFor();
  assert.equal(await page.getByRole('button', { name: '关闭菜单' }).evaluate(el => el === document.activeElement), true);
  await page.keyboard.press('Shift+Tab');
  assert.equal(await page.getByRole('dialog').evaluate(el => el.contains(document.activeElement)), true);
  await page.getByRole('button', { name: '变小', exact: true }).click();
  await page.getByRole('button', { name: '短发', exact: true }).click();
  assert.equal(await page.getByRole('button', { name: /短发/ }).getAttribute('aria-pressed'), 'true');
  await screenshot(page, `${label}-menu.png`);
  await page.keyboard.press('Escape');
  assert.equal(await page.getByRole('button', { name: '角色换装', exact: true }).evaluate(el => el === document.activeElement), true);
  record(`${label} visible menu entry, focus loop, outfit and scale operate; focus restored`);
  r = await runtime(session);
  const rb = r.model.bounds, dragStart = { x: rb.x + rb.width / 2, y: rb.y + rb.height / 2 };
  const dragEnd = { x: 2, y: width <= 720 ? dragStart.y : 2 };
  const scrollBeforeDrag = await page.evaluate(() => scrollY);
  if (width <= 720) {
    await session.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ ...dragStart, id: 1 }] });
    for (let i = 1; i <= 5; i++) await session.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: dragStart.x + (dragEnd.x - dragStart.x) * i / 5, y: dragStart.y + (dragEnd.y - dragStart.y) * i / 5, id: 1 }] });
    await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  } else {
    await page.mouse.move(dragStart.x, dragStart.y); await page.mouse.down(); await page.mouse.move(dragEnd.x, dragEnd.y, { steps: 5 }); await page.mouse.up();
  }
  await page.waitForTimeout(200);
  ({ g, r } = await capture(page, session, `${label}-drag-constrained`));
  assert.ok(Math.abs(r.model.x - (rb.x + rb.width / 2)) >= 3, 'Actual pointer drag changes model position');
  if (width <= 720) assert.equal(g.scrollY, scrollBeforeDrag, 'Horizontal model touch-drag does not scroll document');
  inside(r.model.bounds, width <= 720 ? g.rects['[data-mascot-region]'] : { x: 0, y: 0, width, height });
  assert.equal(await page.getByRole('dialog').isVisible(), false);
  record(`${label} real drag remains inside area without accidental menu`, { bounds: r.model.bounds });
  if (width <= 720) {
    await page.locator('.landing-chapter').first().scrollIntoViewIfNeeded();
    await page.waitForTimeout(200);
    r = await runtime(session); assert.equal(r.model.visible, false);
    record(`${label} scroll removes offscreen character`);
    await page.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }));
  }
  await page.getByLabel('视频链接', { exact: true }).fill('http://127.0.0.1:8064/owned.html');
  const incoming = page.waitForResponse(response => new URL(response.url()).pathname === '/api/parse' && response.request().method() === 'POST');
  await page.getByRole('button', { name: '解析', exact: true }).click();
  const parsed = await incoming; assert.equal(parsed.status(), 200, await parsed.text());
  await page.getByTestId('selecting-scene').waitFor();
  const selecting = await capture(page, session, `${label}-selecting`);
  if (width <= 720) {
    const card = await page.locator('.format-card').boundingBox();
    assert.ok(selecting.g.rects['[data-mascot-region]'].y >= card.y + card.height - 1);
  }
  await page.getByRole('button', { name: /最佳 MP4/ }).click();
  assert.equal(await page.getByRole('button', { name: '下载', exact: true }).isEnabled(), true);
  record(`${label} actual owned yt-dlp parse200 and format selection remains usable`);
  if (width > 720) {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.locator('[data-mascot-region]').scrollIntoViewIfNeeded();
    await page.waitForTimeout(250);
    const resized = await capture(page, session, 'gpu-desktop-resized375');
    assert.equal(resized.r.screen.width, 375);
    inside(resized.r.model.bounds, resized.g.rects['[data-mascot-region]']);
    record('same live GPU stage resizes desktop to375px without overlap or model reload');
  }
  await session.detach(); await context.close();
  activePage = null;
}
async function lowCapability() {
  const context = await browser.newContext({ viewport: { width: 375, height: 812 }, reducedMotion: 'reduce' });
  const page = await context.newPage(); observe(page, 'simulated-8K');
  activePage = page;
  await page.addInitScript(() => {
    for (const type of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
      if (!type) continue;
      const original = type.prototype.getParameter;
      type.prototype.getParameter = function(parameter) { return parameter === this.MAX_TEXTURE_SIZE ? 8192 : original.call(this, parameter); };
    }
  });
  await register(page);
  assert.equal(await page.locator('.stage canvas').getAttribute('data-mascot'), 'unsupported-texture');
  assert.equal(await page.getByRole('button', { name: '角色换装', exact: true }).isDisabled(), true);
  assert.equal(evidence.requests.filter(r => r.scope === 'simulated-8K' && r.path.startsWith('/live2d/bai/')).length, 0);
  await page.getByLabel('视频链接', { exact: true }).fill('http://127.0.0.1:8064/owned.html');
  const incoming = page.waitForResponse(r => new URL(r.url()).pathname === '/api/parse' && r.request().method() === 'POST');
  await page.getByRole('button', { name: '解析', exact: true }).click();
  const parsed = await incoming; assert.equal(parsed.status(), 200);
  await page.getByTestId('selecting-scene').waitFor();
  await screenshot(page, 'simulated-8K-selecting.png');
  record('simulated 8K capability skips 16K model request, clears loader and allows parse200', { simulated: true, realLowCapDevice: false });
  await context.close();
  activePage = null;
}
async function focusProbe() {
  const context = await browser.newContext({ viewport: { width: 375, height: 812 }, reducedMotion: 'reduce' });
  const page = await context.newPage(); activePage = page; observe(page, 'native-focus375');
  const session = await context.newCDPSession(page);
  await register(page);
  await page.getByLabel('视频链接', { exact: true }).fill('http://127.0.0.1:8064/owned.html');
  const incoming = page.waitForResponse(r => new URL(r.url()).pathname === '/api/parse' && r.request().method() === 'POST');
  await page.getByRole('button', { name: '解析', exact: true }).click();
  const parsed = await incoming; assert.equal(parsed.status(), 200);
  await page.getByTestId('selecting-scene').waitFor();
  const language = page.getByRole('combobox', { name: /字幕语言/ });
  // Place the real control under an existing fixed bar by ordinary scrolling.
  const documentTop = await language.evaluate(el => el.getBoundingClientRect().top + scrollY);
  await page.evaluate(top => scrollTo({ top, behavior: 'instant' }), documentTop - 100);
  await language.focus();
  await page.waitForTimeout(150);
  const check = await language.evaluate(el => {
    const r = el.getBoundingClientRect();
    const bars = [...document.querySelectorAll('.auth-bar, .theme-switch')].map(bar => {
      const b = bar.getBoundingClientRect(); return { x: b.x, y: b.y, width: b.width, height: b.height };
    });
    return { focused: document.activeElement === el, rect: { x: r.x, y: r.y, width: r.width, height: r.height }, bars,
      hitsAtCenter: document.elementsFromPoint(r.x + r.width / 2, r.y + r.height / 2).slice(0, 4).map(hit => hit.className || hit.tagName) };
  });
  evidence.focusProbe = check;
  await screenshot(page, 'native-focus375.png');
  assert.ok(check.focused);
  assert.ok(check.bars.every(bar => check.rect.x + check.rect.width <= bar.x || bar.x + bar.width <= check.rect.x || check.rect.y + check.rect.height <= bar.y || bar.y + bar.height <= check.rect.y), JSON.stringify(check));
  record('375px native focused select entirely clears fixed account/theme bars', check);
  await session.detach(); await context.close(); activePage = null;
}
async function gestureProbe() {
  const context = await browser.newContext({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true, reducedMotion: 'reduce' });
  const page = await context.newPage(); activePage = page; observe(page, 'real-touch375');
  const session = await context.newCDPSession(page);
  await register(page);
  await page.locator('[data-mascot-region]').scrollIntoViewIfNeeded();
  await page.waitForTimeout(200);
  evidence.touchEvents = [];
  await page.exposeFunction('recordAcceptanceTouch', entry => evidence.touchEvents.push(entry));
  await page.evaluate(() => {
    for (const type of ['pointerdown', 'pointermove', 'pointerup', 'pointercancel', 'touchstart', 'touchmove', 'touchend', 'touchcancel', 'scroll']) {
      window.addEventListener(type, event => window.recordAcceptanceTouch({ type, clientX: event.clientX, clientY: event.clientY, pointerId: event.pointerId,
        pointerType: event.pointerType, defaultPrevented: event.defaultPrevented, target: event.target.tagName,
        touchX: event.touches?.[0]?.clientX, touchY: event.touches?.[0]?.clientY, scrollY, time: performance.now() }), { passive: true });
    }
  });
  let state = await runtime(session);
  const b = state.model.bounds;
  const center = { x: b.x + b.width / 2, y: b.y + b.height / 2 };
  await session.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ ...center, id: 1 }] });
  await session.send('Input.dispatchTouchEvent', { type: 'touchCancel', touchPoints: [] });
  await page.waitForTimeout(150);
  const cancelledOpenedMenu = await page.getByRole('dialog').isVisible();
  evidence.cancelProbe = { cancelledOpenedMenu, touchStart: center, movement: false };
  await screenshot(page, 'touch-cancel375.png');
  assert.equal(cancelledOpenedMenu, false, 'A real cancelled touch without movement must not count as a tap');
  record('real touchStart→touchCancel without movement does not open menu', evidence.cancelProbe);
  await page.touchscreen.tap(center.x, center.y);
  await page.getByRole('dialog').waitFor({ state: 'visible' });
  await page.keyboard.press('Escape');
  await page.getByRole('dialog').waitFor({ state: 'hidden' });
  record('real ordinary touch tap still opens menu after cancellation fix');
  await page.waitForTimeout(350);
  state = await runtime(session);
  assert.ok(state.model.visible);
  inside(state.model.bounds, { x: 0, y: 0, width: 375, height: 812 });
  const horizontalStart = { x: state.model.bounds.x + state.model.bounds.width / 2, y: state.model.bounds.y + state.model.bounds.height / 2 };
  const horizontalScrollBefore = await page.evaluate(() => scrollY);
  evidence.horizontalBefore = { state, geometry: await geometry(page) };
  evidence.horizontalTrace = [];
  await session.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ ...horizontalStart, id: 3 }] });
  for (let i = 1; i <= 4; i++) {
    await session.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: horizontalStart.x - 160 * i / 4, y: horizontalStart.y, id: 3 }] });
    await page.waitForTimeout(50);
    const step = await runtime(session);
    evidence.horizontalTrace.push({ step: i, modelX: step.model.x, modelY: step.model.y, scrollY: await page.evaluate(() => scrollY) });
  }
  await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await page.waitForTimeout(150);
  state = await runtime(session);
  evidence.horizontalProbe = { beforeX: evidence.horizontalBefore.state.model.x, afterX: state.model.x, movement: Math.abs(state.model.x - evidence.horizontalBefore.state.model.x),
    scrollBefore: horizontalScrollBefore, scrollAfter: await page.evaluate(() => scrollY), menuOpened: await page.getByRole('dialog').isVisible() };
  assert.ok(evidence.horizontalProbe.movement >= 3, JSON.stringify(evidence.horizontalProbe));
  assert.equal(evidence.horizontalProbe.scrollAfter, horizontalScrollBefore);
  assert.equal(evidence.horizontalProbe.menuOpened, false);
  inside(state.model.bounds, (await geometry(page)).rects['[data-mascot-region]']);
  record('real horizontal touch drag moves model >=3px, stays in region and does not scroll document', evidence.horizontalProbe);
  const active = state.model.bounds;
  const start = { x: active.x + active.width / 2, y: active.y + active.height / 2 };
  const scrollBefore = await page.evaluate(() => scrollY);
  await session.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ ...start, id: 2 }] });
  for (let i = 1; i <= 6; i++) {
    await session.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: start.x, y: start.y - 200 * i / 6, id: 2 }] });
    await page.waitForTimeout(50);
  }
  await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await page.waitForTimeout(250);
  const scrollAfter = await page.evaluate(() => scrollY);
  const verticalOpenedMenu = await page.getByRole('dialog').isVisible();
  evidence.verticalProbe = { scrollBefore, scrollAfter, scrollDistance: scrollAfter - scrollBefore, verticalOpenedMenu, touchStart: start,
    canvasTouchAction: await page.locator('.stage canvas').evaluate(el => ({ inline: el.style.touchAction, computed: getComputedStyle(el).touchAction })) };
  await screenshot(page, 'native-vertical-touch375.png');
  assert.ok(scrollAfter >= scrollBefore + 20, JSON.stringify(evidence.verticalProbe));
  assert.equal(verticalOpenedMenu, false);
  record('real vertical finger gesture scrolls document and does not open menu', evidence.verticalProbe);
  await session.detach(); await context.close(); activePage = null;
}
try {
  const systemProxy = execFileSync('powershell.exe', ['-NoProfile', '-Command', "[System.Net.WebRequest]::DefaultWebProxy.GetProxy([uri]'https://fonts.googleapis.com').AbsoluteUri"], { encoding: 'utf8' }).trim();
  const proxy = systemProxy && !systemProxy.startsWith('https://fonts.googleapis.com') ? { server: systemProxy, bypass: '127.0.0.1,localhost' } : undefined;
  evidence.proxyFromSystem = Boolean(proxy);
  browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true, args: ['--no-first-run'], proxy });
  const cdp = await browser.newBrowserCDPSession(); const info = await cdp.send('SystemInfo.getInfo'); evidence.gpuDevices = info.gpu?.devices; await cdp.detach();
  if (options['gesture-only']) await gestureProbe();
  else if (options['focus-only']) await focusProbe();
  else {
    for (const [width, height] of [[320, 568], [375, 812], [720, 900], [1440, 900]]) await exercise(width, height);
    await lowCapability();
  }
  assert.equal(evidence.requests.filter(r => ['/api/summary', '/api/subtitle/translate'].includes(r.path)).length, 0);
  assert.equal(evidence.errors.length, 0, JSON.stringify(evidence.errors));
  record('no AI API, pageerror or unexpected console warning/error');
  evidence.pass = true;
} catch (error) {
  evidence.failure = String(error); process.exitCode = 1;
  if (activePage && !activePage.isClosed()) {
    try { await screenshot(activePage, 'failure-state.png'); } catch {}
  }
} finally {
  if (browser) await browser.close();
  writeFileSync(path.join(output, 'results.json'), JSON.stringify(evidence, null, 2), { flag: 'wx' });
  console.log(JSON.stringify({ pass: evidence.pass || false, checks: evidence.checks.length, errors: evidence.errors.length, failure: evidence.failure, output }));
}
