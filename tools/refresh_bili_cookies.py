#!/usr/bin/env python3
"""One bounded, isolated Bilibili session candidate; production publishing is external.

Default is a credential-free dry run. No timer, automatic retry, challenge solver,
or browser fingerprint modifications. Backend access goes through ytdlp_service.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

DEFAULT_TARGET = 'https://www.bilibili.com/video/BV1JSh265EQm/'
MAX_BYTES = 1024 * 1024
SIGNAL_COOKIE = 'X-BILI-SEC-TOKEN'
_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_DOMAIN = re.compile(r'\.?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+')


class RefreshError(RuntimeError):
    """Only fixed, credential-free error categories cross this boundary."""
    def __init__(self, error_type: str):
        self.error_type = error_type if re.fullmatch(r'[a-z_]{1,64}', error_type) else 'refresh_failed'
        super().__init__(self.error_type)


def _bili_domain(domain):
    bare = domain.lstrip('.').lower()
    return bare == 'bilibili.com' or bare.endswith('.bilibili.com')


def _safe_string(value, *, empty=False):
    return (isinstance(value, str) and (empty or bool(value))
            and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def normalize_cookies(cookies: list[dict], *, now: float | None = None) -> bytes:
    now = time.time() if now is None else now
    if not isinstance(cookies, list) or not cookies or len(cookies) > 4096:
        raise RefreshError('invalid_cookies')
    rows = ['# Netscape HTTP Cookie File']
    size = len(rows[0]) + 1
    for item in cookies:
        if not isinstance(item, dict):
            raise RefreshError('invalid_cookies')
        domain = item.get('domain')
        if not _safe_string(domain) or not _DOMAIN.fullmatch(domain):
            raise RefreshError('invalid_cookies')
        if not _bili_domain(domain):
            continue
        path, name, value = item.get('path'), item.get('name'), item.get('value')
        if (not _safe_string(path) or not path.startswith('/')
                or not isinstance(name, str) or not _NAME.fullmatch(name)
                or not _safe_string(value, empty=True) or type(item.get('secure')) is not bool):
            raise RefreshError('invalid_cookies')
        expiry = item.get('expires')
        if expiry is not None and (isinstance(expiry, bool) or not isinstance(expiry, (float, int))
                                   or not math.isfinite(expiry) or expiry < -1 or expiry > 999999999999):
            raise RefreshError('invalid_cookies')
        # Explicitly expired tokens never become session cookies through a flag.
        if expiry and expiry > 0 and expiry <= now:
            if name.lower() == SIGNAL_COOKIE.lower():
                raise RefreshError('expired_signal_cookie')
            continue
        expiry = 0 if item.get('session') is True or expiry in (None, -1, 0) else int(expiry)
        row = '\t'.join([domain, 'TRUE' if domain.startswith('.') else 'FALSE', path,
                          'TRUE' if item['secure'] else 'FALSE', str(expiry) if expiry else '', name, value])
        size += len(row.encode('utf-8')) + 1
        if size > MAX_BYTES:
            raise RefreshError('cookies_too_large')
        rows.append(row)
    data = ('\n'.join(rows) + '\n').encode('utf-8')
    validate_cookie_bytes(data, now=now)
    return data


def validate_cookie_bytes(data: bytes, *, now: float | None = None) -> dict:
    """Validate before any mature parser can echo malformed credential rows."""
    now = time.time() if now is None else now
    if not isinstance(data, bytes) or not data or len(data) > MAX_BYTES:
        raise RefreshError('invalid_cookie_file')
    try:
        text = data.decode('utf-8')
    except UnicodeError:
        raise RefreshError('invalid_cookie_file') from None
    lines = text.split('\n')
    if lines[0] != '# Netscape HTTP Cookie File' or '\r' in text or '\x00' in text:
        raise RefreshError('invalid_cookie_file')
    count, signal_expiries, keys = 0, [], set()
    for line in lines[1:]:
        if not line:
            continue
        parts = line.removeprefix('#HttpOnly_').split('\t')
        if len(parts) != 7:
            raise RefreshError('invalid_cookie_file')
        domain, subdomains, path, secure, expiry, name, value = parts
        if (not _DOMAIN.fullmatch(domain) or not _bili_domain(domain)
                or subdomains not in ('TRUE', 'FALSE') or domain.startswith('.') != (subdomains == 'TRUE')
                or secure not in ('TRUE', 'FALSE') or not _safe_string(path) or not path.startswith('/')
                or not _NAME.fullmatch(name) or not _safe_string(value, empty=True)
                or (expiry and not re.fullmatch(r'[0-9]{1,12}', expiry))):
            raise RefreshError('invalid_cookie_file')
        expires = int(expiry) if expiry else 0
        key = (domain, path, name)
        if key in keys or count >= 4096:
            raise RefreshError('invalid_cookie_file')
        keys.add(key)
        if expires and expires <= now:
            raise RefreshError('expired_cookie')
        count += 1
        if name.lower() == SIGNAL_COOKIE.lower():
            if not value.strip():
                raise RefreshError('empty_signal_cookie')
            signal_expiries.append(expires)
    if not count or not signal_expiries:
        raise RefreshError('missing_signal_cookie')
    # Earliest non-session expiry is a conservative summary, never a lifetime promise.
    return {'cookie_count': count, 'has_signal_cookie': True,
            'signal_expires': min(signal_expiries)}


def _private_dir(path: Path):
    path = Path(path).absolute()
    # Reject symlinks anywhere in the dedicated path, including parent aliases.
    for part in (path, *path.parents):
        if part.is_symlink():
            raise RefreshError('unsafe_state_dir')
    try:
        metadata = path.lstat()
    except OSError:
        raise RefreshError('unsafe_state_dir') from None
    if not stat.S_ISDIR(metadata.st_mode):
        raise RefreshError('unsafe_state_dir')
    if os.name == 'posix' and (metadata.st_uid != os.geteuid()
                              or stat.S_IMODE(metadata.st_mode) != 0o700):
        raise RefreshError('unsafe_state_dir')
    return path


def write_candidate(data: bytes, out_path: Path) -> dict:
    summary = validate_cookie_bytes(data)
    out_path = Path(out_path).absolute()
    _private_dir(out_path.parent)
    if out_path.name in ('.', '..', 'profile', '.refresh.lock') or out_path.is_symlink():
        raise RefreshError('unsafe_candidate')
    if out_path.exists() and not stat.S_ISREG(out_path.lstat().st_mode):
        raise RefreshError('unsafe_candidate')
    temporary = None
    try:
        descriptor, name = tempfile.mkstemp(prefix='.candidate-', dir=out_path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, 'wb') as handle:
            if os.name == 'posix':
                os.fchmod(handle.fileno(), 0o600)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, out_path)
        temporary = None
        return {**summary, 'candidate_path': str(out_path),
                'candidate_sha256': hashlib.sha256(data).hexdigest()}
    except OSError:
        raise RefreshError('candidate_write_failed') from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate_target(target: str) -> str:
    if not isinstance(target, str) or not re.fullmatch(
            r'https://www\.bilibili\.com/video/(BV[0-9A-Za-z]{10})/?', target):
        raise RefreshError('invalid_target')
    return target.rstrip('/') + '/'


class NavigationEvidence:
    def __init__(self, target):
        self.target = validate_target(target)
        self.bvid = self.target.rstrip('/').split('/')[-1]
        self.main_frame = None
        self.document_status = None
        self.document_frames = []
        self.document_navigations = 0

    def on_event(self, event):
        if event.get('method') != 'Network.responseReceived':
            return
        params = event.get('params', {})
        response = params.get('response', {})
        if params.get('type') != 'Document':
            return
        # Only bounded non-credential fields; never retain query, headers or body.
        parsed = urlsplit(response.get('url', ''))
        status = response.get('status')
        frame = params.get('frameId')
        if len(self.document_frames) < 32:
            self.document_frames.append((frame, parsed.hostname, parsed.path, status))
        self._select_document()

    def _select_document(self):
        for frame, host, path, status in self.document_frames:
            if frame == self.main_frame:
                if host != 'www.bilibili.com' or path.rstrip('/') != urlsplit(self.target).path.rstrip('/'):
                    raise RefreshError('unexpected_navigation')
                self.document_status = status
                if status != 200:
                    # A later automatic document response cannot erase a refusal.
                    return
        self.document_navigations = sum(frame == self.main_frame for frame, *_ in self.document_frames)

    def check_page(self, page):
        self._select_document()
        if self.document_status is not None and self.document_status != 200:
            raise RefreshError('document_rejected')
        if not isinstance(page, dict):
            return False
        if page.get('challenge'):
            raise RefreshError('verification_required')
        href = page.get('href', '')
        if href and href != 'about:blank' and href.rstrip('/') != self.target.rstrip('/'):
            raise RefreshError('unexpected_navigation')
        return bool(self.document_status == 200 and page.get('bvid') == self.bvid
                    and isinstance(page.get('aid'), (int, float)) and page['aid'] > 0
                    and page.get('has_video_title'))


@contextmanager
def state_lock(state_dir: Path):
    import fcntl
    state_dir = _private_dir(state_dir)
    descriptor = None
    try:
        descriptor = os.open(state_dir / '.refresh.lock', os.O_RDWR | os.O_CREAT
                             | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
            raise RefreshError('unsafe_lock')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RefreshError('busy') from None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)


def cleanup_processes(processes):
    """Signal owned session groups even when their original leader exited."""
    cleaned = True
    for process in reversed(processes):
        try:
            os.killpg(process.pid, getattr(signal, 'SIGKILL', 9))
        except ProcessLookupError:
            pass
        except OSError:
            cleaned = False
        try:
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            cleaned = False
    return cleaned


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RefreshError('timeout')
    return remaining


class Cdp:
    """Sequential CDP calls; event observations retain no credential payloads."""
    def __init__(self, socket, deadline, evidence):
        self.socket, self.deadline, self.evidence = socket, deadline, evidence
        self.sequence = 0

    def send(self, method, params):
        self.sequence += 1
        self.socket.send(json.dumps({'id': self.sequence, 'method': method, 'params': params}))
        return self.sequence

    def call(self, method, **params):
        message_id = self.send(method, params)
        while True:
            try:
                message = json.loads(self.socket.recv(timeout=_remaining(self.deadline)))
            except TimeoutError:
                raise RefreshError('timeout') from None
            except (ValueError, TypeError):
                raise RefreshError('invalid_cdp_response') from None
            if message.get('id') == message_id:
                if 'error' in message:
                    raise RefreshError('cdp_command_failed')
                return message.get('result', {})
            if message.get('method') == 'Fetch.requestPaused':
                # Media requests cannot continue while an unrelated CDP call waits.
                self.send('Fetch.failRequest', {'requestId': message['params']['requestId'],
                                               'errorReason': 'BlockedByClient'})
            else:
                self.evidence.on_event(message)


_PAGE_EVIDENCE_JS = r'''(() => {
 const state = window.__INITIAL_STATE__ || {};
 const video = state.videoData || {};
 const text = (document.body && document.body.innerText || '').slice(0, 16000);
 const title = document.title || '';
 return {href: location.href, bvid: video.bvid || '', aid: video.aid || 0,
   has_video_title: !!document.querySelector('h1.video-title'),
   challenge: /安全验证|验证身份|人机验证|访问受限|请求被拦截|captcha/i.test(title)
     || !!document.querySelector('iframe[src*="captcha"],.geetest_panel,.bili-captcha')
     || /请完成以下验证|请先登录后再访问|异常请求/.test(text)};
})()'''


def collect_cookies(socket, target, deadline, evidence=None):
    evidence = evidence or NavigationEvidence(target)
    cdp = Cdp(socket, deadline, evidence)
    cdp.call('Page.enable')
    cdp.call('Runtime.enable')
    cdp.call('Network.enable', maxTotalBufferSize=1048576, maxResourceBufferSize=131072)
    cdp.call('Network.setBlockedURLs', urls=[
        '*://*.bilivideo.com/*', '*://bilivideo.com/*', '*://*.bilivideo.cn/*',
        '*.mp4*', '*.m4s*', '*.m3u8*', '*.flv*', '*.mp3*', '*.aac*'])
    cdp.call('Fetch.enable', patterns=[{'resourceType': 'Media', 'requestStage': 'Request'}])
    cdp.call('Browser.setDownloadBehavior', behavior='deny')
    navigation = cdp.call('Page.navigate', url=target)
    evidence.main_frame = navigation.get('frameId')
    if not evidence.main_frame or navigation.get('errorText'):
        raise RefreshError('navigation_failed')
    while True:
        page = cdp.call('Runtime.evaluate', expression=_PAGE_EVIDENCE_JS,
                        returnByValue=True, awaitPromise=False).get('result', {}).get('value')
        if evidence.check_page(page):
            break
        time.sleep(min(0.2, _remaining(deadline)))
    # getCookies is scoped to Bilibili URLs and the normalizer rejects other domains.
    cookies = cdp.call('Network.getCookies', urls=[target, 'https://api.bilibili.com/'])
    data = normalize_cookies(cookies.get('cookies'))
    return data, {'document_status': evidence.document_status, 'explicit_navigations': 1,
                  'document_navigations': evidence.document_navigations}


def _assert_worker_user():
    if os.name != 'posix' or os.geteuid() == 0:
        raise RefreshError('nonroot_linux_required')


def _child_environment():
    # Only the newly launched children see this; inherited browser DISPLAY is ignored.
    result = {key: value for key, value in os.environ.items()
              if key.lower() not in {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
                                     'display', 'wayland_display', 'xauthority'}}
    result.update(NO_PROXY='*', no_proxy='*')
    return result


def _start_display(environment, deadline, processes):
    import select
    read_fd, write_fd = os.pipe()
    try:
        process = subprocess.Popen(['/usr/bin/Xvfb', '-displayfd', str(write_fd),
                                    '-screen', '0', '1280x720x24', '-nolisten', 'tcp'],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, env=environment,
                                   start_new_session=True, pass_fds=(write_fd,))
        processes.append(process)
        os.close(write_fd)
        write_fd = None
        if not select.select([read_fd], [], [], min(10, _remaining(deadline)))[0]:
            raise RefreshError('display_start_failed')
        display = os.read(read_fd, 32).decode('ascii').strip()
        if not re.fullmatch(r'[0-9]{1,5}', display) or process.poll() is not None:
            raise RefreshError('display_start_failed')
        return ':' + display
    finally:
        os.close(read_fd)
        if write_fd is not None:
            os.close(write_fd)


def _page_endpoint(profile, process, deadline):
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while True:
        _remaining(deadline)
        if process.poll() is not None:
            raise RefreshError('browser_exited')
        try:
            port_file = profile / 'DevToolsActivePort'
            metadata = port_file.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 256:
                raise RefreshError('unsafe_cdp_port_file')
            port_text = port_file.read_text(encoding='ascii').splitlines()[0]
            if not port_text.isdigit() or not 1024 <= int(port_text) <= 65535:
                raise RefreshError('unsafe_cdp_port_file')
            with opener.open(f'http://127.0.0.1:{port_text}/json/list',
                             timeout=min(2, _remaining(deadline))) as response:
                payload = response.read(65537)
            if len(payload) > 65536:
                raise RefreshError('invalid_cdp_endpoint')
            pages = json.loads(payload)
            for page in pages:
                if page.get('type') == 'page' and page.get('url') == 'about:blank':
                    endpoint = page.get('webSocketDebuggerUrl', '')
                    if not re.fullmatch(r'ws://127\.0\.0\.1:' + port_text
                                        + r'/devtools/page/[A-Za-z0-9-]+', endpoint):
                        raise RefreshError('invalid_cdp_endpoint')
                    return endpoint
        except (OSError, ValueError, IndexError):
            pass
        time.sleep(min(0.1, _remaining(deadline)))


def launch_browser(args, deadline, processes):
    # Import only on --run; no dependency loading or profile access on dry run.
    from websockets.sync.client import connect
    profile = args.state_dir / 'profile'
    if not profile.exists():
        profile.mkdir(mode=0o700)
    _private_dir(profile)
    # A fresh browser writes this itself. Never connect to an older profile endpoint.
    (profile / 'DevToolsActivePort').unlink(missing_ok=True)
    environment = _child_environment()
    if args.mode == 'headed':
        environment['DISPLAY'] = _start_display(environment, deadline, processes)
    if args.chrome not in {'/usr/bin/google-chrome', '/opt/google/chrome/chrome',
                           '/usr/bin/chromium', '/usr/bin/chromium-browser'}:
        raise RefreshError('unsafe_browser_binary')
    command = [args.chrome, '--user-data-dir=' + str(profile),
               '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
               '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
               '--disable-component-update', '--disable-default-apps', '--disable-sync',
               '--disable-breakpad', '--metrics-recording-only', '--mute-audio',
               '--no-proxy-server', '--autoplay-policy=user-gesture-required']
    if args.mode == 'headless':
        command.append('--headless=new')
    command.append('about:blank')
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, env=environment, start_new_session=True)
    processes.append(process)
    endpoint = _page_endpoint(profile, process, deadline)
    return connect(endpoint, origin=None, open_timeout=min(5, _remaining(deadline)),
                   close_timeout=1, max_size=2 * MAX_BYTES, max_queue=16,
                   compression=None, proxy=None)


def validate_with_backend(candidate, target, deadline):
    """Exactly one metadata extraction in this isolated worker, never a download."""
    backend = str(Path(__file__).resolve().parents[1] / 'backend')
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.services import ytdlp_service as service
    settings = service.settings
    overrides = {'bilibili_cookie_file': str(candidate), 'network_retries': 0,
                 'parse_extractor_retries': 0,
                 'parse_socket_timeout_seconds': max(1, min(8, int(_remaining(deadline))))}
    original = {key: getattr(settings, key) for key in overrides}
    proxy_environment = {key: value for key, value in os.environ.items()
                         if key.lower() in {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'}}
    # Existing service supplies private logger, strict-domain jar, no playlist,
    # skip_download and download=False. Never import yt_dlp here.
    try:
        for key, value in overrides.items():
            setattr(settings, key, value)
        for key in proxy_environment:
            os.environ.pop(key, None)
        info = service.extract_info(target)
        formats = [item for item in info.get('formats', []) if isinstance(item, dict)
                   and item.get('url') and item.get('vcodec') not in (None, 'none')]
        if info.get('id') != target.rstrip('/').split('/')[-1] or not formats:
            raise RefreshError('backend_no_formats')
        return {'success': True, 'usable_format_count': len(formats),
                'heights': sorted({int(item['height']) for item in formats
                                   if isinstance(item.get('height'), (int, float))
                                   and 0 < item['height'] < 10000})}
    except RefreshError:
        raise
    except Exception:
        raise RefreshError('backend_rejected') from None
    finally:
        os.environ.update(proxy_environment)
        for key, value in original.items():
            setattr(settings, key, value)


def run_refresh(args):
    result = {'success': False, 'explicit_navigations': 0, 'stage': 'preflight',
              'own_processes_cleaned': True}
    processes, socket, created_candidate = [], None, False
    lock, lock_acquired, evidence = None, False, None
    deadline = time.monotonic() + args.timeout
    old_handlers = {}
    try:
        _assert_worker_user()
        args.state_dir = _private_dir(args.state_dir) if args.state_dir else None
        if args.state_dir is None or args.out is None:
            raise RefreshError('state_and_output_required')
        args.out = args.out.absolute()
        if args.out.parent != args.state_dir or args.out.name != 'candidate.cookies.txt':
            raise RefreshError('unsafe_candidate')
        # Whole worker deadline also bounds the lazy backend's multiple socket operations.
        def alarm_handler(signum, frame):
            raise RefreshError('timeout')
        def termination_handler(signum, frame):
            raise RefreshError('terminated')
        old_handlers[signal.SIGALRM] = signal.signal(signal.SIGALRM, alarm_handler)
        for signum in (signal.SIGTERM, signal.SIGINT):
            old_handlers[signum] = signal.signal(signum, termination_handler)
        signal.setitimer(signal.ITIMER_REAL, _remaining(deadline))
        lock = state_lock(args.state_dir)
        lock.__enter__()
        lock_acquired = True
        if args.out.exists() or args.out.is_symlink():
            raise RefreshError('candidate_already_exists')
        result['stage'] = 'browser'
        socket = launch_browser(args, deadline, processes)
        result['stage'] = 'navigation'
        result['explicit_navigations'] = 1
        evidence = NavigationEvidence(args.target)
        data, observation = collect_cookies(socket, args.target, deadline, evidence)
        result.update(observation)
        result['stage'] = 'candidate'
        created_candidate = True
        summary = write_candidate(data, args.out)
        result.update(summary)
        result['stage'] = 'backend_validation'
        result['backend_validation'] = {'success': False}
        result['backend_validation'] = validate_with_backend(args.out, args.target, deadline)
        _remaining(deadline)
        result.update(success=True, stage='complete')
    except Exception as error:
        result['error_type'] = error.error_type if isinstance(error, RefreshError) else 'refresh_failed'
    finally:
        if evidence is not None:
            result['document_status'] = evidence.document_status
        if old_handlers:
            signal.setitimer(signal.ITIMER_REAL, 0)
            # Complete bounded cleanup if a supervisor sends a second TERM.
            for signum in (signal.SIGTERM, signal.SIGINT):
                signal.signal(signum, signal.SIG_IGN)
        if socket is not None:
            try:
                socket.close()
            except Exception:
                result['own_processes_cleaned'] = False
        result['own_processes_cleaned'] = cleanup_processes(processes) and result['own_processes_cleaned']
        if not result['own_processes_cleaned']:
            result.update(success=False, error_type='cleanup_failed')
        if not result['success'] and created_candidate:
            args.out.unlink(missing_ok=True)
            result.pop('candidate_path', None)
            result.pop('candidate_sha256', None)
        if lock_acquired:
            lock.__exit__(None, None, None)
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
    return result


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--mode', choices=('headed', 'headless'), default='headed')
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--target', default=DEFAULT_TARGET)
    parser.add_argument('--timeout', type=int, default=60)
    parser.add_argument('--chrome', default='/usr/bin/google-chrome')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    result = {'success': False, 'dry_run': not args.run, 'mode': args.mode,
              'own_processes_cleaned': True, 'explicit_navigations': 0, 'stage': 'preflight'}
    try:
        args.target = validate_target(args.target)
        if not 1 <= args.timeout <= 90:
            raise RefreshError('invalid_timeout')
        if args.run:
            result.update(run_refresh(args))
        else:
            result.update(success=True, stage='dry_run')
        exit_code = 0 if result['success'] else 1
    except Exception as error:
        result['error_type'] = error.error_type if isinstance(error, RefreshError) else 'refresh_failed'
        exit_code = 1
    print(json.dumps(result, separators=(',', ':'), ensure_ascii=True), flush=True)
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
