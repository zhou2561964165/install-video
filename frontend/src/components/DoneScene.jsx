import React, { useEffect } from 'react';
import Bubble from './ui/Bubble.jsx';
import { playSfx } from '../audio/audioManager.js';

export default function DoneScene({ job, onSave, saveBusy = false, saveError, onReset }) {
  useEffect(() => { playSfx('done'); }, []);
  return (
    <div data-testid="done-scene" className="scene done-scene">
      <Bubble className="done-bubble">
        <p>下载完成{job?.title ? `：${job.title}` : ''}</p>
        {onSave && <button type="button" onClick={onSave} disabled={saveBusy} aria-busy={saveBusy}>保存文件</button>}
        {saveBusy && <p role="status">正在获取文件，随后将交给浏览器保存…</p>}
        {saveError && <p role="alert">保存失败：{saveError.error || '请重试'}</p>}
      </Bubble>
      <button onClick={onReset}>继续下载</button>
    </div>
  );
}
