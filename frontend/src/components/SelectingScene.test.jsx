import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SelectingScene from './SelectingScene.jsx';
import { normalizeParse } from '../lib/videoAdapter.js';

const parseResult = normalizeParse({
  title: '测试视频',
  thumbnail: 'https://i.example/t.jpg',
  duration: 125,
  uploader: '某人',
  platform: 'youtube',
  view_count: 12345,
  description: '简介',
  formats: [
    { format_id: '18', label: '360p MP4 (1KB)', ext: 'mp4', has_audio: true, direct: true },
    { format_id: '137', label: '1080p MP4 (仅视频)', ext: 'mp4', has_audio: false, direct: false },
  ],
});

describe('SelectingScene 解析展示对齐参考站', () => {
  it('免费格式仍可查看，但超出720p禁用并就地提供升级入口', async () => {
    const onUpgrade = vi.fn();
    render(<SelectingScene parseResult={normalizeParse({ formats: [{ format_id: 'sd', label: '720p', height: 720 }, { format_id: 'hd', label: '1080p', height: 1080 }] })} selectedFormat={{ height: 1080 }} onSelect={vi.fn()} onDownload={vi.fn()} membership={{ plan: 'free', features: { max_height: 720 } }} onUpgrade={onUpgrade} />);
    expect(screen.getByRole('button', { name: '720p MP4 · 含音频' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '1080p MP4 · 含音频 · VIP 专享' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '下载', exact: true })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '查看 VIP 方案' })); expect(onUpgrade).toHaveBeenCalledOnce();
  });
  it('会员读取失败时不猜测权限，可手动刷新', async () => {
    const refresh = vi.fn(); render(<SelectingScene parseResult={parseResult} selectedFormat={parseResult.formats[0]} onSelect={vi.fn()} onDownload={vi.fn()} onUpgrade={vi.fn()} onMembershipRefresh={refresh} />);
    expect(screen.getByRole('button', { name: '下载', exact: true })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: '刷新会员状态' })); expect(refresh).toHaveBeenCalledOnce();
  });
  it('标题命名选项说明直链的文件名限制，取消后仍可显式走直链', async () => {
    const onSelect = vi.fn();
    const format = parseResult.formats[0];
    render(<SelectingScene parseResult={parseResult} selectedFormat={format} forceServer onSelect={onSelect} onDownload={() => {}} />);
    const naming = screen.getByRole('checkbox', { name: '按视频标题命名' });
    expect(naming).toBeChecked();
    expect(naming).toHaveAccessibleDescription('关闭后使用来源直链，文件名由来源站决定。');
    await userEvent.click(naming);
    expect(onSelect).toHaveBeenCalledWith(format, false);
  });

  it('按参考站顺序展示：封面时长角标→标题→up主/平台/播放量→简介→格式两行', () => {
    render(<SelectingScene parseResult={parseResult} selectedFormat={null} forceServer={false} onSelect={() => {}} onDownload={() => {}} />);
    expect(screen.getByText('测试视频')).toBeInTheDocument();
    expect(screen.getByText('2:05')).toBeInTheDocument();          // 时长角标
    expect(screen.getByText('某人')).toBeInTheDocument();          // up主
    expect(screen.getByText('youtube')).toBeInTheDocument();       // 平台
    expect(screen.getByText('1.2万')).toBeInTheDocument();         // 播放量
    expect(screen.getByText('简介')).toBeInTheDocument();          // 简介
    expect(screen.getByText('360p MP4 (1KB)')).toBeInTheDocument();
    expect(screen.getByText('1080p MP4 (仅视频)')).toBeInTheDocument();
    expect(screen.getByText('MP4 · 含音频')).toBeInTheDocument();
    expect(screen.getByText('MP4 · 仅视频')).toBeInTheDocument();
  });

  it('封面不带 Referer 请求，避免平台图床防盗链返回 403', () => {
    const { container } = render(<SelectingScene parseResult={parseResult} selectedFormat={null} forceServer={false} onSelect={() => {}} onDownload={() => {}} />);
    const img = container.querySelector('.cover img');
    expect(img).toHaveAttribute('src', 'https://i.example/t.jpg');
    expect(img).toHaveAttribute('referrerpolicy', 'no-referrer');
  });
});
