"""Synthetic API responses only; no live sources or credentials."""
import copy
import importlib

import httpx
import pytest

from app.config import Settings, settings

URL = 'https://www.bilibili.com/video/BV1DdnM6bEL4'
CDN = 'https://upos-test.bilivideo.com/video.m4s?token=synthetic'


def fixtures():
    view = {'bvid': 'BV1DdnM6bEL4', 'aid': 123, 'title': 'Example', 'desc': 'Description',
            'owner': {'name': 'Uploader', 'mid': 42}, 'pubdate': 1700000000,
            'pages': [{'page': 1, 'cid': 456, 'duration': 100, 'part': 'Part one'},
                      {'page': 2, 'cid': 789, 'duration': 30, 'part': 'Part two'}]}
    def stream(ident, **fields):
        return {'id': ident, 'baseUrl': 'https://edge.invalid:4483/unsafe',
                'backupUrl': [CDN], 'bandwidth': 100000, **fields}
    play = {'timelength': 100000, 'quality': 64, 'accept_quality': [80, 64, 32], 'dash': {
        'video': [stream(64, height=720, width=1280, codecs='avc1.64001f', mimeType='video/mp4')],
        'audio': [stream(30280, codecs='mp4a.40.2', mimeType='audio/mp4')]}}
    return view, play


def module():
    return importlib.import_module('app.services.bilibili_api_source')


def install(monkeypatch, view=None, play=None, responder=None):
    default_view, default_play = fixtures()
    view, play = default_view if view is None else view, default_play if play is None else play
    calls = []
    real_client = httpx.Client
    def respond(request):
        calls.append(request)
        if responder:
            return responder(request)
        data = view if request.url.path.endswith('/view') else play
        return httpx.Response(200, json={'code': 0, 'data': copy.deepcopy(data)})
    def client(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        assert kwargs['timeout'].read <= 8
        return real_client(transport=httpx.MockTransport(respond), **kwargs)
    monkeypatch.setattr(module().httpx, 'Client', client)
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    return calls


def test_api_switch_is_opt_in(monkeypatch):
    monkeypatch.delenv('BILIBILI_API_ENABLED', raising=False)
    assert getattr(Settings.from_env(), 'bilibili_api_enabled', None) is False
    monkeypatch.setenv('BILIBILI_API_ENABLED', 'true')
    assert Settings.from_env().bilibili_api_enabled is True


def test_upower_exclusive_stops_before_play_request(monkeypatch):
    view, play = fixtures()
    view['is_upower_exclusive'] = True
    calls = install(monkeypatch, view, play)
    with pytest.raises(module().BilibiliApiError) as error:
        module().extract_api_video(URL)
    assert error.value.category == 'login_required'
    assert len(calls) == 1


def test_encoded_metadata_is_rejected_before_decoding(monkeypatch):
    reads = []
    class Source(httpx.SyncByteStream):
        def __iter__(self):
            reads.append(True)
            yield b'invalid-compressed-fixture'
    calls = install(monkeypatch, responder=lambda r: httpx.Response(200,
        headers={'Content-Encoding': 'gzip'}, stream=Source()))
    with pytest.raises(module().BilibiliApiError):
        module().extract_api_video(URL)
    assert reads == [] and len(calls) == 1


def test_two_gets_and_safe_backup_selection(monkeypatch):
    calls = install(monkeypatch)
    result = module().extract_api_video(URL)
    assert len(calls) == 2
    assert calls[0].url.host == calls[1].url.host == 'api.bilibili.com'
    assert calls[1].url.params['qn'] == '80'
    assert calls[1].url.params['fnval'] == '16'
    assert calls[1].url.params['cid'] == '456'
    assert result['duration'] == 100
    assert result['play_info']['dash']['video'][0]['baseUrl'] == CDN
    assert 'backupUrl' not in result['play_info']['dash']['video'][0]


@pytest.mark.parametrize('url', [URL+'?p=0', URL+'?p=2&p=1', URL+'?p=',
    URL+'?p=999', URL.replace('BV1DdnM6bEL4', 'BVtest'),
    URL.replace('www.bilibili.com', 'evil.test'), URL.replace('https://', 'https://user@'),
    URL+'#x', 'https://b23.tv/short'])
def test_invalid_identity_or_part_never_changes_video(monkeypatch, url):
    calls = install(monkeypatch)
    with pytest.raises(module().BilibiliApiError):
        module().extract_api_video(url)
    assert len(calls) <= 1


def test_av_and_part_binding(monkeypatch):
    view, play = fixtures()
    play['timelength'] = 30000
    calls = install(monkeypatch, view, play)
    result = module().extract_api_video('https://www.bilibili.com/video/av123?p=2')
    assert result['id'] == 'BV1DdnM6bEL4_p2'
    assert result['duration'] == 30 and result['title'] == 'Example - Part two'
    assert calls[0].url.params['aid'] == '123' and calls[1].url.params['cid'] == '789'


@pytest.mark.parametrize('change', ['bvid', 'aid', 'cid', 'preview', 'drm', 'missing_audio', 'paid'])
def test_mismatch_and_restricted_streams_fail_closed(monkeypatch, change):
    view, play = fixtures()
    if change == 'bvid': view['bvid'] = 'BV1JSh265EQm'
    if change == 'aid': view['aid'] = 0
    if change == 'cid': play['cid'] = 999
    if change == 'preview': play['is_preview'] = 1
    if change == 'drm': play['dash']['video'][0]['drm_tech_type'] = 2
    if change == 'missing_audio': play['dash']['audio'] = []
    if change == 'paid': view['rights'] = {'is_pay': 1}
    install(monkeypatch, view, play)
    with pytest.raises(module().BilibiliApiError): module().extract_api_video(URL)


@pytest.mark.parametrize('value', ['https://evil.test/v', 'https://cdn.bilivideo.com:4483/v',
    'https://user@cdn.bilivideo.com/v', 'https://cdn.bilivideo.com/v#x',
    'https://cdn.bilivideo.com.evil.test/v', 'https://127.0.0.1/v',
    'https://cdn.bilivideo.com/\nv', 'https://cdn.bilivideo.com\\@evil.test/v'])
def test_unsafe_cdn_rejected(value):
    assert module().safe_media_url(value) is None


def test_http_official_cdn_is_upgraded():
    assert module().safe_media_url(CDN.replace('https:', 'http:')) == CDN


@pytest.mark.parametrize('status,code,category', [(412, 0, 'verification_required'),
    (200, -352, 'verification_required'), (200, -101, 'login_required'),
    (200, -404, 'unsupported_site'), (302, 0, 'network')])
def test_http_and_business_denials_no_retry_or_secret(monkeypatch, status, code, category):
    calls = install(monkeypatch, responder=lambda r: httpx.Response(status,
        headers={'location': 'https://evil.test/'}, json={'code': code, 'message': 'synthetic-secret'}))
    with pytest.raises(module().BilibiliApiError) as error: module().extract_api_video(URL)
    assert error.value.category == category and 'synthetic-secret' not in str(error.value)
    assert len(calls) == 1


def test_response_body_bound(monkeypatch):
    calls = install(monkeypatch, responder=lambda r: httpx.Response(200, content=b'x' * (1024*1024+1)))
    with pytest.raises(module().BilibiliApiError): module().extract_api_video(URL)
    assert len(calls) == 1


def test_phase_deadline_includes_response_headers(monkeypatch):
    calls = install(monkeypatch)
    timestamps = iter([0, 17, 17, 17, 17, 17])
    monkeypatch.setattr(module().time, 'monotonic', lambda: next(timestamps))
    with pytest.raises(module().BilibiliApiError): module().extract_api_video(URL)
    assert len(calls) == 1


def test_api_cookies_preserve_scope_refresh_and_never_follow_redirect(tmp_path, monkeypatch):
    from test_bilibili_session import cookie_file, SECRET
    calls = install(monkeypatch)
    path = cookie_file(tmp_path, monkeypatch,
        f'api.bilibili.com\tFALSE\t/x/web-interface\tTRUE\t4102444800\thost_only\t{SECRET}\n')
    original = path.read_bytes()
    module().extract_api_video(URL)
    assert calls[0].headers['cookie'] == 'host_only=' + SECRET
    assert 'cookie' not in calls[1].headers
    path.write_bytes(original.replace(SECRET.encode(), b'updated'))
    module().extract_api_video(URL)
    assert calls[2].headers['cookie'] == 'host_only=updated'


def test_expired_cookie_stops_before_api_get(tmp_path, monkeypatch):
    from test_bilibili_session import cookie_file, SECRET
    from app.services.bilibili_session import SessionError
    calls = install(monkeypatch)
    cookie_file(tmp_path, monkeypatch,
        f'.bilibili.com\tTRUE\t/\tTRUE\t1\tX-BILI-SEC-TOKEN\t{SECRET}\n')
    with pytest.raises(SessionError): module().extract_api_video(URL)
    assert calls == []


def test_slow_small_chunks_cannot_hide_deadline_in_buffer(monkeypatch):
    clock = [0]
    class SlowStream(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(100):
                clock[0] += 1
                yield b' '
    calls = install(monkeypatch, responder=lambda r: httpx.Response(200, stream=SlowStream()))
    monkeypatch.setattr(module().time, 'monotonic', lambda: clock[0])
    with pytest.raises(module().BilibiliApiError): module().extract_api_video(URL)
    assert clock[0] <= 17
    assert len(calls) == 1


@pytest.mark.parametrize('value', ['0', '29', '3601', '-1'])
def test_download_deadline_configuration_rejects_unbounded_values(monkeypatch, value):
    monkeypatch.setenv('BILIBILI_API_DOWNLOAD_TIMEOUT_SECONDS', value)
    with pytest.raises(ValueError): Settings.from_env()


def test_download_deadline_configuration_defaults_and_environment(monkeypatch):
    monkeypatch.delenv('BILIBILI_API_DOWNLOAD_TIMEOUT_SECONDS', raising=False)
    assert Settings.from_env().bilibili_api_download_timeout_seconds == 180
    monkeypatch.setenv('BILIBILI_API_DOWNLOAD_TIMEOUT_SECONDS', '60')
    assert Settings.from_env().bilibili_api_download_timeout_seconds == 60


@pytest.mark.parametrize('kind', ['video', 'audio', 'dolby', 'flac'])
def test_unsafe_nested_audio_or_video_never_survives_normalization(monkeypatch, kind):
    view, play = fixtures()
    unsafe = dict(play['dash']['audio'][0], baseUrl='https://evil.test/v', backupUrl=['https://edge.invalid:4483/v'])
    if kind in {'video', 'audio'}:
        play['dash'][kind].append(unsafe)
    elif kind == 'dolby': play['dash']['dolby'] = {'audio': [unsafe]}
    else: play['dash']['flac'] = {'audio': unsafe}
    install(monkeypatch, view, play)
    with pytest.raises(module().BilibiliApiError): module().extract_api_video(URL)
