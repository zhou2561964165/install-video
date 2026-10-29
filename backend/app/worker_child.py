"""C3 worker child: python -m app.worker_child. One ExecutionRequest line on stdin, JSON lines on stdout.

Writes only the attempt's media.part and bounded scratch inputs. Never opens the
database or cookie file. An optional bounded cookie snapshot arrives only through
private stdin and is removed before executor dispatch; stdout contains fixed events.
After the request, stdin stays open as the stop channel: EOF means stop now.
"""
import json
import os
from pathlib import Path
import signal
import sys
import threading

from .services import executors
from .services.egress_evidence import PROXY_ENV

_MAX_REQUEST = 64 * 1024
STOPPED_EXIT = 143


def _watch_stop() -> None:
    while sys.stdin.buffer.read(1024):
        pass
    if not executors.ignore_stop:
        if os.name != 'nt':
            # The parent (worker) stopped us or died: end this child's whole process group
            # (it leads its own session), so helpers such as a merger cannot keep downloading.
            os.killpg(0, signal.SIGKILL)
        os._exit(STOPPED_EXIT)


_EMIT_LOCK = threading.Lock()  # an executor may report progress from a helper thread (B5 U5b)


def _emit(event: dict) -> None:
    line = json.dumps(event, separators=(',', ':')) + '\n'
    with _EMIT_LOCK:
        sys.stdout.write(line)
        sys.stdout.flush()


def main() -> int:
    if PROXY_ENV in os.environ:
        # Isolated child (external gate G3): files stay group-writable in the shared attempt
        # directory, so the worker (a group member) can remove whatever the child leaves.
        os.umask(0o002)
    raw = sys.stdin.buffer.readline(_MAX_REQUEST + 1)
    if len(raw) > _MAX_REQUEST or not raw.endswith(b'\n'):
        _emit({'type': 'error', 'code': 'execution_request_invalid'})
        return 2
    try:
        request = json.loads(raw)
        part = Path(request['attempt_dir']) / 'media.part'
    except (ValueError, KeyError, TypeError):
        _emit({'type': 'error', 'code': 'execution_request_invalid'})
        return 2
    threading.Thread(target=_watch_stop, daemon=True).start()
    try:
        snapshot = request.pop('bili_cookie_snapshot', None)
        if snapshot is None and request.get('executor') != 'ytdlp':
            ext, media_check = executors.run(request, part, _emit)
        else:
            from .services.bilibili_session import cookie_snapshot_scope, SessionError
            try:
                with cookie_snapshot_scope(snapshot):
                    ext, media_check = executors.run(request, part, _emit)
            except SessionError:
                raise executors.ExecutionFailure('source_unavailable') from None
    except executors.ExecutionFailure as failure:
        _emit({'type': 'error', 'code': failure.code})
        return 0
    except OSError:
        _emit({'type': 'error', 'code': 'disk_error'})
        return 0
    _emit({'type': 'done', 'ext': ext, 'media_check': media_check})
    return 0


if __name__ == '__main__':
    code = main()
    sys.stdout.flush()
    # Leave without interpreter shutdown: the stop-channel thread may still block in stdin.read(),
    # and CPython 3.12 aborts finalizing that buffered reader (_enter_buffered_busy). Every event
    # is already flushed and the executor closed its files before main() returned.
    os._exit(code)
