let ctx = null;
let muted = false;
let bgm = null;

function ensureCtx() {
  const AC = typeof window !== 'undefined' ? (window.AudioContext || window.webkitAudioContext) : null;
  if (!AC) return null;                 // jsdom / 无 WebAudio → 静默
  if (!ctx) ctx = new AC();
  if (ctx.state === 'suspended') ctx.resume();
  return ctx;
}

// SFX：振荡器合成短音，v1 无需外部音频文件（spec §7 允许占位）
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
  if (muted) return;
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

export function setScene(scene) {
  // v1：BGM 用占位音源（若缺失则静默跳过）；scene 只影响音量/是否继续
  if (!bgm && window.Audio) {
    try {
      bgm = new Audio('/audio/bgm.mp3');
      bgm.loop = true;
      bgm.volume = 0.3;
    } catch { /* 占位音源缺失时忽略 */ }
  }
  // jsdom 无 AudioContext 且 play() 是 "Not implemented" 占位（返回 undefined），
  // 跳过 play 以避免 TypeError / jsdom 噪音（与 R-6a「无 WebAudio → 静默」一致）
  if (bgm && !muted && (window.AudioContext || window.webkitAudioContext)) {
    bgm.play().catch(() => {});
  }
}

export function setMuted(m) {
  muted = m;
  if (bgm) bgm.volume = m ? 0 : 0.3;
}

export function _resetForTest() {
  ctx = null; muted = false; bgm = null;
}
