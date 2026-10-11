import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App.jsx';

const mockVisual = vi.hoisted(() => ({ webgl: false, available: true, onTap: null }));

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
    return { isAvailable: () => mockVisual.available, resize: vi.fn(), destroy: vi.fn(), startRandomProps: vi.fn(), setStageExpression: vi.fn(), setExpression: vi.fn(), scaleBy: vi.fn() };
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

// HTTP fixture handlers; the real API, download hook and reducer run in these tests.
const parseVideo = vi.fn();
const startDownload = vi.fn();
const getJob = vi.fn();
const summarizeVideo = vi.fn();
const getFile = vi.fn();
let saves;
const parseFixture = { title: 'T', formats: [{ format_id: 'b', label: '1080p', height: 1080, ext: 'mp4', direct: false }] };
const fileFixture = () => ({ ok: true, blob: async () => new Blob(['video']), headers: new Headers({ 'Content-Disposition': 'attachment; filename="actual.mp4"' }) });
async function beginServer() {
  await userEvent.type(screen.getByLabelText('视频链接'), 'https://example.com/v');
  await userEvent.click(screen.getByRole('button', { name: '解析' }));
  await userEvent.click(await screen.findByRole('button', { name: '1080p MP4 · 含音频' }));
  await userEvent.click(screen.getByRole('button', { name: '下载', exact: true }));
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); clearAuthToken(); });

describe('App 功能闭环', () => {
  beforeEach(() => {
    vi.resetAllMocks(); mockAuth.status = 'authed'; mockAuth.user = { id: 'u1', email: 't@e.com' }; mockVisual.webgl = false; mockVisual.available = true; mockVisual.onTap = null;
    createBackground.mockImplementation(() => ({ resize: vi.fn(), destroy: vi.fn(), setIntensity: vi.fn() }));
    createMascot.mockImplementation(async (_app, _modelId, options) => {
      mockVisual.onTap = options.onTap;
      return { isAvailable: () => mockVisual.available, resize: vi.fn(), destroy: vi.fn(), startRandomProps: vi.fn(), setStageExpression: vi.fn(), setExpression: vi.fn(), scaleBy: vi.fn() };
    });
    vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
    setAuthToken('owner-token');
    saves = [];
    getFile.mockImplementation(fileFixture);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { saves.push({ url: this.href, filename: this.download }); });
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: vi.fn(() => 'blob:app-video'), revokeObjectURL: vi.fn() }));
    vi.stubGlobal('fetch', vi.fn(async (path, options) => {
      const body = options.body ? JSON.parse(options.body) : {};
      try {
        let value;
        if (path === '/api/parse') value = await parseVideo(body.url);
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

  it.each(['invalid_url', 'geo_blocked', 'quota'])('渲染 %s 错误场景', async (type) => {
    parseVideo.mockRejectedValue({ error_type: type, error: 'x' });
    render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'https://x');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    expect(await screen.findByTestId('error-scene')).toBeInTheDocument();
  });

  it('未登录时渲染登录场景（强制门）', () => {
    mockAuth.status = 'gate';
    mockVisual.webgl = true;
    render(<App />);
    expect(screen.getByTestId('auth-scene')).toBeInTheDocument();
    expect(screen.queryByLabelText('视频链接')).not.toBeInTheDocument();
    expect(screen.queryByTestId('preloader')).not.toBeInTheDocument();
    expect(createMascot).not.toHaveBeenCalled();
    expect(createBackground).not.toHaveBeenCalled();
  });

  it('退出后清理下载会话，重新登录回到入口', async () => {
    parseVideo.mockRejectedValue({ error_type: 'invalid_url', error: '无效链接' });
    const view = render(<App />);
    await userEvent.type(screen.getByLabelText('视频链接'), 'not-a-url');
    await userEvent.click(screen.getByRole('button', { name: '解析' }));
    expect(await screen.findByTestId('error-scene')).toBeInTheDocument();

    mockAuth.status = 'gate';
    view.rerender(<App />);
    expect(screen.getByTestId('auth-scene')).toBeInTheDocument();

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
    const signal = fetch.mock.calls[0][1].signal;
    mockAuth.user = { id: 'u2', email: 'new@e.com' };
    view.rerender(<App />);
    await act(async () => resolveParse(parseFixture));
    expect(signal.aborted).toBe(true);
    expect(screen.getByTestId('entry-scene')).toBeInTheDocument();
    expect(screen.queryByTestId('selecting-scene')).toBeNull();
  });

  it('不增设可见换装按键，原角色点击仍打开原菜单', async () => {
    mockVisual.webgl = true;
    render(<App />);
    await waitFor(() => expect(mockVisual.onTap).toBeTypeOf('function'));
    expect(document.querySelector('button.mascot-menu-trigger')).toBeNull();
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

  it.each(['Enter', ' '])('已有角色区域支持键盘 %s 打开菜单', async (key) => {
    mockVisual.webgl = true;
    render(<App />);
    const region = document.querySelector('[data-mascot-region]');
    await waitFor(() => expect(region).toHaveAttribute('tabindex', '0'));
    expect(region).toHaveAttribute('role', 'button');
    expect(region).toHaveAttribute('aria-haspopup', 'dialog');
    region.focus();
    fireEvent.keyDown(region, { key });
    expect(screen.getByRole('dialog', { name: '角色换装' })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: '角色换装' })).toBeNull();
    expect(region).toHaveFocus();
  });

  it('模型不可用时角色区域不接受键盘换装操作', async () => {
    mockVisual.webgl = true; mockVisual.available = false;
    render(<App />);
    await act(async () => {});
    const region = document.querySelector('[data-mascot-region]');
    expect(region).toHaveAttribute('aria-disabled', 'true');
    expect(region).toHaveAttribute('tabindex', '-1');
    fireEvent.keyDown(region, { key: 'Enter' });
    expect(screen.queryByRole('dialog', { name: '角色换装' })).toBeNull();
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
