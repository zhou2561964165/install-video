"""C4 streaming of an already-open media file: one byte range, read-lease renewal (no DB).

file_reads has already authorized the read, recorded the read lease and opened the file
without following links; this layer streams only that handle (never re-opens by path,
unlike Starlette's FileResponse). Renewal runs on a fixed schedule from the start of the
read; a failed renewal or the maximum read duration aborts the transfer by raising, so
the server drops the connection instead of sending a short body that looks complete.
The file is always closed and the end callback always runs, whatever happens.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from urllib.parse import quote

import anyio
from starlette.responses import Response, StreamingResponse

CHUNK_SIZE = 64 * 1024
RENEW_SECONDS = 10.0
MAX_SECONDS = 30 * 60.0
UNSATISFIABLE = object()
_RANGE = re.compile(r'bytes=(\d{0,19})-(\d{0,19})')  # bounded: an absurd number is ignored, never parsed
_log = logging.getLogger(__name__)


class ReadAborted(RuntimeError):
    """Fixed-code stop of a transfer already in progress (lease lost, too long, short file)."""


def parse_range(header: str | None, size: int):
    """(start, end) inclusive for one satisfiable byte range; None to send the whole file;
    UNSATISFIABLE for a range starting past the end. Multiple ranges, other units and
    malformed headers are ignored (RFC 9110 §14.2 allows a server to ignore Range)."""
    if header is None:
        return None
    match = _RANGE.fullmatch(header.strip())
    if match is None:
        return None
    first, last = match.groups()
    if not first:
        if not last:
            return None
        suffix = int(last)
        return UNSATISFIABLE if suffix == 0 else (max(0, size - suffix), size - 1)
    start = int(first)
    if last and int(last) < start:
        return None  # inverted range: malformed, ignored
    if start >= size:
        return UNSATISFIABLE
    return start, min(int(last) if last else size - 1, size - 1)


def _disposition(filename: str) -> str:
    fallback = ''.join(char if 32 <= ord(char) < 127 and char not in '"\\;' else '_' for char in filename)
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{quote(filename, safe="")}'


class _Finish:
    """Close the file and record the end of the read exactly once, from whichever path gets there first."""

    def __init__(self, file, end):
        self._file, self._end, self._done, self._lock = file, end, False, threading.Lock()

    def __call__(self) -> None:
        with self._lock:
            if self._done:
                return
            self._done = True
        try:
            self._file.close()
        finally:
            try:
                self._end()
            except Exception:
                _log.warning('file read end could not be recorded')  # the read lease then lapses on its own


async def _finish_shielded(finish) -> None:
    # A client disconnect cancels the transfer; the cleanup itself must not be cancelled with it.
    with anyio.CancelScope(shield=True):
        await anyio.to_thread.run_sync(finish)


class _ReadResponse(StreamingResponse):
    """Also finishes when the body is never iterated (client gone before start, middleware error)."""

    def __init__(self, *args, finish, **kwargs):
        super().__init__(*args, **kwargs)
        self._finish = finish

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await _finish_shielded(self._finish)


async def _body(file, start, length, renew, finish, renew_seconds, max_seconds, chunk_size, clock):
    try:
        began = clock()
        next_renewal = began + renew_seconds
        await anyio.to_thread.run_sync(file.seek, start)
        remaining = length
        while remaining:
            now = clock()
            if now - began >= max_seconds:
                raise ReadAborted('read_max_duration')
            if now >= next_renewal:
                if not await anyio.to_thread.run_sync(renew):
                    raise ReadAborted('read_lease_lost')
                next_renewal += renew_seconds
                if next_renewal <= now:  # after a stall: one renewal, then a fresh schedule
                    next_renewal = now + renew_seconds
            block = await anyio.to_thread.run_sync(file.read, min(chunk_size, remaining))
            if not block:
                raise ReadAborted('read_short_file')
            remaining -= len(block)
            yield block
    finally:
        await _finish_shielded(finish)


def stream_response(file, size: int, *, etag: str, filename: str, media_type: str, range_header: str | None,
                    if_range: str | None, renew, end, renew_seconds: float = RENEW_SECONDS,
                    max_seconds: float = MAX_SECONDS, chunk_size: int = CHUNK_SIZE, clock=time.monotonic) -> Response:
    headers = {'accept-ranges': 'bytes', 'etag': etag, 'content-disposition': _disposition(filename)}
    # If-Range applies the range only to this exact (strong ETag) representation.
    selected = None if if_range is not None and if_range != etag else parse_range(range_header, size)
    finish = _Finish(file, end)
    if selected is UNSATISFIABLE:
        finish()
        return Response(status_code=416, headers={**headers, 'content-range': f'bytes */{size}'})
    start, stop = selected or (0, size - 1)
    headers['content-length'] = str(stop - start + 1)
    status = 200
    if selected is not None:
        status = 206
        headers['content-range'] = f'bytes {start}-{stop}/{size}'
    return _ReadResponse(_body(file, start, stop - start + 1, renew, finish, renew_seconds, max_seconds,
                               chunk_size, clock), status_code=status, headers=headers, media_type=media_type,
                         finish=finish)
