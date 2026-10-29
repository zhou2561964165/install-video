"""B5 U5b Task 1: download_attempt — guarded metadata projection -> one selected single file -> native HttpFD.

Synthetic wire only; run via run_b5_ytdlp_u4_offline.py (DNS/connect denied, YTDLP_NO_PLUGINS=1).
"""
import json

import pytest

from app.services import ytdlp_service as service
from app.services.outbound_budget import BudgetLimits, OutboundBudget
from app.services.outbound_policy import OutboundError, OutboundUnavailableError
from app.services.source_network import SourceNetworkContext, source_network_scope
from test_outbound_httpx import transport_network  # noqa: F401  (fixture)
from test_source_ytdlp_wiring import PAGE, metadata, registry, sends, serve  # noqa: F401  (fixture/helpers)
from test_ytdlp_guard_director import context, reply, safe

BODY = bytes(range(256)) * 260  # 66560 bytes, crosses the fixed 65536-byte read
LIMITS = dict(max_bytes=200_000, deadline_seconds=60.0)


def scratch(tmp_path):
    directory = tmp_path / 'attempt' / 'scratch'
    directory.mkdir(parents=True)
    return directory


def leaf(format_id, url, ext='mp4', **extra):
    return dict(url=url, format_id=format_id, ext=ext, **extra)


def test_explicit_format_downloads_one_file_into_scratch(registry, transport_network, tmp_path):
    directory, network = scratch(tmp_path), context()
    serve(transport_network, metadata())
    transport_network.replies.append(reply(BODY))
    with service.download_attempt(PAGE, '720', scratch_dir=directory, network=network, **LIMITS) as file:
        assert file.path == directory / 'media.bin' and file.ext == 'mp4'
        assert file.path.read_bytes() == BODY
    assert list(directory.iterdir()) == []  # the seam cleans its own files; the caller moves before exit
    wire = b''.join(transport_network.writes)
    assert b'GET http://cdn.example/v720.mp4' in wire and b'Cookie' not in wire and b'sub.example' not in wire
    saved = network.budget.snapshot()
    assert saved.requests == 2 and sends(transport_network) == 2


def test_default_selection_takes_the_last_complete_single_file(registry, transport_network, tmp_path):
    formats = [leaf('low', 'http://cdn.example/low.mp4', vcodec='avc1', acodec='mp4a'),
               leaf('video-only', 'http://cdn.example/vo.mp4', vcodec='avc1', acodec='none'),
               leaf('high', 'http://cdn.example/high.webm', ext='webm'),
               leaf('audio-only', 'http://cdn.example/ao.m4a', ext='m4a', vcodec='none', acodec='mp4a')]
    serve(transport_network, metadata(formats=formats))
    transport_network.replies.append(reply(BODY))
    with service.download_attempt(PAGE, '', scratch_dir=scratch(tmp_path), network=context(), **LIMITS) as file:
        assert file.ext == 'webm'
    wire = b''.join(transport_network.writes)
    assert b'GET http://cdn.example/high.webm' in wire and b'/low.mp4' not in wire and b'/ao.m4a' not in wire


def test_explicit_audio_only_format_is_allowed(registry, transport_network, tmp_path):
    formats = [leaf('audio', 'http://cdn.example/a.m4a', ext='m4a', vcodec='none', acodec='mp4a')]
    serve(transport_network, metadata(formats=formats))
    transport_network.replies.append(reply(BODY))
    with service.download_attempt(PAGE, 'audio', scratch_dir=scratch(tmp_path), network=context(), **LIMITS) as file:
        assert file.ext == 'm4a'


def test_real_generic_direct_media(transport_network, tmp_path):
    # Locked yt-dlp GenericIE: a plain video/mp4 response is the metadata; the file is a second GET.
    transport_network.replies.append(reply(b'\x00' * 64, b'200 OK', b'Content-Type: video/mp4\r\n'))
    transport_network.replies.append(reply(BODY, b'200 OK', b'Content-Type: video/mp4\r\n'))
    with service.download_attempt('http://public.example/clip.mp4', '', scratch_dir=scratch(tmp_path),
                                  network=context(), **LIMITS) as file:
        assert file.ext == 'mp4' and file.path.read_bytes() == BODY
    assert sends(transport_network) == 2


@pytest.mark.parametrize('format_id, formats', [
    ('missing', None),  # no such format id
    ('', [leaf('vo', 'http://cdn.example/vo.mp4', vcodec='avc1', acodec='none'),
          leaf('ao', 'http://cdn.example/ao.m4a', ext='m4a', vcodec='none', acodec='mp4a')]),  # needs a merge
    ('exe', [leaf('exe', 'http://cdn.example/x.exe', ext='exe')]),  # not a media container
    ('noext', [dict(url='http://cdn.example/x', format_id='noext')]),  # no ext at all
    ('dup', [leaf('dup', 'http://cdn.example/a.mp4'), leaf('dup', 'http://cdn.example/b.mp4')]),  # ambiguous
], ids=['missing', 'split-streams', 'exe', 'no-ext', 'duplicate-id'])
def test_unselectable_formats_fail_closed_before_media_io(registry, transport_network, tmp_path, format_id, formats):
    directory = scratch(tmp_path)
    serve(transport_network, metadata(**({} if formats is None else {'formats': formats})))
    with pytest.raises(service.DownloadFormatUnsupported) as error:
        with service.download_attempt(PAGE, format_id, scratch_dir=directory, network=context(), **LIMITS):
            pytest.fail('must not yield')
    safe(error.value)
    assert sends(transport_network) == 1 and list(directory.iterdir()) == []


def test_manifest_format_makes_the_whole_metadata_unavailable(registry, transport_network, tmp_path):
    formats = [leaf('hls', 'http://cdn.example/master.m3u8', protocol='m3u8_native')]
    serve(transport_network, metadata(formats=formats))
    with pytest.raises(OutboundError):
        with service.download_attempt(PAGE, 'hls', scratch_dir=scratch(tmp_path), network=context(), **LIMITS):
            pytest.fail('must not yield')
    assert sends(transport_network) == 1


def test_without_network_the_closed_runtime_factory_refuses_before_io(transport_network, tmp_path):
    with pytest.raises(OutboundUnavailableError):
        with service.download_attempt(PAGE, '720', scratch_dir=scratch(tmp_path), **LIMITS):
            pytest.fail('must not yield')
    assert sends(transport_network) == 0


def test_scoped_network_is_used_when_not_passed(registry, transport_network, tmp_path):
    serve(transport_network, metadata())
    transport_network.replies.append(reply(BODY))
    with source_network_scope(context()):
        with service.download_attempt(PAGE, '720', scratch_dir=scratch(tmp_path), **LIMITS) as file:
            assert file.path.read_bytes() == BODY


def test_bilibili_is_refused_before_io(transport_network, tmp_path):
    with pytest.raises(OutboundUnavailableError):
        with service.download_attempt('https://www.bilibili.com/video/BV1xx411c7mD', '', scratch_dir=scratch(tmp_path),
                                      network=context(), **LIMITS):
            pytest.fail('must not yield')
    assert sends(transport_network) == 0


def test_file_over_the_attempt_limit_is_refused_and_cleaned(registry, transport_network, tmp_path):
    directory = scratch(tmp_path)
    serve(transport_network, metadata())
    transport_network.replies.append(reply(BODY))
    with pytest.raises(OutboundError) as error:
        with service.download_attempt(PAGE, '720', scratch_dir=directory, network=context(),
                                      max_bytes=len(BODY) - 1, deadline_seconds=60.0):
            pytest.fail('must not yield')
    safe(error.value)
    assert list(directory.iterdir()) == []


def test_source_budget_is_shared_by_metadata_and_media(registry, transport_network, tmp_path):
    budget = OutboundBudget(BudgetLimits(seconds=100, requests=1))  # metadata only fits
    network = SourceNetworkContext(context().channel, budget)
    serve(transport_network, metadata())
    transport_network.replies.append(reply(BODY))
    with pytest.raises(OutboundError):
        with service.download_attempt(PAGE, '720', scratch_dir=scratch(tmp_path), network=network, **LIMITS):
            pytest.fail('must not yield')
    assert sends(transport_network) == 1


@pytest.mark.parametrize('bad', [dict(max_bytes=0), dict(max_bytes=True), dict(deadline_seconds=0),
                                 dict(deadline_seconds=float('inf')), dict(format_id=None), dict(format_id='x' * 65)])
def test_invalid_arguments_refused_before_io(transport_network, tmp_path, bad):
    arguments = dict(format_id='720', scratch_dir=scratch(tmp_path), network=context(), **LIMITS) | bad
    format_id = arguments.pop('format_id')
    with pytest.raises((ValueError, OutboundUnavailableError, service.DownloadFormatUnsupported)):
        with service.download_attempt(PAGE, format_id, **arguments):
            pytest.fail('must not yield')
    assert sends(transport_network) == 0



# Review I3: the three format-id shapes the product stores; anything else fails before any I/O.
@pytest.mark.parametrize('format_id, chosen', [
    ('best', b'/h1080.mp4'),
    ('bestvideo[height<=720]+bestaudio/best[height<=720]', b'/h720.mp4'),
    ('h360[height<=720]', b'/h360.mp4'),
    ('best[height<=720]', b'/h720.mp4'),
    ('h1080', b'/h1080.mp4'),
])
def test_product_format_ids(registry, transport_network, tmp_path, format_id, chosen):
    formats = [leaf('h1080', 'http://cdn.example/h1080.mp4', height=1080),  # DOM order: best first
               leaf('h360', 'http://cdn.example/h360.mp4', height=360),
               leaf('h720', 'http://cdn.example/h720.mp4', height=720),
               leaf('nosize', 'http://cdn.example/nosize.mp4')]
    serve(transport_network, metadata(formats=formats))
    transport_network.replies.append(reply(BODY))
    with service.download_attempt(PAGE, format_id, scratch_dir=scratch(tmp_path), network=context(), **LIMITS):
        pass
    assert b'GET http://cdn.example' + chosen in b''.join(transport_network.writes)


@pytest.mark.parametrize('format_id', ['720+140', 'bestvideo+bestaudio', 'bestvideo[height<=720]+bestaudio/best[height<=480]',
                                       'x' * 65, 'a/b'])
def test_unsupported_format_ids_fail_before_any_io(transport_network, tmp_path, format_id):
    with pytest.raises(service.DownloadFormatUnsupported):
        with service.download_attempt(PAGE, format_id, scratch_dir=scratch(tmp_path), network=context(), **LIMITS):
            pytest.fail('must not yield')
    assert sends(transport_network) == 0


def test_height_limit_excludes_taller_and_unknown_heights(registry, transport_network, tmp_path):
    formats = [leaf('tall', 'http://cdn.example/tall.mp4', height=1080), leaf('unknown', 'http://cdn.example/u.mp4')]
    serve(transport_network, metadata(formats=formats))
    with pytest.raises(service.DownloadFormatUnsupported):
        with service.download_attempt(PAGE, 'bestvideo[height<=720]+bestaudio/best[height<=720]',
                                      scratch_dir=scratch(tmp_path), network=context(), **LIMITS):
            pytest.fail('must not yield')
    assert sends(transport_network) == 1


# Review I2: a lone audio-only direct link is a single file; it is not filtered as a split stream.
def test_real_generic_direct_audio(transport_network, tmp_path):
    transport_network.replies.append(reply(b'ID3' + b'\x00' * 61, b'200 OK', b'Content-Type: audio/mpeg\r\n'))
    transport_network.replies.append(reply(BODY, b'200 OK', b'Content-Type: audio/mpeg\r\n'))
    with service.download_attempt('http://public.example/song.mp3', '', scratch_dir=scratch(tmp_path),
                                  network=context(), **LIMITS) as file:
        assert file.ext == 'mp3'


# Review I1: extraction keeps the tight metadata limit even when the attempt allows far more.
def test_extraction_keeps_the_metadata_size_limit(registry, transport_network, tmp_path):
    big = json.dumps(metadata(description='x' * (4 * 1024 * 1024))).encode()
    transport_network.replies.append(reply(big))
    network = context()
    with pytest.raises(OutboundError) as error:
        with service.download_attempt(PAGE, '720', scratch_dir=scratch(tmp_path), network=network,
                                      max_bytes=50_000_000, deadline_seconds=60.0):
            pytest.fail('must not yield')
    # The read itself stops at the metadata limit (not the later projection bounds on a full read).
    assert error.value.code == 'source_too_large' and network.budget.snapshot().raw_bytes <= 1024 * 1024 + 65536
    assert sends(transport_network) == 1


# Review I4: an extraction-phase HTTP status keeps its class (a transient 503 stays retryable).
@pytest.mark.parametrize('status, code', [(b'503 Service Unavailable', 503), (b'429 Too Many Requests', 429),
                                          (b'404 Not Found', 404)])
def test_extraction_http_status_is_preserved(registry, transport_network, tmp_path, status, code):
    transport_network.replies.append(reply(b'', status))
    with pytest.raises(service.ControlledHttpStatusError) as error:
        with service.download_attempt(PAGE, '720', scratch_dir=scratch(tmp_path), network=context(), **LIMITS):
            pytest.fail('must not yield')
    assert error.value.source_status == code
    safe(error.value)


# Review M4/M2: only plain request headers reach HttpFD; a Bilibili media target is refused.
def test_only_plain_headers_reach_the_media_request(registry, transport_network, tmp_path):
    formats = [leaf('720', 'http://cdn.example/v.mp4', http_headers={'User-Agent': 'ua-x', 'Range': 'bytes=5-',
                                                                     'If-None-Match': 'tag'})]
    serve(transport_network, metadata(formats=formats))
    transport_network.replies.append(reply(BODY))
    with service.download_attempt(PAGE, '720', scratch_dir=scratch(tmp_path), network=context(), **LIMITS):
        pass
    media = b''.join(transport_network.writes).split(b'GET http://cdn.example/v.mp4', 1)[1].lower()
    assert b'ua-x' in media and b'range' not in media and b'if-none-match' not in media


def test_bilibili_media_target_is_refused_before_media_io(registry, transport_network, tmp_path):
    formats = [leaf('720', 'http://www.bilibili.com/v.mp4')]
    serve(transport_network, metadata(formats=formats))
    transport_network.replies.append(reply(BODY))
    with pytest.raises(OutboundError):
        with service.download_attempt(PAGE, '720', scratch_dir=scratch(tmp_path), network=context(), **LIMITS):
            pytest.fail('must not yield')
    assert sends(transport_network) == 1 and b'bilibili.com' not in b''.join(transport_network.writes)
