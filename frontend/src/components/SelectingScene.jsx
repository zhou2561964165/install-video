import React, { useRef } from 'react';
import { playSfx } from '../audio/audioManager.js';
import VideoInsights from './ui/VideoInsights.jsx';
import VideoIcon from './ui/VideoIcon.jsx';

// 解析结果展示：按参考站信息结构对齐（封面时长角标 → 标题 → up主/平台/播放量 → 简介 → 格式两行），
// 白蓝局部 token 与参考双栏布局。字段来自 normalizeParse 的派生值。
export default function SelectingScene({ parseResult, selectedFormat, forceServer, onSelect, onDownload, insights, downloadContent, locked = false, sourceUrl }) {
  const insightsRef = useRef(null);
  const {
    title, thumbnail, durationLabel, uploader, platform, viewCountLabel, description, formats,
  } = parseResult;
  return (
    <div data-testid="selecting-scene" className="selecting-scene video-workspace">
      <div className="format-card">
        <div className="video-card__info">
          <div className="cover">
            {/* 平台图床（如 B 站 hdslb）按 Referer 防盗链，第三方来源会 403；不带 Referer 即可直接加载 */}
            {thumbnail ? <img src={thumbnail} alt="" referrerPolicy="no-referrer" onError={(event) => { event.currentTarget.hidden = true; }} /> : <VideoIcon name="video" />}
            {durationLabel && <span className="cover__duration">{durationLabel}</span>}
          </div>
        <h2>{title}</h2>
        {(uploader || platform || viewCountLabel) && (
          <div className="meta">
            {uploader && <span className="meta__uploader">{uploader}</span>}
            {platform && <span className="meta__platform">{platform}</span>}
            {viewCountLabel && <span className="meta__views">{viewCountLabel}</span>}
          </div>
        )}
        {description && <p className="desc">{description}</p>}
        </div>
        <div className="video-card__download">
        <h3 className="video-card__section-title"><VideoIcon name="settings" />选择清晰度和格式</h3>
        <div className="format-list">
          {formats.map((f) => (
            <button
              key={f.format_id}
              className={selectedFormat?.format_id === f.format_id ? 'selected' : ''}
              aria-pressed={selectedFormat?.format_id === f.format_id}
              disabled={locked}
              onClick={() => { playSfx('select'); onSelect(f); }}
            >
              <span className="format-list__icon" aria-hidden="true"><VideoIcon name="video" /></span>
              <span className="format-list__text"><span className="format-list__label">{f.label}</span><span className="format-list__meta">{f.metaLine}</span></span>
            </button>
          ))}
        </div>
        <label className="badge-switch">
          <input type="checkbox" checked={forceServer} disabled={locked} aria-describedby="download-naming-help" onChange={(e) => { playSfx('select'); onSelect(selectedFormat, e.target.checked); }} />
          按视频标题命名
        </label>
        <p id="download-naming-help" className="download-naming-help">关闭后使用来源直链，文件名由来源站决定。</p>
        {downloadContent || <button className="video-download-button" onClick={onDownload} disabled={!selectedFormat}><VideoIcon name="download" />下载</button>}
        {insights && <button type="button" className="video-summary-button" disabled={Boolean(insights.loading)} onClick={() => insightsRef.current?.summarizeCurrent()}><VideoIcon name="summary" />AI 总结</button>}
        {selectedFormat && <p className="video-card__selection">已选择：{selectedFormat.label}</p>}
        </div>
      </div>
      {insights && <VideoInsights ref={insightsRef} languages={parseResult.subtitles || []} insights={insights} title={title} sourceUrl={sourceUrl} />}
    </div>
  );
}
