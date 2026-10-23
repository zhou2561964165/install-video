import pytest

from app.services import ytdlp_service as service
from test_bilibili_session import VIDEO, SECRET, cookie_file


def test_real_ydl_in_memory_jar_does_not_write_file(tmp_path, monkeypatch, capsys):
    path = cookie_file(tmp_path, monkeypatch)
    original = path.read_bytes()
    with service._source_youtube_dl(VIDEO, {'quiet': True, 'no_warnings': True}) as ydl:
        assert SECRET in ydl.cookiejar.get_cookie_header(VIDEO)
        assert not ydl.cookiejar.get_cookie_header('https://cdn.bilivideo.com/a')
        assert ydl.params['http_headers']['Referer'] == 'https://www.bilibili.com/'
        assert not ydl.params.get('cookiefile')
        ydl.report_warning('cookie ' + SECRET)
        ydl.report_error('signed https://cdn.test/?token=' + SECRET, is_error=False)
    assert path.read_bytes() == original
    assert capsys.readouterr() == ('', '')


def test_configured_bili_never_returns_browser_direct_url(tmp_path, monkeypatch):
    cookie_file(tmp_path, monkeypatch)
    monkeypatch.setattr(service, '_youtube_dl', lambda opts: pytest.fail('direct extraction forbidden'))
    assert service.requires_server_download(VIDEO)
    assert service.get_direct_url(VIDEO, '80') == (None, {})
    assert not service.requires_server_download('https://youtube.com/watch?v=a')


@pytest.mark.parametrize('operation', ['extract', 'download', 'audio'])
def test_all_source_operations_use_session_and_hide_provider_secrets(tmp_path, monkeypatch, capsys, operation):
    cookie_file(tmp_path, monkeypatch)
    def failure(self, url, download=False):
        assert SECRET in self.cookiejar.get_cookie_header(VIDEO)
        self.report_warning(SECRET)
        raise service.ExtractorError('HTTP Error 412 signed=' + SECRET)
    monkeypatch.setattr(service.yt_dlp.YoutubeDL, 'extract_info', failure)
    with pytest.raises(Exception) as error:
        if operation == 'extract':
            service.extract_info(VIDEO)
        elif operation == 'download':
            service.download(VIDEO, 'best', str(tmp_path / 'v.%(ext)s'), lambda _: None)
        else:
            service.fetch_transcription_audio(VIDEO, tmp_path)
    assert SECRET not in str(error.value)
    assert SECRET not in service.public_error_message(error.value)
    if operation == 'audio':
        assert error.value.error_type == 'verification_required'
    else:
        assert service.classify_error(error.value) == 'verification_required'
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err


def test_bili_real_dash_has_free_720_480_360_choices():
    formats = [{'format_id': str(h), 'height': h, 'vcodec': 'avc1', 'acodec': 'none',
                'url': f'https://cdn.test/{h}'} for h in [1080, 720, 480, 360]]
    formats.append({'format_id': 'audio', 'vcodec': 'none', 'acodec': 'mp4a', 'url': 'https://cdn.test/a'})
    info = {'extractor_key': 'BiliBili', 'formats': formats}
    assert [f['height'] for f in service.build_format_options(info)] == [1080, 720, 480, 360]
    assert [f['height'] for f in service.build_format_options({**info, 'extractor_key': 'Youtube'})] == [1080]


@pytest.mark.parametrize('protocol', ['m3u8', 'm3u8_native', 'http_dash_segments', 'rtmp'])
def test_cookie_context_rejects_external_protocol_before_downloader(tmp_path, monkeypatch, protocol):
    cookie_file(tmp_path, monkeypatch)
    monkeypatch.setattr(service.yt_dlp.YoutubeDL, 'process_info', lambda *a: pytest.fail('downloader started'))
    with pytest.raises(Exception) as error:
        with service._source_youtube_dl(VIDEO, {}) as ydl:
            ydl.process_info({'protocol': protocol, 'url': VIDEO, 'ext': 'mp4'})
    assert service.classify_error(error.value) == 'unsupported_site'
    assert SECRET not in service.public_error_message(error.value)


def test_cookie_context_allows_native_dash_streams_and_local_merge(tmp_path, monkeypatch):
    cookie_file(tmp_path, monkeypatch)
    completed = []
    monkeypatch.setattr(service.yt_dlp.YoutubeDL, 'process_info', lambda self, info: completed.append(info['format_id']))
    with service._source_youtube_dl(VIDEO, {}) as ydl:
        ydl.process_info({'format_id': '80+30280', 'requested_formats': [
            {'protocol': 'https', 'url': 'https://cdn.bilivideo.com/v', 'ext': 'mp4'},
            {'protocol': 'https', 'url': 'https://cdn.bilivideo.com/a', 'ext': 'm4a'},
        ]})
    assert completed == ['80+30280']


def test_expired_session_audio_keeps_verification_message(tmp_path, monkeypatch):
    cookie_file(tmp_path, monkeypatch,
        f'.bilibili.com\tTRUE\t/\tTRUE\t1\tX-BILI-SEC-TOKEN\t{SECRET}\n')
    monkeypatch.setattr(service, '_youtube_dl', lambda opts: pytest.fail('expired session reached extractor'))
    with pytest.raises(service.ASRError) as error:
        service.fetch_transcription_audio(VIDEO, tmp_path)
    assert error.value.error_type == 'verification_required'
    assert '更新' in str(error.value)
    assert SECRET not in str(error.value)


@pytest.mark.parametrize(('upstream', 'category'), [
    ('ffmpeg not found', 'ffmpeg_missing'), ('private video login required', 'login_required'),
    ('geo-restricted', 'geo_blocked'), ('connection timeout', 'network'),
])
def test_safe_session_errors_preserve_classification(tmp_path, monkeypatch, upstream, category):
    cookie_file(tmp_path, monkeypatch)
    def failure(self, *args, **kwargs):
        raise service.ExtractorError(upstream + ' ' + SECRET)
    monkeypatch.setattr(service.yt_dlp.YoutubeDL, 'extract_info', failure)
    with pytest.raises(Exception) as error:
        service.extract_info(VIDEO)
    assert service.classify_error(error.value) == category
    assert SECRET not in service.public_error_message(error.value)


def test_actual_urllib_handler_preserves_cookie_scope_without_requests_fallback(tmp_path, monkeypatch):
    """Exercise urlopen -> director -> urllib cookie processor; no sockets open."""
    import io
    from email.message import Message
    from urllib.response import addinfourl
    from yt_dlp.networking._urllib import HTTPHandler

    cookie_file(tmp_path, monkeypatch,
        f'api.bilibili.com\tFALSE\t/private\tTRUE\t4102444800\thost_only\t{SECRET}\n')
    captured = []

    def offline_response(self, request):
        captured.append((request.full_url, request.get_header('Cookie')))
        response = addinfourl(io.BytesIO(b'offline fixture'), Message(), request.full_url, 200)
        response.msg = 'OK'
        return response

    monkeypatch.setattr(HTTPHandler, 'http_open', offline_response)
    monkeypatch.setattr(HTTPHandler, 'https_open', offline_response)
    with service._source_youtube_dl(VIDEO, {'proxy': ''}) as ydl:
        # A preference alone is insufficient: director can fall back to Requests
        # on unsupported requests or handler errors, losing the strict policy.
        assert set(ydl._request_director.handlers) == {'Urllib'}
        for url in [
            'https://api.bilibili.com/private/x',
            'https://child.api.bilibili.com/private/x',
            'https://api.bilibili.com/public/x',
            'http://api.bilibili.com/private/x',
            'https://cdn.bilivideo.com/private/x',
        ]:
            with ydl.urlopen(url) as response:
                assert response.read() == b'offline fixture'
    assert captured == [
        ('https://api.bilibili.com/private/x', 'host_only=' + SECRET),
        ('https://child.api.bilibili.com/private/x', None),
        ('https://api.bilibili.com/public/x', None),
        ('http://api.bilibili.com/private/x', None),
        ('https://cdn.bilivideo.com/private/x', None),
    ]


def test_other_sources_retain_upstream_request_handlers(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, 'bilibili_cookie_file', 'must-not-read')
    with service._source_youtube_dl('https://example.com/v', {'quiet': True}) as ydl:
        assert 'Urllib' in ydl._request_director.handlers
        assert 'Requests' in ydl._request_director.handlers
