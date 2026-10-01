let ctx = null;

function ensureCtx() {
  const AC = typeof window !== 'undefined' ? (window.AudioContext || window.webkitAudioContext) : null;
  if (!AC) return null;                 // jsdom / 无 WebAudio → 静默
  if (!ctx) ctx = new AC();
  if (ctx.state === 'suspended') ctx.resume();
  return ctx;
}

// SFX：振荡器合成短音，无需外部音频文件
const SFX = {
  paste:  { freq: 880, dur: 0.12, type: 'sine' },
  select: { freq: 1320, dur: 0.08, type: 'triangle' },
  done:   { freq: 1760, dur: 0.25, type: 'sine' },
  error:  { freq: 220, dur: 0.3, type: 'sawtooth' },
};

export function unlock() {
  ensureCtx();
}

export function playSfx(name) {
  const cfg = SFX[name];
  if (!cfg) return;
  const c = ensureCtx();
  if (!c) return;
  const osc = c.createOscillator();
  const gain = c.createGain();
  osc.type = cfg.type;
  osc.frequency.value = cfg.freq;
  gain.gain.setValueAtTime(0.15, c.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, c.currentTime + cfg.dur);
  osc.connect(gain).connect(c.destination);
  osc.start();
  osc.stop(c.currentTime + cfg.dur);
}

export function _resetForTest() {
  ctx = null;
}
