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
