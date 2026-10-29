"""B5 U5b Task 2: the worker child's 'ytdlp' executor over download_attempt (in-process, synthetic wire).

The runtime factory stays closed: only an explicitly scoped offline network reaches the source.
Run via run_b5_ytdlp_u4_offline.py (DNS/connect denied, YTDLP_NO_PLUGINS=1).
"""
import uuid

import pytest

from app.services import artifact_store as store, executors, ytdlp_service as service
from app.services.outbound_budget import BudgetLimits, OutboundBudget
from app.services.source_network import SourceNetworkContext, source_network_scope
from test_outbound_httpx import transport_network  # noqa: F401  (fixture)
from test_source_ytdlp_wiring import PAGE, metadata, registry, sends, serve  # noqa: F401  (fixture/helpers)
from test_ytdlp_guard_director import context, reply

MP4 = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom' + bytes(range(256)) * 300  # 76824 bytes


@pytest.fixture
def attempt(tmp_path):
    root = tmp_path / 'media'
    root.mkdir()
    store.provision_root(root.resolve())
    return store.prepare_attempt(root.resolve(), str(uuid.uuid4()), 1, str(uuid.uuid4()))


def request(paths, **changes):
    return dict(executor='ytdlp', url=PAGE, format_id='720', attempt_dir=str(paths.directory),
                max_bytes=200_000, deadline_seconds=60.0, job_id=paths.job_id, epoch=paths.epoch,
                attempt_id=paths.attempt_id) | changes


def execute(paths, network=None, **changes):
    events = []
    with source_network_scope(network or context()):
        result = executors.run(request(paths, **changes), paths.part, events.append)
    return result, events


def failure(paths, network=None, **changes):
    with pytest.raises(executors.ExecutionFailure) as error:
        execute(paths, network, **changes)
    return error.value.code


def test_success_moves_the_file_to_media_part_and_seals(registry, transport_network, attempt):
    serve(transport_network, metadata())
    transport_network.replies.append(reply(MP4))
    (ext, check), events = execute(attempt)
    assert (ext, check) == ('mp4', 'signature')
    assert attempt.part.read_bytes() == MP4 and attempt.part.stat().st_nlink == 1
    assert sorted(entry.name for entry in attempt.directory.iterdir()) == ['media.part']  # scratch removed
    assert events and events[-1] == {'type': 'progress', 'bytes': len(MP4), 'percent': 100.0}
    sizes = [event['bytes'] for event in events]
    assert sizes == sorted(sizes)
    candidate = store.seal_candidate(attempt, ext=ext, max_bytes=200_000, media_check=check)
    assert candidate.byte_size == len(MP4) and candidate.media_check == 'signature'


def test_wrong_container_signature_is_media_invalid(registry, transport_network, attempt):
    serve(transport_network, metadata())
    transport_network.replies.append(reply(b'<html>not a video</html>' * 10))
    assert failure(attempt) == 'media_invalid'


def test_closed_runtime_factory_is_source_unavailable_without_io(transport_network, attempt):
    with pytest.raises(executors.ExecutionFailure) as error:
        executors.run(request(attempt), attempt.part, lambda event: None)  # no scope: the factory
    assert error.value.code == 'source_unavailable' and sends(transport_network) == 0
    assert list(attempt.directory.iterdir()) == []  # the empty scratch directory is removed again


@pytest.mark.parametrize('status, code', [(b'404 Not Found', 'http_404'), (b'403 Forbidden', 'http_403'),
                                          (b'401 Unauthorized', 'http_401'), (b'410 Gone', 'http_410'),
                                          (b'412 Precondition Failed', 'http_412'), (b'418 Teapot', 'http_4xx'),
                                          (b'429 Too Many Requests', 'http_429'), (b'408 Timeout', 'http_408'),
                                          (b'503 Service Unavailable', 'http_5xx')])
def test_media_http_status_maps_to_fixed_codes(registry, transport_network, attempt, status, code):
    serve(transport_network, metadata())
    transport_network.replies.append(reply(b'', status))
    assert failure(attempt) == code


def test_media_redirect_into_a_private_address_is_source_blocked(registry, transport_network, attempt):
    serve(transport_network, metadata())
    transport_network.replies.append(reply(b'', b'302 Found', b'Location: http://10.0.0.1/v.mp4\r\n'))
    assert failure(attempt) == 'source_blocked'
    assert sends(transport_network) == 2  # the private target is never contacted


def test_private_format_url_in_metadata_is_refused_before_media_io(registry, transport_network, attempt):
    # The bounded projection refuses it (outbound_blocked) before any media GET.
    serve(transport_network, metadata(formats=[dict(url='http://10.0.0.1/v.mp4', format_id='720', ext='mp4')]))
    assert failure(attempt) == 'source_blocked' and sends(transport_network) == 1


def test_file_over_the_attempt_limit_is_file_too_large(registry, transport_network, attempt):
    serve(transport_network, metadata())
    transport_network.replies.append(reply(MP4))
    assert failure(attempt, max_bytes=len(MP4) - 1) == 'file_too_large'


def test_exhausted_request_budget_is_source_budget_exhausted(registry, transport_network, attempt):
    network = SourceNetworkContext(context().channel, OutboundBudget(BudgetLimits(seconds=100, requests=1)))
    serve(transport_network, metadata())
    assert failure(attempt, network) == 'source_budget_exhausted'


def test_unsupported_stored_format_is_format_unsupported(transport_network, attempt):
    assert failure(attempt, format_id='137+140') == 'format_unsupported'
    assert sends(transport_network) == 0


def test_missing_leaf_is_format_unsupported(registry, transport_network, attempt):
    serve(transport_network, metadata())
    assert failure(attempt, format_id='999') == 'format_unsupported'


def test_invalid_request_values_are_refused(transport_network, attempt):
    assert failure(attempt, format_id=None) == 'execution_request_invalid'
    assert failure(attempt, deadline_seconds=float('inf')) == 'execution_request_invalid'
    assert sends(transport_network) == 0


def test_signature_table_covers_every_download_container():
    assert set(store.CONTAINER_SIGNATURES) == set(service.DOWNLOAD_EXTS)


# C3-3: the attempt's scratch directory is a known object for every remover.
def test_remove_own_attempt_removes_scratch_leftovers(attempt):
    scratch = attempt.directory / 'scratch'
    scratch.mkdir()
    (scratch / 'media.bin.part').write_bytes(b'x')
    (scratch / 'media.bin').write_bytes(b'x')
    attempt.part.write_bytes(b'x')
    store.remove_own_attempt(attempt)
    assert not attempt.directory.exists()


def test_remove_own_attempt_refuses_unknown_scratch_content(attempt):
    scratch = attempt.directory / 'scratch'
    scratch.mkdir()
    (scratch / 'other.bin').write_bytes(b'x')
    with pytest.raises(store.ArtifactError, match='artifact_unknown_entry'):
        store.remove_own_attempt(attempt)
    assert (scratch / 'other.bin').exists()


def test_remove_own_attempt_refuses_nested_scratch_directories(attempt):
    nested = attempt.directory / 'scratch' / 'media.bin'
    nested.mkdir(parents=True)
    with pytest.raises(store.ArtifactError):
        store.remove_own_attempt(attempt)
    assert nested.exists()



# Review M1: mappings without a wire scenario, the progress reporter and failure paths.
def test_timeout_and_busy_are_retryable_network():
    from app.services.outbound_httpx import ControlledHttpBusyError
    from app.services.outbound_policy import OutboundError
    assert executors._source_code(OutboundError('source_timeout', 'deadline')) == 'network'
    assert executors._source_code(ControlledHttpBusyError()) == 'network'
    assert executors._source_code(OutboundError('outbound_unavailable', 'unavailable')) == 'source_unavailable'


def test_progress_reporter_emits_growing_sizes(tmp_path, monkeypatch):
    import threading
    import time
    monkeypatch.setattr(executors, 'PROGRESS_SECONDS', 0.01)
    scratch, events, stop = tmp_path / 'scratch', [], threading.Event()
    scratch.mkdir()
    reporter = threading.Thread(target=executors._report, args=(scratch, events.append, stop))
    reporter.start()
    for size in (10, 20, 30):
        (scratch / 'media.bin.part').write_bytes(b'x' * size)
        deadline = time.monotonic() + 5
        while not any(event['bytes'] == size for event in events) and time.monotonic() < deadline:
            time.sleep(0.005)
    stop.set()
    reporter.join()
    assert [event['bytes'] for event in events] == [10, 20, 30]
    assert all(event == {'type': 'progress', 'bytes': event['bytes'], 'percent': 0.0} for event in events)


def test_unexaminable_file_is_disk_error(registry, transport_network, attempt, monkeypatch):
    serve(transport_network, metadata())
    transport_network.replies.append(reply(MP4))

    def broken(path, ext):
        raise store.ArtifactError('artifact_path_unsafe')
    monkeypatch.setattr(store, 'container_signature_ok', broken)
    assert failure(attempt) == 'disk_error'


def test_link_failure_is_a_file_system_error(registry, transport_network, attempt, monkeypatch):
    import os
    serve(transport_network, metadata())
    transport_network.replies.append(reply(MP4))

    def no_link(source, target):
        raise OSError('no hard links here')
    monkeypatch.setattr(os, 'link', no_link)
    with pytest.raises(OSError):  # worker_child reports it as disk_error
        execute(attempt)
    assert not attempt.part.exists() and not (attempt.directory / 'scratch').exists()


def test_container_signature_details(tmp_path):
    def check(data, ext):
        path = tmp_path / f'f.{ext}'
        path.write_bytes(data + b'\x00' * 16)
        return store.container_signature_ok(path, ext)
    assert check(b'\x00\x00\x00\x08moov', 'mp4') and check(b'\x00\x00\x00\x08free', 'm4a')
    assert check(b'\xff\xfb\x90\x00', 'mp3') and not check(b'\xff\xf1\x50\x80', 'mp3')  # ADTS is not mp3
    assert check(b'\xff\xf1\x50\x80', 'aac') and not check(b'\x00' * 12, 'mp4')
