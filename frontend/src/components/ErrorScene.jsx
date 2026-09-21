import React, { useCallback, useState } from 'react';
import { ERROR_SCENES } from '../state/sceneMachine.js';
import Bubble from './ui/Bubble.jsx';
import Danmaku from './ui/Danmaku.jsx';

export default function ErrorScene({ error, onReset }) {
  const cfg = ERROR_SCENES[error?.error_type] || ERROR_SCENES.network;
  const [showDanmaku, setShowDanmaku] = useState(true);
  const dismiss = useCallback(() => setShowDanmaku(false), []);
  return (
    <div data-testid="error-scene" className="scene error-scene">
      {showDanmaku && <Danmaku text={cfg.hint} onDone={dismiss} />}
      <Bubble className="error-bubble">
        <span aria-hidden>{cfg.emoji}</span>
        <h2>{cfg.title}</h2>
        <p>{error?.error || cfg.hint}</p>
      </Bubble>
      <button onClick={onReset}>重试</button>
    </div>
  );
}
