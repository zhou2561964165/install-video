import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App.jsx';

const mockVisual = vi.hoisted(() => ({ webgl: false }));

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

vi.mock('./api.js', () => ({
  parseVideo: vi.fn(),
  startDownload: vi.fn(),
  getJob: vi.fn(),
  getSubtitle: vi.fn(),
  translateSubtitle: vi.fn(),
  summarizeVideo: vi.fn(),
  fileUrl: (id) => `/api/file/${id}`,
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

import { parseVideo, startDownload, getJob, summarizeVideo } from './api.js';

describe('App 功能闭环', () => {
  beforeEach(() => { vi.clearAllMocks(); mockAuth.status = 'authed'; mockVisual.webgl = false; });

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
    expect(screen.getByRole('link', { name: /保存文件/ })).toHaveAttribute('href', '/api/file/j1');
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
});
