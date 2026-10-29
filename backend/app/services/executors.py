"""C3 executor registry, run inside the worker child process (no DB or credential files).

An executor writes only the attempt's media.part, bounded by max_bytes, and reports
progress through `emit`. 'ytdlp' (B5 U5b) downloads one selected single file through
ytdlp_service.download_attempt (Generic single file or controlled Bilibili DASH)
into the attempt's scratch directory and links the local result to
media.part; without an explicit source network the closed runtime factory makes it
'source_unavailable'. 'fake:<scenario>' exists for process-level tests only and needs
the explicit DOWNLOAD_WORKER_ALLOW_FAKE=1 opt-in.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

_CHUNK = 64 * 1024
ignore_stop = False  # set only by fake:hang_tree, to prove the force-kill path


class ExecutionFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def fake_allowed() -> bool:
    return os.environ.get('DOWNLOAD_WORKER_ALLOW_FAKE') == '1'


def known(executor: str) -> bool:
    return executor == 'ytdlp' or (executor.startswith('fake:') and fake_allowed())


def available(executor: str, *, isolated: bool = False) -> bool:
    """Whether a worker may lease work for this executor: 'ytdlp' only when the worker starts its
    children isolated (external gate G4: download user, firewall, controlled proxy); without that
    the child's runtime source network stays closed anyway."""
    return known(executor) and (executor != 'ytdlp' or isolated is True)


def _write(part: Path, size: int, max_bytes: int, emit) -> None:
    written = 0
    with open(part, 'xb') as handle:
        while written < size:
            block = min(_CHUNK, size - written)
            if written + block > max_bytes:
                raise ExecutionFailure('file_too_large')
            handle.write(b'\0' * block)
            written += block
            emit({'type': 'progress', 'bytes': written, 'percent': round(100.0 * written / size, 2)})
        handle.flush()
        os.fsync(handle.fileno())


def _fake(scenario: str, request: dict, part: Path, emit):
    kind, _, argument = scenario.partition(':')
    directory = part.parent
    if kind == 'ok':
        _write(part, int(argument), request['max_bytes'], emit)
        return 'mp4', 'verified'
    if kind == 'okmp4':  # an mp4-signed file that over-claims 'verified' (G3/G4: the worker re-checks)
        _write(part, int(argument), request['max_bytes'], emit)
        with open(part, 'r+b') as handle:
            handle.write(b'\0\0\0\x18ftypisom')
        return 'mp4', 'verified'
    if kind == 'oksig':  # like ok, with the container-signature check value (B5 U5b)
        _write(part, int(argument), request['max_bytes'], emit)
        return 'mp4', 'signature'
    if kind == 'silent':  # writes the bytes but never reports progress
        with open(part, 'xb') as handle:
            handle.write(b'\0' * int(argument))
        return 'mp4', 'verified'
    if kind == 'progress_then_hang':
        _write(part, int(argument), request['max_bytes'], emit)
        time.sleep(600)
    if kind == 'ok_orphan':
        # Succeeds but leaves a group member running (like a merger that outlives the parent).
        _write(part, int(argument), request['max_bytes'], emit)
        orphan = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (directory / 'grandchild.pid').write_text(str(orphan.pid), encoding='ascii')
        return 'mp4', 'verified'
    if kind == 'error':
        raise ExecutionFailure(argument)
    if kind == 'crash':
        os._exit(3)
    if kind == 'garbage':
        sys.stdout.write('not json\n')
        sys.stdout.flush()
        time.sleep(30)
    if kind == 'longline':
        sys.stdout.write('{"type":"progress","bytes":1,"percent":' + '1' * 5000 + '}\n')
        sys.stdout.flush()
        time.sleep(30)
    if kind == 'flood':
        for index in range(10_005):
            sys.stdout.write(json.dumps({'type': 'progress', 'bytes': index, 'percent': 0.0}) + '\n')
        sys.stdout.flush()
        time.sleep(30)
    if kind == 'forged':
        sys.stdout.write(json.dumps({'type': 'done', 'ext': 'mp4', 'media_check': 'verified',
                                     'job_id': 'someone-else'}) + '\n')
        sys.stdout.flush()
        time.sleep(30)
    if kind == 'env':
        (directory / 'env.json').write_text(json.dumps(dict(os.environ)), encoding='utf8')
        _write(part, 10, request['max_bytes'], emit)
        return 'mp4', 'verified'
    if kind == 'hang':
        time.sleep(600)
    if kind == 'flood_forever':
        line = json.dumps({'type': 'progress', 'bytes': 1, 'percent': 0.0}) + '\n'
        while True:
            sys.stdout.write(line)
    if kind in ('done_then_flood', 'done_then_hang'):
        sys.stdout.write(json.dumps({'type': 'done', 'ext': 'mp4', 'media_check': 'verified'}) + '\n')
        sys.stdout.flush()
        if kind == 'done_then_flood':
            for index in range(1000):
                sys.stdout.write(json.dumps({'type': 'progress', 'bytes': index, 'percent': 0.0}) + '\n')
            sys.stdout.flush()
        time.sleep(600)
    if kind == 'hang_tree_obedient':  # like hang_tree, but honours the stop channel (stdin EOF)
        grandchild = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (directory / 'grandchild.pid').write_text(str(grandchild.pid), encoding='ascii')
        time.sleep(600)
    if kind == 'hang_pid':
        (directory / 'child.pid').write_text(str(os.getpid()), encoding='ascii')
        time.sleep(600)
    if kind == 'partial':
        size, _, code = argument.partition(':')  # writes some bytes, then fails with code
        _write(part, int(size), request['max_bytes'], emit)
        raise ExecutionFailure(code)
    if kind == 'hang_tree':
        # Ignore the polite stop so the supervisor must force-kill the whole tree.
        global ignore_stop
        ignore_stop = True
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        grandchild = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])
        (directory / 'grandchild.pid').write_text(str(grandchild.pid), encoding='ascii')
        time.sleep(600)
    raise ExecutionFailure('execution_scenario_unknown')


def run(request: dict, part: Path, emit):
    """Returns (ext, media_check) or raises ExecutionFailure(code)."""
    executor = request['executor']
    if executor == 'ytdlp':
        return _ytdlp(request, part, emit)
    if executor.startswith('fake:') and fake_allowed():
        return _fake(executor[5:], request, part, emit)
    raise ExecutionFailure('executor_unknown')


PROGRESS_SECONDS = 0.5
# Packages whose absence makes the ytdlp executor unavailable (any other import error is a bug).
_SOURCE_STACK = frozenset({'yt_dlp', 'httpx', 'httpcore', 'certifi', 'h11', 'idna', 'sniffio', 'anyio'})


def _source_code(error) -> str:
    """Fixed child codes for the safe source errors (C1 classifies retry/failed/review)."""
    from .outbound_httpx import ControlledHttpBusyError, ControlledHttpStatusError
    if isinstance(error, ControlledHttpStatusError):
        status = error.source_status
        if status in (401, 403, 404, 408, 410, 412, 429):
            return f'http_{status}'
        return 'http_5xx' if status >= 500 else 'http_4xx'
    if isinstance(error, ControlledHttpBusyError):
        return 'network'
    # The guarded layer re-creates safe errors as plain OutboundError(code, reason): map by code.
    code = getattr(error, 'code', None)
    if code in ('outbound_blocked', 'invalid_url'):
        return 'source_blocked'
    if code == 'source_too_large':
        return 'file_too_large'
    if code == 'source_timeout':
        return 'network'
    if code == 'source_budget_exhausted':
        return 'source_budget_exhausted'
    return 'source_unavailable'


def _report(scratch: Path, emit, stop: threading.Event) -> None:
    """Progress from the scratch file size (download hooks stay disabled); never touches the network."""
    last = 0
    while not stop.wait(PROGRESS_SECONDS):
        size = 0
        for name in ('media.bin.part', 'media.bin'):
            try:
                size = max(size, os.lstat(scratch / name).st_size)
            except OSError:
                continue
        if size > last:
            last = size
            emit({'type': 'progress', 'bytes': size, 'percent': 0.0})  # total unknown until done


def _ytdlp(request: dict, part: Path, emit):
    from . import artifact_store
    try:
        from . import ytdlp_service
        from .outbound_httpx import ControlledHttpError
        from .outbound_policy import OutboundError
    except ModuleNotFoundError as error:
        if (error.name or '').split('.')[0] not in _SOURCE_STACK:
            raise  # a real import bug in this application stays visible (crash), never masked
        raise ExecutionFailure('source_unavailable') from None  # source stack not installed: fail closed
    url, format_id = request.get('url'), request.get('format_id')
    max_bytes, deadline = request.get('max_bytes'), request.get('deadline_seconds')
    if (type(url) is not str or type(format_id) is not str or type(max_bytes) is not int or max_bytes < 1
            or type(deadline) not in (int, float)):
        raise ExecutionFailure('execution_request_invalid')
    scratch = part.parent / artifact_store.SCRATCH_DIR
    scratch.mkdir()
    stop = threading.Event()
    bili = ytdlp_service._bilibili_family(url)
    source_bytes, last_report = 0, time.monotonic()
    def source_progress(size):
        nonlocal source_bytes, last_report
        source_bytes = max(source_bytes, size)
        now = time.monotonic()
        if now - last_report >= PROGRESS_SECONDS:
            emit({'type': 'progress', 'bytes': source_bytes, 'percent': 0.0})
            last_report = now
    reporter = None if bili else threading.Thread(target=_report, args=(scratch, emit, stop), daemon=True)
    if reporter is not None:
        reporter.start()
    try:
        options = {'progress_hook': source_progress} if bili else {}
        with ytdlp_service.download_attempt(url, format_id, scratch_dir=scratch, max_bytes=max_bytes,
                                            deadline_seconds=float(deadline), **options) as downloaded:
            # A second name on the same file system: the seam then removes its own name, leaving
            # media.part as the only link (seal_candidate requires a single link).
            os.link(downloaded.path, part)
            ext = downloaded.ext
    except (OutboundError, ControlledHttpError) as error:
        raise ExecutionFailure(_source_code(error)) from None
    except ytdlp_service.DownloadFormatUnsupported:
        raise ExecutionFailure('format_unsupported') from None
    except ValueError:
        raise ExecutionFailure('execution_request_invalid') from None
    except Exception as error:
        if ytdlp_service.safe_bilibili_error_category(error) is not None:
            raise ExecutionFailure('source_unavailable') from None
        raise  # unknown application/import/disk bugs keep their established behavior
    finally:
        stop.set()
        if reporter is not None:
            reporter.join()
        if bili:
            emit({'type': 'progress', 'bytes': source_bytes, 'percent': 0.0})
        try:
            scratch.rmdir()  # empty unless the seam kept an unknown file; then cleanup refuses later
        except OSError:
            pass
    size = part.stat().st_size
    if size > max_bytes:
        raise ExecutionFailure('file_too_large')
    try:
        signature_ok = artifact_store.container_signature_ok(part, ext)
    except artifact_store.ArtifactError:
        raise ExecutionFailure('disk_error') from None  # the file could not be examined
    if not signature_ok:
        raise ExecutionFailure('media_invalid')
    emit({'type': 'progress', 'bytes': max(size, source_bytes), 'percent': 100.0})
    return ext, 'signature'
