#!/usr/bin/env python3
"""Bounded expiry-driven Bilibili session renewal (default: read-free dry run).

One absolute timer deadline follows the signal Cookie's expiry hint. Source
navigation uses only an owned page in the operator-authorized existing Chrome.
Cookie material stays in memory/private server files; output is a safe receipt.
Backend metadata uses refresh_bili_cookies.validate_with_backend exclusively.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import posixpath
import re
import signal
import stat
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

TIMER_NAME = 'install-video-bili-session-refresh.timer'
DEPLOY = Path('/opt/install-video/deployment-state')
STATE_DIR = DEPLOY / 'bili-expiry-scheduler'
POLICY = Path('/etc/install-video/bili-refresh-policy.json')
DROPIN = Path('/etc/systemd/system') / (TIMER_NAME + '.d') / 'next.conf'
COOKIE = Path('/etc/install-video/bilibili-cookies.txt')
LOCK = DEPLOY / 'bili-refresh-launcher.lock'
TARGET = 'https://www.bilibili.com/video/BV1JSh265EQm/'
MAX_BYTES = 1024 * 1024
DEFAULT_POLICY = {
    'lead_seconds': 1800, 'failure_retry_seconds': 900, 'max_failure_retries': 1,
    'max_daily_navigations': 8, 'max_daily_metadata': 8, 'max_daily_api': 8,
    'browser_timeout_seconds': 35, 'minimum_available_mib': 1536,
}
BOUNDS = {
    'lead_seconds': (60, 3600), 'failure_retry_seconds': (60, 3600),
    'max_failure_retries': (0, 1), 'max_daily_navigations': (1, 8),
    'max_daily_metadata': (1, 8), 'max_daily_api': (1, 8),
    'browser_timeout_seconds': (5, 35), 'minimum_available_mib': (1536, 65536),
}
MANUAL_ERRORS = frozenset({
    'verification_requires_user', 'budget_exhausted', 'ambiguous_transaction',
    'protected_state_changed', 'cleanup_failed', 'unsafe_file', 'unsafe_path',
    'production_changed', 'invalid_policy', 'invalid_state', 'unknown_expiry',
    'rollback_refused', 'interrupted', 'timer_update_failed', 'invalid_api_mode',
})


class SafeError(RuntimeError):
    def __init__(self, code):
        self.code = code if isinstance(code, str) and re.fullmatch(r'[a-z_]{1,64}', code) else 'scheduler_failed'
        super().__init__(self.code)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_policy(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULT_POLICY):
        raise SafeError('invalid_policy')
    result = dict(DEFAULT_POLICY)
    result.update(value)
    for key, (low, high) in BOUNDS.items():
        if type(result[key]) is not int or not low <= result[key] <= high:
            raise SafeError('invalid_policy')
    return result


def parse_cookie(data):
    """Parse expired material too: expiry is a scheduling hint, never validity proof."""
    tool = load_module(Path(__file__).with_name('refresh_bili_cookies.py'), 'bili_scheduler_parser')
    try:
        info = tool.validate_cookie_bytes(data, now=-1)
    except Exception:
        raise SafeError('invalid_cookie') from None
    signals = []
    for row in data.decode('utf-8').splitlines()[1:]:
        if row:
            parts = row.removeprefix('#HttpOnly_').split('\t')
            if parts[5].lower() == 'x-bili-sec-token':
                signals.append(tuple(parts))
    # A digest is private comparison material, never an authorization decision.
    fingerprint = hashlib.sha256(json.dumps(sorted(signals)).encode()).hexdigest()
    return {'expiry': info['signal_expires'] or None, 'signal_fingerprint': fingerprint,
            'cookie_count': info['cookie_count']}


def utc_day(now):
    return dt.datetime.fromtimestamp(now, dt.timezone.utc).date().isoformat()


def new_state(now):
    return {'version': 1, 'day': utc_day(now), 'counts': {'navigation': 0, 'metadata': 0, 'api': 0},
            'failure_retries': 0, 'status': 'new', 'next_at': None,
            'unchanged_expiry': None, 'transaction': None, 'last_result': {}}


def validate_state(value):
    if (not isinstance(value, dict) or value.get('version') != 1
            or value.get('status') not in ('new', 'armed', 'running', 'needs_operator')
            or not isinstance(value.get('day'), str)
            or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value['day'])
            or type(value.get('failure_retries')) is not int
            or not 0 <= value['failure_retries'] <= 1
            or not isinstance(value.get('counts'), dict)
            or set(value['counts']) != {'navigation', 'metadata', 'api'}
            or any(type(n) is not int or not 0 <= n <= 8 for n in value['counts'].values())
            or not isinstance(value.get('last_result'), dict)):
        raise SafeError('invalid_state')
    for key in ('next_at', 'unchanged_expiry', 'retry_at'):
        if value.get(key) is not None and (type(value[key]) is not int or not 0 < value[key] < 253402300800):
            raise SafeError('invalid_state')
    if value.get('transaction') is not None and not isinstance(value['transaction'], dict):
        raise SafeError('invalid_state')
    return value


def plan_next(state, info, now, policy):
    if state.get('transaction'):
        return {'status': 'needs_operator', 'next_at': None, 'reason': 'ambiguous_transaction'}
    if state.get('status') == 'needs_operator':
        return {'status': 'needs_operator', 'next_at': None, 'reason': 'manual_clear_required'}
    if state['day'] == utc_day(now) and any(state['counts'][stage] >= policy[key]
            for stage, key in (('navigation', 'max_daily_navigations'),
                               ('metadata', 'max_daily_metadata'), ('api', 'max_daily_api'))):
        return {'status': 'needs_operator', 'next_at': None, 'reason': 'budget_exhausted'}
    # A bounded retry cannot be pulled forward by repeated schedule-only calls.
    if state.get('retry_at') and state['retry_at'] > now:
        return {'status': 'armed', 'next_at': state['retry_at'], 'reason': 'bounded_retry'}
    if info is not None and info['expiry'] is None:
        return {'status': 'needs_operator', 'next_at': None, 'reason': 'unknown_expiry'}
    expiry = info['expiry'] if info else None
    if expiry and state.get('unchanged_expiry') == expiry and expiry + 60 > now:
        return {'status': 'armed', 'next_at': expiry + 60, 'reason': 'unchanged_wait_expiry'}
    return {'status': 'armed', 'next_at': max(int(now) + 2, expiry - policy['lead_seconds']) if expiry else int(now) + 2,
            'reason': 'expiry_lead' if expiry and expiry - policy['lead_seconds'] > now else 'due'}


def failure_plan(state, reason, now, policy):
    if reason not in MANUAL_ERRORS and state['failure_retries'] < policy['max_failure_retries']:
        state['failure_retries'] += 1
        state['retry_at'] = int(now) + policy['failure_retry_seconds']
        return {'status': 'armed', 'next_at': state['retry_at'], 'reason': reason}
    state.pop('retry_at', None)
    return {'status': 'needs_operator', 'next_at': None, 'reason': reason}


def reserve(state, stage, now, policy, save):
    if state['day'] != utc_day(now):
        state['day'] = utc_day(now)
        state['counts'] = {'navigation': 0, 'metadata': 0, 'api': 0}
    key = {'navigation': 'max_daily_navigations', 'metadata': 'max_daily_metadata', 'api': 'max_daily_api'}[stage]
    if state['counts'][stage] >= policy[key]:
        raise SafeError('budget_exhausted')
    state['counts'][stage] += 1
    save(state)


def no_symlinks(path):
    for part in (Path(path), *Path(path).parents):
        if part.is_symlink():
            raise SafeError('unsafe_path')


def checked_dir(path, mode, *, enforce_owner=True):
    path = Path(path)
    no_symlinks(path)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or (enforce_owner and os.name == 'posix' and
            (info.st_uid != 0 or stat.S_IMODE(info.st_mode) != mode)):
        raise SafeError('unsafe_path')


def private_read(path, *, mode=0o600, enforce_owner=True):
    no_symlinks(path)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES
                or (enforce_owner and os.name == 'posix' and
                    (info.st_uid != 0 or stat.S_IMODE(info.st_mode) != mode))):
            raise SafeError('unsafe_file')
        with os.fdopen(descriptor, 'rb', closefd=False) as handle:
            data = handle.read(MAX_BYTES + 1)
        after = os.fstat(descriptor)
        if (len(data) > MAX_BYTES or (info.st_ino, info.st_mtime_ns, info.st_size) !=
                (after.st_ino, after.st_mtime_ns, after.st_size)):
            raise SafeError('unsafe_file')
        return data
    finally:
        os.close(descriptor)


def protected_metadata(path):
    """Root-owned nonsecret baseline may be 0600, 0640 or 0644."""
    no_symlinks(path)
    info = Path(path).lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES or info.st_nlink != 1
            or (os.name == 'posix' and (info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022))):
        raise SafeError('unsafe_file')
    return private_read(path, mode=stat.S_IMODE(info.st_mode))


def _config_identity(info, *, directory=False):
    value = (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode)
    return value if directory else value + (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


def _open_protected_config(path, filesystem):
    """Walk from a root descriptor; follow only the one approved Caddy alias.

    A future root-managed generation may change between runs. Its location,
    alias inode/readlink and real ancestor identities are bound to each run's
    protected snapshot; changing them during a run fails comparison.
    """
    fs = filesystem
    flags = fs.O_RDONLY | fs.O_DIRECTORY | fs.O_NOFOLLOW
    descriptor = fs.open('/', flags)
    bindings, pending, current, links = [], path.lstrip('/').split('/'), '/', 0
    try:
        while True:
            directory = fs.fstat(descriptor)
            if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != 0 or directory.st_mode & 0o022:
                raise SafeError('unsafe_path')
            bindings.append({'kind': 'directory', 'path': current,
                             'identity': _config_identity(directory, directory=True)})
            name, pending = pending[0], pending[1:]
            address = posixpath.join(current, name)
            item = fs.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISLNK(item.st_mode):
                # Symlink mode 0777 has no write semantics on Linux. Its owner
                # and containing real directory are the relevant trust checks.
                if item.st_uid != 0 or address != '/etc/caddy/acli.d' or links:
                    raise SafeError('unsafe_path')
                target = fs.readlink(name, dir_fd=descriptor)
                if not isinstance(target, str) or not re.fullmatch(
                        r'/var/lib/acli/caddy-manager/generations/generation\.[A-Za-z0-9_-]{1,64}', target):
                    raise SafeError('unsafe_path')
                if _config_identity(fs.stat(name, dir_fd=descriptor, follow_symlinks=False)) != _config_identity(item):
                    raise SafeError('protected_state_changed')
                bindings.append({'kind': 'symlink', 'path': address, 'target': target,
                                 'identity': _config_identity(item)})
                links += 1
                pending = target.lstrip('/').split('/') + pending
                fs.close(descriptor)
                descriptor = None
                descriptor = fs.open('/', flags)
                current = '/'
                continue
            if pending:
                if not stat.S_ISDIR(item.st_mode):
                    raise SafeError('unsafe_path')
                child = fs.open(name, flags, dir_fd=descriptor)
                try:
                    if _config_identity(fs.fstat(child), directory=True) != _config_identity(item, directory=True):
                        raise SafeError('protected_state_changed')
                except BaseException:
                    fs.close(child)
                    raise
                fs.close(descriptor)
                descriptor, current = child, address
                continue
            if (not stat.S_ISREG(item.st_mode) or item.st_uid != 0 or item.st_mode & 0o022
                    or item.st_nlink != 1 or not 0 <= item.st_size <= 4 * MAX_BYTES):
                raise SafeError('unsafe_file')
            file_descriptor = fs.open(name, fs.O_RDONLY | fs.O_NOFOLLOW | fs.O_NONBLOCK, dir_fd=descriptor)
            try:
                if _config_identity(fs.fstat(file_descriptor)) != _config_identity(item):
                    raise SafeError('protected_state_changed')
            except BaseException:
                fs.close(file_descriptor)
                raise
            return file_descriptor, {'resolved_path': address, 'bindings': bindings,
                                     'file_identity': _config_identity(item)}
    finally:
        if descriptor is not None:
            fs.close(descriptor)


def protected_config_snapshot(path, *, approved_paths, filesystem=None):
    """Bounded read of a baseline-approved file with descriptor-bound identities."""
    fs = os if filesystem is None else filesystem
    if (not isinstance(path, str) or path not in approved_paths or not path.startswith('/')
            or any(part in ('', '.', '..') for part in path.split('/')[1:]) or '\\' in path):
        raise SafeError('unsafe_path')
    descriptor = check_descriptor = None
    try:
        descriptor, before = _open_protected_config(path, fs)
        data = bytearray()
        while len(data) <= 4 * MAX_BYTES:
            chunk = fs.read(descriptor, min(65536, 4 * MAX_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > 4 * MAX_BYTES:
            raise SafeError('unsafe_file')
        if _config_identity(fs.fstat(descriptor)) != before['file_identity']:
            raise SafeError('protected_state_changed')
        # Re-resolve the original alias after the bounded read to catch rotation
        # while the first descriptor still pins the old, otherwise valid file.
        check_descriptor, after = _open_protected_config(path, fs)
        if before != after:
            raise SafeError('protected_state_changed')
        return dict(before, sha256=hashlib.sha256(data).hexdigest())
    except (OSError, KeyError, ValueError):
        raise SafeError('unsafe_path') from None
    finally:
        if descriptor is not None:
            fs.close(descriptor)
        if check_descriptor is not None:
            fs.close(check_descriptor)


def parse_api_enabled(data):
    """Read only one nonsecret bool using an unambiguous EnvironmentFile subset.

    Match Settings' true values (1/true/yes). Unknown values, interpolation,
    duplicate assignments and shell syntax fail closed rather than guessing.
    """
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        raise SafeError('invalid_api_mode')
    try:
        lines = data.decode('utf-8').splitlines()
    except UnicodeError:
        raise SafeError('invalid_api_mode') from None
    found = None
    for line in lines:
        line = line.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if re.match(r'export\s+BILIBILI_API_ENABLED\b', line):
            raise SafeError('invalid_api_mode')
        if not re.match(r'BILIBILI_API_ENABLED\b', line):
            continue
        match = re.fullmatch(r'''BILIBILI_API_ENABLED\s*=\s*(?:([A-Za-z0-9]+)|"([A-Za-z0-9]+)"|'([A-Za-z0-9]+)')\s*''', line)
        if not match or found is not None:
            raise SafeError('invalid_api_mode')
        value = next(part for part in match.groups() if part is not None).lower()
        if value not in ('1', 'true', 'yes', '0', 'false', 'no'):
            raise SafeError('invalid_api_mode')
        found = value in ('1', 'true', 'yes')
    return False if found is None else found


def trusted_module(path, name):
    # current is an intentional root-maintained release alias, never reject it
    # merely for being a symlink. Verify its resolved immutable trust boundary.
    resolved = Path(path).resolve(strict=True)
    roots = (Path('/opt/install-video/releases'), DEPLOY)
    if not any(resolved.is_relative_to(root) for root in roots):
        raise SafeError('unsafe_path')
    for part in (resolved, *resolved.parents):
        info = part.lstat()
        if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
            raise SafeError('unsafe_path')
    if not stat.S_ISREG(resolved.stat().st_mode) or resolved.stat().st_size > MAX_BYTES:
        raise SafeError('unsafe_file')
    return load_module(resolved, name)


def atomic_write(path, data, *, mode=0o600, enforce_owner=True):
    path = Path(path)
    no_symlinks(path)
    if path.exists():
        private_read(path, mode=mode, enforce_owner=enforce_owner)
    descriptor, name = tempfile.mkstemp(prefix='.scheduler-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            if os.name == 'posix':
                os.fchmod(handle.fileno(), mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # Refuse a concurrent symlink insertion at the destination.
        no_symlinks(path)
        os.replace(temporary, path)
        if os.name == 'posix':
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


class Store:
    def __init__(self, directory=STATE_DIR, *, enforce_owner=True):
        self.directory = Path(directory)
        self.path = self.directory / 'state.json'
        self.recovery = self.directory / 'old-cookie.recovery'
        self.enforce_owner = enforce_owner

    def read(self, now):
        checked_dir(self.directory, 0o700, enforce_owner=self.enforce_owner)
        try:
            value = json.loads(private_read(self.path, enforce_owner=self.enforce_owner))
        except FileNotFoundError:
            value = new_state(now)
        except (ValueError, UnicodeError):
            raise SafeError('invalid_state') from None
        validate_state(value)
        if self.recovery.exists() or self.recovery.is_symlink():
            value['transaction'] = value.get('transaction') or {'phase': 'unknown_recovery'}
        return value

    def save(self, value):
        validate_state(value)
        checked_dir(self.directory, 0o700, enforce_owner=self.enforce_owner)
        data = json.dumps(value, sort_keys=True, separators=(',', ':')).encode() + b'\n'
        if len(data) > 16384:
            raise SafeError('invalid_state')
        atomic_write(self.path, data, enforce_owner=self.enforce_owner)


def system_command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        raise SafeError('timer_update_failed')
    return result


class Timer:
    def __init__(self, path=DROPIN, command=system_command, *, enforce_owner=True):
        self.path, self.command, self.enforce_owner = Path(path), command, enforce_owner

    def apply(self, plan):
        if plan['next_at'] is None:
            self.command(['systemctl', '--no-block', 'stop', TIMER_NAME])
            return
        no_symlinks(self.path)
        if not self.path.parent.exists():
            self.path.parent.mkdir(mode=0o755)
        checked_dir(self.path.parent, 0o755, enforce_owner=self.enforce_owner)
        date = dt.datetime.fromtimestamp(plan['next_at'], dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        atomic_write(self.path, ('[Timer]\nOnCalendar=\nOnCalendar=' + date + '\n').encode(),
                     mode=0o644, enforce_owner=self.enforce_owner)
        self.command(['systemctl', 'daemon-reload'])
        # Restart must not wait: a timer orders itself Before its oneshot service.
        self.command(['systemctl', '--no-block', 'restart', TIMER_NAME])


def public_state(state):
    result = {key: state.get(key) for key in ('version', 'day', 'counts', 'failure_retries', 'status', 'next_at')}
    result['next_refresh_at'] = state.get('next_at')
    result['schedule_reason'] = state.get('schedule_reason')
    result['last_result'] = {key: value for key, value in state.get('last_result', {}).items()
                           if key in ('success', 'reason', 'skip_reason', 'not_due', 'document_statuses',
                                      'renewed', 'production_cookie_updated', 'existing_services_and_configs_unchanged',
                                      'own_tab_closed', 'candidate_removed', 'private_recovery_retained')}
    result['needs_operator'] = bool(state.get('transaction')) or state.get('status') == 'needs_operator'
    return result


@contextmanager
def launcher_lock(path=LOCK):
    import fcntl
    no_symlinks(path)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
            raise SafeError('unsafe_file')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SafeError('already_running') from None
        yield
    finally:
        os.close(descriptor)


class NormalBrowser:
    def __init__(self, tool, timeout, *, opener_factory=None, connect_factory=None):
        self.tool, self.timeout, self.tab, self.opener = tool, timeout, None, None
        self.statuses = []
        self.closed = True
        self.opener_factory, self.connect_factory = opener_factory, connect_factory

    def close(self):
        if self.tab is not None:
            with self.opener.open('http://127.0.0.1:9222/json/close/' + self.tab['id'], timeout=3) as response:
                response.read(128)
            self.tab = None
            self.closed = True

    def refresh(self):
        import urllib.request
        if self.connect_factory is None:
            from websockets.sync.client import connect
        else:
            connect = self.connect_factory
        self.opener = (self.opener_factory() if self.opener_factory else
                       urllib.request.build_opener(urllib.request.ProxyHandler({})))
        with self.opener.open(urllib.request.Request('http://127.0.0.1:9222/json/new?about:blank', method='PUT'), timeout=3) as response:
            self.tab = json.load(response)
        self.closed = False
        endpoint = self.tab.get('webSocketDebuggerUrl', '')
        if (not re.fullmatch(r'ws://127\.0\.0\.1:9222/devtools/page/[A-Za-z0-9-]+', endpoint)
                or not re.fullmatch(r'[A-Za-z0-9-]+', self.tab.get('id', ''))
                or not endpoint.endswith('/' + self.tab['id'])):
            raise SafeError('invalid_browser_target')
        observer = self
        self.main_frame = None
        self.documents = []
        deadline = time.monotonic() + self.timeout
        with connect(endpoint, proxy=None, open_timeout=3, close_timeout=1, max_size=2 * MAX_BYTES) as socket:
            cdp = self.tool.Cdp(socket, deadline, observer)
            cdp.call('Page.enable')
            cdp.call('Runtime.enable')
            cdp.call('Network.enable', maxTotalBufferSize=MAX_BYTES, maxResourceBufferSize=131072)
            cdp.call('Network.setBlockedURLs', urls=['*://*.bilivideo.com/*', '*://bilivideo.com/*',
                '*://*.bilivideo.cn/*', '*.mp4*', '*.m4s*', '*.m3u8*', '*.flv*', '*.aac*'])
            cdp.call('Fetch.enable', patterns=[{'resourceType': 'Media', 'requestStage': 'Request'}])
            navigation = cdp.call('Page.navigate', url=TARGET)
            self.main_frame = navigation.get('frameId')
            if not self.main_frame or navigation.get('errorText'):
                raise SafeError('navigation_failed')
            while True:
                page = cdp.call('Runtime.evaluate', expression=self.tool._PAGE_EVIDENCE_JS,
                                returnByValue=True, awaitPromise=False).get('result', {}).get('value')
                selected = [(host, path, status) for frame, host, path, status in self.documents if frame == self.main_frame]
                if any(host != 'www.bilibili.com' or path.rstrip('/') != '/video/BV1JSh265EQm'
                       for host, path, _ in selected):
                    raise SafeError('unexpected_navigation')
                self.statuses = [int(status) for _, _, status in selected]
                if isinstance(page, dict):
                    if page.get('challenge'):
                        raise SafeError('verification_requires_user')
                    if page.get('href') not in (None, '', 'about:blank', TARGET, TARGET.rstrip('/')):
                        raise SafeError('unexpected_navigation')
                    if (self.statuses and self.statuses[-1] == 200 and page.get('bvid') == 'BV1JSh265EQm'
                            and type(page.get('aid')) in (int, float) and page['aid'] > 0
                            and page.get('has_video_title')):
                        break
                if time.monotonic() >= deadline:
                    raise SafeError('normal_browser_not_ready')
                time.sleep(0.2)
            values = cdp.call('Network.getCookies', urls=[TARGET, 'https://api.bilibili.com/'])['cookies']
            data = self.tool.normalize_cookies(values)
        self.close()
        return data

    def on_event(self, event):
        params = event.get('params', {})
        if event.get('method') == 'Network.responseReceived' and params.get('type') == 'Document':
            address = urlsplit(params.get('response', {}).get('url', ''))
            if len(self.documents) >= 32:
                raise SafeError('too_many_document_responses')
            self.documents.append((params.get('frameId'), address.hostname, address.path,
                                   params.get('response', {}).get('status')))


class Runtime:
    """Adapter to the separately reviewed root publisher and existing backend tool."""
    def __init__(self, root, tool, policy, store):
        import pwd
        self.root, self.tool, self.policy, self.store = root, tool, policy, store
        self.account = pwd.getpwnam('video-demo')
        self.candidate = root.WORK / 'candidate.cookies.txt'
        self.browser = NormalBrowser(tool, policy['browser_timeout_seconds'])

    def cookie_snapshot(self):
        return self.root.read_snapshot(COOKIE, uid=0, gid=self.account.pw_gid)

    def info(self):
        try:
            return parse_cookie(self.cookie_snapshot()['data'])
        except FileNotFoundError:
            return None

    def admission(self):
        # The helper checks the readonly project DB and the same 1536 MiB floor.
        value = self.root.admission()
        if value['memory_available_mib'] < self.policy['minimum_available_mib']:
            raise SafeError('insufficient_memory')
        return value

    def protected(self):
        units = {}
        for unit in ('caddy', 'hermes-dashboard', 'install-video-demo'):
            result = self.root.command(['systemctl', 'show', unit, '-p', 'MainPID', '-p', 'ActiveState', '-p', 'SubState'])
            values = dict(row.split('=', 1) for row in result.stdout.splitlines() if '=' in row)
            if result.returncode or values.get('ActiveState') != 'active' or not values.get('MainPID', '').isdigit() or int(values['MainPID']) <= 0:
                raise SafeError('existing_service_unhealthy')
            units[unit] = values
        baseline = json.loads(protected_metadata(DEPLOY / 'baseline.json'))
        paths = baseline.get('config_hashes')
        if not isinstance(paths, dict) or not paths:
            raise SafeError('unsafe_file')
        # Compare the state at this run's start/end; no perpetual historical PID assertion.
        hashes, bindings = {}, {}
        for path in paths:
            if not isinstance(path, str) or not posixpath.isabs(path):
                raise SafeError('unsafe_file')
            snapshot = protected_config_snapshot(path, approved_paths=paths)
            hashes[path] = snapshot['sha256']
            bindings[path] = {key: value for key, value in snapshot.items() if key != 'sha256'}
        hashes[str(self.root.ENVFILE)] = hashlib.sha256(private_read(self.root.ENVFILE)).hexdigest()
        return {'services': units, 'config_hashes': hashes, 'config_bindings': bindings}

    def write_candidate(self, data):
        checked_dir(self.root.WORK, 0o700, enforce_owner=False)
        details = self.root.WORK.lstat()
        if details.st_uid != self.account.pw_uid or stat.S_IMODE(details.st_mode) != 0o700:
            raise SafeError('unsafe_path')
        no_symlinks(self.candidate)
        fd = os.open(self.candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            os.fchown(handle.fileno(), self.account.pw_uid, self.account.pw_gid)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    def validate(self, kind, run_id):
        if kind == 'metadata':
            api_enabled = parse_api_enabled(private_read(self.root.ENVFILE))
            code = ("import importlib.util,json,os,time;from pathlib import Path;"
                    "os.environ['BILIBILI_API_ENABLED']='" + ('true' if api_enabled else 'false') + "';"
                    "s=importlib.util.spec_from_file_location('tool','/opt/install-video/current/deployment/refresh_bili_cookies.py');"
                    "t=importlib.util.module_from_spec(s);s.loader.exec_module(t);"
                    "r=t.validate_with_backend(Path('/var/lib/install-video/bili-refresh/candidate.cookies.txt'),"
                    "t.DEFAULT_TARGET,time.monotonic()+16);print(json.dumps(r),flush=True)")
        else:
            code = self.root.API_CHECK
        receipt, metrics = self.root.run_isolated('install-video-bili-refresh-scheduler-' + run_id + '-' + kind,
            [str(self.root.PYTHON), '-B', '-c', code], memory='256M', runtime=20 if kind == 'metadata' else 45,
            envfile=kind == 'api')
        # Metrics are already captured by the helper before releasing an exact,
        # stopped transient unit. Never reset unrelated failed services.
        if metrics.get('cleanup_cgroup_empty') is True:
            unit = 'install-video-bili-refresh-scheduler-' + run_id + '-' + kind
            self.root.command(['systemctl', 'reset-failed', unit], timeout=8)
        if (not receipt.get('success') or metrics.get('ExecMainStatus') != '0'
                or metrics.get('cleanup_cgroup_empty') is not True):
            if metrics.get('cleanup_cgroup_empty') is not True:
                raise SafeError('cleanup_failed')
            raise SafeError('candidate_backend_rejected' if kind == 'metadata' else 'post_publish_api_rejected')

    def publish(self, data, old):
        self.root.atomic_publish(COOKIE, data, old, uid=0, gid=self.account.pw_gid)
        if self.cookie_snapshot()['sha256'] != hashlib.sha256(data).hexdigest():
            raise SafeError('production_changed')

    def remove_candidate(self, data):
        if not self.candidate.exists():
            return
        snap = self.root.read_snapshot(self.candidate, uid=self.account.pw_uid, gid=self.account.pw_gid, mode=0o600)
        if data is None or snap['sha256'] != hashlib.sha256(data).hexdigest():
            raise SafeError('cleanup_failed')
        self.candidate.unlink()

    def prune_logs(self):
        """Keep 64 receipts, and inspect stopped exact own units before deletion."""
        pattern = re.compile(r'(install-video-bili-refresh-scheduler-[0-9]{1,12}-[0-9a-f]{12}-(?:metadata|api))-output\.json')
        files = []
        for path in DEPLOY.iterdir():
            match = pattern.fullmatch(path.name)
            if not match:
                continue
            no_symlinks(path)
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) != 0o600):
                raise SafeError('cleanup_failed')
            files.append((info.st_mtime_ns, path.name, path, match[1]))
        files.sort(reverse=True)
        # Daily reservations create at most 16 such files; a bounded cleanup
        # refuses a pre-existing accumulation rather than deleting indefinitely.
        if len(files) > 128:
            raise SafeError('cleanup_failed')
        for _, _, path, unit in files[64:]:
            observed = self.root.own_unit_state(unit)
            if observed.get('cgroup_empty') is not True or observed.get('ActiveState') not in (None, '', 'inactive', 'failed'):
                raise SafeError('cleanup_failed')
            private_read(path)
            path.unlink()
            self.root.command(['systemctl', 'reset-failed', unit], timeout=8)


def error_code(error, runtime=None):
    if isinstance(error, SafeError):
        return error.code
    if runtime is not None and isinstance(error, runtime.tool.RefreshError):
        return error_code(SafeError(error.error_type))
    if runtime is not None and isinstance(error, runtime.root.SafeError):
        return error_code(SafeError(str(error)))
    return 'scheduler_failed'


@contextmanager
def interrupt_guard():
    handlers = {}
    def interrupt(signum, frame):
        for value in handlers:
            signal.signal(value, signal.SIG_IGN)
        raise SafeError('interrupted')
    try:
        for value in (getattr(signal, name) for name in ('SIGTERM', 'SIGINT', 'SIGHUP') if hasattr(signal, name)):
            handlers[value] = signal.signal(value, interrupt)
        yield
    finally:
        for value, handler in handlers.items():
            signal.signal(value, handler)


def refresh_transaction(runtime, state, store, policy, now):
    """Reserve each external stage durably; restore only our own published candidate."""
    result = {'success': False, 'renewed': False, 'production_cookie_updated': False,
              'document_statuses': [], 'own_tab_closed': True, 'candidate_removed': True,
              'private_recovery_retained': False}
    old = None
    new_data = None
    candidate_owned = False
    before = None
    published_attempted = False
    reason = None
    run_id = str(int(now)) + '-' + os.urandom(6).hex()
    try:
        runtime.admission()
        before = runtime.protected()
        try:
            old = runtime.cookie_snapshot()
        except FileNotFoundError:
            # Publisher requires a CAS snapshot. Missing production needs manual recovery.
            raise SafeError('production_changed') from None
        if runtime.candidate.exists() or runtime.candidate.is_symlink():
            raise SafeError('ambiguous_transaction')
        state['transaction'] = {'phase': 'navigation', 'run_id': run_id}
        state['status'] = 'running'
        store.save(state)
        reserve(state, 'navigation', time.time(), policy, store.save)
        new_data = runtime.browser.refresh()
        info = parse_cookie(new_data)
        old_info = parse_cookie(old['data'])
        result['document_statuses'] = list(runtime.browser.statuses)
        if info['expiry'] is None:
            raise SafeError('unknown_expiry')
        if info['signal_fingerprint'] == old_info['signal_fingerprint']:
            if info['expiry'] > time.time():
                state['unchanged_expiry'] = info['expiry']
                result.update(success=True, reason='unchanged_cookie')
                return result, info
            raise SafeError('unchanged_expired_cookie')
        # Mark ownership before writing so interruption cannot orphan a partial candidate.
        candidate_owned = True
        runtime.write_candidate(new_data)
        state['transaction']['phase'] = 'metadata'
        reserve(state, 'metadata', time.time(), policy, store.save)
        runtime.validate('metadata', run_id)
        if runtime.protected() != before:
            raise SafeError('protected_state_changed')
        no_symlinks(store.recovery)
        fd = os.open(store.recovery, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(old['data']); handle.flush(); os.fsync(handle.fileno())
        if os.name == 'posix':
            directory = os.open(store.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        state['transaction'].update(phase='publish', old_sha256=old['sha256'],
            new_sha256=hashlib.sha256(new_data).hexdigest())
        store.save(state)
        published_attempted = True
        runtime.publish(new_data, old)
        result['production_cookie_updated'] = True
        state['transaction']['phase'] = 'api'
        reserve(state, 'api', time.time(), policy, store.save)
        runtime.validate('api', run_id)
        if runtime.protected() != before:
            raise SafeError('protected_state_changed')
        state['unchanged_expiry'] = None
        result.update(success=True, renewed=True, reason='renewed')
        return result, info
    except Exception as error:
        reason = error_code(error, runtime)
        result['reason'] = reason
        return result, None
    finally:
        try:
            runtime.browser.close()
            result['own_tab_closed'] = runtime.browser.closed
        except Exception:
            result['own_tab_closed'] = False
        result['document_statuses'] = list(runtime.browser.statuses)
        try:
            if before is not None:
                result['existing_services_and_configs_unchanged'] = runtime.protected() == before
                if result['existing_services_and_configs_unchanged'] is not True:
                    result.update(success=False, reason='protected_state_changed')
        except Exception:
            result.update(success=False, reason='protected_state_changed')
        if not result['own_tab_closed']:
            result.update(success=False, reason='cleanup_failed')
        if candidate_owned:
            try:
                runtime.remove_candidate(new_data)
            except Exception:
                result.update(success=False, candidate_removed=False, reason='cleanup_failed')
        try:
            runtime.prune_logs()
        except Exception:
            result.update(success=False, reason='cleanup_failed')
        if not result['success'] and published_attempted:
            try:
                current = runtime.cookie_snapshot()
                if current['sha256'] == hashlib.sha256(new_data).hexdigest():
                    runtime.publish(old['data'], current)
                    result['production_cookie_updated'] = False
                elif current['sha256'] == old['sha256']:
                    result['production_cookie_updated'] = False
                else:
                    raise SafeError('rollback_refused')
            except Exception:
                result.update(production_cookie_updated=None, reason='rollback_refused')
        # Remove recovery only after confirmed success or confirmed original content.
        safe = result['success']
        if not safe and old is not None:
            try:
                safe = runtime.cookie_snapshot()['sha256'] == old['sha256']
            except Exception:
                safe = False
        if store.recovery.exists() and safe:
            try:
                private_read(store.recovery, enforce_owner=store.enforce_owner)
                store.recovery.unlink()
            except Exception:
                result.update(success=False, reason='cleanup_failed')
        result['private_recovery_retained'] = store.recovery.exists() or store.recovery.is_symlink()
        if not result['private_recovery_retained'] and result['candidate_removed'] and result['own_tab_closed']:
            state['transaction'] = None
        else:
            result.update(success=False, reason='ambiguous_transaction')
        if result['success']:
            state['failure_retries'] = 0
            state.pop('retry_at', None)
        state['last_result'] = result
        store.save(state)


def load_runtime(policy, store):
    root = trusted_module(DEPLOY / 'run-bili-refresh-once.py', 'bili_scheduler_root')
    tool = trusted_module(root.TOOL, 'bili_scheduler_tool')
    return Runtime(root, tool, policy, store)


def execute(mode, state, store, timer, runtime, policy, now, *, clear_pause=False):
    if clear_pause:
        if state.get('transaction'):
            raise SafeError('ambiguous_transaction')
        state.update(status='new', failure_retries=0)
        state.pop('retry_at', None)
    # Paused or uncertain transactions must stop the timer even if Cookie parsing
    # itself would fail; no recovery guessing and no credential reads are needed.
    if state.get('transaction') or state.get('status') == 'needs_operator':
        info = None
    else:
        try:
            info = runtime.info()
        except Exception:
            state['status'] = 'needs_operator'
            state['last_result'] = {'success': False, 'reason': 'invalid_cookie'}
            info = None
    plan = plan_next(state, info, now, policy)
    if mode == 'run' and plan['status'] == 'armed':
        # Due is derived from Cookie expiry, or the last explicit finite deadline.
        expiry = info['expiry'] if info else None
        deadline = state.get('retry_at') or (expiry + 60 if expiry and state.get('unchanged_expiry') == expiry
                                            else expiry - policy['lead_seconds'] if expiry else now)
        if now < deadline:
            state['last_result'] = {'success': True, 'skip_reason': 'not_due', 'not_due': True}
        else:
            with interrupt_guard():
                receipt, new_info = refresh_transaction(runtime, state, store, policy, now)
            if receipt['success']:
                state['status'] = 'new'
                plan = plan_next(state, new_info, time.time(), policy)
            else:
                plan = failure_plan(state, receipt['reason'], time.time(), policy)
    state.update(status=plan['status'], next_at=plan['next_at'])
    state['schedule_reason'] = plan['reason']
    if not state['last_result']:
        state['last_result'] = {'reason': plan['reason']}
    store.save(state)
    try:
        timer.apply(plan)
    except Exception:
        state.update(status='needs_operator', next_at=None)
        state['last_result'].update(success=False, reason='timer_update_failed')
        store.save(state)
        # Best effort stop avoids leaving the old past deadline running.
        try:
            timer.apply({'status': 'needs_operator', 'next_at': None})
        except Exception:
            pass
        raise SafeError('timer_update_failed') from None
    return public_state(state)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--run', action='store_true')
    group.add_argument('--schedule-only', action='store_true')
    group.add_argument('--status', action='store_true')
    parser.add_argument('--clear-pause', action='store_true')
    args = parser.parse_args(argv)
    if args.clear_pause and not args.schedule_only:
        parser.error('--clear-pause requires --schedule-only')
    if not (args.run or args.schedule_only or args.status):
        print(json.dumps({'success': True, 'dry_run': True, 'source_requests': 0,
                          'timer_mutations': 0, 'policy': DEFAULT_POLICY}), flush=True)
        return 0
    try:
        if os.name != 'posix' or os.geteuid() != 0:
            raise SafeError('root_required')
        store = Store()
        with launcher_lock():
            now = time.time()
            state = store.read(now)
            if args.status:
                result = public_state(state)
            else:
                policy = validate_policy(json.loads(private_read(POLICY)))
                runtime = load_runtime(policy, store)
                result = execute('run' if args.run else 'schedule', state, store, Timer(), runtime,
                                 policy, now, clear_pause=args.clear_pause)
        print(json.dumps(result, sort_keys=True), flush=True)
        return 0 if result['status'] != 'needs_operator' else 1
    except Exception as error:
        code = error_code(error)
        if not args.status and code not in ('already_running', 'root_required'):
            try:
                Timer().apply({'status': 'needs_operator', 'next_at': None})
            except Exception:
                pass
        print(json.dumps({'success': False, 'error_type': code, 'needs_operator': True}), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
