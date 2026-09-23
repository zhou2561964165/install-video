import React, { useEffect } from 'react';
import { ERROR_SCENES } from '../state/sceneMachine.js';
import Bubble from './ui/Bubble.jsx';
import { playSfx } from '../audio/audioManager.js';

// 9 种 error_type → 差异化视觉 class（文案仍来自 ERROR_SCENES）
const ERR_CLASS = {
  invalid_url: 'err-invalid',
  unsupported_site: 'err-invalid',
  age_restricted: 'err-drm',
  geo_blocked: 'err-drm',
  drm: 'err-drm',
  login_required: 'err-drm',
  ffmpeg_missing: 'err-quota',
  network: 'err-quota',
  quota: 'err-quota',
};

export default function ErrorScene({ error, onReset }) {
  const cfg = ERROR_SCENES[error?.error_type] || ERROR_SCENES.network;
  useEffect(() => { playSfx('error'); }, []);
  return (
    <div data-testid="error-scene" className={`scene error-scene ${ERR_CLASS[error?.error_type] || ''}`}>
      <Bubble className="error-bubble">
        <span className="error-emoji" aria-hidden>{cfg.emoji}</span>
        <h2>{cfg.title}</h2>
        <p>{error?.error || cfg.hint}</p>
      </Bubble>
      <button onClick={onReset}>重试</button>
    </div>
  );
}
