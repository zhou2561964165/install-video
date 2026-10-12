import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import VideoInsights from './VideoInsights.jsx';

const baseInsights = {
  loading: null,
  error: null,
  active: null,
  subtitle: null,
  translation: null,
  summary: null,
  loadSubtitle: vi.fn(),
  translate: vi.fn(),
  summarize: vi.fn(),
};

describe('VideoInsights', () => {
  it('明确提示长文暂不支持且短篇中篇正常使用', () => {
    render(<VideoInsights languages={['en']} insights={baseInsights} />);
    const notice = screen.getByText('当前支持短篇和中篇总结，长文总结暂不支持。');
    expect(screen.getByRole('button', { name: '生成总结' })).toHaveAccessibleDescription(notice.textContent);
    expect(screen.getByRole('button', { name: '生成总结' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '查看字幕' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '翻译字幕' })).toBeEnabled();
  });

  it('长文不可用原因就地展示，不展示旧总结', () => {
    render(<VideoInsights languages={['en']} insights={{
      ...baseInsights,
      error: { error_type: 'summary_unsupported_length', error: '长文总结暂不支持，当前仅支持短篇和中篇总结。' },
    }} />);
    expect(screen.getByRole('alert')).toHaveTextContent('长文总结暂不支持');
    expect(screen.queryByTestId('summary-result')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '查看字幕' })).toBeEnabled();
  });

  it('按选择的字幕/输出语言触发三个动作', async () => {
    const insights = { ...baseInsights, loadSubtitle: vi.fn(), translate: vi.fn(), summarize: vi.fn() };
    render(<VideoInsights languages={['en', 'ja']} insights={insights} />);
    await userEvent.selectOptions(screen.getByLabelText('输出语言'), 'ja');
    await userEvent.click(screen.getByRole('button', { name: '查看字幕' }));
    await userEvent.click(screen.getByRole('button', { name: '翻译字幕' }));
    await userEvent.click(screen.getByRole('button', { name: '生成总结' }));
    expect(insights.loadSubtitle).toHaveBeenCalledWith('en');
    expect(insights.translate).toHaveBeenCalledWith('en', 'ja');
    expect(insights.summarize).toHaveBeenCalledWith('en', 'ja');
  });

  it('展示总结与关键要点', () => {
    render(<VideoInsights languages={['en']} insights={{
      ...baseInsights,
      active: 'summary',
      summary: { summary: '这是摘要', key_points: ['要点一', '要点二'], provider: 'mock', model: 'm' },
    }} />);
    expect(screen.getByTestId('summary-result')).toHaveTextContent('这是摘要');
    expect(screen.getByText('要点一')).toBeInTheDocument();
  });

  it('无字幕和错误状态均就地展示', () => {
    render(<VideoInsights languages={[]} insights={{ ...baseInsights, error: { error: 'LLM 尚未配置' } }} />);
    expect(screen.getByText(/尚未检测到字幕/)).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('LLM 尚未配置');
  });
});
