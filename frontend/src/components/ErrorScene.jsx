import React from 'react';
import { ERROR_SCENES } from '../state/sceneMachine.js';

export default function ErrorScene({ error, onReset }) {
  const cfg = ERROR_SCENES[error?.error_type] || ERROR_SCENES.network;
  return (
    <div data-testid="error-scene">
      <span aria-hidden>{cfg.emoji}</span>
      <h2>{cfg.title}</h2>
      <p>{error?.error || cfg.hint}</p>
      <button onClick={onReset}>重试</button>
    </div>
  );
}
