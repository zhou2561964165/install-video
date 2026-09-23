import React from 'react';
import { playSfx } from '../audio/audioManager.js';

function formatDuration(seconds) {
  if (seconds == null) return '';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export default function SelectingScene({ parseResult, selectedFormat, forceServer, onSelect, onDownload }) {
  const { title, thumbnail, duration, formats } = parseResult;
  return (
    <div data-testid="selecting-scene" className="scene selecting-scene">
      <div className="format-card">
        {thumbnail && <img src={thumbnail} alt="" />}
        <h2>{title}</h2>
        <p className="duration">{formatDuration(duration)}</p>
        <div className="format-list">
          {formats.map((f) => (
            <button
              key={f.format_id}
              className={selectedFormat?.format_id === f.format_id ? 'selected' : ''}
              aria-pressed={selectedFormat?.format_id === f.format_id}
              onClick={() => { playSfx('select'); onSelect(f); }}
            >
              {f.label} · {f.ext}
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
