import React, { useEffect, useState } from 'react';
import { TARGET_LANGUAGES } from '../../state/insightConfig.js';

const loadingLabel = {
  subtitle: '正在读取字幕…',
  translation: '正在翻译字幕…',
  summary: '正在生成总结…',
};

export default function VideoInsights({ languages = [], insights }) {
  const [sourceLanguage, setSourceLanguage] = useState(languages[0] || '');
  const [targetLanguage, setTargetLanguage] = useState(TARGET_LANGUAGES[0].value);

  useEffect(() => {
    setSourceLanguage((current) => (current && languages.includes(current) ? current : languages[0] || ''));
  }, [languages]);

  const available = languages.length > 0;
  const busy = Boolean(insights.loading);

  return (
    <section className="video-insights" aria-labelledby="video-insights-title" aria-busy={busy}>
      <div className="video-insights__heading">
        <div>
          <p className="video-insights__eyebrow">读懂视频内容</p>
          <h3 id="video-insights-title">视频智能</h3>
        </div>
        <span className="video-insights__badge">AI</span>
      </div>

      {!available && (
        <p className="video-insights__empty">尚未检测到字幕。可以尝试读取内容；无可用字幕时会显示原因。</p>
      )}
        <div className="video-insights__controls">
          <label>
            <span>字幕语言</span>
            <select value={sourceLanguage} onChange={(event) => setSourceLanguage(event.target.value)}>
              <option value="">自动选择</option>
              {languages.map((language) => <option key={language} value={language}>{language}</option>)}
            </select>
          </label>
          <label>
            <span>输出语言</span>
            <select value={targetLanguage} onChange={(event) => setTargetLanguage(event.target.value)}>
              {TARGET_LANGUAGES.map((language) => (
                <option key={language.value} value={language.value}>{language.label}</option>
              ))}
            </select>
          </label>
          <div className="video-insights__actions">
            <button type="button" onClick={() => insights.loadSubtitle(sourceLanguage)} disabled={busy}>查看字幕</button>
            <button type="button" onClick={() => insights.translate(sourceLanguage, targetLanguage)} disabled={busy}>翻译字幕</button>
            <button type="button" onClick={() => insights.summarize(sourceLanguage, targetLanguage)} disabled={busy}>生成总结</button>
          </div>
        </div>

      <div className="video-insights__status" aria-live="polite" aria-atomic="true">
        {insights.loading && <p>{loadingLabel[insights.loading]}</p>}
        {insights.error && <p className="video-insights__error" role="alert">{insights.error.error || '处理失败，请重试'}</p>}
      </div>

      {insights.active === 'summary' && insights.summary && (
        <article className="video-insights__result" data-testid="summary-result">
          <h4>内容总结</h4>
          <p>{insights.summary.summary}</p>
          <ul>{insights.summary.key_points.map((point, index) => <li key={`${index}-${point}`}>{point}</li>)}</ul>
          <small>{insights.summary.provider} · {insights.summary.model}</small>
        </article>
      )}
      {insights.active === 'translation' && insights.translation && (
        <article className="video-insights__result" data-testid="translation-result">
          <h4>字幕翻译 · {insights.translation.target_language}</h4>
          <pre>{insights.translation.text}</pre>
          <small>{insights.translation.provider} · {insights.translation.model}</small>
        </article>
      )}
      {insights.active === 'subtitle' && insights.subtitle && (
        <article className="video-insights__result" data-testid="subtitle-result">
          <h4>{insights.subtitle.language} 字幕{insights.subtitle.is_auto ? ' · 自动生成' : ''}</h4>
          <pre>{insights.subtitle.text}</pre>
        </article>
      )}
    </section>
  );
}
