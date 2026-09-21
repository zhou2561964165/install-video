import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App.jsx';

vi.mock('pixi.js', () => ({}));
vi.mock('pixi-live2d-display', () => ({
  Live2DModel: {
    from: () => Promise.reject(new Error('no model in test')),
    registerTicker: () => {},
  },
}));
vi.mock('./pixi/stage.js', () => ({
  webglSupported: () => false,
  detectTier: () => 'none',
  initStage: vi.fn(),
  destroyStage: vi.fn(),
}));

vi.mock('./api.js', () => ({
  parseVideo: vi.fn(),
  startDownload: vi.fn(),
  getJob: vi.fn(),
  fileUrl: (id) => `/api/file/${id}`,
}));

import { parseVideo, startDownload, getJob } from './api.js';

describe('App 功能闭环', () => {
  beforeEach(() => vi.clearAllMocks());

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
    await userEvent.click(screen.getByRole('button', { name: '1080p · mp4' }));
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
    await userEvent.click(await screen.findByRole('button', { name: '1080p · mp4' }));
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
});
