import React from 'react';
import EnergyBar from './ui/EnergyBar.jsx';

// 下载中反馈：对齐参考站 spinner「下载中，请稍候...」。
//   直链模式浏览器原生跳转（瞬时），文案「正在发送…」；服务端模式显示 spinner + 进度条。
export default function DownloadingScene({ job, mode }) {
  const server = mode === 'server';
  return (
    <div data-testid="downloading-scene" className="scene downloading-scene">
      <div className="downloading-state">
        <span className="spinner" aria-hidden="true" />
        <p>{server ? '下载中，请稍候...' : '正在发送…'}</p>
      </div>
      {server && <EnergyBar value={job?.progress} />}
    </div>
  );
}
