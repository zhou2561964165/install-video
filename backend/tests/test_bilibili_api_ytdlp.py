import pytest

from app.config import settings
from app.services import ytdlp_service as service
from test_bilibili_api_source import URL, fixtures, install, CDN


def test_real_registration_formats_parse_no_optional_subtitles(monkeypatch):
    monkeypatch.setattr(settings, 'bilibili_api_enabled', True, raising=False)
    calls = install(monkeypatch)
    monkeypatch.setattr(service, 'resolve_public_subtitles', lambda _: pytest.fail('optional subtitle network'))
    info = service.extract_info(URL)
    assert info['extractor_key'] == 'BiliBili' and info['_bilibili_api'] is True
    assert {f.get('height') for f in info['formats'] if f.get('vcodec') != 'none'} == {720}
    assert all(f['url'] == CDN for f in info['formats'])
    meta, choices = service.parse_video(URL)
    assert meta['title'] == 'Example' and meta['subtitles'] == []
    assert [c['height'] for c in choices] == [720]
    assert len(calls) == 4
    assert service.requires_server_download(URL)
    assert service.get_direct_url(URL, 'best') == (None, {})


def test_restrict_uses_real_formats_and_free_bound(monkeypatch):
    monkeypatch.setattr(settings, 'bilibili_api_enabled', True, raising=False)
    view, play = fixtures()
    high = dict(play['dash']['video'][0], id=80, height=1080, width=1920, codecs='hev1.1.6.L120')
    play['dash']['video'].append(high)
    install(monkeypatch, view, play)
    with pytest.raises(ValueError): service.restrict_format(URL, 'bestvideo[height<=1080]+bestaudio/best[height<=1080]', 720)
    assert service.restrict_format(URL, 'bestvideo[height<=720]+bestaudio/best[height<=720]', 720).endswith('[height<=720]')


def test_disabled_switch_retains_original_and_other_platform(monkeypatch):
    monkeypatch.setattr(settings, 'bilibili_api_enabled', False, raising=False)
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    with service._youtube_dl({'quiet': True}) as ydl:
        assert isinstance(ydl.get_info_extractor('BiliBili'), service._BiliBiliVerificationIE)
    monkeypatch.setattr(settings, 'bilibili_api_enabled', True, raising=False)
    assert not service.requires_server_download('https://www.youtube.com/watch?v=test')


@pytest.mark.parametrize('redirect', [None, 'https://evil.test/stolen', 'https://other.bilivideo.com/v'])
def test_actual_urllib_chain_strips_credentials_and_blocks_redirect(tmp_path, monkeypatch, redirect):
    import io
    from email.message import Message
    from urllib.response import addinfourl
    from yt_dlp.networking import Request
    from yt_dlp.networking._urllib import HTTPHandler
    from test_bilibili_session import cookie_file, SECRET
    monkeypatch.setattr(settings, 'bilibili_api_enabled', True, raising=False)
    cookie_file(tmp_path, monkeypatch)
    captured = []
    def offline_response(self, request):
        captured.append((request.full_url, dict(request.header_items())))
        headers = Message()
        if redirect: headers['Location'] = redirect
        response = addinfourl(io.BytesIO(b'offline'), headers, request.full_url, 302 if redirect else 200)
        response.msg = 'Found' if redirect else 'OK'
        return response
    monkeypatch.setattr(HTTPHandler, 'http_open', offline_response)
    monkeypatch.setattr(HTTPHandler, 'https_open', offline_response)
    with service._source_youtube_dl(URL, {'proxy': ''}) as ydl:
        assert len(ydl._request_director.handlers) == 1
        assert ydl.params['retries'] == ydl.params['extractor_retries'] == 0
        request = Request(CDN, headers={'Cookie': SECRET, 'Authorization': SECRET, 'Proxy-Authorization': SECRET})
        if redirect:
            with pytest.raises(Exception): ydl.urlopen(request)
        else:
            with ydl.urlopen(request) as response: assert response.read() == b'offline'
        for invalid in ['https://evil.test/v', 'http://cdn.bilivideo.com/v', 'https://api.bilibili.com/x']:
            with pytest.raises(Exception): ydl.urlopen(invalid)
    assert len(captured) == 1
    assert all(name.lower() not in {'cookie', 'cookie2', 'authorization', 'proxy-authorization'} for name in captured[0][1])


def test_download_and_asr_use_real_api_extract_and_selected_formats(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(settings, 'bilibili_api_enabled', True, raising=False)
    calls = install(monkeypatch)
    selected = []
    # Only disk transfer/postprocessing is replaced. Real registered IE, conversion,
    # sorting and format selection run through YoutubeDL for both public methods.
    def disk_transfer(self, info):
        selected.append(info)
        path = Path(self.prepare_filename(info))
        path.write_bytes(b'offline media')
        info['filepath'] = str(path)
        info['requested_downloads'] = [{'filepath': str(path)}]
    monkeypatch.setattr(service.yt_dlp.YoutubeDL, 'process_info', disk_transfer)
    path = service.download(URL, 'bestvideo[height<=720]+bestaudio/best[height<=720]',
                            str(tmp_path/'video.%(ext)s'), lambda _: None)
    assert Path(path).is_file()
    assert len(selected[0]['requested_formats']) == 2
    audio, title = service.fetch_transcription_audio(URL, tmp_path)
    assert audio.is_file() and title == 'Example'
    assert selected[1]['vcodec'] == 'none' and not selected[1].get('requested_formats')
    assert len(calls) == 4


def test_dolby_flac_multicodec_formats_are_converted_without_quality_probes(monkeypatch):
    monkeypatch.setattr(settings, 'bilibili_api_enabled', True, raising=False)
    view, play = fixtures()
    audio = play['dash']['audio'][0]
    play['dash']['dolby'] = {'audio': [dict(audio, id=30250, codecs='ec-3')]}
    play['dash']['flac'] = {'audio': dict(audio, id=30251, codecs='fLaC', mimeType='audio/flac')}
    play['dash']['video'].append(dict(play['dash']['video'][0], codecs='hev1.1.6.L120'))
    calls = install(monkeypatch, view, play)
    info = service.extract_info(URL)
    assert {f['acodec'] for f in info['formats']} >= {'mp4a.40.2', 'ec-3', 'flac'}
    assert {f['vcodec'] for f in info['formats']} >= {'avc1.64001f', 'hev1.1.6.L120'}
    assert len(calls) == 2


def test_explicit_subtitles_remain_on_demand(monkeypatch):
    monkeypatch.setattr(settings, 'bilibili_api_enabled', True, raising=False)
    monkeypatch.setattr(service, 'resolve_public_subtitles', lambda _: {'tracks': [{'language': 'zh', 'url': 'fixture'}]})
    assert service.extract_subtitle_tracks(URL)['_source'] == 'public'


@pytest.mark.parametrize('operation', ['parse', 'download', 'audio'])
def test_all_operations_safe_denial_no_extra_request(monkeypatch, tmp_path, operation, capsys):
    import httpx
    monkeypatch.setattr(settings, 'bilibili_api_enabled', True, raising=False)
    calls = install(monkeypatch, responder=lambda r: httpx.Response(200,
        json={'code': -352, 'message': 'secret https://cdn.test/?signed=sensitive'}))
    with pytest.raises(Exception) as error:
        if operation == 'parse': service.parse_video(URL)
        elif operation == 'download': service.download(URL, 'best', str(tmp_path/'v.%(ext)s'), lambda _: None)
        else: service.fetch_transcription_audio(URL, tmp_path)
    assert service.classify_error(error.value) == 'verification_required' if operation != 'audio' else error.value.error_type == 'verification_required'
    assert len(calls) == 1 and 'sensitive' not in str(error.value)
    assert capsys.readouterr() == ('', '')


def test_malformed_official_url_never_reaches_generic_web_extractor(monkeypatch):
    monkeypatch.setattr(settings, 'bilibili_api_enabled', True, raising=False)
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    monkeypatch.setattr(service, '_youtube_dl', lambda _: pytest.fail('generic webpage attempted'))
    with pytest.raises(service._BilibiliSourceError):
        service.extract_info(URL.replace('https://', 'https://user@'))


def test_media_deadline_checks_each_socket_read_before_block_fills(monkeypatch):
    import io
    from email.message import Message
    from urllib.response import addinfourl
    from yt_dlp.networking import Request
    from yt_dlp.networking._urllib import HTTPHandler
    clock = [0]
    class Slow(io.BytesIO):
        def read1(self, size=-1):
            clock[0] += 1
            return b'x'
        def read(self, size=-1):
            pytest.fail('buffer-filling read hides deadline')
    def response(self, request):
        res = addinfourl(Slow(), Message(), request.full_url, 200)
        res.msg = 'OK'
        return res
    monkeypatch.setattr(settings, 'bilibili_api_enabled', True, raising=False)
    monkeypatch.setattr(settings, 'bilibili_api_download_timeout_seconds', 30, raising=False)
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    monkeypatch.setattr(HTTPHandler, 'https_open', response)
    monkeypatch.setattr(service.time, 'monotonic', lambda: clock[0])
    with pytest.raises(service._BilibiliSourceError):
        with service._source_youtube_dl(URL, {'proxy': ''}) as ydl:
            with ydl.urlopen(Request(CDN)) as res:
                for _ in range(100): res.read(1024 * 1024)
    assert clock[0] <= 31


@pytest.mark.parametrize('encoding', ['gzip', 'deflate', 'br'])
def test_encoded_media_is_rejected_before_upstream_eager_read(monkeypatch, encoding):
    import io
    from email.message import Message
    from urllib.response import addinfourl
    from yt_dlp.networking._urllib import HTTPHandler
    reads = []
    class Source(io.BytesIO):
        def read(self, *args):
            reads.append(True)
            return super().read(*args)
    def response(self, request):
        headers = Message()
        headers['Content-Encoding'] = encoding
        res = addinfourl(Source(b'compressed-fixture'), headers, request.full_url, 200)
        res.msg = 'OK'
        return res
    monkeypatch.setattr(settings, 'bilibili_api_enabled', True)
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    monkeypatch.setattr(HTTPHandler, 'https_open', response)
    with pytest.raises(Exception):
        with service._source_youtube_dl(URL, {'proxy': ''}) as ydl:
            ydl.urlopen(CDN)
    assert reads == []
