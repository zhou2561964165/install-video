import React from 'react';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
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
  it('free summary and subtitle actions lead to VIP while ASR and mindmap retain existing access', async () => {
    const onUpgrade = vi.fn(), transcribe = vi.fn(), mindmap = vi.fn(), summarize = vi.fn(), loadSubtitle = vi.fn();
    render(<VideoInsights insights={{ ...baseInsights, transcribe, mindmap, summarize, loadSubtitle }} membershipFeatures={{ subtitles: false, translation: false, summary: false }} onUpgrade={onUpgrade} />);
    await userEvent.click(screen.getByRole('button', { name: '查看 VIP 方案' }));
    expect(onUpgrade).toHaveBeenCalledOnce(); expect(summarize).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('tab', { name: '字幕文本' }));
    await userEvent.click(screen.getByRole('button', { name: '查看 VIP 方案' })); expect(loadSubtitle).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('tab', { name: '音频转写' }));
    await userEvent.click(screen.getByRole('button', { name: '转写音频' })); expect(transcribe).toHaveBeenCalledOnce();
    await userEvent.click(screen.getByRole('tab', { name: '思维导图' }));
    await userEvent.click(screen.getByRole('button', { name: '生成导图' })); expect(mindmap).toHaveBeenCalledOnce();
  });
  it('offers an upgrade when the server rejects a stale local entitlement', async () => {
    const onUpgrade = vi.fn();
    render(<VideoInsights insights={{ ...baseInsights, error: { error_type: 'membership_required', error: '此功能需要 VIP' }, errorKind: 'summary' }} membershipFeatures={{ summary: true }} onUpgrade={onUpgrade} />);
    expect(screen.getByRole('alert')).toHaveTextContent('此功能需要 VIP');
    await userEvent.click(screen.getByRole('button', { name: '查看 VIP 方案' })); expect(onUpgrade).toHaveBeenCalledOnce();
  });
  it('keeps ASR text separate from platform subtitles and identifies the actual recognized language', async () => {
    render(<VideoInsights languages={[]} insights={{ ...baseInsights, active: 'transcription',
      transcription: { language: 'en', text: '识别正文', segments: [{ start: 0, end: 1, text: '识别片段' }], provider: 'faster-whisper', model: 'tiny' },
      subtitle: { text: '平台原文', language: 'ja' },
    }} />);
    expect(screen.getByRole('heading', { name: '音频转写 · en' })).toBeInTheDocument();
    expect(screen.queryByText(/尚未检测到字幕/)).toBeNull();
    expect(screen.getByText('识别片段')).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('音频语言'), 'ja');
    expect(screen.getByRole('heading', { name: '音频转写 · en' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: '字幕文本' }));
    expect(screen.getByText('平台原文')).toBeInTheDocument();
    expect(screen.queryByText('识别正文')).toBeNull();
  });

  it('keeps untimed text usable and disables timed export instead of inventing timestamps', () => {
    const exportTimedSubtitle = vi.fn();
    render(<VideoInsights insights={{ ...baseInsights, active: 'subtitle', subtitle: { text: '没有时码的完整原文', language: 'en', segments: [{ start: -1, end: 3, text: '不合法' }, { start: 3, end: 2, text: '倒序' }] }, exportTimedSubtitle }} />);
    expect(screen.getByText('没有时码的完整原文')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '导出 SRT' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '导出 VTT' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '导出 TXT' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '导出 VTT' })).toHaveAccessibleDescription(/没有有效时码/);
    expect(exportTimedSubtitle).not.toHaveBeenCalled();
  });

  it('exports exact timed content with a safe filename and releases the blob URL', async () => {
    let outputBlob;
    const saved = [];
    const content = 'WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n原文\n';
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: vi.fn((blob) => { outputBlob = blob; return 'blob:timed'; }), revokeObjectURL: vi.fn() }));
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { saved.push(this.download); });
    render(<VideoInsights insights={{ ...baseInsights, active: 'subtitle', subtitle: { text: '原文', language: 'en', segments: [{ start: 0, end: 1, text: '原文' }] }, exportTimedSubtitle: vi.fn().mockResolvedValue({ filename: '../unsafe.vtt', content, format: 'vtt' }) }} />);
    await userEvent.click(screen.getByRole('button', { name: '导出 VTT' }));
    expect(saved).toEqual(['.._unsafe.vtt']);
    const exported = await new Promise((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(outputBlob); });
    expect(exported).toBe(content);
    expect(outputBlob.type).toBe('text/vtt;charset=utf-8');
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:timed'));
  });

  it('does not download a pending old-video export after the source URL changes', async () => {
    let resolveExport;
    const createObjectURL = vi.fn();
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL, revokeObjectURL: vi.fn() }));
    const insights = { ...baseInsights, active: 'subtitle', subtitle: { text: '旧原文', language: 'en', segments: [{ start: 0, end: 1, text: '旧原文' }] }, exportTimedSubtitle: vi.fn(() => new Promise((resolve) => { resolveExport = resolve; })) };
    const view = render(<VideoInsights sourceUrl="https://example.com/old" insights={insights} />);
    await userEvent.click(screen.getByRole('button', { name: '导出 SRT' }));
    view.rerender(<VideoInsights sourceUrl="https://example.com/new" insights={insights} />);
    await act(async () => resolveExport({ filename: 'old.srt', content: '旧原文', format: 'srt' }));
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(screen.queryByText('已导出 SRT')).toBeNull();
  });

  it.each(['srt', 'vtt'])('preserves the %s extension when a 124-character timed filename is shortened', async (format) => {
    const saved = [];
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: vi.fn(() => 'blob:long-name'), revokeObjectURL: vi.fn() }));
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { saved.push(this.download); });
    const filename = `${'长'.repeat(120)}.${format}`;
    expect(filename).toHaveLength(124);
    render(<VideoInsights insights={{ ...baseInsights, active: 'subtitle', subtitle: { text: '原文', language: 'en', segments: [{ start: 0, end: 1, text: '原文' }] }, exportTimedSubtitle: vi.fn().mockResolvedValue({ filename, content: '原文', format }) }} />);
    await userEvent.click(screen.getByRole('button', { name: `导出 ${format.toUpperCase()}` }));
    expect(saved).toEqual([`${'长'.repeat(116)}.${format}`]);
    expect(saved[0]).toHaveLength(120);
  });

  it('exposes cancel and busy status during export, and associates errors with their own tab', async () => {
    const cancel = vi.fn();
    const view = render(<VideoInsights insights={{ ...baseInsights, active: 'transcription', loading: 'transcription-export', cancel, transcription: { text: '识别正文', language: 'en' } }} />);
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText('正在导出时码文件…')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '取消处理' }));
    expect(cancel).toHaveBeenCalledTimes(1);
    view.rerender(<VideoInsights insights={{ ...baseInsights, errorKind: 'transcription', error: { error: '本地转写未启用' } }} />);
    expect(screen.getByRole('alert')).toHaveTextContent('本地转写未启用');
    await userEvent.click(screen.getByRole('tab', { name: '总结摘要' }));
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('supports Home and End across all five tabs without requesting content', () => {
    const insights = { ...baseInsights, transcribe: vi.fn(), mindmap: vi.fn() };
    render(<VideoInsights insights={insights} />);
    fireEvent.keyDown(screen.getByRole('tab', { name: '总结摘要' }), { key: 'End' });
    expect(screen.getByRole('tab', { name: '思维导图' })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole('tab', { name: '思维导图' }), { key: 'Home' });
    expect(screen.getByRole('tab', { name: '总结摘要' })).toHaveFocus();
    expect(insights.transcribe).not.toHaveBeenCalled();
    expect(insights.mindmap).not.toHaveBeenCalled();
  });

  it('reveals large timelines in finite pages while retaining complete plain text', async () => {
    const segments = Array.from({ length: 101 }, (_, index) => ({ start: index, end: index + 1, text: `片段${index}` }));
    render(<VideoInsights insights={{ ...baseInsights, active: 'subtitle', subtitle: { language: 'en', text: '完整正文', segments } }} />);
    expect(screen.getByText('完整正文')).toBeInTheDocument();
    expect(screen.queryByText('片段100')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: /显示更多时码/ }));
    expect(screen.getByText('片段100')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /显示更多时码/ })).toBeNull();
  });
  it('adds explicit ASR and mindmap tabs without auto requests or question answering', async () => {
    const insights = { ...baseInsights, transcribe: vi.fn(), mindmap: vi.fn() };
    render(<VideoInsights languages={['zh-CN']} insights={insights} />);
    await userEvent.click(screen.getByRole('tab', { name: '音频转写' }));
    expect(insights.transcribe).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('输出语言')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: '转写音频' }));
    expect(insights.transcribe).toHaveBeenCalledWith('');
    await userEvent.click(screen.getByRole('tab', { name: '思维导图' }));
    expect(insights.mindmap).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: '生成导图' }));
    expect(insights.mindmap).toHaveBeenCalledWith('zh-CN', 'zh-CN');
    expect(screen.queryByRole('tab', { name: /问答/ })).toBeNull();
  });

  it('shows timed subtitle text and exports cached language independently of current selection', async () => {
    const insights = { ...baseInsights, active: 'subtitle', subtitle: { language: 'en', text: '完整字幕', segments: [{ start: 1.25, end: 3.5, text: '时间段内容' }] }, exportTimedSubtitle: vi.fn().mockResolvedValue(undefined) };
    render(<VideoInsights languages={['en', 'ja']} insights={insights} />);
    expect(screen.getByText('00:00:01.250 → 00:00:03.500')).toBeInTheDocument();
    expect(screen.getByText('完整字幕')).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('字幕语言'), 'ja');
    await userEvent.click(screen.getByRole('button', { name: '导出 VTT' }));
    expect(insights.exportTimedSubtitle).toHaveBeenCalledWith('vtt', 'subtitle');
  });

  it('renders mindmap labels as safe collapsible text and preserves local JSON/Markdown exports', async () => {
    render(<VideoInsights insights={{ ...baseInsights, active: 'mindmap', mindmapResult: { root: { label: '主题', children: [{ label: '<img src=x onerror=alert(1)>', children: [{ label: '详细条件', children: [] }] }] } } }} />);
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(document.querySelector('img, script')).toBeNull();
    expect(screen.getByRole('button', { name: '导出 JSON' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '导出 Markdown' })).toBeEnabled();
    const branch = screen.getByText('<img src=x onerror=alert(1)>').closest('details');
    expect(branch).toHaveAttribute('open');
    await userEvent.click(screen.getByText('<img src=x onerror=alert(1)>'));
    expect(branch).not.toHaveAttribute('open');
  });

  it('copies and exports the complete mindmap locally, including collapsed descendants', async () => {
    const result = { title: '主题', source_language: 'en', root: { label: '概览', children: [{ label: '条件', children: [{ label: '完整限定', children: [] }] }] }, provider: 'p', model: 'm' };
    const blobs = [];
    const names = [];
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: vi.fn((blob) => { blobs.push(blob); return 'blob:mindmap'; }), revokeObjectURL: vi.fn() }));
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { names.push(this.download); });
    const insights = { ...baseInsights, active: 'mindmap', mindmapResult: result, mindmap: vi.fn() };
    render(<VideoInsights insights={insights} title="主题" />);
    await user.click(screen.getByText('条件'));
    await user.click(screen.getByRole('button', { name: '复制' }));
    expect(writeText).toHaveBeenCalledWith('- 概览\n  - 条件\n    - 完整限定');
    await user.click(screen.getByRole('button', { name: '导出 Markdown' }));
    await user.click(screen.getByRole('button', { name: '导出 JSON' }));
    const contents = await Promise.all(blobs.map((blob) => new Promise((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(blob); })));
    expect(contents[0]).toBe('- 概览\n  - 条件\n    - 完整限定');
    expect(JSON.parse(contents[1])).toEqual(result);
    expect(names).toEqual(['主题-思维导图.md', '主题-思维导图.json']);
    expect(insights.mindmap).not.toHaveBeenCalled();
  });
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
    expect(screen.getByRole('heading', { level: 3, name: '内容总结' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 4, name: '概览' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '总结', exact: true })).toBeNull();
  });

  it('按标题、概览、分层主题和总结呈现结构化内容并完整复制导出', async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
    let outputBlob;
    vi.stubGlobal('URL', Object.assign(class extends URL {}, {
      createObjectURL: vi.fn((blob) => { outputBlob = blob; return 'blob:structured-summary'; }), revokeObjectURL: vi.fn(),
    }));
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<VideoInsights title="原视频标题" insights={{ ...baseInsights, summary: {
      title: '计算器：从算术到程序执行', summary: '解释计算器的**能力边界**。',
      key_points: ['## 算术计算\n\n仅处理算术表达式。\n\n### 条件与限制\n\n不执行完整程序。', '## 后续扩展\n\n以教学示例说明程序执行。'],
      conclusion: '算术求值与完整程序执行的范围不同。',
    } }} />);
    expect(screen.getAllByRole('heading').map((heading) => [heading.tagName, heading.textContent])).toEqual([
      ['H3', '计算器：从算术到程序执行'], ['H4', '概览'], ['H4', '关键要点'],
      ['H5', '算术计算'], ['H6', '条件与限制'], ['H5', '后续扩展'], ['H4', '总结'],
    ]);
    expect(screen.queryByRole('heading', { name: '原视频标题' })).toBeNull();
    expect(screen.getByText('能力边界').tagName).toBe('STRONG');
    const expected = '# 计算器：从算术到程序执行\n\n## 概览\n\n解释计算器的**能力边界**。\n\n## 关键要点\n\n### 算术计算\n\n仅处理算术表达式。\n\n#### 条件与限制\n\n不执行完整程序。\n\n### 后续扩展\n\n以教学示例说明程序执行。\n\n## 总结\n\n算术求值与完整程序执行的范围不同。';
    await user.click(screen.getByRole('button', { name: '复制' }));
    expect(writeText).toHaveBeenCalledWith(expected);
    await user.click(screen.getByRole('button', { name: '导出 TXT' }));
    const exported = await new Promise((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(outputBlob); });
    expect(exported).toBe(expected);
  });

  it('结构化 Markdown 避免跳级和危险内容，旧结果不凭空生成总结', () => {
    render(<VideoInsights title="原始标题" insights={{ ...baseInsights, summary: {
      summary: '概览[危险](javascript:alert%281%29)',
      key_points: ['## 主题\n\n#### 深层说明\n\n![追踪图](https://tracker.example/pixel)\n\n<script>alert(1)</script>'],
    } }} />);
    expect(screen.getAllByRole('heading').map((heading) => heading.tagName)).toEqual(['H3', 'H4', 'H4', 'H5', 'H6']);
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('图片未加载：追踪图')).toBeInTheDocument();
    expect(document.querySelector('img, script')).toBeNull();
    expect(screen.queryByRole('heading', { name: '原始标题' })).toBeNull();
    expect(screen.queryByRole('heading', { name: '总结', exact: true })).toBeNull();
  });

  it('完整 Markdown 标题和二三级主题按文章层次展示，保留最后总结', () => {
    render(<VideoInsights insights={{ ...baseInsights, summary: { format: 'markdown', summary: '# 标题概括\n\n## 主体主题\n\n### 细节条件\n\n详细内容。\n\n## 总结\n\n最终归纳。' } }} />);
    expect(screen.getAllByRole('heading').map((heading) => [heading.tagName, heading.textContent])).toEqual([
      ['H3', '内容总结'], ['H4', '标题概括'], ['H5', '主体主题'], ['H6', '细节条件'], ['H5', '总结'],
    ]);
    expect(screen.getByText('最终归纳。')).toBeInTheDocument();
  });

  it('缺少可选标题和总结时仍复制分层主题，不改变代码围栏里的标题字符', async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
    const point = '## 实验步骤\n\n```markdown\n## 代码内的原文\n```\n\n### 使用条件\n\n保留条件。';
    render(<VideoInsights insights={{ ...baseInsights, summary: { summary: '实验概览。', key_points: [point] } }} />);
    await user.click(screen.getByRole('button', { name: '复制' }));
    expect(writeText).toHaveBeenCalledWith('## 概览\n\n实验概览。\n\n## 关键要点\n\n### 实验步骤\n\n```markdown\n## 代码内的原文\n```\n\n#### 使用条件\n\n保留条件。');
    expect(screen.queryByRole('heading', { name: '代码内的原文' })).toBeNull();
    expect(document.querySelector('pre code')).toHaveTextContent('## 代码内的原文');
    expect(screen.queryByRole('heading', { name: '总结', exact: true })).toBeNull();
  });

  it('概括标题保持安全文本，总结遵循相同Markdown安全规则', () => {
    render(<VideoInsights insights={{ ...baseInsights, summary: {
      title: '<img src=x onerror=alert(1)>', summary: '概览。', key_points: [],
      conclusion: '**结论**：[安全资料](https://example.com/final)；[危险资料](data:text/html,unsafe)。\n\n![远程结论图](https://tracker.example/final)',
    } }} />);
    expect(screen.getByRole('heading', { level: 3, name: '<img src=x onerror=alert(1)>' })).toBeInTheDocument();
    expect(screen.getByText('结论').tagName).toBe('STRONG');
    expect(screen.getByRole('link', { name: '安全资料' })).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.queryByRole('link', { name: '危险资料' })).toBeNull();
    expect(document.querySelector('img, script')).toBeNull();
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
