import React from 'react';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('VideoInsights', () => {
  it('页签键盘切换不请求内容，保留各类缓存并显示真实来源链接', async () => {
    const insights = { ...baseInsights, summarize: vi.fn(), translate: vi.fn(), loadSubtitle: vi.fn(), active: 'summary',
      summary: { summary: '摘要', key_points: ['要点'], provider: 'p', model: 'm' },
      subtitle: { text: '<script>不可执行</script>', language: 'en' } };
    render(<VideoInsights languages={['en']} insights={insights} sourceUrl="https://example.com/video" />);
    const summary = screen.getByRole('tab', { name: '总结摘要' });
    fireEvent.keyDown(summary, { key: 'ArrowRight' });
    expect(screen.getByRole('tab', { name: '字幕文本' })).toHaveFocus();
    expect(screen.getByRole('tab', { name: '字幕文本' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('subtitle-result')).toHaveTextContent('<script>不可执行</script>');
    expect(screen.getByRole('link', { name: '视频来源' })).toHaveAttribute('href', 'https://example.com/video');
    expect(document.querySelector('script')).toBeNull();
    await userEvent.click(summary);
    expect(screen.getByTestId('summary-result')).toHaveTextContent('摘要');
    expect(insights.summarize).not.toHaveBeenCalled();
    expect(insights.translate).not.toHaveBeenCalled();
    expect(insights.loadSubtitle).not.toHaveBeenCalled();
  });
  it('提示长文支持范围与结果核对建议', () => {
    render(<VideoInsights languages={['en']} insights={baseInsights} />);
    const notice = screen.getByText('支持有长度上限的长文总结；处理可能需要较长时间，请对照原字幕核对结果。');
    expect(screen.getByRole('button', { name: '生成总结' })).toHaveAccessibleDescription(notice.textContent);
    expect(screen.getByRole('button', { name: '生成总结' })).toBeEnabled();
    expect(screen.getByRole('tab', { name: '字幕文本' })).toBeEnabled();
    expect(screen.getByRole('tab', { name: '字幕翻译' })).toBeEnabled();
  });

  it('长文不可用原因就地展示，不展示旧总结', () => {
    render(<VideoInsights languages={['en']} insights={{
      ...baseInsights,
      error: { error_type: 'summary_unsupported_length', error: '长文总结暂不支持，当前仅支持短篇和中篇总结。' },
    }} />);
    expect(screen.getByRole('alert')).toHaveTextContent('长文总结暂不支持');
    expect(screen.queryByTestId('summary-result')).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '字幕文本' })).toBeEnabled();
  });

  it('按选择的字幕/输出语言触发三个动作', async () => {
    const insights = { ...baseInsights, loadSubtitle: vi.fn(), translate: vi.fn(), summarize: vi.fn() };
    render(<VideoInsights languages={['en', 'ja']} insights={insights} />);
    await userEvent.selectOptions(screen.getByLabelText('输出语言'), 'ja');
    await userEvent.click(screen.getByRole('tab', { name: '字幕文本' }));
    await userEvent.click(screen.getByRole('button', { name: '查看字幕' }));
    await userEvent.click(screen.getByRole('tab', { name: '字幕翻译' }));
    await userEvent.click(screen.getByRole('button', { name: '翻译字幕' }));
    await userEvent.click(screen.getByRole('tab', { name: '总结摘要' }));
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

  it('安全渲染长文 Markdown，不执行 raw HTML、不加载远程图片并限定外链', () => {
    const markdown = [
      '# 长文标题',
      '',
      '正文包含 **重点**、`行内代码` 和完整条件。',
      '',
      '- 第一条要点',
      '- 第二条要点',
      '',
      '```text',
      '可滚动查看的代码片段',
      '```',
      '',
      '[参考资料](https://example.com/reference)',
      '[危险链接](javascript:alert%281%29)',
      '',
      '![远程图片](https://tracker.example/pixel.png)',
      '<script>window.__summaryInjected = true</script>',
      '<img src="https://tracker.example/raw.png" onerror="alert(1)">',
    ].join('\n');
    render(<VideoInsights languages={['en']} insights={{ ...baseInsights, active: 'summary', summary: {
      format: 'markdown', summary: markdown, key_points: [], provider: 'mock', model: 'm',
    } }} />);

    const result = screen.getByTestId('summary-markdown');
    expect(screen.getByRole('heading', { name: '长文标题' })).toBeInTheDocument();
    expect(result.querySelector('strong')).toHaveTextContent('重点');
    expect(result.querySelector('code')).toHaveTextContent('行内代码');
    expect(result.querySelector('pre code')).toHaveTextContent('可滚动查看的代码片段');
    expect(screen.getByRole('link', { name: '参考资料' })).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByRole('link', { name: '参考资料' })).toHaveAttribute('target', '_blank');
    expect(screen.queryByRole('link', { name: '危险链接' })).toBeNull();
    expect(screen.getByText('图片未加载：远程图片')).toBeInTheDocument();
    expect(document.querySelector('img, script')).toBeNull();
    expect(window.__summaryInjected).toBeUndefined();
    expect(screen.queryByRole('heading', { name: '关键要点' })).toBeNull();
  });

  it('复制与导出 Markdown 总结时保留原始完整文本', async () => {
    const markdown = '# 完整总结\n\n第一段。\n\n- 原始要点\n\n> 保留限定条件。';
    const insights = { ...baseInsights, active: 'summary', summary: {
      format: 'markdown', summary: markdown, key_points: [], provider: 'mock', model: 'm',
    } };
    let outputBlob;
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
    vi.stubGlobal('URL', Object.assign(class extends URL {}, {
      createObjectURL: vi.fn((blob) => { outputBlob = blob; return 'blob:markdown'; }),
      revokeObjectURL: vi.fn(),
    }));
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<VideoInsights insights={insights} />);

    await user.click(screen.getByRole('button', { name: '导出 TXT' }));
    const exported = await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.readAsText(outputBlob);
    });
    expect(exported).toBe(markdown);
    await user.click(screen.getByRole('button', { name: '复制' }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(markdown);
    expect(insights.summarize).not.toHaveBeenCalled();
  });

  it('无字幕和错误状态均就地展示', () => {
    render(<VideoInsights languages={[]} insights={{ ...baseInsights, error: { error: 'LLM 尚未配置' } }} />);
    expect(screen.getByText(/尚未检测到字幕/)).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('LLM 尚未配置');
  });

  it('缓存输出显示实际语种，当前选择不改写旧译文且错误属于发起页签', async () => {
    const insights = { ...baseInsights, translate: vi.fn(), translation: { text: '既有英文译文', target_language: 'en', provider: 'p', model: 'm' } };
    const view = render(<VideoInsights languages={['en', 'ja']} insights={insights} />);
    await userEvent.click(screen.getByRole('tab', { name: '字幕翻译' }));
    await userEvent.selectOptions(screen.getByLabelText('输出语言'), 'ja');
    expect(screen.getByRole('heading', { name: '字幕翻译 · en' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '翻译字幕' }));
    view.rerender(<VideoInsights languages={['en', 'ja']} insights={{ ...insights, translation: null, error: { error: '翻译失败' } }} />);
    expect(screen.getByRole('alert')).toHaveTextContent('翻译失败');
    await userEvent.click(screen.getByRole('tab', { name: '总结摘要' }));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByText('生成总结后，这里会显示内容概览和关键要点。')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: '字幕翻译' }));
    expect(screen.getByRole('alert')).toHaveTextContent('翻译失败');
  });

  it('TXT导出完整正文与要点并释放Blob，复制不调用模型', async () => {
    const insights = { ...baseInsights, summarize: vi.fn(), summary: { summary: '多行\n摘要', key_points: ['条件：不能省略'], provider: 'p', model: 'm' } };
    const exportCalls = [];
    let outputBlob;
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: vi.fn((blob) => { outputBlob = blob; return 'blob:insights'; }), revokeObjectURL: vi.fn() }));
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { exportCalls.push({ name: this.download, url: this.href }); });
    render(<VideoInsights insights={insights} title="视频/标题" />);
    await user.click(screen.getByRole('button', { name: '导出 TXT' }));
    expect(exportCalls).toEqual([{ name: '视频_标题-总结摘要.txt', url: 'blob:insights' }]);
    const exported = await new Promise((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(outputBlob); });
    expect(exported).toBe('多行\n摘要\n\n• 条件：不能省略');
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:insights'));
    await user.click(screen.getByRole('button', { name: '复制' }));
    expect(writeText).toHaveBeenCalledWith('多行\n摘要\n\n• 条件：不能省略');
    expect(screen.getByText('已复制内容')).toBeInTheDocument();
    expect(insights.summarize).not.toHaveBeenCalled();
  });

  it.each(['javascript:alert(1)', 'data:text/html,unsafe'])('不将不安全来源 %s 渲染为链接', (sourceUrl) => {
    render(<VideoInsights insights={{ ...baseInsights, summary: { summary: '摘要', key_points: [] } }} sourceUrl={sourceUrl} />);
    expect(screen.queryByRole('link')).toBeNull();
  });
});
