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
