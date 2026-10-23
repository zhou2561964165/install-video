import { describe, it, expect } from 'vitest';
import { formatDuration, formatViewCount, formatMetaLine, normalizeParse } from './videoAdapter.js';

describe('videoAdapter', () => {
  it('来源提供2160p时显示4K，保留真实格式ID与下载参数', () => {
    const selector = 'bestvideo[height<=2160]+bestaudio/best[height<=2160]';
    const out = normalizeParse({ formats: [
      { format_id: selector, label: '2160p 最佳 (视频+音频合并)', height: 2160, direct: false },
      { format_id: '1080', label: '1080p MP4', height: 1080 },
    ] });
    expect(out.formats[0].label).toBe('4K · 2160p 最佳 (视频+音频合并)');
    expect(out.formats[0].format_id).toBe(selector);
    expect(out.formats[0].direct).toBe(false);
    expect(out.formats[1].label).toBe('1080p MP4');
    expect(normalizeParse({ formats: [{ height: 2160, label: '4K 2160p' }] }).formats[0].label).toBe('4K 2160p');
  });
  it('formatDuration 秒 → m:ss / h:mm:ss', () => {
    expect(formatDuration(59)).toBe('0:59');
    expect(formatDuration(125)).toBe('2:05');
    expect(formatDuration(3600)).toBe('1:00:00');
  });

  it('formatDuration 空值/非法值返回空串', () => {
    expect(formatDuration(null)).toBe('');
    expect(formatDuration(undefined)).toBe('');
    expect(formatDuration(-1)).toBe('');
  });

  it('formatViewCount 万/亿/原样', () => {
    expect(formatViewCount(999)).toBe('999');
    expect(formatViewCount(12345)).toBe('1.2万');
    expect(formatViewCount(123456789)).toBe('1.2亿');
  });

  it('formatMetaLine 含音频/仅视频，has_audio 缺省按含音频', () => {
    expect(formatMetaLine({ ext: 'mp4', has_audio: true })).toBe('MP4 · 含音频');
    expect(formatMetaLine({ ext: 'webm', has_audio: false })).toBe('WEBM · 仅视频');
    expect(formatMetaLine({ ext: 'mp4' })).toBe('MP4 · 含音频');
  });

  it('normalizeParse 派生字段 + 透传原始字段', () => {
    const out = normalizeParse({
      title: 't',
      duration: 125,
      view_count: 12345,
      subtitles: ['zh-Hans'],
      formats: [{ format_id: '18', ext: 'mp4', has_audio: true }],
    });
    expect(out.title).toBe('t');
    expect(out.durationLabel).toBe('2:05');
    expect(out.viewCountLabel).toBe('1.2万');
    expect(out.subtitles).toEqual(['zh-Hans']);
    expect(out.formats[0].format_id).toBe('18');
    expect(out.formats[0].metaLine).toBe('MP4 · 含音频');
  });
});
