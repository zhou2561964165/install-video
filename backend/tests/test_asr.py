from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings, settings
from app.services import ytdlp_service
from app.services import asr_service
from app.services.asr_service import ASRError


def test_asr_defaults_are_local_and_bounded():
    value = Settings()
    assert value.asr_model == 'tiny'
    assert value.asr_max_duration_seconds == 1800
    assert value.asr_max_bytes == 128 * 1024 * 1024
    assert value.asr_max_concurrent == 1


def test_audio_acquisition_rejects_long_source_before_download(monkeypatch, tmp_path):
    called = []
    class YDL:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            called.append(download)
            return {'duration': 1801, 'title': 'video'}
    monkeypatch.setattr(ytdlp_service, '_youtube_dl', lambda options: YDL())
    from app.services.asr_service import ASRError
    with pytest.raises(ASRError, match='时长'):
        ytdlp_service.fetch_transcription_audio('https://example.com/v', tmp_path)
    assert called == [False]


@pytest.fixture
def local_asr(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'temp_dir', tmp_path)
    monkeypatch.setattr(asr_service, 'capabilities', lambda: {'available': True})
    monkeypatch.setattr(asr_service, '_check_audio_duration', lambda *args: None)
    paths = []
    def acquire(url, directory):
        paths.append(directory)
        path = directory / 'audio.wav'
        path.write_bytes(b'audio')
        return path, 'video title'
    monkeypatch.setattr(ytdlp_service, 'fetch_transcription_audio', acquire)
    monkeypatch.setattr(asr_service, '_get_model', lambda: SimpleNamespace(
        transcribe=lambda *args, **kwargs: (iter([SimpleNamespace(start=0., end=1., text=' hello ')]),
                                            SimpleNamespace(language='en'))))
    return paths


def test_transcribe_success_preserves_times_and_cleans_temporary_files(local_asr):
    result = asr_service.transcribe_video('https://example.com/v')
    assert result.text == 'hello'
    assert result.segments == [{'start': 0., 'end': 1., 'text': 'hello'}]
    assert result.provider == 'faster-whisper'
    assert all(not path.exists() for path in local_asr)
    assert asr_service._active == 0


@pytest.mark.parametrize('case', ['exception', 'empty', 'invalid', 'capacity'])
def test_failure_is_safe_releases_slot_and_cleans_files(local_asr, monkeypatch, case):
    if case == 'exception':
        def fail(): raise RuntimeError('private path/token')
        monkeypatch.setattr(asr_service, '_get_model', fail)
    else:
        segments = [] if case == 'empty' else [SimpleNamespace(start=-1 if case == 'invalid' else 0,
                                                             end=1, text='hello')] * 2
        if case == 'capacity': monkeypatch.setattr(settings, 'subtitle_max_cues', 1)
        monkeypatch.setattr(asr_service, '_get_model', lambda: SimpleNamespace(
            transcribe=lambda *a, **kw: (iter(segments), SimpleNamespace(language='en'))))
    with pytest.raises(ASRError) as exc:
        asr_service.transcribe_video('https://example.com/v')
    assert 'private' not in str(exc.value)
    assert all(not path.exists() for path in local_asr)
    assert asr_service._active == 0


def test_concurrent_limit_rejects_before_audio_fetch(local_asr, monkeypatch):
    monkeypatch.setattr(asr_service, '_active', settings.asr_max_concurrent)
    with pytest.raises(ASRError) as exc:
        asr_service.transcribe_video('https://example.com/v')
    assert exc.value.error_type == 'transcription_busy'
    assert not local_asr


@pytest.mark.parametrize('metadata', [{'duration': None}, {'duration': float('nan')},
                                     {'duration': True}, {'duration': 3, 'is_live': True},
                                     {'duration': 3, '_type': 'playlist'}])
def test_unbounded_audio_source_rejected_before_download(monkeypatch, tmp_path, metadata):
    calls = []
    class YDL:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def extract_info(self, url, download): calls.append(download); return metadata
    monkeypatch.setattr(ytdlp_service, '_youtube_dl', lambda options: YDL())
    with pytest.raises(ASRError):
        ytdlp_service.fetch_transcription_audio('https://example.com/v', tmp_path)
    assert calls == [False]


def test_audio_download_enforces_progress_size_and_output_containment(monkeypatch, tmp_path):
    options = {}
    class YDL:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def extract_info(self, url, download):
            assert not download
            return {'duration': 3, 'title': 'title', 'protocol': 'https', 'url': 'https://example.com/audio'}
        def process_info(self, info):
            options['progress_hooks'][0]({'downloaded_bytes': settings.asr_max_bytes + 1})
    def factory(opts): options.update(opts); return YDL()
    monkeypatch.setattr(ytdlp_service, '_youtube_dl', factory)
    with pytest.raises(ASRError) as exc:
        ytdlp_service.fetch_transcription_audio('https://example.com/v', tmp_path)
    assert exc.value.error_type == 'transcription_too_large'
    assert options['retries'] == options['fragment_retries'] == 0


@pytest.mark.parametrize('protocol', ['m3u8', 'm3u8_native', 'rtmp', 'rtmp_ffmpeg', 'http_dash_segments'])
def test_audio_rejects_unmonitored_download_protocol_before_work(monkeypatch, tmp_path, protocol):
    calls = []
    class YDL:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            calls.append(download)
            return {'duration': 3, 'protocol': protocol, 'url': 'https://example.com/stream'}
        def process_info(self, info): pytest.fail('unbounded protocol used')
        def prepare_filename(self, info): return str(tmp_path / 'audio.wav')
    monkeypatch.setattr(ytdlp_service, '_youtube_dl', lambda options: YDL())
    with pytest.raises(ASRError) as exc:
        ytdlp_service.fetch_transcription_audio('https://example.com/v', tmp_path)
    assert exc.value.error_type == 'transcription_source_unsupported'
    assert calls == [False]


@pytest.mark.parametrize('section', ['section_start', 'section_end'])
def test_audio_http_sections_cannot_select_external_downloader(monkeypatch, tmp_path, section):
    class YDL:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def extract_info(self, *a, **kw):
            return {'duration': 3, 'protocol': 'https', 'url': 'https://example.com/audio', section: 1}
        def process_info(self, info): raise AssertionError('external download started')
    monkeypatch.setattr(ytdlp_service, '_youtube_dl', lambda options: YDL())
    with pytest.raises(ASRError) as exc:
        ytdlp_service.fetch_transcription_audio('https://example.com/v', tmp_path)
    assert exc.value.error_type == 'transcription_source_unsupported'


def test_music_transcription_can_disable_speech_activity_filter(local_asr, monkeypatch):
    monkeypatch.setattr(settings, 'asr_vad_filter', False, raising=False)
    def transcribe(*a, **kw):
        assert kw['vad_filter'] is False
        return iter([SimpleNamespace(start=0., end=1., text='recognized music')]), SimpleNamespace(language='en')
    monkeypatch.setattr(asr_service, '_get_model', lambda: SimpleNamespace(transcribe=transcribe))
    assert asr_service.transcribe_video('https://example.com/v').text == 'recognized music'


def test_actual_audio_duration_limit_is_checked_incrementally(tmp_path, monkeypatch):
    pytest.importorskip('av')
    import wave
    path = tmp_path / 'source.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
        audio.writeframes(b'\x00\x00' * 32000)
    monkeypatch.setattr(settings, 'asr_max_duration_seconds', 1)
    import time
    with pytest.raises(ASRError) as exc:
        asr_service._check_audio_duration(path, time.monotonic())
    assert exc.value.error_type == 'transcription_duration'


def test_optional_whisper_decoder_matches_locked_pyav_api(tmp_path):
    pytest.importorskip('faster_whisper')
    from faster_whisper.audio import decode_audio
    import wave
    path = tmp_path / 'decode.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
        audio.writeframes(b'\x00\x00' * 1600)
    assert len(decode_audio(str(path))) == 1600


def test_cached_lookup_never_starts_a_producer():
    from app.services.request_cache import RequestCache
    cache = RequestCache(max_bytes=1024, max_entries=2, ttl=10, max_inflight=1, max_waiters=1, wait_seconds=1)
    assert cache.lookup('missing') is None
    cache.run('done', lambda: {'text': 'value'})
    value = cache.lookup('done')
    value['text'] = 'changed'
    assert cache.lookup('done')['text'] == 'value'


@pytest.fixture
def api(monkeypatch, local_asr):
    from collections import defaultdict
    from uuid import uuid4
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr('app.main._window', defaultdict(list))
    client = TestClient(app)
    def account():
        response = client.post('/api/auth/register', json={'email': f'{uuid4()}@example.com', 'password': 'password123'})
        assert response.status_code == 200
        return {'Authorization': f"Bearer {response.json()['token']}"}
    return client, account, local_asr


@pytest.mark.parametrize('path,method', [('/api/transcribe', 'post'),
                                       ('/api/transcribe/export', 'post'),
                                       ('/api/transcribe/capabilities', 'get')])
def test_transcription_routes_require_authentication(api, path, method):
    client, _, paths = api
    kwargs = {'json': {'url': 'https://example.com/v', 'format': 'srt'}} if method == 'post' else {}
    assert getattr(client, method)(path, **kwargs).status_code == 401
    assert not paths


def test_explicit_transcription_reuses_result_and_export_never_retranscribes(api):
    client, account, paths = api
    headers = account()
    body = {'url': 'https://example.com/v', 'language': 'en'}
    before = client.post('/api/transcribe/export', json={**body, 'format': 'srt'}, headers=headers)
    assert before.status_code == 422
    assert not paths
    first = client.post('/api/transcribe', json=body, headers=headers)
    assert first.status_code == 200
    assert first.json()['segments'][0]['text'] == 'hello'
    assert client.post('/api/transcribe', json=body, headers=headers).json() == first.json()
    exported = client.post('/api/transcribe/export', json={**body, 'format': 'srt'}, headers=headers)
    assert exported.status_code == 200
    assert '00:00:00,000 --> 00:00:01,000' in exported.json()['content']
    assert len(paths) == 1
    assert client.post('/api/transcribe/export', json={**body, 'format': 'vtt'}, headers=account()).status_code == 422
    assert len(paths) == 1


def test_changed_transcription_language_or_model_invalidates_cache(api, monkeypatch):
    client, account, paths = api
    headers = account()
    body = {'url': 'https://example.com/v'}
    for language in ['en', 'zh-CN']:
        assert client.post('/api/transcribe', json={**body, 'language': language}, headers=headers).status_code == 200
    assert len(paths) == 2
    monkeypatch.setattr(settings, 'asr_model', 'base')
    assert client.post('/api/transcribe/export', json={**body, 'language': 'en', 'format': 'vtt'}, headers=headers).status_code == 422
    assert len(paths) == 2


def test_transcription_invalid_url_does_not_acquire_audio(api):
    client, account, paths = api
    assert client.post('/api/transcribe', json={'url': 'file:///private'}, headers=account()).status_code == 400
    assert not paths


@pytest.mark.parametrize('language', ['zz', 'eng', '123', 'unknown'])
def test_invalid_transcription_language_rejected_before_io(api, language):
    client, account, paths = api
    assert client.post('/api/transcribe', json={'url': 'https://example.com/v', 'language': language}, headers=account()).status_code == 422
    assert not paths


def test_asr_plain_text_export_does_not_treat_speech_as_markup(api, monkeypatch):
    import html
    client, account, _ = api
    headers = account()
    body = {'url': 'https://example.com/v'}
    text = '<div> a < b > c {literal} \\New'
    monkeypatch.setattr(asr_service, '_get_model', lambda: SimpleNamespace(
        transcribe=lambda *a, **kw: (iter([SimpleNamespace(start=0., end=1., text=text)]), SimpleNamespace(language='en'))))
    assert client.post('/api/transcribe', json=body, headers=headers).json()['text'] == text
    result = client.post('/api/transcribe/export', json={**body, 'format': 'srt'}, headers=headers)
    assert result.status_code == 200
    assert text in html.unescape(result.json()['content'])


def test_asr_export_timing_failure_is_mapped_to_422(api, monkeypatch):
    from app.services.subtitle_timing import TimingError
    client, account, _ = api
    headers = account()
    body = {'url': 'https://example.com/v'}
    assert client.post('/api/transcribe', json=body, headers=headers).status_code == 200
    def reject(*a, **kw): raise TimingError('subtitle_invalid', 'invalid timeline')
    monkeypatch.setattr('app.services.subtitle_timing.export_segments', reject)
    result = client.post('/api/transcribe/export', json={**body, 'format': 'vtt'}, headers=headers)
    assert result.status_code == 422
