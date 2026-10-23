import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App.jsx';

const mockVisual = vi.hoisted(() => ({ webgl: false, available: true, visual: true, onTap: null, instance: null }));
function visualFixture() {
  return { isAvailable: () => mockVisual.available, hasVisual: () => mockVisual.visual, resize: vi.fn(), destroy: vi.fn(), startRandomProps: vi.fn(), setStageExpression: vi.fn(), setExpression: vi.fn(), scaleBy: vi.fn(), moveBy: vi.fn(), resetPosition: vi.fn(), setMotionEnabled: vi.fn() };
}

function phoneViewport(width) {
  const media = new EventTarget();
  media.matches = width <= 800;
  vi.stubGlobal('innerWidth', width);
  vi.stubGlobal('matchMedia', (query) => query === '(max-width: 800px)' ? media : { matches: false, addEventListener() {}, removeEventListener() {} });
  return (nextWidth) => {
    window.innerWidth = nextWidth;
    media.matches = nextWidth <= 800;
    media.dispatchEvent(new Event('change'));
  };
}

vi.mock('pixi.js', () => ({}));
vi.mock('pixi-live2d-display/cubism4', () => ({
  Live2DModel: {
    from: () => Promise.reject(new Error('no model in test')),
    registerTicker: () => {},
  },
}));
vi.mock('./pixi/stage.js', () => ({
  webglSupported: () => mockVisual.webgl,
  detectTier: () => 'none',
  initStage: vi.fn(),
  destroyStage: vi.fn(),
}));
vi.mock('./pixi/background.js', () => ({
  createBackground: vi.fn(() => ({ resize: vi.fn(), destroy: vi.fn(), setIntensity: vi.fn() })),
  intensityForScene: () => 0,
}));
vi.mock('./pixi/mascot.js', () => ({
  createMascot: vi.fn(async (_app, _modelId, options) => {
    mockVisual.onTap = options.onTap;
    return (mockVisual.instance = visualFixture());
  }),
}));

const mockAuth = vi.hoisted(() => ({
  status: 'authed',
  user: { id: 'u1', email: 't@e.com', created_at: '' },
  quota: { date: '2026-09-24', limit: 10, used: 0, remaining: 10 },
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  refreshQuota: vi.fn(),
}));
vi.mock('./hooks/useAuth.js', () => ({
  useAuth: () => mockAuth,
}));

import { clearAuthToken, setAuthToken } from './api.js';
import { createBackground } from './pixi/background.js';
import { createMascot } from './pixi/mascot.js';
import { installMascotLoadTokens } from './test/mascotLoadTokens.js';

// HTTP fixture handlers; the real API, download hook and reducer run in these tests.
const parseVideo = vi.fn();
const startDownload = vi.fn();
const getJob = vi.fn();
const summarizeVideo = vi.fn();
const getFile = vi.fn();
const membershipAccount = vi.fn();
const membershipPlans = vi.fn();
let saves;
const parseFixture = { title: 'T', formats: [{ format_id: 'b', label: '1080p', height: 1080, ext: 'mp4', direct: false }] };
const fileFixture = () => ({ ok: true, blob: async () => new Blob(['video']), headers: new Headers({ 'Content-Disposition': 'attachment; filename="actual.mp4"' }) });
async function beginServer() {
  await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/v');
  await userEvent.click(screen.getByRole('button', { name: '解析' }));
  await userEvent.click(await screen.findByRole('button', { name: '1080p MP4 · 含音频' }));
  await userEvent.click(screen.getByRole('button', { name: '下载', exact: true }));
}

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); clearAuthToken(); });

describe('App 功能闭环', () => {
  beforeEach(() => {
    vi.resetAllMocks(); mockAuth.status = 'authed'; mockAuth.user = { id: 'u1', email: 't@e.com' }; mockVisual.webgl = false; mockVisual.available = true; mockVisual.onTap = null; mockVisual.visual = true; mockVisual.instance = null;
    createBackground.mockImplementation(() => ({ resize: vi.fn(), destroy: vi.fn(), setIntensity: vi.fn() }));
    createMascot.mockImplementation(async (_app, _modelId, options) => {
      mockVisual.onTap = options.onTap;
      return (mockVisual.instance = visualFixture());
    });
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    setAuthToken('owner-token');
    saves = [];
    membershipAccount.mockResolvedValue({ plan: 'vip', status: 'active', checkout_available: false, features: { max_height: null, subtitles: true, translation: true, summary: true } });
    membershipPlans.mockResolvedValue({ enabled: false, checkout_available: false, price_label: null });
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
    getFile.mockImplementation(fileFixture);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { saves.push({ url: this.href, filename: this.download }); });
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: vi.fn(() => 'blob:app-video'), revokeObjectURL: vi.fn() }));
    vi.stubGlobal('fetch', vi.fn(async (path, options) => {
      const body = options.body ? JSON.parse(options.body) : {};
      try {
        let value;
        if (path === '/api/membership') value = await membershipAccount();
        else if (path === '/api/membership/plans') value = await membershipPlans();
        else if (path === '/api/parse') value = await parseVideo(body.url);
        else if (path === '/api/download') value = await startDownload(body.url, body.format_id, body.force_server);
        else if (path.startsWith('/api/job/')) value = await getJob(path.slice('/api/job/'.length));
        else if (path.startsWith('/api/file/')) return await getFile(path.slice('/api/file/'.length), options.signal);
        else if (path === '/api/summary') value = await summarizeVideo(body.url, body.subtitle_language || '', body.output_language, options.signal);
        else throw new Error(`Unexpected test HTTP request: ${path}`);
        return { ok: true, json: async () => value };
      } catch (error) {
        return { ok: false, json: async () => ({ detail: error }) };
      }
    }));
  });

  it('会员开通登录后保留意图并返回会员页，未自动创建支付', async () => {
    mockAuth.status = 'gate';
    membershipPlans.mockResolvedValue({ enabled: true, checkout_available: true, price_label: '$5 / 月', billing_mode: 'subscription' });
    const view = render(<App />);
    await userEvent.click(screen.getByRole('button', { name: '会员方案' }));
    expect(screen.getByRole('heading', { name: '选择适合你的下载方案' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '登录后开通 VIP' }));
    expect(screen.getByTestId('auth-scene')).toBeInTheDocument();
    mockAuth.status = 'authed';
    await act(async () => view.rerender(<App />));
    expect(screen.getByText(/已登录。请查看价格与计费说明/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '选择适合你的下载方案' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path === '/api/billing/checkout')).toBe(false);
  });

  it('免费账号解析选择可用720p，高清可见但不可点击', async () => {
    membershipAccount.mockResolvedValue({ plan: 'free', status: 'free', features: { max_height: 720, subtitles: false, translation: false, summary: false } });
    parseVideo.mockResolvedValue({ title: '免费版视频', formats: [{ format_id: 'hd', label: '1080p', height: 1080 }, { format_id: 'sd', label: '720p', height: 720 }] });
    render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/free');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    const hd = await screen.findByRole('button', { name: '1080p MP4 · 含音频 · VIP 专享' });
    expect(hd).toBeDisabled(); expect(screen.getByRole('button', { name: '720p MP4 · 含音频' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(screen.getByRole('button', { name: 'AI 总结' }));
    expect(screen.getByRole('heading', { name: '选择适合你的下载方案' })).toBeInTheDocument();
    expect(summarizeVideo).not.toHaveBeenCalled();
  });

  it('解析未发现字幕时仍可显式获取内容并生成总结', async () => {
    parseVideo.mockResolvedValue({ title: '字幕发现暂时失败', subtitles: [], formats: [{ format_id: 'b', label: '720p', height: 720, ext: 'mp4', direct: true }] });
    summarizeVideo.mockResolvedValue({ summary: '恢复获取后的摘要', key_points: ['内容要点'], provider: 'compatible', model: 'm' });
    render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/recovered');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    await screen.findByTestId('selecting-scene');
    await userEvent.click(screen.getByRole('button', { name: '720p MP4 · 含音频' }));
    expect(summarizeVideo).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: '生成总结' }));
    expect(await screen.findByTestId('summary-result')).toHaveTextContent('恢复获取后的摘要');
    expect(summarizeVideo).toHaveBeenCalledWith('https://example.com/recovered', '', 'zh-CN', expect.any(AbortSignal));
    expect(screen.getByRole('button', { name: '下载', exact: true })).toBeEnabled();
  });

  it('解析中返回取消请求，保留可编辑链接并忽略迟到结果', async () => {
    let resolveParse;
    parseVideo.mockImplementation(() => new Promise((resolve) => { resolveParse = resolve; }));
    render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/back');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    const signal = fetch.mock.calls.find(([path]) => path === '/api/parse')[1].signal;
    await userEvent.click(screen.getByRole('button', { name: '返回输入' }));
    expect(signal.aborted).toBe(true);
    expect(screen.getByLabelText('视频链接')).toHaveValue('https://example.com/back');
    expect(screen.getByLabelText('视频链接')).toHaveFocus();
    await act(async () => resolveParse(parseFixture));
    expect(screen.queryByTestId('selecting-scene')).toBeNull();
  });

  it('下载与完成保留同屏内容页签，返回中断迟到保存', async () => {
    let resolveFile;
    parseVideo.mockResolvedValue(parseFixture);
    startDownload.mockResolvedValue({ mode: 'server', job_id: 'j1' });
    getJob.mockResolvedValue({ id: 'j1', status: 'done' });
    getFile.mockImplementation(() => new Promise((resolve) => { resolveFile = resolve; }));
    render(<App />);
    await beginServer();
    expect(screen.getByRole('tablist', { name: '视频内容' })).toBeInTheDocument();
    await screen.findByTestId('done-scene', {}, { timeout: 5000 });
    expect(screen.getByRole('tab', { name: '总结摘要' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'T' })).toBeInTheDocument();
    const signal = getFile.mock.calls[0][1];
    await userEvent.click(screen.getByRole('button', { name: '返回输入' }));
    expect(signal.aborted).toBe(true);
    await act(async () => resolveFile(fileFixture()));
    expect(saves).toHaveLength(0);
    expect(screen.getByTestId('entry-scene')).toBeInTheDocument();
  }, 10000);

  it('下载发起失败保留视频信息与内容面板并提供返回', async () => {
    parseVideo.mockResolvedValue(parseFixture);
    startDownload.mockRejectedValue({ error_type: 'network', error: '下载连接失败' });
    render(<App />);
    await beginServer();
    await screen.findByTestId('error-scene');
    expect(screen.getByRole('heading', { name: 'T' })).toBeInTheDocument();
    expect(screen.getByRole('tablist', { name: '视频内容' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '返回输入' }));
    expect(screen.getByTestId('entry-scene')).toBeInTheDocument();
  });

  it('返回输入使迟到下载创建响应失效，不启动轮询或直链跳转', async () => {
    let resolveDownload;
    parseVideo.mockResolvedValue(parseFixture);
    startDownload.mockImplementation(() => new Promise((resolve) => { resolveDownload = resolve; }));
    render(<App />);
    await beginServer();
    const signal = fetch.mock.calls.find(([path]) => path === '/api/download')[1].signal;
    await userEvent.click(screen.getByRole('button', { name: '返回输入' }));
    expect(signal.aborted).toBe(true);
    await act(async () => resolveDownload({ mode: 'server', job_id: 'late-job' }));
    expect(getJob).not.toHaveBeenCalled();
    expect(screen.getByTestId('entry-scene')).toBeInTheDocument();
    expect(screen.queryByTestId('downloading-scene')).toBeNull();
  });

  it('解析完成默认选中首个有效格式，但不自动下载或生成总结', async () => {
    parseVideo.mockResolvedValue(parseFixture);
    render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/default-format');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    expect(await screen.findByRole('button', { name: '1080p MP4 · 含音频' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '下载', exact: true })).toBeEnabled();
    expect(startDownload).not.toHaveBeenCalled();
    expect(summarizeVideo).not.toHaveBeenCalled();
  });

  it.each(['字幕文本', '字幕翻译'])('左卡 AI 总结从%s使用当前语种，切回摘要并仅发起一次显式请求', async (tabName) => {
    parseVideo.mockResolvedValue({ ...parseFixture, subtitles: ['en', 'ja'] });
    summarizeVideo.mockResolvedValue({ summary: '按选定语言生成', key_points: ['要点'], provider: 'p', model: 'm' });
    render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/left-summary');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    await screen.findByTestId('selecting-scene');
    await userEvent.click(screen.getByRole('tab', { name: '字幕翻译' }));
    await userEvent.selectOptions(screen.getByLabelText('字幕语言'), 'ja');
    await userEvent.selectOptions(screen.getByLabelText('输出语言'), 'en');
    await userEvent.click(screen.getByRole('tab', { name: tabName }));
    await userEvent.click(screen.getByRole('button', { name: 'AI 总结' }));
    expect(screen.getByRole('tab', { name: '总结摘要' })).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByTestId('summary-result')).toHaveTextContent('按选定语言生成');
    expect(summarizeVideo).toHaveBeenCalledTimes(1);
    expect(summarizeVideo).toHaveBeenCalledWith('https://example.com/left-summary', 'ja', 'en', expect.any(AbortSignal));
    expect(startDownload).not.toHaveBeenCalled();
  });

  it('粘贴 → 解析 → 选清晰度 → 直链下载', async () => {
    // jsdom has no navigation; isolate only this browser side effect.
    const assign = vi.fn();
    vi.stubGlobal('window', new Proxy(window, { get: (target, key) => key === 'location' ? { assign } : Reflect.get(target, key) }));
    parseVideo.mockResolvedValue({
      title: '测试视频', thumbnail: null, duration: 125,
      formats: [
        { format_id: '720', label: '720p', height: 720, ext: 'mp4', direct: true },
        { format_id: '1080', label: '1080p', height: 1080, ext: 'mp4', direct: false },
      ],
    });
    startDownload.mockResolvedValue({ mode: 'direct', url: 'https://cdn/v.mp4', headers: {} });

    render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/v');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));

    expect(await screen.findByTestId('selecting-scene')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('checkbox', { name: '按视频标题命名' }));
    await userEvent.click(screen.getByRole('button', { name: '1080p MP4 · 含音频' }));
    await userEvent.click(screen.getByRole('button', { name: '下载' }));

    expect(startDownload).toHaveBeenCalledWith('https://example.com/v', '1080', false);
    expect(screen.getByTestId('downloading-scene')).toBeInTheDocument();
    expect(assign).toHaveBeenCalledWith('https://cdn/v.mp4');
  });

  it('服务端模式轮询到 done', async () => {
    parseVideo.mockResolvedValue({ title: 'T', thumbnail: null, duration: 1, formats: [{ format_id: 'b', label: '1080p', height: 1080, ext: 'mp4', direct: false }] });
    startDownload.mockResolvedValue({ mode: 'server', job_id: 'j1' });
    getJob.mockResolvedValueOnce({ id: 'j1', status: 'downloading', progress: 50 })
          .mockResolvedValueOnce({ id: 'j1', status: 'done', progress: 100, title: 'T' });

    render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/v');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    await userEvent.click(await screen.findByRole('button', { name: '1080p MP4 · 含音频' }));
    await userEvent.click(screen.getByRole('button', { name: '下载' }));

    expect(await screen.findByTestId('done-scene', {}, { timeout: 8000 })).toBeInTheDocument();
    expect(startDownload).toHaveBeenCalledWith('https://example.com/v', 'b', true);
    await waitFor(() => expect(saves).toEqual([{ url: 'blob:app-video', filename: 'actual.mp4' }]));
    expect(screen.getByRole('button', { name: /保存文件/ })).toBeEnabled();
    expect(screen.queryByRole('link', { name: /保存文件/ })).toBeNull();
    const protectedRequests = fetch.mock.calls.filter(([path]) => path.startsWith('/api/job/') || path.startsWith('/api/file/'));
    expect(protectedRequests.every(([, opts]) => opts.headers.Authorization === 'Bearer owner-token')).toBe(true);
    await userEvent.click(screen.getByRole('button', { name: /保存文件/ }));
    expect(saves).toHaveLength(2);
    expect(getFile).toHaveBeenCalledTimes(1);
  }, 15000);

  it('解析失败进入错误场景', async () => {
    parseVideo.mockRejectedValue({ error_type: 'invalid_url', error: '无效链接' });
    render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'not-a-url');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    expect(await screen.findByTestId('error-scene')).toBeInTheDocument();
    expect(screen.getByText('链接好像不对')).toBeInTheDocument();
  });

  it('平台安全校验错误显示明确提示且不自动重试或要求登录', async () => {
    const explanation = '平台暂未提供视频地址，请稍后重试。';
    parseVideo.mockRejectedValue({ error_type: 'verification_required', error: explanation });
    render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://www.bilibili.com/video/BV13vpG67ELM');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));

    const errorScene = await screen.findByTestId('error-scene');
    expect(screen.getByRole('heading', { name: '平台安全校验' })).toBeInTheDocument();
    expect(errorScene).toHaveTextContent(explanation);
    expect(errorScene).toHaveClass('err-drm');
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
    expect(screen.queryByText('需要登录')).toBeNull();
    expect(screen.queryByText('网络出错了')).toBeNull();
    expect(parseVideo).toHaveBeenCalledTimes(1);
    expect(startDownload).not.toHaveBeenCalled();
  });

  it.each(['invalid_url', 'geo_blocked', 'quota'])('渲染 %s 错误场景', async (type) => {
    parseVideo.mockRejectedValue({ error_type: type, error: 'x' });
    render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://x');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    expect(await screen.findByTestId('error-scene')).toBeInTheDocument();
  });

  it('访客默认显示首页与顶部登录入口，不加载角色', () => {
    mockAuth.status = 'gate';
    mockVisual.webgl = true;
    render(<App />);
    expect(screen.getByTestId('entry-scene')).toBeInTheDocument();
    expect(screen.queryByTestId('auth-scene')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '登录', exact: true })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: '页面导航' })).toBeInTheDocument();
    expect(screen.queryByTestId('preloader')).not.toBeInTheDocument();
    expect(createMascot).not.toHaveBeenCalled();
    expect(createBackground).not.toHaveBeenCalled();
  });

  it('访客解析留在首页提示顶部登录，不发业务请求', async () => {
    mockAuth.status = 'gate';
    render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/guest');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    expect(screen.getByRole('status')).toHaveTextContent('请先点击顶部登录按钮登录后再解析');
    expect(screen.getByTestId('entry-scene')).toBeInTheDocument();
    expect(screen.queryByTestId('auth-scene')).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
    expect(startDownload).not.toHaveBeenCalled();
    expect(summarizeVideo).not.toHaveBeenCalled();
  });

  it('只有顶部按钮打开登录，往返保留未提交草稿并恢复焦点', async () => {
    mockAuth.status = 'gate';
    render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/draft');
    await userEvent.click(screen.getByRole('button', { name: '登录', exact: true }));
    expect(screen.getByTestId('auth-scene')).toBeInTheDocument();
    expect(screen.getByLabelText('邮箱')).toHaveFocus();
    await userEvent.click(screen.getByRole('button', { name: '返回首页' }));
    expect(screen.getByLabelText('视频链接')).toHaveValue('https://example.com/draft');
    expect(screen.getByLabelText('视频链接')).toHaveFocus();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('认证恢复期间首页可输入，解析不发请求，恢复登录后保留输入且不自动解析', async () => {
    mockAuth.status = 'loading';
    const view = render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/restoring');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    expect(screen.getByRole('status')).toHaveTextContent('正在验证登录状态，请稍后再解析');
    expect(fetch).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: '登录', exact: true }));
    expect(screen.getByTestId('auth-scene')).toBeInTheDocument();
    expect(screen.queryByLabelText('邮箱')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: '返回首页' }));
    mockAuth.status = 'authed';
    await act(async () => view.rerender(<App />));
    expect(screen.getByLabelText('视频链接')).toHaveValue('https://example.com/restoring');
    expect(within(screen.getByTestId('entry-scene')).queryByRole('status')).toBeNull();
    expect(parseVideo).not.toHaveBeenCalled();
    expect(startDownload).not.toHaveBeenCalled();
  });

  it('认证恢复失败回到访客态时保留链接，提示同步为顶部登录且不发业务请求', async () => {
    mockAuth.status = 'loading';
    const view = render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/restore-failed');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    expect(screen.getByRole('status')).toHaveTextContent('正在验证登录状态');
    mockAuth.status = 'gate';
    view.rerender(<App />);
    expect(screen.getByLabelText('视频链接')).toHaveValue('https://example.com/restore-failed');
    expect(screen.getByRole('status')).toHaveTextContent('请先点击顶部登录按钮登录后再解析');
    expect(screen.getByRole('status')).not.toHaveTextContent('正在验证');
    expect(screen.queryByTestId('auth-scene')).toBeNull();
    expect(parseVideo).not.toHaveBeenCalled();
    expect(startDownload).not.toHaveBeenCalled();
  });

  it.each(['登录', '注册'])('%s成功返回首页保留访客草稿，显式解析才发请求', async (mode) => {
    mockAuth.status = 'gate';
    const view = render(<App />);
    const authenticate = mode === '登录' ? mockAuth.login : mockAuth.register;
    authenticate.mockImplementation(async () => {
      mockAuth.status = 'authed';
      view.rerender(<App />);
    });
    parseVideo.mockResolvedValue(parseFixture);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/after-login');
    await userEvent.click(screen.getByRole('button', { name: '登录', exact: true }));
    if (mode === '注册') await userEvent.click(within(screen.getByTestId('auth-scene')).getByRole('button', { name: '注册', exact: true }));
    await userEvent.type(screen.getByLabelText('邮箱'), 'guest@example.com');
    await userEvent.type(screen.getByLabelText('密码'), 'password123');
    await userEvent.click(screen.getByRole('button', { name: `立即${mode}` }));
    expect(screen.queryByTestId('auth-scene')).toBeNull();
    expect(screen.getByLabelText('视频链接')).toHaveValue('https://example.com/after-login');
    expect(screen.getByLabelText('视频链接')).toHaveFocus();
    expect(parseVideo).not.toHaveBeenCalled();
    expect(startDownload).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    await screen.findByTestId('selecting-scene');
    expect(parseVideo).toHaveBeenCalledWith('https://example.com/after-login');
  });

  it('退出清空当前账号输入，其他账号登录也不保留上一账号草稿', async () => {
    const view = render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/private');
    mockAuth.user = { id: 'u2', email: 'other@example.com' };
    view.rerender(<App />);
    expect(screen.getByLabelText('视频链接')).toHaveValue('');
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/private2');
    await userEvent.click(screen.getByRole('button', { name: '退出', exact: true }));
    mockAuth.status = 'gate';
    view.rerender(<App />);
    expect(screen.getByLabelText('视频链接')).toHaveValue('');
    expect(screen.queryByTestId('auth-scene')).toBeNull();
  });

  it('退出后清理下载会话，重新登录回到入口', async () => {
    parseVideo.mockRejectedValue({ error_type: 'invalid_url', error: '无效链接' });
    const view = render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'not-a-url');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    expect(await screen.findByTestId('error-scene')).toBeInTheDocument();

    mockAuth.status = 'gate';
    view.rerender(<App />);
    expect(screen.getByTestId('entry-scene')).toBeInTheDocument();
    expect(screen.queryByTestId('auth-scene')).toBeNull();

    mockAuth.status = 'authed';
    view.rerender(<App />);
    await waitFor(() => expect(screen.getByTestId('entry-scene')).toBeInTheDocument());
  });

  it('文件获取失败仍显示完成页，手动保存重试成功', async () => {
    parseVideo.mockResolvedValue(parseFixture);
    startDownload.mockResolvedValue({ mode: 'server', job_id: 'j1' });
    getJob.mockResolvedValue({ id: 'j1', status: 'done' });
    getFile.mockResolvedValueOnce({ ok: false, status: 404, json: async () => ({ detail: { error: '文件不可访问' } }) });
    render(<App />);
    await beginServer();
    expect(await screen.findByRole('alert', {}, { timeout: 5000 })).toHaveTextContent('文件不可访问');
    expect(screen.getByTestId('done-scene')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /保存文件/ }));
    await waitFor(() => expect(saves).toHaveLength(1));
    expect(screen.queryByRole('alert')).toBeNull();
  }, 10000);

  it('退出立即取消待保存文件，迟到结果不保存且重新登录回入口', async () => {
    let resolveFile;
    parseVideo.mockResolvedValue(parseFixture);
    startDownload.mockResolvedValue({ mode: 'server', job_id: 'j1' });
    getJob.mockResolvedValue({ id: 'j1', status: 'done' });
    getFile.mockImplementation(() => new Promise((resolve) => { resolveFile = resolve; }));
    const view = render(<App />);
    await beginServer();
    await screen.findByTestId('done-scene', {}, { timeout: 5000 });
    const saveButton = screen.getByRole('button', { name: /保存文件/ });
    expect(saveButton).toBeDisabled();
    expect(screen.getByText(/正在获取文件/)).toBeInTheDocument();
    const signal = getFile.mock.calls[0][1];
    await userEvent.click(screen.getByRole('button', { name: '退出', exact: true }));
    expect(signal.aborted).toBe(true);
    mockAuth.status = 'gate';
    view.rerender(<App />);
    await act(async () => resolveFile(fileFixture()));
    expect(saves).toHaveLength(0);
    mockAuth.status = 'authed'; mockAuth.user = { id: 'u2', email: 'new@e.com' }; setAuthToken('new-token');
    view.rerender(<App />);
    expect(screen.getByTestId('entry-scene')).toBeInTheDocument();
  }, 10000);

  it('账号更换后忽略旧解析响应', async () => {
    let resolveParse;
    parseVideo.mockImplementation(() => new Promise((resolve) => { resolveParse = resolve; }));
    const view = render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/old');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    const signal = fetch.mock.calls.find(([path]) => path === '/api/parse')[1].signal;
    mockAuth.user = { id: 'u2', email: 'new@e.com' };
    view.rerender(<App />);
    await act(async () => resolveParse(parseFixture));
    expect(signal.aborted).toBe(true);
    expect(screen.getByTestId('entry-scene')).toBeInTheDocument();
    expect(screen.queryByTestId('selecting-scene')).toBeNull();
  });

  it('点击模型可打开菜单且页面没有角色悬浮按钮', async () => {
    mockVisual.webgl = true;
    render(<App />);
    await waitFor(() => expect(mockVisual.onTap).toBeTypeOf('function'));
    expect(document.querySelector('.mascot-controls')).toBeNull();
    expect(screen.queryByRole('button', { name: '角色菜单', exact: true })).toBeNull();
    expect(screen.queryByRole('dialog', { name: '角色换装' })).toBeNull();
    act(() => mockVisual.onTap());
    const menu = screen.getByRole('dialog', { name: '角色换装' });
    expect(menu).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '短发', exact: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '围裙', exact: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '眼镜（方）', exact: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '哭', exact: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '变大', exact: true })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '变小', exact: true })).toBeInTheDocument();
  });

  it('只恢复示例网站前的唯一试试，角色提供独立可见区域标记', async () => {
    mockVisual.webgl = true;
    render(<App />);
    await waitFor(() => expect(document.querySelector('[data-mascot-interaction]')).toHaveAttribute('tabindex', '0'));
    const examples = document.querySelector('.landing-examples');
    expect(examples.firstElementChild).toHaveTextContent('试试');
    expect(screen.getAllByText('试试', { exact: true })).toHaveLength(1);
    expect(document.querySelector('[data-mascot-region]')).toBeNull();
    expect(createMascot.mock.calls.at(-1)[2].placementMode).toBe('free');
    expect(document.querySelector('[data-mascot-interaction]')).toHaveAttribute('data-follow-exclude', 'mascot');
  });

  it.each(['Enter', ' '])('已有角色区域支持键盘 %s 打开菜单', async (key) => {
    mockVisual.webgl = true;
    render(<App />);
    const region = document.querySelector('[data-mascot-interaction]');
    await waitFor(() => expect(region).toHaveAttribute('tabindex', '0'));
    expect(region).toHaveAttribute('role', 'button');
    expect(region).toHaveAttribute('aria-haspopup', 'dialog');
    expect(region.closest('.stage')).not.toBeNull();
    expect(createMascot.mock.calls.at(-1)[2].interactionTarget).toBe(region);
    expect(document.querySelector('[data-mascot-region]')).toBeNull();
    region.focus();
    fireEvent.keyDown(region, { key });
    expect(screen.getByRole('dialog', { name: '角色换装' })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: '角色换装' })).toBeNull();
    expect(region).toHaveFocus();
  });

  it('模型不可用时角色区域不接受键盘换装操作', async () => {
    mockVisual.webgl = true; mockVisual.available = false; mockVisual.visual = false;
    render(<App />);
    await act(async () => {});
    const region = document.querySelector('[data-mascot-interaction]');
    expect(region).toHaveAttribute('aria-disabled', 'true');
    expect(region).toHaveAttribute('tabindex', '-1');
    expect(region).toHaveAttribute('hidden');
    fireEvent.keyDown(region, { key: 'Enter' });
    expect(screen.queryByRole('dialog', { name: '角色换装' })).toBeNull();
  });
  it('嵌入角色不可见后关闭菜单，回焦主区域的可见输入', async () => {
    mockVisual.webgl = true; render(<App />);
    const target = document.querySelector('[data-mascot-interaction]');
    await waitFor(() => expect(target).toHaveAttribute('tabindex', '0'));
    target.focus(); fireEvent.keyDown(target, { key: 'Enter' });
    target.style.visibility = 'hidden'; fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.getByLabelText('视频链接')).toHaveFocus();
  });

  it('保留方向键手动移动，菜单开关和重新聚焦不暂停模型且保留业务输入', async () => {
    mockVisual.webgl = true;
    render(<App />);
    const target = document.querySelector('[data-mascot-interaction]');
    await waitFor(() => expect(target).toHaveAttribute('tabindex', '0'));
    const model = mockVisual.instance;
    const input = screen.getByLabelText('视频链接');
    fireEvent.change(input, { target: { value: 'https://example.com/kept' } });
    fireEvent.keyDown(target, { key: 'ArrowRight' });
    fireEvent.keyDown(target, { key: 'ArrowUp' });
    fireEvent.keyDown(target, { key: 'Home' });
    expect(model.moveBy.mock.calls).toEqual([[24, 0], [0, -24]]);
    expect(model.resetPosition).toHaveBeenCalledOnce();
    model.setMotionEnabled.mockClear();
    target.focus();
    fireEvent.keyDown(target, { key: 'Enter' });
    const menu = screen.getByRole('dialog', { name: '角色换装' });
    expect(model.setMotionEnabled).not.toHaveBeenCalledWith(false);
    for (const name of ['向上移动', '向下移动', '向左移动', '向右移动', '角色复位', '暂停活动', '恢复活动']) {
      expect(within(menu).queryByRole('button', { name })).toBeNull();
    }
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(model.setMotionEnabled).not.toHaveBeenCalledWith(false);
    expect(target).toHaveFocus();
    target.focus();
    fireEvent.keyDown(target, { key: 'Enter' });
    const reopenedMenu = screen.getByRole('dialog', { name: '角色换装' });
    expect(reopenedMenu).toBeVisible();
    expect(model.setMotionEnabled).not.toHaveBeenCalledWith(false);
    expect(input).toHaveValue('https://example.com/kept');
  });

  it('fallback仅显示静态角色，不展示空菜单或无效换装', async () => {
    mockVisual.webgl = true; mockVisual.available = false;
    render(<App />);
    const target = document.querySelector('[data-mascot-interaction]');
    await waitFor(() => expect(target).not.toHaveAttribute('hidden'));
    target.focus();
    fireEvent.keyDown(target, { key: 'Enter' });
    expect(target).toHaveAttribute('role', 'img');
    expect(target).toHaveAttribute('tabindex', '-1');
    expect(target).toHaveAttribute('aria-disabled', 'true');
    expect(screen.queryByRole('dialog', { hidden: true })).toBeNull();
    expect(document.querySelector('.expression-menu')).toBeNull();
    expect(screen.queryByRole('button', { name: '短发', exact: true })).toBeNull();
    expect(screen.queryByRole('button', { name: '变大', exact: true })).toBeNull();
  });

  it('角色等待显示明确提示，就绪后移除且不阻塞业务输入', async () => {
    mockVisual.webgl = true;
    let resolve;
    createMascot.mockImplementation(() => new Promise((done) => { resolve = done; }));
    const view = render(<App />);
    expect(screen.getByTestId('mascot-load-status')).toHaveTextContent('角色正在加载，首次打开可能需要几分钟；其他功能可正常使用。');
    expect(screen.getByLabelText('视频链接')).toBeEnabled();
    await act(async () => resolve(visualFixture()));
    expect(screen.queryByTestId('mascot-load-status')).toBeNull(); view.unmount();
  });

  it.each(['reject', 'no-visual'])('角色%s时明确提示刷新重试', async (failure) => {
    mockVisual.webgl = true;
    if (failure === 'reject') createMascot.mockRejectedValue(new Error('load failed'));
    else mockVisual.visual = false;
    render(<App />);
    await waitFor(() => expect(screen.getByTestId('mascot-load-status')).toHaveTextContent('角色加载失败。请刷新页面重试；其他功能可正常使用。'));
    expect(screen.getByLabelText('视频链接')).toBeEnabled();
  });

  it.each(['guest', 'mobile', 'no-webgl'])('角色加载提示不向%s显示', async (kind) => {
    mockVisual.webgl = kind !== 'no-webgl';
    if (kind === 'guest') mockAuth.status = 'gate';
    if (kind === 'mobile') phoneViewport(390);
    render(<App />); await act(async () => {});
    expect(screen.queryByTestId('mascot-load-status')).toBeNull(); expect(createMascot).not.toHaveBeenCalled();
  });

  it('角色等待卸载后迟到失败不挂回提示', async () => {
    mockVisual.webgl = true; let reject;
    createMascot.mockImplementation(() => new Promise((_resolve, fail) => { reject = fail; }));
    const view = render(<App />); expect(screen.getByTestId('mascot-load-status')).toBeInTheDocument();
    const signal = createMascot.mock.calls.at(-1)[2].signal;
    view.unmount(); expect(signal.aborted).toBe(true);
    await act(async () => reject(new Error('late failure')));
    expect(screen.queryByTestId('mascot-load-status')).toBeNull();
  });

  it('真实样式加载预算覆盖实际185秒传输后仍可就绪，不阻塞业务输入', async () => {
    vi.useFakeTimers(); installMascotLoadTokens(); mockVisual.webgl = true;
    let resolve;
    createMascot.mockImplementation(() => new Promise((done) => { resolve = done; }));
    const model = visualFixture(); const view = render(<App />);
    const signal = createMascot.mock.calls.at(-1)[2].signal;
    await act(async () => vi.advanceTimersByTime(185029));
    expect(signal.aborted).toBe(false);
    expect(screen.getByLabelText('视频链接')).toBeEnabled();
    await act(async () => resolve(model));
    expect(document.querySelector('[data-mascot-interaction]')).not.toHaveAttribute('hidden');
    expect(model.destroy).not.toHaveBeenCalled();
    view.unmount(); expect(signal.aborted).toBe(true); expect(model.destroy).toHaveBeenCalledOnce();
  });

  it('真实样式加载预算等待期间卸载立即取消并释放晚到模型', async () => {
    vi.useFakeTimers(); installMascotLoadTokens(); mockVisual.webgl = true;
    let resolve;
    createMascot.mockImplementation(() => new Promise((done) => { resolve = done; }));
    const model = visualFixture(); const view = render(<App />);
    const signal = createMascot.mock.calls.at(-1)[2].signal;
    await act(async () => vi.advanceTimersByTime(9000));
    expect(signal.aborted).toBe(false);
    view.unmount(); expect(signal.aborted).toBe(true);
    await act(async () => resolve(model)); expect(model.destroy).toHaveBeenCalledOnce();
  });

  it('真实样式加载预算到期取消，未无限等待且晚到实例仍被释放', async () => {
    vi.useFakeTimers(); installMascotLoadTokens(); mockVisual.webgl = true;
    let resolve;
    createMascot.mockImplementation(() => new Promise((done) => { resolve = done; }));
    const model = visualFixture(); const view = render(<App />);
    const signal = createMascot.mock.calls.at(-1)[2].signal;
    await act(async () => vi.advanceTimersByTime(299999)); expect(signal.aborted).toBe(false);
    await act(async () => vi.advanceTimersByTime(1)); expect(signal.aborted).toBe(true);
    expect(screen.getByTestId('mascot-load-status')).toHaveTextContent('角色加载超时。请刷新页面重试；其他功能可正常使用。');
    await act(async () => resolve(model)); expect(model.destroy).toHaveBeenCalledOnce();
    view.unmount();
  });

  it('慢模型不挡输入，超时取消且晚到结果只释放一次', async () => {
    vi.useFakeTimers();
    mockVisual.webgl = true;
    let resolve;
    createMascot.mockImplementation(() => new Promise((done) => { resolve = done; }));
    const model = visualFixture();
    const view = render(<App />);
    const signal = createMascot.mock.calls.at(-1)[2].signal;
    expect(screen.queryByTestId('preloader')).toBeNull();
    expect(screen.getByLabelText('视频链接')).toBeEnabled();
    await act(async () => vi.advanceTimersByTime(8000));
    expect(signal.aborted).toBe(true);
    await act(async () => resolve(model));
    expect(model.destroy).toHaveBeenCalledOnce();
    expect(document.querySelector('.mascot-controls')).toBeNull();
    expect(screen.queryByRole('button', { name: '角色菜单', exact: true })).toBeNull();
    view.unmount();
    expect(model.destroy).toHaveBeenCalledOnce();
    vi.useRealTimers();
  });

  it('未完成模型卸载时取消，拒绝结果不泄露且视觉资源清理一次', async () => {
    mockVisual.webgl = true;
    let reject;
    createMascot.mockImplementation(() => new Promise((_resolve, fail) => { reject = fail; }));
    const view = render(<App />);
    const signal = createMascot.mock.calls.at(-1)[2].signal;
    const bg = createBackground.mock.results.at(-1).value;
    view.unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => reject(new Error('cancelled')));
    expect(bg.destroy).toHaveBeenCalledOnce();
  });

  it('慢模型就绪时使用加载期间已经切换的新场景', async () => {
    mockVisual.webgl = true;
    let resolve;
    createMascot.mockImplementation(() => new Promise((done) => { resolve = done; }));
    const model = visualFixture();
    parseVideo.mockResolvedValue(parseFixture);
    render(<App />);
    fireEvent.change(screen.getByLabelText('视频链接'), { target: { value: 'https://example.com/new-scene' } });
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    await screen.findByTestId('selecting-scene');
    await act(async () => resolve(model));
    expect(model.setStageExpression.mock.calls[0]).toEqual(['selecting']);
  });

  it('卸载已就绪模型只销毁一次并取消加载controller', async () => {
    mockVisual.webgl = true;
    const model = visualFixture();
    createMascot.mockImplementation(async (_app, _id, { signal }) => {
      const dispose = () => model.destroy();
      signal.addEventListener('abort', dispose);
      model.destroy.mockImplementation(() => signal.removeEventListener('abort', dispose));
      return model;
    });
    const view = render(<App />);
    const target = document.querySelector('[data-mascot-interaction]');
    await waitFor(() => expect(target).toHaveAttribute('tabindex', '0'));
    const signal = createMascot.mock.calls.at(-1)[2].signal;
    view.unmount();
    expect(signal.aborted).toBe(true);
    expect(model.destroy).toHaveBeenCalledOnce();
  });

  it.each([390, 800])('手机宽度%s初始不创建任何角色或fallback，业务输入可聚焦', async (width) => {
    mockVisual.webgl = true;
    phoneViewport(width);
    parseVideo.mockResolvedValue(parseFixture);
    render(<App />);
    await act(async () => {});
    expect(createMascot).not.toHaveBeenCalled();
    expect(document.querySelector('[data-mascot-interaction], [data-mascot-region], .mascot-controls')).toBeNull();
    expect(screen.queryByRole('dialog', { hidden: true })).toBeNull();
    const input = screen.getByLabelText('视频链接');
    input.focus();
    expect(input).toHaveFocus();
    fireEvent.change(input, { target: { value: 'https://example.com/mobile' } });
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    expect(await screen.findByTestId('selecting-scene')).toBeInTheDocument();
    expect(createMascot).not.toHaveBeenCalled();
  });

  it.each(['Android', 'iPhone', 'iPod', 'IEMobile', 'Windows Phone'])('手机UA %s即使宽屏也不创建角色', async (ua) => {
    mockVisual.webgl = true;
    phoneViewport(1200);
    vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(`Mozilla/5.0 ${ua}`);
    render(<App />);
    await act(async () => {});
    expect(createMascot).not.toHaveBeenCalled();
    expect(document.querySelector('[data-mascot-interaction], .mascot-controls')).toBeNull();
  });

  it('桌面缩窄立即清理模型，菜单回焦业务输入，恢复宽屏可重新加载', async () => {
    mockVisual.webgl = true;
    const resize = phoneViewport(1200);
    render(<App />);
    const target = document.querySelector('[data-mascot-interaction]');
    await waitFor(() => expect(target).toHaveAttribute('tabindex', '0'));
    target.focus();
    fireEvent.keyDown(target, { key: 'Enter' });
    const model = mockVisual.instance;
    const signal = createMascot.mock.calls.at(-1)[2].signal;
    act(() => resize(800));
    expect(signal.aborted).toBe(true);
    expect(model.destroy).toHaveBeenCalledOnce();
    expect(document.querySelector('[data-mascot-interaction], .mascot-controls')).toBeNull();
    expect(screen.queryByRole('dialog', { hidden: true })).toBeNull();
    expect(screen.getByLabelText('视频链接')).toHaveFocus();
    expect(createMascot).toHaveBeenCalledTimes(1);
    act(() => resize(801));
    await waitFor(() => expect(target).toHaveAttribute('tabindex', '0'));
    expect(createMascot).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('桌面模型加载中缩窄取消请求并释放晚到模型', async () => {
    mockVisual.webgl = true;
    const resize = phoneViewport(1200);
    let resolve;
    createMascot.mockImplementation(() => new Promise((done) => { resolve = done; }));
    render(<App />);
    const signal = createMascot.mock.calls.at(-1)[2].signal;
    act(() => resize(390));
    expect(signal.aborted).toBe(true);
    const late = visualFixture();
    await act(async () => resolve(late));
    expect(late.destroy).toHaveBeenCalledOnce();
    expect(createMascot).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[data-mascot-interaction], .mascot-controls')).toBeNull();
    expect(screen.getByLabelText('视频链接')).toBeEnabled();
  });

  it('解析响应包含真实接口字段时仍显示封面与视频信息卡', async () => {
    // This is an HTTP unit fixture, not evidence of a live external extraction.
    parseVideo.mockResolvedValue({ ...parseFixture, title: '接口返回的视频', thumbnail: 'https://example.com/cover.jpg', duration: 125, uploader: '视频作者', platform: 'YouTube', view_count: 12500, description: '接口返回的视频简介' });
    render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/metadata');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    const selecting = await screen.findByTestId('selecting-scene');
    expect(selecting.querySelector('.format-card')).not.toBeNull();
    expect(selecting.querySelector('.cover img')).toHaveAttribute('src', 'https://example.com/cover.jpg');
    expect(screen.getByRole('heading', { name: '接口返回的视频' })).toBeInTheDocument();
    expect(screen.getByText('2:05')).toBeInTheDocument();
    expect(screen.getByText('视频作者')).toBeInTheDocument();
    expect(screen.getByText('YouTube', { exact: true })).toBeInTheDocument();
    expect(screen.getByText('1.3万')).toBeInTheDocument();
    expect(screen.getByText('接口返回的视频简介')).toBeInTheDocument();
  });
});
