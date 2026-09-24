import React from 'react';
import { playSfx } from '../audio/audioManager.js';

// 解析结果展示：按参考站信息结构对齐（封面时长角标 → 标题 → up主/平台/播放量 → 简介 → 格式两行），
// 视觉沿用项目 token（樱花粉玻璃卡片 + 胶囊格式单选）。字段来自 normalizeParse 的派生值。
export default function SelectingScene({ parseResult, selectedFormat, forceServer, onSelect, onDownload }) {
  const {
    title, thumbnail, durationLabel, uploader, platform, viewCountLabel, description, formats,
  } = parseResult;
  return (
    <div data-testid="selecting-scene" className="scene selecting-scene">
      <div className="format-card">
        {thumbnail && (
          <div className="cover">
            <img src={thumbnail} alt="" />
            {durationLabel && <span className="cover__duration">{durationLabel}</span>}
          </div>
        )}
        <h2>{title}</h2>
        {(uploader || platform || viewCountLabel) && (
          <div className="meta">
            {uploader && <span className="meta__uploader">{uploader}</span>}
            {platform && <span className="meta__platform">{platform}</span>}
            {viewCountLabel && <span className="meta__views">{viewCountLabel}</span>}
          </div>
        )}
        {description && <p className="desc">{description}</p>}
        <div className="format-list">
          {formats.map((f) => (
            <button
              key={f.format_id}
              className={selectedFormat?.format_id === f.format_id ? 'selected' : ''}
              aria-pressed={selectedFormat?.format_id === f.format_id}
              onClick={() => { playSfx('select'); onSelect(f); }}
            >
              <span className="format-list__label">{f.label}</span>
              <span className="format-list__meta">{f.metaLine}</span>
            </button>
          ))}
        </div>
        <label className="badge-switch">
          <input type="checkbox" checked={forceServer} onChange={(e) => { playSfx('select'); onSelect(selectedFormat, e.target.checked); }} />
          强制走服务器
        </label>
        <button onClick={onDownload} disabled={!selectedFormat}>下载</button>
      </div>
    </div>
  );
}
