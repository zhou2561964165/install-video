import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render } from '@testing-library/react';
import PointerFollower from './PointerFollower.jsx';
import * as silhouettes from '../../pixi/mascotSilhouette.js';
import AuthScene from '../AuthScene.jsx';
import SelectingScene from '../SelectingScene.jsx';
import ParsingScene from '../ParsingScene.jsx';

let external;
beforeEach(() => {
  external = [];
  vi.stubGlobal('CSS', { supports: () => true });
  vi.stubGlobal('matchMedia', (query) => ({ matches: query.includes('pointer: fine'), addEventListener() {}, removeEventListener() {} }));
  document.documentElement.style.setProperty('--cursor-lens-enter-gap', '8px');
  document.documentElement.style.setProperty('--cursor-lens-exit-gap', '16px');
});
afterEach(() => { cleanup(); external.forEach((el) => el.remove()); document.documentElement.removeAttribute('style'); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function rect(element, box) {
  const bounds = { ...box, right: box.left + box.width, bottom: box.top + box.height };
  element.getBoundingClientRect = () => bounds;
  for (const [key, value] of Object.entries({ offsetLeft: box.left, offsetTop: box.top, offsetWidth: box.width, offsetHeight: box.height })) Object.defineProperty(element, key, { configurable: true, value });
}
function mount() {
  const rootRef = { current: null };
  const view = render(<><div className="stage" /><div ref={(el) => { rootRef.current = el; }}><section data-ui-follow><h1 data-follow-plane>标题</h1><button>控件</button><form data-follow-exclude="parse"><input aria-label="解析输入" /></form></section></div><PointerFollower rootRef={rootRef} /></>);
  const plane = view.container.querySelector('[data-ui-follow]');
  const button = view.container.querySelector('button');
  const lens = view.container.querySelector('.cursor-lens');
  const parse = view.container.querySelector('[data-follow-exclude="parse"]');
  rect(plane, { left: 0, top: 0, width: 1200, height: 900 });
  rect(button, { left: 600, top: 200, width: 100, height: 40 });
  rect(parse, { left: 600, top: 200, width: 100, height: 40 });
  rect(lens, { left: 0, top: 0, width: 190, height: 190 });
  fireEvent(window, new Event('resize'));
  return { view, plane, button, parse, lens };
}
const move = (x, y, buttons = 0) => {
  const event = new MouseEvent('pointermove', { clientX: x, clientY: y, buttons });
  Object.defineProperty(event, 'pointerType', { value: 'mouse' });
  fireEvent(window, event);
};

describe('镜片避让', () => {
  it.each(['login', 'register', 'loading', 'video', 'content', 'parsing'])('实际%s面板整圈接触隐藏，离开面板空白恢复', async (kind) => {
    const rootRef = { current: null };
    const auth = ['login', 'register', 'loading'].includes(kind);
    const scene = auth ? <AuthScene loading={kind === 'loading'} onLogin={vi.fn()} onRegister={vi.fn()} />
      : kind === 'parsing' ? <ParsingScene />
        : <SelectingScene parseResult={{ title: '测试视频', formats: [], subtitles: [] }} selectedFormat={null} onSelect={vi.fn()} onDownload={vi.fn()}
          insights={{ loading: null, active: null, subtitle: null, translation: null, summary: null }} />;
    const view = render(<><div ref={el => { rootRef.current = el; }}>{scene}</div><PointerFollower rootRef={rootRef} /></>);
    if (kind === 'register') fireEvent.click(view.getByRole('button', { name: '注册', exact: true }));
    const panel = view.container.querySelector(auth ? '.auth-card' : kind === 'content' ? '.video-insights' : kind === 'parsing' ? '[data-testid="parsing-scene"]' : '.format-card');
    expect(panel).toHaveAttribute('data-follow-exclude', 'panel');
    const lens = view.container.querySelector('.cursor-lens');
    rect(lens, { left: 0, top: 0, width: 190, height: 190 });
    rect(panel, { left: 400, top: 300, width: 400, height: 400 });
    fireEvent(window, new Event('resize'));
    move(200, 500); expect(lens.dataset.active).toBe('true');
    move(300, 500); expect(lens.dataset.active).toBe('false'); // radius95 + enter gap8
    move(600, 500); expect(lens.dataset.active).toBe('false');
    move(288, 500); expect(lens.dataset.active).toBe('true');
    await act(async () => { panel.hidden = true; });
    move(600, 500); expect(lens.dataset.active).toBe('true');
  });
  it('面板动态出现后静止指针立即避让，移除后恢复', async () => {
    const { lens, plane } = mount();
    move(400, 500); expect(lens.dataset.active).toBe('true');
    const panel = document.createElement('article'); panel.dataset.followExclude = 'panel';
    rect(panel, { left: 400, top: 400, width: 300, height: 250 });
    await act(async () => { plane.append(panel); });
    expect(lens.dataset.active).toBe('false');
    await act(async () => { panel.remove(); });
    expect(lens.dataset.active).toBe('true');
  });
  it('模型在舞台内动态挂载或移除后自动更新避让，不等待第二次resize', async () => {
    const { lens, view } = mount();
    move(755, 500); expect(lens.dataset.active).toBe('true');
    const model = document.createElement('div'); model.dataset.followExclude = 'mascot';
    rect(model, { left: 850, top: 400, width: 180, height: 250 });
    await act(async () => { view.container.querySelector('.stage').append(model); });
    expect(lens.dataset.active).toBe('false');
    await act(async () => model.remove());
    expect(lens.dataset.active).toBe('true');
  });
  it('未标记的普通按钮、链接、菜单和两侧保留显示，顶部与解析表单仍避让', () => {
    const { lens, plane, button } = mount();
    move(1250, 500); expect(lens.dataset.active).toBe('true');
    expect(plane).toHaveAttribute('data-follow-active', 'true');
    rect(button, { left: 300, top: 300, width: 100, height: 40 });
    const link = document.createElement('a'); link.href = '#test'; link.textContent = '其他链接';
    const menu = document.createElement('aside'); menu.setAttribute('role', 'dialog'); menu.setAttribute('aria-hidden', 'false');
    const header = document.createElement('header'); header.className = 'site-header';
    for (const e of [link, menu, header]) { document.body.append(e); external.push(e); }
    rect(link, { left: 300, top: 400, width: 100, height: 40 });
    rect(menu, { left: 300, top: 500, width: 100, height: 40 });
    rect(header, { left: 0, top: 0, width: 1200, height: 80 });
    fireEvent(window, new Event('resize'));
    for (const [element, y] of [[button,320],[link,420],[menu,520]]) {
      fireEvent(element, new MouseEvent('pointermove', { bubbles: true, clientX: 350, clientY: y }));
      expect(lens.dataset.active).toBe('true');
    }
    move(350, 40); expect(lens.dataset.active).toBe('false');
    move(650, 220); expect(lens.dataset.active).toBe('false');
    move(1250, 500); expect(lens.dataset.active).toBe('true');
  });
  it('小圈移到左右空白时标题也随位置连续倾斜，离开区域后清理旧标题', () => {
    const { lens, plane } = mount();
    vi.stubGlobal('innerWidth', 1440);
    rect(plane, { left: 100, top: 0, width: 1200, height: 900 });
    fireEvent(window, new Event('resize'));
    move(1250, 500);
    expect(lens.dataset.active).toBe('true');
    expect(plane).toHaveAttribute('data-follow-active', 'true');
    const first = parseFloat(plane.style.getPropertyValue('--follow-x'));
    move(1300, 500);
    expect(parseFloat(plane.style.getPropertyValue('--follow-x'))).toBeGreaterThan(first);
    move(15, 500);
    const left = parseFloat(plane.style.getPropertyValue('--follow-x'));
    expect(left).toBeLessThan(0);
    expect(lens.dataset.active).toBe('true');
    move(400, 950);
    expect(lens.dataset.active).toBe('true');
    expect(plane).not.toHaveAttribute('data-follow-active');
    expect(plane.style.getPropertyValue('--follow-x')).toBe('');
  });
  it('模型透明外框和role button不提前隐藏镜片，只有可见轮廓接触才隐藏', () => {
    const { lens } = mount();
    const model = document.createElement('div'); model.dataset.followExclude = 'mascot';
    model.setAttribute('role', 'button');
    rect(model, { left: 850, top: 400, width: 180, height: 250 });
    const overlapsCircle = vi.fn((x, _y, radius) => x + radius >= 980);
    vi.spyOn(silhouettes, 'getMascotSilhouette').mockImplementation(e => e === model ? { overlapsCircle } : undefined);
    document.body.append(model); external.push(model); fireEvent(window, new Event('resize'));
    const dispatch = x => {
      const event = new MouseEvent('pointermove', { bubbles: true, clientX: x, clientY: 500 });
      Object.defineProperty(event, 'pointerType', { value: 'mouse' });
      fireEvent(model, event);
    };
    dispatch(860); expect(lens.dataset.active).toBe('true');
    dispatch(885); expect(lens.dataset.active).toBe('false');
    dispatch(884); expect(lens.dataset.active).toBe('true');
    expect(overlapsCircle).toHaveBeenCalledWith(884, 500, 95);
  });
  it('静止指针遇到模型姿态轮廓变化时立即复核，不扫描所有标题', () => {
    const { lens, plane } = mount();
    const model = document.createElement('div'); model.dataset.followExclude = 'mascot';
    rect(model, { left: 850, top: 400, width: 180, height: 250 });
    document.body.append(model); external.push(model); fireEvent(window, new Event('resize'));
    let contact = false;
    vi.spyOn(silhouettes, 'getMascotSilhouette').mockImplementation(e => e === model ? { overlapsCircle: () => contact } : undefined);
    const query = vi.spyOn(plane.parentElement, 'querySelectorAll');
    move(900, 500); expect(lens.dataset.active).toBe('true');
    contact = true; fireEvent(model, new CustomEvent('mascot-silhouette-change', { bubbles: true }));
    expect(lens.dataset.active).toBe('false');
    contact = false; fireEvent(model, new CustomEvent('mascot-silhouette-change', { bubbles: true }));
    expect(lens.dataset.active).toBe('true');
    expect(query).not.toHaveBeenCalledWith('[data-ui-follow]');
  });
  it('接近控件先淡出，离开需额外余量，并立即恢复原生指针', () => {
    const { lens, plane } = mount();
    move(500, 220); expect(lens.dataset.active).toBe('true');
    move(593, 220); expect(lens.dataset.active).toBe('false');
    expect(document.documentElement).not.toHaveClass('has-pointer-follow');
    expect(plane).not.toHaveAttribute('data-follow-active');
    move(588, 220); expect(lens.dataset.active).toBe('false');
    move(580, 220); expect(lens.dataset.active).toBe('true');
  });
  it('足迹接触uiRef外角色时隐藏，判定不随视觉缩小反复切换', () => {
    const { lens } = mount();
    const model = document.createElement('div'); model.dataset.followExclude = 'mascot';
    rect(model, { left: 850, top: 400, width: 180, height: 250 });
    document.body.append(model); external.push(model); fireEvent(window, new Event('resize'));
    move(730, 500); expect(lens.dataset.active).toBe('true');
    move(752, 500); expect(lens.dataset.active).toBe('true'); // 还差3px，不提前消失。
    move(755, 500); expect(lens.dataset.active).toBe('false');
    move(754, 500); expect(lens.dataset.active).toBe('true');
    move(730, 500); expect(lens.dataset.active).toBe('true');
    expect(lens.querySelector('.cursor-lens__surface')).not.toBeNull();
  });
  it('热区隐藏后不留下排除范围，样式边界更新无需再移动指针', async () => {
    const { lens } = mount();
    const model = document.createElement('div'); model.dataset.followExclude = 'mascot';
    rect(model, { left: 850, top: 400, width: 180, height: 250 });
    document.body.append(model); external.push(model); fireEvent(window, new Event('resize'));
    move(755, 500); expect(lens.dataset.active).toBe('false');
    await act(async () => { model.style.visibility = 'hidden'; });
    expect(lens.dataset.active).toBe('true');
    await act(async () => { model.style.visibility = 'visible'; });
    expect(lens.dataset.active).toBe('false');
  });
  it('自由模型移入静止镜片时隐藏，移开后恢复且不重扫标题区域', async () => {
    const { lens, plane } = mount();
    const model = document.createElement('div'); model.dataset.followExclude = 'mascot';
    rect(model, { left: 850, top: 400, width: 180, height: 250 });
    document.body.append(model); external.push(model); fireEvent(window, new Event('resize'));
    const root = plane.parentElement;
    const query = vi.spyOn(root, 'querySelectorAll');
    move(500, 500); expect(lens.dataset.active).toBe('true');
    await act(async () => {
      rect(model, { left: 550, top: 400, width: 180, height: 250 });
      model.style.left = '550px';
    });
    expect(lens.dataset.active).toBe('false');
    expect(document.documentElement).not.toHaveClass('has-pointer-follow');
    await act(async () => {
      rect(model, { left: 850, top: 400, width: 180, height: 250 });
      model.style.left = '850px';
    });
    expect(lens.dataset.active).toBe('true');
    expect(query).not.toHaveBeenCalledWith('[data-ui-follow]');
    query.mockRestore();
  });
  it('隐藏镜片期间的滚动刷新仍按新解析组件几何判断', () => {
    const { lens, parse } = mount();
    move(593, 220); expect(lens.dataset.active).toBe('false');
    rect(parse, { left: 600, top: 400, width: 100, height: 40 });
    fireEvent(window, new Event('scroll'));
    expect(lens.dataset.active).toBe('true');
    expect(lens.style.getPropertyValue('--cursor-x')).toBe('593px');
  });
  it('拖动和blur清理镜片/标题/指针，卸载解除监听', () => {
    const { view, lens, plane } = mount();
    move(400, 500); expect(lens.dataset.active).toBe('true');
    move(410, 500, 1); expect(lens.dataset.active).toBe('false');
    move(420, 500); fireEvent(window, new Event('blur'));
    expect(lens.dataset.active).toBe('false'); expect(plane).not.toHaveAttribute('data-follow-active');
    view.unmount(); move(420, 500); expect(document.documentElement).not.toHaveClass('has-pointer-follow');
  });
  it('普通菜单不在新的小圈避让名单中，开关均不隐藏小圈', async () => {
    const { lens } = mount();
    const menu = document.createElement('aside'); menu.setAttribute('role', 'dialog'); menu.setAttribute('aria-hidden', 'false');
    rect(menu, { left: 300, top: 300, width: 400, height: 350 }); document.body.append(menu); external.push(menu);
    fireEvent(window, new Event('resize')); move(400, 500); expect(lens.dataset.active).toBe('true');
    await act(async () => { menu.setAttribute('aria-hidden', 'true'); menu.setAttribute('inert', ''); });
    expect(getComputedStyle(menu).visibility).not.toBe('hidden'); // 模拟CSS延迟visibility隐藏。
    move(400, 500); expect(lens.dataset.active).toBe('true');
  });
});
