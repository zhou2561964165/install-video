import { describe, it, expect } from 'vitest';
import { SCENE, initialState, reduce, ERROR_SCENES } from './sceneMachine.js';

describe('sceneMachine', () => {
  it('默认按视频标题命名，每个新视频恢复该选项，允许显式选择直链', () => {
    expect(initialState().forceServer).toBe(true);
    const direct = reduce(initialState(), { type: 'SELECT_FORMAT', format: null, forceServer: false });
    expect(direct.forceServer).toBe(false);
    expect(reduce(direct, { type: 'SUBMIT_URL', url: 'https://b' }).forceServer).toBe(true);
    expect(reduce(direct, { type: 'RESET' }).forceServer).toBe(true);
  });

  it('starts at entry', () => {
    expect(initialState().scene).toBe(SCENE.ENTRY);
  });

  it('SUBMIT_URL → parsing and resets prior state', () => {
    const s0 = { ...initialState(), scene: SCENE.SELECTING, parseResult: { title: 'x' } };
    const s1 = reduce(s0, { type: 'SUBMIT_URL', url: 'https://a' });
    expect(s1.scene).toBe(SCENE.PARSING);
    expect(s1.url).toBe('https://a');
    expect(s1.parseResult).toBeNull();
  });

  it('PARSE_SUCCESS → selecting with payload', () => {
    const s = reduce(initialState(), { type: 'PARSE_SUCCESS', payload: { title: 't', formats: [] } });
    expect(s.scene).toBe(SCENE.SELECTING);
    expect(s.parseResult.title).toBe('t');
  });

  it('PARSE_FAIL → error with typed error', () => {
    const s = reduce(initialState(), { type: 'PARSE_FAIL', error: { error_type: 'invalid_url', error: 'x' } });
    expect(s.scene).toBe(SCENE.ERROR);
    expect(s.error.error_type).toBe('invalid_url');
  });

  it('DOWNLOAD_PROGRESS done → done scene', () => {
    const s = reduce({ ...initialState(), scene: SCENE.DOWNLOADING }, { type: 'DOWNLOAD_PROGRESS', job: { status: 'done', progress: 100 } });
    expect(s.scene).toBe(SCENE.DONE);
  });

  it('DOWNLOAD_PROGRESS error → error scene with error_type', () => {
    const s = reduce({ ...initialState(), scene: SCENE.DOWNLOADING }, { type: 'DOWNLOAD_PROGRESS', job: { status: 'error', error_type: 'geo_blocked', error: 'x' } });
    expect(s.scene).toBe(SCENE.ERROR);
    expect(s.error.error_type).toBe('geo_blocked');
  });

  it('RESET returns a fresh initial state', () => {
    const s = reduce({ ...initialState(), scene: SCENE.DONE }, { type: 'RESET' });
    expect(s).toEqual(initialState());
  });

  it('ERROR_SCENES covers all 9 error types', () => {
    expect(Object.keys(ERROR_SCENES).sort()).toEqual(
      ['age_restricted', 'drm', 'ffmpeg_missing', 'geo_blocked', 'invalid_url', 'login_required', 'network', 'quota', 'unsupported_site'].sort(),
    );
  });
});
