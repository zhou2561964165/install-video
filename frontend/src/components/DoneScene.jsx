import React from 'react';
import Bubble from './ui/Bubble.jsx';

export default function DoneScene({ job, fileUrl, onReset }) {
  return (
    <div data-testid="done-scene" className="scene done-scene">
      <Bubble className="done-bubble">
        <p>下载完成{job?.title ? `：${job.title}` : ''}</p>
        {fileUrl && <a href={fileUrl} download>打开 / 保存文件</a>}
      </Bubble>
      <button onClick={onReset}>继续下载</button>
    </div>
  );
}
