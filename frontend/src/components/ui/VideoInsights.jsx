import React, { forwardRef, useEffect, useId, useImperativeHandle, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { INSIGHT_TABS, SUMMARY_SUPPORT_NOTICE, TARGET_LANGUAGES } from '../../state/insightConfig.js';
import { saveFile } from '../../lib/saveFile.js';
import VideoIcon from './VideoIcon.jsx';

const loadingLabel = { subtitle: '正在读取字幕…', translation: '正在翻译字幕…', summary: '正在生成总结…' };
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

const VideoInsights = forwardRef(function VideoInsights({ languages = [], insights, title = '视频内容', sourceUrl }, ref) {
  const id = useId();
  const tabRefs = useRef([]);
  const [tab, setTab] = useState(insights.active || 'summary');
  const [errorTab, setErrorTab] = useState(insights.loading || insights.active || 'summary');
  const [sourceLanguage, setSourceLanguage] = useState(languages[0] || '');
  const [targetLanguage, setTargetLanguage] = useState(TARGET_LANGUAGES[0].value);
  const [localStatus, setLocalStatus] = useState('');

  useEffect(() => {
    setSourceLanguage((current) => (current && languages.includes(current) ? current : languages[0] || ''));
  }, [languages]);
  const busy = Boolean(insights.loading);
  const result = insights[tab];
  const isMarkdownSummary = tab === 'summary' && result?.format === 'markdown';
  const config = INSIGHT_TABS.find((item) => item.key === tab);
  const text = !result ? '' : tab === 'summary'
    ? (isMarkdownSummary ? result.summary : [result.summary, ...(result.key_points || []).map((point) => `• ${point}`)].join('\n\n'))
    : result.text;
  const href = sourceLink(sourceUrl);

  const chooseTab = (key) => { setTab(key); setLocalStatus(''); };
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
    setErrorTab(tab);
    setLocalStatus('');
    if (tab === 'subtitle') insights.loadSubtitle(sourceLanguage);
    if (tab === 'translation') insights.translate(sourceLanguage, targetLanguage);
    if (tab === 'summary') insights.summarize(sourceLanguage, targetLanguage);
  };
  // 左侧显式总结入口只暴露一个动作，语种及页签仍由内容组件管理。
  useImperativeHandle(ref, () => ({
    summarizeCurrent() {
      if (busy) return;
      chooseTab('summary');
      setErrorTab('summary');
      insights.summarize(sourceLanguage, targetLanguage);
    },
  }), [busy, insights.summarize, sourceLanguage, targetLanguage]);
  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setLocalStatus('已复制内容'); }
    catch { setLocalStatus('复制失败，可选择文本后手动复制。'); }
  };
  const exportText = () => {
    let url;
    try {
      url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
      saveFile(url, `${title.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_').slice(0, 100) || '视频内容'}-${config.label}.txt`);
      setLocalStatus('已导出 TXT');
    } catch { setLocalStatus('导出失败，请重试。'); }
    finally { if (url) setTimeout(() => URL.revokeObjectURL(url), 0); }
  };

  return (
    <section className="video-insights" aria-label="视频内容工作区">
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
        className="video-insights__panel" aria-busy={insights.loading === item.key}>
        {tab === item.key && <>
          <div className="video-insights__controls">
            <label><span>字幕语言</span><select value={sourceLanguage} onChange={(event) => setSourceLanguage(event.target.value)}>
              <option value="">自动选择</option>{languages.map((language) => <option key={language} value={language}>{language}</option>)}
            </select></label>
            {tab !== 'subtitle' && <label><span>输出语言</span><select value={targetLanguage} onChange={(event) => setTargetLanguage(event.target.value)}>
              {TARGET_LANGUAGES.map((language) => <option key={language.value} value={language.value}>{language.label}</option>)}
            </select></label>}
            <button type="button" className="video-insights__generate" aria-describedby={tab === 'summary' ? `${id}-notice` : undefined} onClick={run} disabled={busy}>{config.action}</button>
          </div>
          {tab === 'summary' && <p id={`${id}-notice`} className="video-insights__notice">{SUMMARY_SUPPORT_NOTICE}</p>}
          {!languages.length && <p className="video-insights__empty">尚未检测到字幕。可以尝试读取内容；无可用字幕时会显示原因。</p>}
          <div className="video-insights__status" aria-live="polite" aria-atomic="true">
            {insights.loading === tab && <p>{loadingLabel[tab]}</p>}
            {insights.error && errorTab === tab && <p className="video-insights__error" role="alert">{insights.error.error || '处理失败，请重试'}</p>}
          </div>
          {result ? <article className="video-insights__result" data-testid={`${tab}-result`}>
            <div className="video-insights__result-heading">
              <h3>{tab === 'summary' ? '内容总结' : tab === 'subtitle' ? `${result.language} 字幕${result.is_auto ? ' · 自动生成' : ''}` : `字幕翻译 · ${result.target_language}`}</h3>
              <div className="video-insights__local-actions"><button type="button" onClick={copy}>复制</button><button type="button" onClick={exportText}>导出 TXT</button></div>
            </div>
            {tab === 'summary' ? isMarkdownSummary
              ? <div className="video-insights__markdown" data-testid="summary-markdown"><ReactMarkdown components={markdownComponents}>{result.summary || ''}</ReactMarkdown></div>
              : <>
                <p>{result.summary}</p>
                {!!result.key_points?.length && <><h4>关键要点</h4><ul>{result.key_points.map((point, index) => <li key={index}>{point}</li>)}</ul></>}
              </>
              : <pre>{result.text}</pre>}
            {href && <a href={href} target="_blank" rel="noopener noreferrer">视频来源</a>}
            {tab !== 'subtitle' && <small>{result.provider} · {result.model}</small>}
          </article> : insights.loading !== tab && !(insights.error && errorTab === tab) && <div className="video-insights__placeholder"><VideoIcon name={tab} /><h3>{config.label}</h3><p>{config.empty}</p><p>点击“{config.action}”开始处理。</p></div>}
          <p className="video-insights__local-status" role="status">{localStatus}</p>
        </>}
      </div>)}
    </section>
  );
});

export default VideoInsights;
