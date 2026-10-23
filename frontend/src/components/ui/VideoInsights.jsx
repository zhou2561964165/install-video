import React, { forwardRef, useEffect, useId, useImperativeHandle, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { INSIGHT_TABS, SUMMARY_SUPPORT_NOTICE, TARGET_LANGUAGES, TRANSCRIPTION_LANGUAGES, TIMELINE_PAGE_SIZE } from '../../state/insightConfig.js';
import { saveFile } from '../../lib/saveFile.js';
import VideoIcon from './VideoIcon.jsx';
import MindMapView, { mindmapMarkdown } from './MindMapView.jsx';

const loadingLabel = { subtitle: '正在读取字幕…', translation: '正在翻译字幕…', summary: '正在生成总结…', transcription: '正在检查本地转写并识别音频…', mindmap: '正在生成思维导图…' };
const safeFilename = (value) => {
  const name = String(value || '视频内容').replace(/[\\/:*?"<>|\u0000-\u001f\u007f]/g, '_');
  const extension = name.match(/\.[a-z0-9]{1,10}$/i)?.[0] || '';
  return extension ? `${name.slice(0, -extension.length).slice(0, 120 - extension.length)}${extension}` : name.slice(0, 120);
};
const timestamp = (seconds) => {
  const milliseconds = Math.round(seconds * 1000);
  return `${String(Math.floor(milliseconds / 3600000)).padStart(2, '0')}:${String(Math.floor(milliseconds / 60000) % 60).padStart(2, '0')}:${String(Math.floor(milliseconds / 1000) % 60).padStart(2, '0')}.${String(milliseconds % 1000).padStart(3, '0')}`;
};
const sourceLink = (value) => {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; } catch { return null; }
};
const markdownComponents = {
  a: ({ href, children }) => {
    const safeHref = sourceLink(href);
    return safeHref
      ? <a href={safeHref} target="_blank" rel="noopener noreferrer">{children}</a>
      : <>{children}</>;
  },
  // Remote images can disclose that a summary was opened. Keep the alt text without fetching them.
  img: ({ alt }) => <span className="video-insights__markdown-image">{alt ? `图片未加载：${alt}` : '图片未加载'}</span>,
};

// Fit a generated document below the workspace heading without changing its text.
const rebaseSummaryHeadings = ({ baseDepth }) => (tree) => {
  const headings = [];
  const collect = (node) => {
    if (node.type === 'heading') headings.push(node);
    node.children?.forEach(collect);
  };
  collect(tree);
  const sourceDepth = Math.min(...headings.map((node) => node.depth));
  let previousDepth = baseDepth - 1;
  headings.forEach((node) => {
    node.depth = Math.min(baseDepth + node.depth - sourceDepth, previousDepth + 1, 6);
    previousDepth = node.depth;
  });
};
const documentHeadingPlugins = [[rebaseSummaryHeadings, { baseDepth: 4 }]];
const sectionHeadingPlugins = [[rebaseSummaryHeadings, { baseDepth: 5 }]];
const SummaryMarkdown = ({ children, document = false }) => <ReactMarkdown
  components={markdownComponents} remarkPlugins={document ? documentHeadingPlugins : sectionHeadingPlugins}
>{children || ''}</ReactMarkdown>;

const structuredSummaryText = (result) => {
  const points = result.key_points || [];
  // Only indent Markdown headings outside fenced examples; preserve all prose/code.
  const nestedPoint = (point) => {
    let fence;
    let hasHeading = false;
    const nested = point.split('\n').map((line) => {
      const marker = line.match(/^ {0,3}(`{3,}|~{3,})/);
      if (marker) {
        if (!fence) fence = marker[1];
        else if (marker[1][0] === fence[0] && marker[1].length >= fence.length && /^\s*$/.test(line.slice(marker[0].length))) fence = undefined;
        return line;
      }
      if (fence || !/^ {0,3}#{1,6}\s/.test(line)) return line;
      hasHeading = true;
      return line.replace(/^( {0,3})(#{1,6})(?=\s)/, (_, indent, hashes) => `${indent}${'#'.repeat(Math.min(hashes.length + 1, 6))}`);
    }).join('\n');
    return { text: hasHeading ? nested : `• ${point}`, hasHeading };
  };
  const nestedPoints = points.map(nestedPoint);
  if (!result.title?.trim() && !result.conclusion?.trim() && !nestedPoints.some((point) => point.hasHeading)) {
    return [result.summary, ...points.map((point) => `• ${point}`)].join('\n\n');
  }
  return [
    result.title?.trim() && `# ${result.title}`,
    result.summary && `## 概览\n\n${result.summary}`,
    points.length && `## 关键要点\n\n${nestedPoints.map((point) => point.text).join('\n\n')}`,
    result.conclusion?.trim() && `## 总结\n\n${result.conclusion}`,
  ].filter(Boolean).join('\n\n');
};

const VideoInsights = forwardRef(function VideoInsights({ languages = [], insights, title = '视频内容', sourceUrl, membershipFeatures, onUpgrade }, ref) {
  const id = useId();
  const tabRefs = useRef([]);
  const localActionId = useRef(0);
  const [tab, setTab] = useState(insights.active || 'summary');
  const [errorTab, setErrorTab] = useState(insights.loading || insights.active || 'summary');
  const [sourceLanguage, setSourceLanguage] = useState(languages[0] || '');
  const [targetLanguage, setTargetLanguage] = useState(TARGET_LANGUAGES[0].value);
  const [transcriptionLanguage, setTranscriptionLanguage] = useState('');
  const [localStatus, setLocalStatus] = useState('');
  const [visibleSegments, setVisibleSegments] = useState(TIMELINE_PAGE_SIZE);

  useEffect(() => {
    localActionId.current += 1;
    setLocalStatus('');
    return () => { localActionId.current += 1; };
  }, [sourceUrl]);
  useEffect(() => {
    setSourceLanguage((current) => (current && languages.includes(current) ? current : languages[0] || ''));
  }, [languages]);
  const busy = Boolean(insights.loading);
  const result = tab === 'mindmap' ? insights.mindmapResult : insights[tab];
  const timedContent = tab === 'subtitle' || tab === 'transcription';
  const segments = timedContent ? (result?.segments || []).filter((segment) => Number.isFinite(segment.start) && Number.isFinite(segment.end) && segment.start >= 0 && segment.end > segment.start) : [];
  const tabLoading = insights.loading === tab || insights.loading === `${tab}-export`;
  const tabError = insights.error && (insights.errorKind || errorTab) === tab;
  const isMarkdownSummary = tab === 'summary' && result?.format === 'markdown';
  const config = INSIGHT_TABS.find((item) => item.key === tab);
  const featureKey = { subtitle: 'subtitles', translation: 'translation', summary: 'summary' };
  const requiresVip = (kind) => membershipFeatures?.[featureKey[kind]] === false;
  const text = !result ? '' : tab === 'summary'
    ? (isMarkdownSummary ? result.summary : structuredSummaryText(result))
    : tab === 'mindmap' ? mindmapMarkdown(result.root) : result.text;
  const href = sourceLink(sourceUrl);
  useEffect(() => { setVisibleSegments(TIMELINE_PAGE_SIZE); }, [result]);

  const chooseTab = (key) => { localActionId.current += 1; setTab(key); setLocalStatus(''); };
  const handleKeys = (event, index) => {
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % INSIGHT_TABS.length;
    if (event.key === 'ArrowLeft') next = (index + INSIGHT_TABS.length - 1) % INSIGHT_TABS.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = INSIGHT_TABS.length - 1;
    if (next === undefined) return;
    event.preventDefault();
    chooseTab(INSIGHT_TABS[next].key);
    tabRefs.current[next]?.focus();
  };
  const run = () => {
    if (requiresVip(tab)) { onUpgrade?.(); return; }
    localActionId.current += 1;
    setErrorTab(tab);
    setLocalStatus('');
    if (tab === 'subtitle') insights.loadSubtitle(sourceLanguage);
    if (tab === 'translation') insights.translate(sourceLanguage, targetLanguage);
    if (tab === 'summary') insights.summarize(sourceLanguage, targetLanguage);
    if (tab === 'transcription') insights.transcribe(transcriptionLanguage);
    if (tab === 'mindmap') insights.mindmap(sourceLanguage, targetLanguage);
  };
  // 左侧显式总结入口只暴露一个动作，语种及页签仍由内容组件管理。
  useImperativeHandle(ref, () => ({
    summarizeCurrent() {
      if (busy) return;
      chooseTab('summary');
      if (requiresVip('summary')) { onUpgrade?.(); return; }
      setErrorTab('summary');
      insights.summarize(sourceLanguage, targetLanguage);
    },
  }), [busy, insights.summarize, sourceLanguage, targetLanguage, membershipFeatures, onUpgrade]);
  const copy = async () => {
    const actionId = localActionId.current;
    try { await navigator.clipboard.writeText(text); if (actionId === localActionId.current) setLocalStatus('已复制内容'); }
    catch { if (actionId === localActionId.current) setLocalStatus('复制失败，可选择文本后手动复制。'); }
  };
  const saveContent = (content, filename, type, label) => {
    let url;
    try {
      url = URL.createObjectURL(new Blob([content], { type }));
      saveFile(url, safeFilename(filename));
      setLocalStatus(`已导出 ${label}`);
    } catch { setLocalStatus('导出失败，请重试。'); }
    finally { if (url) setTimeout(() => URL.revokeObjectURL(url), 0); }
  };
  const exportText = () => saveContent(text, `${safeFilename(title).slice(0, 100)}-${config.label}.txt`, 'text/plain;charset=utf-8', 'TXT');
  const exportMindmap = (format) => saveContent(format === 'json' ? JSON.stringify(result, null, 2) : text, `${safeFilename(title).slice(0, 100)}-思维导图.${format === 'json' ? 'json' : 'md'}`, format === 'json' ? 'application/json;charset=utf-8' : 'text/markdown;charset=utf-8', format === 'json' ? 'JSON' : 'Markdown');
  const exportTimed = async (format) => {
    const actionId = ++localActionId.current;
    setLocalStatus('');
    try {
      const file = await insights.exportTimedSubtitle(format, tab);
      if (file && actionId === localActionId.current) saveContent(file.content, file.filename, format === 'vtt' ? 'text/vtt;charset=utf-8' : 'application/x-subrip;charset=utf-8', format.toUpperCase());
    } catch { if (actionId === localActionId.current) setLocalStatus('导出失败，请重试。'); }
  };

  return (
    <section className="video-insights" data-follow-exclude="panel" aria-label="视频内容工作区">
      <div className="video-insights__tabs" role="tablist" aria-label="视频内容">
        {INSIGHT_TABS.map((item, index) => <button key={item.key} type="button" role="tab"
          id={`${id}-tab-${item.key}`} aria-controls={`${id}-panel-${item.key}`} aria-selected={tab === item.key}
          tabIndex={tab === item.key ? 0 : -1} ref={(node) => { tabRefs.current[index] = node; }}
          onKeyDown={(event) => handleKeys(event, index)} onClick={() => chooseTab(item.key)}>
          <VideoIcon name={item.key} />{item.label}
        </button>)}
      </div>
      {INSIGHT_TABS.map((item) => <div key={item.key} role="tabpanel" id={`${id}-panel-${item.key}`}
        aria-labelledby={`${id}-tab-${item.key}`} hidden={tab !== item.key} tabIndex={0}
        className="video-insights__panel" aria-busy={insights.loading === item.key || insights.loading === `${item.key}-export`}>
        {tab === item.key && <>
          <div className="video-insights__controls">
            {tab === 'transcription' ? <label><span>音频语言</span><select value={transcriptionLanguage} onChange={(event) => setTranscriptionLanguage(event.target.value)}>
              <option value="">自动识别</option>{TRANSCRIPTION_LANGUAGES.map((language) => <option key={language.value} value={language.value}>{language.label}</option>)}
            </select></label> : <label><span>字幕语言</span><select value={sourceLanguage} onChange={(event) => setSourceLanguage(event.target.value)}>
              <option value="">自动选择</option>{languages.map((language) => <option key={language} value={language}>{language}</option>)}
            </select></label>}
            {!timedContent && <label><span>输出语言</span><select value={targetLanguage} onChange={(event) => setTargetLanguage(event.target.value)}>
              {TARGET_LANGUAGES.map((language) => <option key={language.value} value={language.value}>{language.label}</option>)}
            </select></label>}
            <button type="button" className="video-insights__generate" aria-describedby={tab === 'summary' ? `${id}-notice` : undefined} onClick={run} disabled={busy}>{requiresVip(tab) ? '查看 VIP 方案' : config.action}</button>
            {busy && <button type="button" onClick={() => { localActionId.current += 1; insights.cancel(); }}>取消处理</button>}
          </div>
          {requiresVip(tab) && <p className="membership-inline">{config.label}为 VIP 权益，可开通后使用。</p>}
          {tab === 'summary' && <p id={`${id}-notice`} className="video-insights__notice">{SUMMARY_SUPPORT_NOTICE}</p>}
          {tab === 'transcription' && <p className="video-insights__notice">本地音频转写会先检查可用性，点击后才开始识别；识别结果独立于平台字幕，不自动用于总结。</p>}
          {!languages.length && tab !== 'transcription' && <p className="video-insights__empty">尚未检测到字幕。可以尝试读取内容；无可用字幕时会显示原因。</p>}
          <div className="video-insights__status" aria-live="polite" aria-atomic="true">
            {tabLoading && <p>{insights.loading.endsWith('-export') ? '正在导出时码文件…' : loadingLabel[tab]}</p>}
            {tabError && <p className="video-insights__error" role="alert">{insights.error.error || '处理失败，请重试'}</p>}
            {tabError && insights.error.error_type === 'membership_required' && onUpgrade && <button type="button" onClick={onUpgrade}>查看 VIP 方案</button>}
          </div>
          {result ? <article className="video-insights__result" data-testid={`${tab}-result`}>
            <div className="video-insights__result-heading">
              <h3>{tab === 'summary' ? (!isMarkdownSummary && result.title?.trim() || '内容总结') : tab === 'subtitle' ? `${result.language} 字幕${result.is_auto ? ' · 自动生成' : ''}` : tab === 'transcription' ? `音频转写 · ${result.language}` : tab === 'mindmap' ? '思维导图' : `字幕翻译 · ${result.target_language}`}</h3>
              <div className="video-insights__local-actions"><button type="button" onClick={copy}>复制</button>{tab === 'mindmap' ? <>
                <button type="button" onClick={() => exportMindmap('json')}>导出 JSON</button><button type="button" onClick={() => exportMindmap('markdown')}>导出 Markdown</button>
              </> : <button type="button" onClick={exportText}>导出 TXT</button>}
                {timedContent && ['srt', 'vtt'].map((format) => <button key={format} type="button" onClick={() => exportTimed(format)} disabled={busy || !segments.length} aria-describedby={!segments.length ? `${id}-timing-notice` : undefined}>导出 {format.toUpperCase()}</button>)}
              </div>
            </div>
            {tab === 'summary' ? isMarkdownSummary
              ? <div className="video-insights__markdown" data-testid="summary-markdown"><SummaryMarkdown document>{result.summary}</SummaryMarkdown></div>
              : <div className="video-insights__markdown video-insights__structured-summary">
                {result.summary && <section className="video-insights__summary-section"><h4>概览</h4><SummaryMarkdown>{result.summary}</SummaryMarkdown></section>}
                {!!result.key_points?.length && <section className="video-insights__summary-section"><h4>关键要点</h4><ul>{result.key_points.map((point, index) => <li key={index}><SummaryMarkdown>{point}</SummaryMarkdown></li>)}</ul></section>}
                {!!result.conclusion?.trim() && <section className="video-insights__summary-section"><h4>总结</h4><SummaryMarkdown>{result.conclusion}</SummaryMarkdown></section>}
              </div>
              : tab === 'mindmap' ? <MindMapView root={result.root} /> : <>
                <pre>{result.text}</pre>
                {timedContent && (segments.length ? <details className="video-insights__timeline" open>
                  <summary>时码列表（{segments.length} 段）</summary>
                  <ol aria-label="字幕时码">{segments.slice(0, visibleSegments).map((segment, index) => <li key={index}>
                    <span className="video-insights__time">{timestamp(segment.start)} → {timestamp(segment.end)}</span><p>{segment.text}</p>
                  </li>)}</ol>
                  {visibleSegments < segments.length && <button type="button" onClick={() => setVisibleSegments((current) => current + TIMELINE_PAGE_SIZE)}>显示更多时码（已显示 {Math.min(visibleSegments, segments.length)}/{segments.length}）</button>}
                </details> : <p id={`${id}-timing-notice`} className="video-insights__notice">此结果没有有效时码，可复制或导出 TXT；SRT/VTT 导出暂不可用。</p>)}
              </>}
            {href && <a href={href} target="_blank" rel="noopener noreferrer">视频来源</a>}
            {tab !== 'subtitle' && <small>{result.provider} · {result.model}</small>}
          </article> : !tabLoading && !tabError && <div className="video-insights__placeholder"><VideoIcon name={tab} /><h3>{config.label}</h3><p>{config.empty}</p><p>点击“{config.action}”开始处理。</p></div>}
          <p className="video-insights__local-status" role="status">{localStatus}</p>
        </>}
      </div>)}
    </section>
  );
});

export default VideoInsights;
