import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { playSfx, setMuted, _resetForTest } from './audioManager.js';

function makeFakeCtx() {
  const osc = {
    type: null,
    frequency: { value: 0 },
    connect: vi.fn(() => osc),
    start: vi.fn(),
    stop: vi.fn(),
  };
  const gain = {
    gain: {
      setValueAtTime: vi.fn(),
      exponentialRampToValueAtTime: vi.fn(),
    },
    connect: vi.fn(() => osc),
  };
  return {
    state: 'suspended',
    resume: vi.fn(),
    currentTime: 0,
    destination: {},
    createOscillator: vi.fn(() => osc),
    createGain: vi.fn(() => gain),
  };
}

describe('audioManager', () => {
  beforeEach(() => _resetForTest());
  afterEach(() => vi.unstubAllGlobals());

  it('playSfx 创建振荡器，并在挂起的上下文上调用 resume()', () => {
    const fakeCtx = makeFakeCtx();
    vi.stubGlobal('AudioContext', function FakeAudioContext() { return fakeCtx; });

    playSfx('paste');

    expect(fakeCtx.createOscillator).toHaveBeenCalledTimes(1);
    expect(fakeCtx.createGain).toHaveBeenCalledTimes(1);
    expect(fakeCtx.resume).toHaveBeenCalledTimes(1);
  });

  it('setMuted(true) 后 playSfx 不再创建振荡器', () => {
    const fakeCtx = makeFakeCtx();
    vi.stubGlobal('AudioContext', function FakeAudioContext() { return fakeCtx; });

    setMuted(true);
    playSfx('paste');

    expect(fakeCtx.createOscillator).not.toHaveBeenCalled();
    expect(fakeCtx.createGain).not.toHaveBeenCalled();
  });

  it('无 AudioContext 时 playSfx 不抛错（jsdom 环境）', () => {
    // 不 stub AudioContext：jsdom 无 WebAudio，ensureCtx 应静默返回 null
    expect(() => playSfx('paste')).not.toThrow();
  });
});
