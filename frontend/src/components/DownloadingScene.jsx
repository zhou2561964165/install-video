import React from 'react';

export default function DownloadingScene({ job, mode }) {
  const progress = job ? Math.round(job.progress || 0) : 0;
  return (
    <div data-testid="downloading-scene">
      <p>{mode === 'direct' ? '正在发送…' : '正在下载…'}</p>
      {mode === 'server' && (
        <progress value={progress} max={100} aria-label="下载进度">{progress}%</progress>
      )}
    </div>
  );
}
