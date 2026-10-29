"""F gate Bilibili adapter: synthetic controlled HTTP, no live source requests."""
import json

import pytest

from app.config import settings
from app.services import bilibili_session as session, ytdlp_service as service
from app.services.source_network import source_network_scope
from test_outbound_httpx import transport_network  # noqa: F401
from test_ytdlp_guard_director import context, reply
from test_bilibili_api_source import URL, fixtures
from app.services.outbound_policy import OutboundError


def api(wire, *, high=False):
    view, play = fixtures()
    if high:
        play['dash']['video'].append(dict(play['dash']['video'][0], id=80, height=1080, width=1920,
            baseUrl='https://upos-test.bilivideo.com/high.m4s', backupUrl=[]))
    for payload in (view, play):
        wire.replies.extend([b'HTTP/1.1 200 Connection established\r\n\r\n',
                             reply(json.dumps({'code': 0, 'data': payload}).encode())])


def test_context_parse_official_api_only_not_legacy(transport_network, monkeypatch):
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    monkeypatch.setattr(service, '_youtube_dl', lambda *a: pytest.fail('legacy path'))
    api(transport_network)
    with source_network_scope(context()):
        meta, choices = service.parse_video(URL)
    assert meta['title'] == 'Example' and meta['platform'].lower() == 'bilibili'
    assert choices[0]['height'] == 720
    gets = [p for p in transport_network.writes if p.startswith(b'GET ')]
    assert len(gets) == 2
    assert gets[0].startswith(b'GET /x/web-interface/view?')
    assert gets[1].startswith(b'GET /x/player/playurl?')


def test_cookie_snapshot_scope_never_reads_child_file(monkeypatch):
    snapshot = '# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tTRUE\t0\ttest\tsynthetic-secret\n'
    monkeypatch.setattr(session, '_read_file', lambda _: pytest.fail('child file read'))
    with session.cookie_snapshot_scope(snapshot):
        jar = session.cookie_jar_for_url(URL)
        assert [(c.name, c.value) for c in jar] == [('test', 'synthetic-secret')]
    with session.cookie_snapshot_scope(None):
        assert list(session.cookie_jar_for_url(URL)) == []


def test_dash_download_both_streams_local_merge_height_and_progress(transport_network, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    api(transport_network, high=True)
    for data in (b'video-source', b'audio-source'):
        transport_network.replies.extend([b'HTTP/1.1 200 Connection established\r\n\r\n', reply(data)])
    merged = []
    def merge(video, audio, output, **kwargs):
        merged.append((video.read_bytes(), audio.read_bytes(), kwargs))
        output.write_bytes(b'local-mp4')
    monkeypatch.setattr(service, '_merge_bilibili_files', merge, raising=False)
    progress = []
    with service.download_attempt(URL, 'bestvideo[height<=720]+bestaudio/best[height<=720]',
            scratch_dir=tmp_path, max_bytes=100, deadline_seconds=30, network=context(),
            progress_hook=progress.append) as downloaded:
        assert downloaded.ext == 'mp4' and downloaded.path.read_bytes() == b'local-mp4'
    assert merged[0][:2] == (b'video-source', b'audio-source')
    assert progress[-1] == 24 and progress == sorted(progress)
    assert not any(b'/high.m4s' in p for p in transport_network.writes)
    assert list(tmp_path.iterdir()) == []


def test_dash_failure_retains_accounting_before_cleanup(transport_network, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    api(transport_network)
    transport_network.replies.extend([b'HTTP/1.1 200 Connection established\r\n\r\n', reply(b'video-source'),
                                     b'HTTP/1.1 200 Connection established\r\n\r\n', reply(b'', b'403 Forbidden')])
    progress = []
    with pytest.raises(Exception):
        with service.download_attempt(URL, 'best', scratch_dir=tmp_path, max_bytes=100,
                deadline_seconds=30, network=context(), progress_hook=progress.append):
            pytest.fail('failed source yielded output')
    assert progress[-1] == len(b'video-source')
    assert list(tmp_path.iterdir()) == []


def test_official_api_cookies_never_reach_cdn(transport_network, monkeypatch, tmp_path, capsys):
    api(transport_network)
    for data in (b'video', b'audio'):
        transport_network.replies.extend([b'HTTP/1.1 200 Connection established\r\n\r\n', reply(data)])
    monkeypatch.setattr(service, '_merge_bilibili_files', lambda v, a, o, **kw: o.write_bytes(b'merged'))
    snapshot = '# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tTRUE\t0\ttest\tsynthetic-secret\n'
    with session.cookie_snapshot_scope(snapshot):
        with service.download_attempt(URL, 'best', scratch_dir=tmp_path, max_bytes=100,
                deadline_seconds=30, network=context()):
            pass
    gets = [p for p in transport_network.writes if p.startswith(b'GET ')]
    assert len(gets) == 4
    assert all(b'test=synthetic-secret' in p for p in gets[:2])
    assert all(b'Cookie:' not in p and b'synthetic-secret' not in p for p in gets[2:])
    assert capsys.readouterr() == ('', '')


@pytest.mark.parametrize('url', ['https://b23.tv/a', URL.replace('/video/', '/evil/'),
                               URL.replace('https://', 'https://user@')])
def test_invalid_bilibili_never_uses_legacy_or_network(url, transport_network, monkeypatch):
    monkeypatch.setattr(service, '_youtube_dl', lambda *a: pytest.fail('legacy path'))
    with source_network_scope(context()), pytest.raises(Exception):
        service.parse_video(url)
    assert transport_network.writes == []


def test_both_media_total_is_bounded_not_each_stream(transport_network, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    api(transport_network)
    for data in (b'v' * 60, b'a' * 60):
        transport_network.replies.extend([b'HTTP/1.1 200 Connection established\r\n\r\n', reply(data)])
    with pytest.raises(OutboundError) as error:
        with service.download_attempt(URL, 'best', scratch_dir=tmp_path, max_bytes=100,
                deadline_seconds=30, network=context()):
            pytest.fail('source over aggregate cap yielded')
    assert error.value.code == 'source_too_large' and list(tmp_path.iterdir()) == []


def test_executor_failure_reports_first_stream_before_deleting_files(transport_network, monkeypatch, tmp_path):
    from app.services import executors
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    api(transport_network)
    transport_network.replies.extend([b'HTTP/1.1 200 Connection established\r\n\r\n', reply(b'v' * 60),
        b'HTTP/1.1 200 Connection established\r\n\r\n', reply(b'', b'403 Forbidden')])
    events = []
    with source_network_scope(context()), pytest.raises(executors.ExecutionFailure) as error:
        executors.run(dict(executor='ytdlp', url=URL, format_id='best', max_bytes=100,
            deadline_seconds=30), tmp_path / 'media.part', events.append)
    assert error.value.code == 'http_403'
    assert events[-1]['bytes'] == 60
    assert list(tmp_path.iterdir()) == []


def test_cookie_snapshot_parent_reads_current_file_and_repr_hides_it(tmp_path, monkeypatch):
    from app.services.execution_supervisor import ExecutionRequest
    from test_bilibili_session import cookie_file
    path = cookie_file(tmp_path, monkeypatch)
    first = session.cookie_snapshot_for_url(URL)
    path.write_text(path.read_text().replace('synthetic-secret-never-log', 'changed-secret'), encoding='utf8')
    second = session.cookie_snapshot_for_url(URL)
    assert 'synthetic-secret-never-log' in first and 'changed-secret' in second
    request = ExecutionRequest('job', 1, 'attempt', URL, 'best', str(tmp_path), 100, 30, 'ytdlp', second)
    assert 'changed-secret' not in repr(request)
    assert session.cookie_snapshot_for_url('https://public.example/v') is None


@pytest.mark.parametrize('snapshot', ['invalid-secret', '# Netscape HTTP Cookie File\n' + 's' * 17000, 42, '\ud800'])
def test_snapshot_invalid_is_silent(snapshot, capsys):
    with pytest.raises(session.SessionError) as error:
        with session.cookie_snapshot_scope(snapshot):
            pytest.fail('invalid snapshot accepted')
    assert 'invalid-secret' not in str(error.value)
    assert capsys.readouterr() == ('', '')


def test_local_merge_real_mp4_and_m4a(tmp_path):
    import shutil
    import subprocess
    import time
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        pytest.skip('ffmpeg not installed')
    video, audio, output = (tmp_path / n for n in ('video.bin', 'audio.bin', 'media.bin'))
    subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'color=size=64x48:rate=1',
        '-t', '1', '-an', '-c:v', 'mpeg4', '-f', 'mp4', str(video)], check=True, capture_output=True)
    subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'anullsrc',
        '-t', '1', '-vn', '-c:a', 'aac', '-f', 'mp4', str(audio)], check=True, capture_output=True)
    service._merge_bilibili_files(video, audio, output, max_bytes=100000, deadline=time.monotonic()+10)
    assert output.stat().st_size > 0
    result = subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-show_entries',
        'stream=codec_type', '-of', 'csv=p=0', str(output)], check=True, capture_output=True)
    assert set(result.stdout.split()) == {b'video', b'audio'}


def test_dash_scratch_symlink_refused_before_metadata(tmp_path, transport_network, monkeypatch):
    target, link = tmp_path / 'target', tmp_path / 'link'
    target.mkdir()
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip('symlink privilege unavailable')
    with pytest.raises(Exception):
        with service.download_attempt(URL, 'best', scratch_dir=link, max_bytes=100,
                deadline_seconds=30, network=context()):
            pytest.fail('symlink scratch accepted')
    assert transport_network.writes == []


def test_dash_missing_scratch_refused_before_metadata(tmp_path, transport_network):
    with pytest.raises(Exception):
        with service.download_attempt(URL, 'best', scratch_dir=tmp_path/'missing', max_bytes=100,
                deadline_seconds=30, network=context()):
            pytest.fail('missing scratch accepted')
    assert transport_network.writes == []


def test_cleanup_removes_only_fixed_dash_names(tmp_path):
    import uuid
    from app.services import artifact_store as store
    root = tmp_path / 'root'
    root.mkdir()
    store.provision_root(root.resolve())
    paths = store.prepare_attempt(root.resolve(), str(uuid.uuid4()), 1, str(uuid.uuid4()))
    scratch = paths.directory/'scratch'
    scratch.mkdir()
    for name in ('video.bin', 'audio.bin', 'media.bin'):
        (scratch/name).write_bytes(b'synthetic')
    (scratch/'unknown.bin').write_bytes(b'preserve')
    with pytest.raises(store.ArtifactError, match='artifact_unknown_entry'):
        store.remove_own_attempt(paths)
    assert (scratch/'video.bin').exists() and (scratch/'unknown.bin').read_bytes() == b'preserve'
    (scratch/'unknown.bin').unlink()
    store.remove_own_attempt(paths)
    assert not paths.directory.exists()


def test_worker_child_consumes_snapshot_privately_and_restores_scope(tmp_path, monkeypatch):
    import io
    from types import SimpleNamespace
    from app import worker_child
    snapshot = '# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tTRUE\t0\ttest\tsynthetic-secret\n'
    message = dict(attempt_dir=str(tmp_path), executor='ytdlp', bili_cookie_snapshot=snapshot)
    monkeypatch.setattr(worker_child.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(json.dumps(message).encode()+b'\n')))
    monkeypatch.setattr(worker_child.threading.Thread, 'start', lambda self: None)
    events = []
    monkeypatch.setattr(worker_child, '_emit', events.append)
    def execute(request, part, emit):
        assert 'bili_cookie_snapshot' not in request
        assert [c.value for c in session.cookie_jar_for_url(URL)] == ['synthetic-secret']
        return 'mp4', 'signature'
    monkeypatch.setattr(worker_child.executors, 'run', execute)
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    assert worker_child.main() == 0
    assert events == [{'type': 'done', 'ext': 'mp4', 'media_check': 'signature'}]
    assert list(session.cookie_jar_for_url(URL)) == []


def test_cdn_redirect_refused_without_following(transport_network, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    api(transport_network)
    transport_network.replies.extend([b'HTTP/1.1 200 Connection established\r\n\r\n',
        reply(b'', b'302 Found', b'Location: https://other.bilivideo.com/v\r\n')])
    with pytest.raises(OutboundError):
        with service.download_attempt(URL, 'best', scratch_dir=tmp_path, max_bytes=100,
                deadline_seconds=30, network=context()):
            pytest.fail('redirect yielded media')
    assert len([p for p in transport_network.writes if p.startswith(b'GET ')]) == 3


def test_metadata_reuses_original_request_budget(transport_network, monkeypatch):
    from app.services.outbound_budget import BudgetLimits, OutboundBudget
    from app.services.source_network import SourceNetworkContext
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    api(transport_network)
    network = SourceNetworkContext(context().channel, OutboundBudget(BudgetLimits(requests=1)))
    with source_network_scope(network), pytest.raises(OutboundError) as error:
        service.parse_video(URL)
    assert error.value.code == 'source_budget_exhausted'
    assert len([p for p in transport_network.writes if p.startswith(b'GET ')]) == 1


def test_local_merge_timeout_kills_its_process(tmp_path, monkeypatch):
    import time
    processes = []
    class Hanging:
        returncode = None
        def __init__(self, *a, **kw):
            self.killed = False
            processes.append(self)
        def poll(self):
            return self.returncode
        def kill(self):
            self.killed = True
            self.returncode = -1
        def wait(self):
            return self.returncode
    monkeypatch.setattr(service.subprocess, 'Popen', Hanging)
    with pytest.raises(OutboundError) as error:
        service._merge_bilibili_files(tmp_path/'video.bin', tmp_path/'audio.bin', tmp_path/'media.bin',
            max_bytes=100, deadline=time.monotonic()-1)
    assert error.value.code == 'source_timeout' and processes[0].killed


def test_download_deadline_expires_during_metadata_before_second_api(transport_network, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    api(transport_network)
    clock = [0.0]
    monkeypatch.setattr(service.time, 'monotonic', lambda: clock[0])
    # The first API body arrives after the complete attempt's deadline. No
    # second metadata or media request may be issued, and no merger may start.
    def tick():
        if any(p.startswith(b'GET ') for p in transport_network.writes):
            clock[0] = 2.0
    transport_network.before_read = tick
    with pytest.raises(OutboundError) as error:
        with service.download_attempt(URL, 'best', scratch_dir=tmp_path, max_bytes=100,
                deadline_seconds=1, network=context()):
            pytest.fail('expired metadata yielded output')
    assert error.value.code == 'source_timeout'
    assert len([p for p in transport_network.writes if p.startswith(b'GET ')]) == 1


def test_api_business_denial_has_safe_public_classification(transport_network, monkeypatch, capsys):
    monkeypatch.setattr(settings, 'bilibili_cookie_file', '')
    transport_network.replies.extend([b'HTTP/1.1 200 Connection established\r\n\r\n',
        reply(json.dumps({'code': -352, 'message': 'synthetic-secret'}).encode())])
    with source_network_scope(context()), pytest.raises(Exception) as error:
        service.parse_video(URL)
    assert service.safe_bilibili_error_category(error.value) == 'verification_required'
    assert 'synthetic-secret' not in str(error.value) and capsys.readouterr() == ('', '')


def test_canonical_height_binding_reuses_parsed_options_without_source():
    options = [{'format_id': 'bestvideo[height<=720]+bestaudio/best[height<=720]', 'height': 720}]
    assert service.restrict_format_options(options, options[0]['format_id'], 720) == options[0]['format_id']
    with pytest.raises(ValueError):
        service.restrict_format_options(options, options[0]['format_id'], 480)


def test_worker_counts_dash_scratch_after_abrupt_child_exit(tmp_path):
    from types import SimpleNamespace
    from app.services import download_worker
    scratch = tmp_path/'scratch'
    scratch.mkdir()
    (scratch/'video.bin').write_bytes(b'v' * 60)
    (scratch/'audio.bin').write_bytes(b'a' * 20)
    assert download_worker._part_size(SimpleNamespace(part=tmp_path/'media.part', directory=tmp_path)) == 80


@pytest.mark.parametrize('error', [service._BilibiliSourceError('verification_required'),
                                 session.SessionError('synthetic-secret')])
def test_executor_maps_safe_bilibili_errors_without_text(tmp_path, monkeypatch, error, capsys):
    from contextlib import contextmanager
    from app.services import executors
    @contextmanager
    def stopped(*args, **kwargs):
        raise error
        yield
    monkeypatch.setattr(service, 'download_attempt', stopped)
    with pytest.raises(executors.ExecutionFailure) as result:
        executors.run(dict(executor='ytdlp', url=URL, format_id='best', max_bytes=100,
            deadline_seconds=30), tmp_path/'media.part', lambda event: None)
    assert result.value.code == 'source_unavailable'
    assert 'synthetic-secret' not in str(result.value) and capsys.readouterr() == ('', '')


def test_non_dash_projection_is_safe_unsupported_without_fallback(transport_network, monkeypatch):
    monkeypatch.setattr(service, 'extract_api_video', lambda *a, **kw: {
        'title': 'Progressive source', 'play_info': {'durl': [{'url': 'https://upos-test.bilivideo.com/v'}]}})
    monkeypatch.setattr(service, '_youtube_dl', lambda *a: pytest.fail('legacy fallback'))
    with source_network_scope(context()), pytest.raises(Exception) as error:
        service.parse_video(URL)
    assert not isinstance(error.value, KeyError)
    assert service.safe_bilibili_error_category(error.value) == 'unsupported_site'
    assert transport_network.writes == []
