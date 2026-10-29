"""C3 execution supervisor (parent side, no DB): start, read and terminate one worker child.

The child runs in its own process group so the whole tree can be stopped; only
groups this supervisor started are ever signalled or killed. The polite stop is
closing the child's stdin (plus SIGTERM on POSIX): console control events cannot
reach a windowless child on Windows, and EOF also stops the child if this parent dies. The child gets a
minimal environment (no database URL, keys or cookies). Its stdout is a bounded
JSON-lines protocol; anything malformed, oversized or carrying unexpected fields
is a protocol error and the child is stopped. Job/epoch/attempt identity comes
only from the request this parent sent, never from the child.

With isolation (external gate G3/G4) the child starts through setpriv as the firewalled
download user and also receives the controlled proxy URL. A signal the worker is not allowed
to send to it is an isolation failure (IsolationError), never ignored; reaping also sweeps
download-user processes that left the group.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time

from . import child_isolation, executors
from .artifact_store import MEDIA_CHECKS

_MAX_LINE = 4096
_MAX_LINES = 10_000
TERMINAL_EXIT_GRACE_SECONDS = 5.0  # after done/error the child must exit, or it is a protocol error
_CODE = re.compile(r'[A-Za-z0-9_.-]{1,64}\Z')
_EXT = re.compile(r'[a-z0-9]{1,8}\Z')
_ENV_KEYS = frozenset({'SYSTEMROOT', 'WINDIR', 'PATH', 'PATHEXT', 'SYSTEMDRIVE', 'TEMP', 'TMP', 'COMSPEC'})
_BACKEND = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    job_id: str
    epoch: int
    attempt_id: str
    url: str
    format_id: str
    attempt_dir: str
    max_bytes: int
    deadline_seconds: float
    executor: str
    bili_cookie_snapshot: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class Event:
    kind: str
    bytes: int
    percent: float


@dataclass(frozen=True, slots=True)
class Outcome:
    ok: bool
    ext: str | None = None
    media_check: str | None = None
    code: str | None = None


def _child_env(isolation=None) -> dict:
    env = {key: value for key, value in os.environ.items() if key.upper() in _ENV_KEYS}
    env['PYTHONPATH'] = str(_BACKEND)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['YTDLP_NO_PLUGINS'] = '1'  # B5 U5b: the ytdlp executor never loads user plugins (official opt-out)
    if executors.fake_allowed():
        env['DOWNLOAD_WORKER_ALLOW_FAKE'] = '1'
    if isolation is not None:
        env.update(isolation.child_env())
    return env


class ChildRun:
    def __init__(self, request: ExecutionRequest, isolation=None):
        flags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) | getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        self._isolation = isolation
        prefix = []
        if isolation is not None:
            child_isolation.sweep(isolation)  # nothing of the download user may outlive a previous run
            prefix = isolation.command_prefix()
        self._process = subprocess.Popen(
            prefix + [sys.executable, '-m', 'app.worker_child'], cwd=_BACKEND, env=_child_env(isolation),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=flags, start_new_session=(os.name != 'nt'))
        # The reader never queues more than _MAX_LINES lines (+ end marker): memory stays bounded
        # whether or not the parent is polling.
        self._lines: queue.Queue = queue.Queue(maxsize=_MAX_LINES + 1)
        self._violation = False
        self._terminal_at: float | None = None
        self._outcome: Outcome | None = None
        self._count = 0
        self._last_bytes = 0
        self._pending: list[Event] = []
        try:
            payload = asdict(request)
            if payload['bili_cookie_snapshot'] is None:
                payload.pop('bili_cookie_snapshot')
            self._process.stdin.write(json.dumps(payload).encode('utf8') + b'\n')
            self._process.stdin.flush()
        except OSError:
            pass
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    @property
    def pid(self) -> int:
        return self._process.pid

    def _read(self) -> None:
        """Enforce the line limits here, independent of polling; a violation stops reading."""
        stream = self._process.stdout
        count = 0
        while True:
            line = stream.readline(_MAX_LINE + 2)
            if not line:
                break
            count += 1
            if count > _MAX_LINES or len(line) > _MAX_LINE or not line.endswith(b'\n'):
                self._violation = True
                break
            self._lines.put(line)
        self._lines.put(None)

    def _protocol_error(self) -> None:
        self._outcome = Outcome(False, code='execution_protocol_error')
        self.terminate(grace=2.0)

    def _event(self, line: bytes) -> Event | None:
        self._count += 1
        if self._count > _MAX_LINES or len(line) > _MAX_LINE or not line.endswith(b'\n'):
            self._protocol_error()
            return None
        try:
            message = json.loads(line)
        except ValueError:
            self._protocol_error()
            return None
        kind = message.get('type') if type(message) is dict else None
        if kind == 'progress' and set(message) == {'type', 'bytes', 'percent'}:
            size, percent = message['bytes'], message['percent']
            if (type(size) is int and size >= self._last_bytes and type(percent) in (int, float)
                    and math.isfinite(percent) and 0 <= percent <= 100):
                self._last_bytes = size
                return Event('progress', size, float(percent))
        elif kind == 'done' and set(message) == {'type', 'ext', 'media_check'}:
            if (type(message['ext']) is str and _EXT.match(message['ext'])
                    and type(message['media_check']) is str and message['media_check'] in MEDIA_CHECKS):
                self._outcome = Outcome(True, ext=message['ext'], media_check=message['media_check'])
                return None
        elif kind == 'error' and set(message) == {'type', 'code'}:
            if type(message['code']) is str and _CODE.match(message['code']):
                self._outcome = Outcome(False, code=message['code'])
                return None
        self._protocol_error()
        return None

    def _close_stdin(self) -> None:
        try:
            self._process.stdin.close()
        except OSError:
            pass

    def poll(self) -> list[Event]:
        """Non-blocking: parse every line that has arrived; stops at the first terminal message."""
        self._drain()
        events, self._pending = self._pending, []
        return events

    def _protocol_failed(self) -> bool:
        return self._outcome is not None and self._outcome.code == 'execution_protocol_error'

    def _drain(self) -> None:
        if self._violation:
            if not self._protocol_failed():
                self._protocol_error()
            return
        while True:
            try:
                line = self._lines.get_nowait()
            except queue.Empty:
                break
            if line is None:
                break
            if self._outcome is not None:
                if not self._protocol_failed():
                    self._protocol_error()  # nothing may follow a terminal message
                break
            event = self._event(line)
            if event is not None:
                self._pending.append(event)

    def result(self) -> Outcome | None:
        self._drain()
        if self._process.poll() is None:
            if self._outcome is None:
                return None
            if self._protocol_failed():
                return self._outcome
            # A terminal message was reported: the child must now exit promptly.
            if self._terminal_at is None:
                self._terminal_at = time.monotonic()
            if time.monotonic() - self._terminal_at <= TERMINAL_EXIT_GRACE_SECONDS:
                return None
            self._protocol_error()
            return self._outcome
        self._close_stdin()
        self._reader.join(timeout=5)
        self._drain()
        if self._outcome is None:
            code = 'execution_crashed' if self._process.returncode != 0 else 'execution_protocol_error'
            self._outcome = Outcome(False, code=code)
        return self._outcome

    def terminate(self, grace: float = 10.0) -> bool:
        """Stop this child's process group; returns True when it had to be force-killed."""
        if self._process.poll() is not None:
            return False
        self._close_stdin()
        if os.name != 'nt':
            self._signal_group(signal.SIGTERM)
        try:
            self._process.wait(timeout=grace)
            return False
        except subprocess.TimeoutExpired:
            pass
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(self._process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        else:
            self._signal_group(signal.SIGKILL)
        self._process.wait(timeout=30)
        if self._outcome is None:
            self._outcome = Outcome(False, code='execution_terminated')
        return True

    def reap(self) -> None:
        """Kill whatever remains of this run's own process group, even after a clean exit.

        The worker calls this before sealing: a successful child may leave group members
        (e.g. a merger) still writing the part file. POSIX signals the group this run
        created (its id stays reserved while any member lives; an empty group is ESRCH).
        On Windows (development only) a group outlives its leader invisibly to taskkill /T;
        only a still-running tree is reached here (ruling C3-4: Job Objects deferred).
        """
        if os.name == 'nt':
            if self._process.poll() is None:
                self.terminate(grace=0)
            return
        if self._isolation is None:
            self._signal_group(signal.SIGKILL)
            return
        # Isolated (the worker holds CAP_KILL): once the leader is reaped its pgid may be recycled
        # by anyone, so only the uid/cgroup-filtered, pidfd-checked sweep is used from then on.
        if self._process.poll() is None:
            self._signal_group(signal.SIGKILL)
        child_isolation.sweep(self._isolation)

    def _signal_group(self, sig) -> None:
        try:
            os.killpg(self._process.pid, sig)
        except PermissionError:
            if self._isolation is not None:
                raise child_isolation.IsolationError('isolation_kill_denied') from None
        except OSError:
            pass


def start(request: ExecutionRequest, isolation=None) -> ChildRun:
    if (type(request) is not ExecutionRequest or type(request.executor) is not str
            or not executors.known(request.executor)):
        raise ValueError('executor_unknown')
    if type(request.max_bytes) is not int or request.max_bytes < 1:
        raise ValueError('max_bytes_invalid')
    if request.bili_cookie_snapshot is not None:
        from .bilibili_session import cookie_snapshot_scope, SessionError
        try:
            with cookie_snapshot_scope(request.bili_cookie_snapshot):
                pass
        except SessionError:
            raise ValueError('execution_request_invalid') from None
    payload = asdict(request)
    if len(json.dumps(payload).encode('utf8')) + 1 > 64 * 1024:
        raise ValueError('execution_request_invalid') from None
    return ChildRun(request, isolation)
