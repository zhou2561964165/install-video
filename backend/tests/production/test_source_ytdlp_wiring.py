"""B5 W1: explicit-ctx metadata wiring through the real guarded yt-dlp; synthetic wire only.

Run via run_b5_source_wiring_offline.py (network/threads denied, YTDLP_NO_PLUGINS=1).
"""
import json
import os
import sys
from pathlib import Path

import pytest
import yt_dlp
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.networking.common import _REQUEST_HANDLERS
from yt_dlp import globals as yt_globals

from app.services import ytdlp_service as service
from app.services.outbound_policy import OutboundError, OutboundUnavailableError
from app.services.outbound_httpx import ControlledHttpError
from app.services.source_network import source_network_scope
from test_outbound_httpx import transport_network  # noqa: F401  (fixture)
from test_ytdlp_guard_director import context, reply, safe

PAGE = 'http://public.example/unit'
YDL_MODULE = sys.modules['yt_dlp.YoutubeDL']


def sends(wire):
    return sum(part.startswith(b'GET ') for part in wire.writes)


class FixtureIE(InfoExtractor):
    _VALID_URL = r'http://public\.example/(?P<id>unit|catch)'

    def _real_extract(self, url):
        video_id = self._match_id(url)
        if video_id == 'catch':
            # A hostile/careless extractor swallowing the first failure and retrying elsewhere.
            try:
                return self._download_json(url, video_id)
            except Exception:
                return self._download_json('http://second.example/unit', video_id)
        return self._download_json(url, video_id)


@pytest.fixture
def registry(monkeypatch):
    """Real default registration, with the local fixture extractor offered first."""
    original, lookup = YDL_MODULE.gen_extractor_classes, YDL_MODULE.get_info_extractor
    monkeypatch.setattr(YDL_MODULE, 'gen_extractor_classes', lambda: [FixtureIE, *original()])
    monkeypatch.setattr(YDL_MODULE, 'get_info_extractor',
                        lambda key: FixtureIE if key == FixtureIE.ie_key() else lookup(key))
    allowed = getattr(service, '_METADATA_EXTRACTORS', frozenset())
    monkeypatch.setattr(service, '_METADATA_EXTRACTORS', frozenset(allowed) | {FixtureIE.ie_key()}, raising=False)


def metadata(**changes):
    data = dict(id='unit', title='Unit', description='d', uploader='u', upload_date='20261025',
                duration=12.5, view_count=3, thumbnail='http://img.example/t.jpg',
                formats=[dict(url='http://cdn.example/v720.mp4', format_id='720', ext='mp4', height=720,
                              width=1280, vcodec='avc1', acodec='mp4a', filesize=1000,
                              http_headers={'User-Agent': 'x', 'Cookie': 'a=b'})],
                subtitles={'en': [dict(url='http://sub.example/en.vtt', ext='vtt')]})
    data.update(changes)
    return data


def serve(wire, data):
    wire.replies.append(reply(json.dumps(data).encode()))


def test_ctx_extract_info_projects_metadata_with_one_get(registry, transport_network):
    before_env, before_handlers = dict(os.environ), dict(_REQUEST_HANDLERS)
    before_plugins = (dict(yt_globals.plugin_ies.value), dict(yt_globals.plugin_pps.value))
    network = context()
    serve(transport_network, metadata())
    with source_network_scope(network):
        info = service.extract_info(PAGE)
    assert info['title'] == 'Unit' and info['duration'] == 12.5 and info['view_count'] == 3
    assert info['webpage_url'] == PAGE and info['extractor_key'] == 'Fixture'
    fmt = info['formats'][0]
    assert fmt['protocol'] == 'http' and fmt['height'] == 720 and fmt['filesize'] == 1000
    assert fmt['http_headers'] == {'User-Agent': 'x'}  # credential header stripped
    assert info['subtitles']['en'][0]['url'] == 'http://sub.example/en.vtt'
    assert 'webpage_url_basename' not in info and 'webpage_url_domain' not in info
    assert sends(transport_network) == 1  # no thumbnail/subtitle/media GET
    assert network.budget.snapshot().requests == 1
    assert dict(os.environ) == before_env and _REQUEST_HANDLERS == before_handlers
    assert before_plugins == (yt_globals.plugin_ies.value, yt_globals.plugin_pps.value)


def test_ctx_follows_redirect_between_unrelated_public_hosts(registry, transport_network):
    network = context()
    transport_network.replies.append(reply(b'', b'302 Found', b'Location: http://other.example/unit.json\r\n'))
    serve(transport_network, metadata(formats=[dict(url='https://cdn.example/a.mp4', format_id='a')]))
    with source_network_scope(network):
        info = service.extract_info(PAGE)
    assert info['formats'][0]['protocol'] == 'https'
    saved = network.budget.snapshot()
    assert (saved.requests, saved.redirects) == (2, 1) and sends(transport_network) == 2


def test_ctx_parse_video_returns_projection_without_urls_or_subtitle_enhancement(registry, transport_network, monkeypatch):
    monkeypatch.setattr(service, 'resolve_public_subtitles', lambda url: pytest.fail('public subtitle enhancement'))
    serve(transport_network, metadata(subtitles={}))
    with source_network_scope(context()):
        meta, options = service.parse_video(PAGE)
    assert meta['title'] == 'Unit' and meta['subtitles'] == []
    assert options and all('url' not in option and 'http_headers' not in option for option in options)
    assert sends(transport_network) == 1


@pytest.mark.parametrize('change', [
    dict(thumbnail='http://127.0.0.1/t.jpg?sig=synthetic-secret'),
    dict(formats=[dict(url='http://169.254.169.254/latest?sig=synthetic-secret', format_id='x')]),
    dict(formats=[dict(url='http://user:synthetic-secret@cdn.example/v.mp4', format_id='x')]),
    dict(formats=[dict(url='ftp://cdn.example/v.mp4?sig=synthetic-secret', format_id='x')]),
    dict(subtitles={'en': [dict(url='http://10.0.0.1/en.vtt?sig=synthetic-secret', ext='vtt')]}),
    dict(webpage_url='http://127.0.0.1/page?sig=synthetic-secret'),
    dict(url='http://127.0.0.1/v.mp4?sig=synthetic-secret'),
    dict(formats=[dict(url='http://cdn.example/v.mp4', format_id='x',
                       http_headers={'Referer': 'http://10.0.0.1/?sig=synthetic-secret'})]),
], ids=['thumbnail-loopback', 'format-metadata-ip', 'format-userinfo', 'format-ftp', 'subtitle-private',
        'webpage-loopback', 'root-url-loopback', 'referer-private'])
def test_derived_urls_blocked_before_return(registry, transport_network, change):
    serve(transport_network, metadata(**change))
    with source_network_scope(context()):
        with pytest.raises(OutboundError) as caught:
            service.extract_info(PAGE)
    safe(caught.value)
    assert sends(transport_network) == 1


@pytest.mark.parametrize('change', [
    dict(manifest_url='http://cdn.example/m.mpd'),
    dict(_type='playlist', entries=[]),
    dict(formats=[dict(url='http://cdn.example/v.mp4', format_id='x', fragments=[])]),
    dict(requested_formats=[]),
    dict(is_live=True),
    dict(live_status='is_live'),
    dict(duration=float('nan')),
    dict(duration=-1),
    dict(view_count=True),
    dict(formats=[dict(url='http://cdn.example/v.mp4', format_id='x', height='720')]),
    dict(formats=[dict(url='http://cdn.example/v.mp4', protocol='m3u8', format_id='x')]),
    dict(formats=[dict(url='https://cdn.example/v.mp4', protocol='http', format_id='x')]),
    dict(formats=[dict(url='http://cdn.example/v.mp4', format_id='x', http_headers={'X-Evil': 'y'})]),
    dict(formats=[dict(url='http://cdn.example/v.mp4', format_id='x', http_headers={'User-Agent': 'a\r\nb'})]),
    dict(formats=[dict(format_id='no-url')]),
    dict(formats=[dict(url='https://cdn.example/master.m3u8', format_id='h', height=720)]),
    dict(formats=[dict(url='https://cdn.example/manifest.f4m', format_id='f')]),
    dict(formats=[dict(url='https://cdn.example/manifest.mpd', format_id='d')]),
    dict(url='https://cdn.example/master.m3u8'),
    dict(formats=[dict(url='http://cdn.example/v.mp4', height=720, vcodec='avc1', acodec='mp4a')]),
    dict(title='x' * 9000),
    dict(unknown_field='z'),
], ids=['manifest', 'playlist', 'fragments', 'requested', 'live', 'live-status', 'nan', 'negative', 'bool-number',
        'string-height', 'm3u8', 'protocol-scheme-mismatch', 'unknown-header', 'crlf-header', 'format-no-url',
        'derived-m3u8', 'derived-f4m', 'derived-mpd', 'root-m3u8', 'format-no-format-id',
        'long-text', 'unknown-key'])
def test_unsupported_metadata_shapes_unavailable(registry, transport_network, change):
    serve(transport_network, metadata(**change))
    with source_network_scope(context()):
        with pytest.raises(OutboundError) as caught:
            service.extract_info(PAGE)
    safe(caught.value)
    assert sends(transport_network) == 1


def test_formats_only_without_root_url_and_null_numbers(registry, transport_network):
    serve(transport_network, metadata(duration=None, view_count=None, thumbnail=None))
    with source_network_scope(context()):
        info = service.extract_info(PAGE)
    assert 'url' not in info and info['duration'] is None and info['thumbnail'] is None


def test_extractor_catch_all_cannot_send_second_get(registry, transport_network):
    transport_network.replies.append(reply(b'', b'302 Found', b'Location: http://127.0.0.1/x\r\n'))
    serve(transport_network, metadata())
    with source_network_scope(context()):
        with pytest.raises(OutboundError) as caught:
            service.extract_info('http://public.example/catch')
    safe(caught.value)
    assert sends(transport_network) == 1  # the latch stopped the retry to second.example


def test_guarded_generic_factory_still_refuses_bilibili_before_cookie_helper(transport_network, monkeypatch):
    monkeypatch.setattr(service, 'cookie_jar_for_url', lambda url: pytest.fail('cookie helper reached'))
    monkeypatch.setattr(service, '_youtube_dl', lambda opts: pytest.fail('legacy factory reached'))
    with source_network_scope(context()):
        for url in ('https://www.bilibili.com/video/BV1xx411c7mD', 'https://b23.tv/abc'):
            with pytest.raises(OutboundUnavailableError):
                with service._guarded_metadata_source(url, context()):
                    pytest.fail('Bilibili reached generic extractor')
    assert sends(transport_network) == 0


@pytest.mark.parametrize('call', [
    lambda: service.get_direct_url(PAGE, '720'),
    lambda: service.get_direct_url('https://www.bilibili.com/video/BV1xx411c7mD', '720'),
    lambda: service.download(PAGE, '720', 'x.%(ext)s', lambda data: None),
    lambda: service.fetch_transcription_audio(PAGE, Path('.')),
    lambda: service.extract_subtitle_tracks(PAGE, use_public_sources=False),
], ids=['direct', 'direct-bilibili-no-fallback', 'download', 'asr', 'subtitles-ytdlp'])
def test_unwired_ctx_paths_fail_closed_before_io(transport_network, monkeypatch, call):
    monkeypatch.setattr(service, '_youtube_dl', lambda opts: pytest.fail('legacy factory reached'))
    monkeypatch.setattr(service, 'resolve_public_subtitles', lambda url: pytest.fail('public subtitles reached'))
    with source_network_scope(context()):
        with pytest.raises(OutboundUnavailableError):
            call()
    assert sends(transport_network) == 0


def test_ctx_subtitles_keep_public_sources_but_never_reach_ytdlp(transport_network, monkeypatch):
    # Public sources are already on the controlled channel (accepted B5 integration);
    # when they yield nothing under a ctx, the yt-dlp caption path stays closed.
    monkeypatch.setattr(service, 'resolve_public_subtitles', lambda url: {'title': 't', 'tracks': []})
    monkeypatch.setattr(service, 'extract_info', lambda url: pytest.fail('yt-dlp caption path reached'))
    with source_network_scope(context()):
        with pytest.raises(OutboundUnavailableError):
            service.extract_subtitle_tracks(PAGE)
    tracks = {'title': 't', 'tracks': [{'language': 'en', 'is_auto': False, 'formats': []}]}
    monkeypatch.setattr(service, 'resolve_public_subtitles', lambda url: tracks)
    with source_network_scope(context()):
        assert service.extract_subtitle_tracks(PAGE)['_source'] == 'public'
    assert sends(transport_network) == 0


def test_no_ctx_keeps_legacy_factory(monkeypatch):
    used = []

    class Legacy:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False):
            used.append(url)
            return {'title': 'legacy'}
    monkeypatch.setattr(service, '_youtube_dl', lambda opts: used.append(opts) or Legacy())
    assert service.extract_info(PAGE) == {'title': 'legacy'}
    assert used[-1] == PAGE and used[0]['skip_download'] is True


def test_legacy_bilibili_branch_keeps_safety_error_first(monkeypatch):
    # Real _source_youtube_dl legacy (no ctx) branch: a safety error must not become _BilibiliSourceError.
    monkeypatch.setattr(service, '_api_mode', lambda url: False)
    monkeypatch.setattr(service, 'session_enabled', lambda url: True)

    def blocked(url):
        raise OutboundUnavailableError()
    monkeypatch.setattr(service, 'cookie_jar_for_url', blocked)
    with pytest.raises(OutboundUnavailableError) as caught:
        with service._source_youtube_dl('https://www.bilibili.com/video/BV1xx411c7mD', {}):
            pytest.fail('unexpected ydl')
    safe(caught.value)


@pytest.mark.parametrize('error', [OutboundUnavailableError, lambda: ControlledHttpError()],
                         ids=['outbound', 'controlled-http'])
def test_parse_optional_subtitles_propagate_safety_errors(monkeypatch, error):
    monkeypatch.setattr(service, 'extract_info', lambda url: {'title': 't', 'formats': []})

    def fail(url):
        raise error()
    monkeypatch.setattr(service, 'resolve_public_subtitles', fail)
    with pytest.raises((OutboundError, ControlledHttpError)):
        service.parse_video(PAGE)
    with pytest.raises((OutboundError, ControlledHttpError)):
        service.extract_subtitle_tracks(PAGE)


def test_real_generic_direct_media_smoke(transport_network):
    # Locked yt-dlp GenericIE via the real default registry: a plain video/mp4 response.
    transport_network.replies.append(reply(b'\x00' * 64, b'200 OK', b'Content-Type: video/mp4\r\n'))
    with source_network_scope(context()):
        info = service.extract_info('http://public.example/clip.mp4')
    assert info['extractor_key'] == 'Generic'
    assert info['formats'] and all(f['url'].startswith('http://public.example/') for f in info['formats'])
    assert sends(transport_network) == 1


def test_ctx_instance_registers_only_allowlisted_extractors(registry, transport_network):
    # Review I1: PhantomJS-capable or handler-adding extractors never join the guarded instance.
    with source_network_scope(context()):
        with service._source_youtube_dl(PAGE, {}) as ydl:
            assert set(ydl._ies) == set(service._METADATA_EXTRACTORS)
            assert len(ydl._request_director.handlers) == 1
    assert sends(transport_network) == 0


def test_ctx_restrict_format_uses_projection(registry, transport_network):
    serve(transport_network, metadata())
    with source_network_scope(context()):
        assert service.restrict_format(PAGE, '720', 720) == '720[height<=720]'
    assert sends(transport_network) == 1


def test_close_failure_after_success_is_unavailable(registry, transport_network, monkeypatch):
    def broken(self):
        raise RuntimeError('synthetic-secret close')
    monkeypatch.setattr(service._GuardedMetadataYoutubeDL, 'close', broken)
    serve(transport_network, metadata())
    with source_network_scope(context()):
        with pytest.raises(OutboundError) as caught:
            service.extract_info(PAGE)
    assert caught.value.code == OutboundUnavailableError().code  # latch rebuilds a fixed descriptor
    safe(caught.value)


def test_caller_exception_wins_over_close_failure(registry, transport_network, monkeypatch):
    def broken(self):
        raise RuntimeError('close')
    monkeypatch.setattr(service._GuardedMetadataYoutubeDL, 'close', broken)
    body = ValueError('caller')
    with source_network_scope(context()):
        with pytest.raises(ValueError) as caught:
            with service._source_youtube_dl(PAGE, {}):
                raise body
    assert caught.value is body


@pytest.mark.parametrize('owner', ['thread', 'process'])
def test_wrong_owner_refused_before_send(registry, transport_network, monkeypatch, owner):
    from app.services import source_network
    network = context()
    name = 'get_ident' if owner == 'thread' else 'getpid'
    with source_network_scope(network):  # the scope itself checks the owner on entry
        monkeypatch.setattr(source_network, name, lambda: -1)
        with pytest.raises(OutboundError) as caught:
            service.extract_info(PAGE)
    safe(caught.value)
    assert sends(transport_network) == 0


def test_registration_failure_unavailable(registry, transport_network, monkeypatch):
    def broken(self):
        raise RuntimeError('synthetic-secret registry')
    monkeypatch.setattr(service._GuardedMetadataYoutubeDL, 'add_default_info_extractors', broken)
    with source_network_scope(context()):
        with pytest.raises(OutboundError) as caught:
            service.extract_info(PAGE)
    assert caught.value.code == OutboundUnavailableError().code
    safe(caught.value)
    assert sends(transport_network) == 0


def test_missing_plugin_opt_out_unavailable(registry, transport_network, monkeypatch):
    monkeypatch.delenv('YTDLP_NO_PLUGINS')
    with source_network_scope(context()):
        with pytest.raises(OutboundUnavailableError):
            service.extract_info(PAGE)
    assert sends(transport_network) == 0


def test_scope_reset_after_failure(registry, transport_network):
    from app.services.source_network import current_source_network
    serve(transport_network, metadata(unknown_field='x'))
    with pytest.raises(OutboundError):
        with source_network_scope(context()):
            service.extract_info(PAGE)
    assert current_source_network() is None


def test_catch_all_retry_after_budget_exhaustion_sends_nothing(registry, transport_network):
    from app.services.outbound_budget import BudgetLimits, OutboundBudget
    from app.services.source_network import SourceNetworkContext
    network = SourceNetworkContext(context().channel, OutboundBudget(BudgetLimits(seconds=100, requests=1)))
    transport_network.replies.append(reply(b'busy', b'500 Internal Server Error'))
    serve(transport_network, metadata())
    with source_network_scope(network):
        with pytest.raises(OutboundError) as caught:
            service.extract_info('http://public.example/catch')
    safe(caught.value)
    assert sends(transport_network) == 1


def test_catch_all_retry_after_deadline_sends_nothing(registry, transport_network):
    clock = [0.0]
    network = context(clock=lambda: clock[0])
    transport_network.replies.append(reply(b'busy', b'500 Internal Server Error'))
    serve(transport_network, metadata())

    def expire():
        clock[0] = 1000.0
    transport_network.before_read = expire
    with source_network_scope(network):
        with pytest.raises(OutboundError) as caught:
            service.extract_info('http://public.example/catch')
    safe(caught.value)
    assert sends(transport_network) == 1


def test_ordinary_401_then_retry_follows_u4_semantics(registry, transport_network):
    # Ordinary HTTP status is not a terminal safety error under U4; the bounded retry may proceed.
    transport_network.replies.append(reply(b'no', b'401 Unauthorized'))
    serve(transport_network, metadata())
    network = context()
    with source_network_scope(network):
        info = service.extract_info('http://public.example/catch')
    assert info['title'] == 'Unit' and sends(transport_network) == 2
    assert network.budget.snapshot().requests == 2
