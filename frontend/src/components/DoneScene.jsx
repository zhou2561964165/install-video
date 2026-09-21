import React from 'react';

export default function DoneScene({ job, fileUrl, onReset }) {
  return (
    <div data-testid="done-scene">
      <p>下载完成{job?.title ? `：${job.title}` : ''}</p>
      {fileUrl && <a href={fileUrl} download>打开 / 保存文件</a>}
      <button onClick={onReset}>继续下载</button>
    </div>
  );
}
