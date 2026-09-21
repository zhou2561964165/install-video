import React from 'react';

function formatDuration(seconds) {
  if (seconds == null) return '';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export default function SelectingScene({ parseResult, selectedFormat, forceServer, onSelect, onDownload }) {
  const { title, thumbnail, duration, formats } = parseResult;
  return (
    <div data-testid="selecting-scene">
      {thumbnail && <img src={thumbnail} alt="" />}
      <h2>{title}</h2>
      <p>{formatDuration(duration)}</p>
      <div>
        {formats.map((f) => (
          <button
            key={f.format_id}
            aria-pressed={selectedFormat?.format_id === f.format_id}
            onClick={() => onSelect(f)}
          >
            {f.label} · {f.ext}
          </button>
        ))}
      </div>
      <label>
        <input type="checkbox" checked={forceServer} onChange={(e) => onSelect(selectedFormat, e.target.checked)} />
        强制走服务器
      </label>
      <button onClick={onDownload} disabled={!selectedFormat}>下载</button>
    </div>
  );
}
