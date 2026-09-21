import React from 'react';
import EnergyBar from './ui/EnergyBar.jsx';

export default function DownloadingScene({ job, mode }) {
  return (
    <div data-testid="downloading-scene" className="scene downloading-scene">
      <p>{mode === 'direct' ? '正在发送…' : '正在下载…'}</p>
      {mode === 'server' && <EnergyBar value={job?.progress} />}
    </div>
  );
}
