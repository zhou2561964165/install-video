"""Offline regression tests: synthetic credentials, no browser or network."""
import importlib.util
import io
import json
import os
import stat
import sys
from contextlib import nullcontext
from types import ModuleType, SimpleNamespace
from pathlib import Path
from http.cookiejar import MozillaCookieJar

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'tools' / 'refresh_bili_cookies.py'


@pytest.fixture
def tool():
    if not SCRIPT.is_file():
        pytest.skip('implementation absent; existence regression is RED')
    spec = importlib.util.spec_from_file_location('refresh_bili_tool_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refresh_tool_available_for_operator():
    assert SCRIPT.is_file(), 'controlled refresh tool is missing'


def cookie(**changes):
    return dict(domain='.bilibili.com', path='/', secure=True,
                name='X-BILI-SEC-TOKEN', value='synthetic-token', expires=2000000000,
                **changes) if not changes else {**cookie(), **changes}


def test_host_only_and_session_survive_mature_parser(tool):
    data = tool.normalize_cookies([cookie(expires=-1), cookie(
        domain='api.bilibili.com', name='session-id', value='fake', expires=0)], now=100)
    jar = MozillaCookieJar()
    jar._really_load(io.StringIO(data.decode()), '<synthetic>', True, True)
    rows = {item.name: item for item in jar}
    assert rows['X-BILI-SEC-TOKEN'].discard
    assert not rows['session-id'].domain_specified
    assert rows['session-id'].domain == 'api.bilibili.com'
    assert tool.validate_cookie_bytes(data, now=100) == {
        'cookie_count': 2, 'has_signal_cookie': True, 'signal_expires': 0}


@pytest.mark.parametrize('expires', [None, 0, -1])
def test_session_expiry_normalized(tool, expires):
    assert b'\t\tX-BILI-SEC-TOKEN\t' in tool.normalize_cookies([cookie(expires=expires)])


@pytest.mark.parametrize('rows', [[], [cookie(value='')], [cookie(expires=1)],
                                  [cookie(domain='bilibili.com.evil.test')]])
def test_empty_or_expired_signal_never_qualifies(tool, rows):
    with pytest.raises(tool.RefreshError):
        tool.normalize_cookies(rows, now=100)


def test_expired_ordinary_and_unrelated_cookie_are_not_exported(tool):
    data = tool.normalize_cookies([cookie(), cookie(name='old', expires=1),
                                  cookie(domain='.example.com', name='unrelated')], now=100)
    assert tool.validate_cookie_bytes(data, now=100)['cookie_count'] == 1


@pytest.mark.parametrize('changes', [dict(value='secret\nrow'), dict(path='/\tbad'),
    dict(domain='..bilibili.com'), dict(name='bad name'), dict(expires='NaN'),
    dict(secure='false'), dict(value='x' * (1024 * 1024))])
def test_injection_and_malformed_cookies_fail_safely(tool, changes, capsys):
    with pytest.raises(tool.RefreshError) as error:
        tool.normalize_cookies([cookie(**changes)])
    assert 'secret' not in str(error.value)
    assert not capsys.readouterr().err


def test_invalid_candidate_leaves_existing_file_untouched(tool, tmp_path):
    old = tmp_path / 'candidate.cookies.txt'
    old.write_bytes(b'old-placeholder')
    with pytest.raises(tool.RefreshError):
        tool.write_candidate(b'invalid secret', old)
    assert old.read_bytes() == b'old-placeholder'
    assert list(tmp_path.iterdir()) == [old]


def test_valid_candidate_is_atomic_and_private(tool, tmp_path):
    if os.name == 'posix':
        tmp_path.chmod(0o700)
    out = tmp_path / 'candidate.cookies.txt'
    data = tool.normalize_cookies([cookie()])
    result = tool.write_candidate(data, out)
    assert out.read_bytes() == data
    assert result['cookie_count'] == 1
    assert len(result['candidate_sha256']) == 64
    if os.name == 'posix':
        assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_symlink_candidate_cannot_replace_target(tool, tmp_path):
    if os.name != 'posix':
        pytest.skip('Linux symlink permissions')
    tmp_path.chmod(0o700)
    target = tmp_path / 'original'
    target.write_text('keep')
    link = tmp_path / 'candidate.cookies.txt'
    link.symlink_to(target)
    with pytest.raises(tool.RefreshError):
        tool.write_candidate(tool.normalize_cookies([cookie()]), link)
    assert target.read_text() == 'keep'


def test_default_dryrun_does_not_start_or_import_browser(tool, capsys, monkeypatch):
    monkeypatch.setattr(tool, 'run_refresh', lambda args: pytest.fail('dryrun started worker'))
    assert tool.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['dry_run'] and result['explicit_navigations'] == 0


@pytest.mark.parametrize('target', ['https://evil.test/video/BV1JSh265EQm/',
    'https://www.bilibili.com/video/BV1JSh265EQm/?secret=x',
    'https://user@www.bilibili.com/video/BV1JSh265EQm/',
    'http://www.bilibili.com/video/BV1JSh265EQm/',
    'https://www.bilibili.com/video/BV1JSh265EQm/extra'])
def test_target_is_narrow_and_query_free(tool, target):
    with pytest.raises(tool.RefreshError):
        tool.validate_target(target)


def test_actual_http_and_target_evidence_required(tool):
    status = tool.NavigationEvidence(tool.DEFAULT_TARGET)
    status.main_frame = 'main'
    status.on_event({'method': 'Network.responseReceived', 'params': {
        'type': 'Document', 'frameId': 'main', 'response': {
            'url': tool.DEFAULT_TARGET, 'status': 200}}})
    with pytest.raises(tool.RefreshError):
        status.check_page({'href': tool.DEFAULT_TARGET, 'bvid': '', 'challenge': True})
    assert status.check_page({'href': tool.DEFAULT_TARGET, 'bvid': 'BV1JSh265EQm',
                              'aid': 123, 'has_video_title': True, 'challenge': False})
    status.on_event({'method': 'Network.responseReceived', 'params': {
        'type': 'Document', 'frameId': 'main', 'response': {
            'url': tool.DEFAULT_TARGET, 'status': 412}}})
    with pytest.raises(tool.RefreshError):
        status.check_page({'href': tool.DEFAULT_TARGET, 'bvid': 'BV1JSh265EQm'})


def test_title_alone_or_subframe_200_never_succeeds(tool):
    status = tool.NavigationEvidence(tool.DEFAULT_TARGET)
    status.main_frame = 'main'
    status.on_event({'method': 'Network.responseReceived', 'params': {
        'type': 'Document', 'frameId': 'sub', 'response': {
            'url': tool.DEFAULT_TARGET, 'status': 200}}})
    assert not status.check_page({'title': 'normal video title', 'challenge': False})


def test_initial_rejection_cannot_be_hidden_by_later_document_200(tool):
    status = tool.NavigationEvidence(tool.DEFAULT_TARGET)
    for code in (412, 200):
        status.on_event({'method': 'Network.responseReceived', 'params': {
            'type': 'Document', 'frameId': 'main', 'response': {
                'url': tool.DEFAULT_TARGET, 'status': code}}})
    status.main_frame = 'main'
    with pytest.raises(tool.RefreshError, match='document_rejected'):
        status.check_page({'href': tool.DEFAULT_TARGET, 'bvid': 'BV1JSh265EQm',
                           'aid': 123, 'has_video_title': True})
    assert status.document_status == 412


def test_lock_rejects_second_worker_and_releases(tool, tmp_path):
    if os.name != 'posix':
        pytest.skip('Linux flock')
    tmp_path.chmod(0o700)
    with tool.state_lock(tmp_path):
        with pytest.raises(tool.RefreshError, match='busy'):
            with tool.state_lock(tmp_path):
                pytest.fail('concurrent lock acquired')
    with tool.state_lock(tmp_path):
        pass


def test_cleanup_kills_group_even_if_leader_exited(tool, monkeypatch):
    calls = []
    class Process:
        pid = 43210
        def poll(self): return 0
        def wait(self, timeout): return 0
    monkeypatch.setattr(tool.os, 'killpg', lambda pid, sig: calls.append((pid, sig)), raising=False)
    assert tool.cleanup_processes([Process()])
    assert calls and calls[0][0] == 43210


class FakeSocket:
    """CDP transport double; commands use realistic responses and events."""
    def __init__(self, *, rejected=False, challenge=False):
        self.queue = []
        self.commands = []
        self.closed = False
        self.rejected = rejected
        self.challenge = challenge

    def send(self, payload):
        item = json.loads(payload)
        self.commands.append(item)
        method = item['method']
        result = {}
        if method == 'Page.navigate':
            self.queue.append({'method': 'Network.responseReceived', 'params': {
                'type': 'Document', 'frameId': 'main', 'response': {
                    'url': 'https://www.bilibili.com/video/BV1JSh265EQm/',
                    'status': 412 if self.rejected else 200}}})
            result = {'frameId': 'main'}
        elif method == 'Runtime.evaluate':
            result = {'result': {'type': 'object', 'value': {
                'href': 'https://www.bilibili.com/video/BV1JSh265EQm/',
                'bvid': 'BV1JSh265EQm', 'aid': 123, 'has_video_title': True,
                'challenge': self.challenge}}}
        elif method == 'Network.getCookies':
            result = {'cookies': [cookie()]}
        self.queue.append({'id': item['id'], 'result': result})

    def recv(self, timeout):
        assert timeout > 0
        return json.dumps(self.queue.pop(0))

    def close(self):
        self.closed = True


def test_browser_one_navigation_and_validation_success(tool):
    socket = FakeSocket()
    data, evidence = tool.collect_cookies(socket, tool.DEFAULT_TARGET, tool.time.monotonic() + 10)
    assert tool.validate_cookie_bytes(data)['has_signal_cookie']
    assert evidence['document_status'] == 200
    assert evidence['explicit_navigations'] == 1
    methods = [item['method'] for item in socket.commands]
    assert methods.count('Page.navigate') == 1
    assert 'Page.reload' not in methods
    blocked = next(item['params']['urls'] for item in socket.commands
                   if item['method'] == 'Network.setBlockedURLs')
    assert '*://*.bilivideo.com/*' in blocked
    assert '*.m4s*' in blocked


@pytest.mark.parametrize('rejected,challenge', [(True, False), (False, True)])
def test_browser_rejection_never_exports_candidate(tool, rejected, challenge):
    socket = FakeSocket(rejected=rejected, challenge=challenge)
    with pytest.raises(tool.RefreshError):
        tool.collect_cookies(socket, tool.DEFAULT_TARGET, tool.time.monotonic() + 10)
    assert 'Network.getCookies' not in [item['method'] for item in socket.commands]


def test_backend_failure_does_not_leave_invalid_candidate(tool, tmp_path, monkeypatch):
    if os.name == 'posix':
        tmp_path.chmod(0o700)
    socket = FakeSocket()
    monkeypatch.setattr(tool, '_assert_worker_user', lambda: None)
    monkeypatch.setattr(tool, 'state_lock', lambda path: nullcontext())
    monkeypatch.setattr(tool.signal, 'SIGALRM', 14, raising=False)
    monkeypatch.setattr(tool.signal, 'ITIMER_REAL', 0, raising=False)
    monkeypatch.setattr(tool.signal, 'signal', lambda *args: 0)
    monkeypatch.setattr(tool.signal, 'setitimer', lambda *args: None, raising=False)
    monkeypatch.setattr(tool, 'launch_browser', lambda *args: socket)
    monkeypatch.setattr(tool, 'validate_with_backend', lambda *args: (_ for _ in ()).throw(
        tool.RefreshError('backend_rejected')))
    args = tool.build_parser().parse_args(['--run', '--state-dir', str(tmp_path),
                                          '--out', str(tmp_path / 'candidate.cookies.txt')])
    result = tool.run_refresh(args)
    assert not result['success'] and result['error_type'] == 'backend_rejected'
    assert not args.out.exists()
    assert socket.closed and result['own_processes_cleaned']


def test_backend_validation_restores_settings_and_disables_proxy(tool, tmp_path, monkeypatch):
    original = dict(bilibili_cookie_file='unused-production-path', network_retries=2,
                    parse_extractor_retries=1, parse_socket_timeout_seconds=15)
    settings = SimpleNamespace(**original)
    observations = []
    def extract(url):
        observations.append(url)
        assert settings.bilibili_cookie_file == str(tmp_path / 'candidate.cookies.txt')
        assert settings.network_retries == settings.parse_extractor_retries == 0
        assert not any(key.lower() == 'https_proxy' for key in os.environ)
        return {'id': 'BV1JSh265EQm', 'formats': [
            {'url': 'https://cdn.invalid/v', 'vcodec': 'avc1', 'height': 720},
            {'url': 'https://cdn.invalid/a', 'vcodec': 'none', 'height': None}]}
    app = ModuleType('app')
    services = ModuleType('app.services')
    services.ytdlp_service = SimpleNamespace(settings=settings, extract_info=extract)
    monkeypatch.setitem(sys.modules, 'app', app)
    monkeypatch.setitem(sys.modules, 'app.services', services)
    monkeypatch.setenv('HTTPS_PROXY', 'http://synthetic.invalid:8080')
    result = tool.validate_with_backend(tmp_path / 'candidate.cookies.txt', tool.DEFAULT_TARGET,
                                        tool.time.monotonic() + 10)
    assert result == {'success': True, 'usable_format_count': 1, 'heights': [720]}
    assert observations == [tool.DEFAULT_TARGET]
    assert vars(settings) == original
    assert os.environ['HTTPS_PROXY'] == 'http://synthetic.invalid:8080'


def test_worker_failure_retains_http_status_and_releases_lock_after_cleanup(tool, tmp_path, monkeypatch):
    if os.name == 'posix':
        tmp_path.chmod(0o700)
    from contextlib import contextmanager
    locked = []
    @contextmanager
    def lock(path):
        locked.append(True)
        try:
            yield
        finally:
            locked.pop()
    socket = FakeSocket(rejected=True)
    monkeypatch.setattr(tool, '_assert_worker_user', lambda: None)
    monkeypatch.setattr(tool, 'state_lock', lock)
    monkeypatch.setattr(tool.signal, 'SIGALRM', 14, raising=False)
    monkeypatch.setattr(tool.signal, 'ITIMER_REAL', 0, raising=False)
    monkeypatch.setattr(tool.signal, 'signal', lambda *args: 0)
    monkeypatch.setattr(tool.signal, 'setitimer', lambda *args: None, raising=False)
    monkeypatch.setattr(tool, 'launch_browser', lambda *args: socket)
    def cleanup(processes):
        assert locked, 'lock must cover cleanup of owned browsers'
        return True
    monkeypatch.setattr(tool, 'cleanup_processes', cleanup)
    args = tool.build_parser().parse_args(['--run', '--state-dir', str(tmp_path),
                                          '--out', str(tmp_path / 'candidate.cookies.txt')])
    result = tool.run_refresh(args)
    assert not result['success'] and result['document_status'] == 412
    assert not locked and socket.closed


def test_sigterm_after_candidate_removes_it_and_cleans_browser(tool, tmp_path, monkeypatch):
    if os.name == 'posix':
        tmp_path.chmod(0o700)
    handlers = {}
    def install(signum, handler):
        previous = handlers.get(signum, 0)
        handlers[signum] = handler
        return previous
    socket = FakeSocket()
    monkeypatch.setattr(tool, '_assert_worker_user', lambda: None)
    monkeypatch.setattr(tool, 'state_lock', lambda path: nullcontext())
    monkeypatch.setattr(tool.signal, 'SIGALRM', 14, raising=False)
    monkeypatch.setattr(tool.signal, 'ITIMER_REAL', 0, raising=False)
    monkeypatch.setattr(tool.signal, 'signal', install)
    monkeypatch.setattr(tool.signal, 'setitimer', lambda *args: None, raising=False)
    monkeypatch.setattr(tool, 'launch_browser', lambda *args: socket)
    def terminate(*args):
        assert args[0].exists()
        if tool.signal.SIGTERM not in handlers:
            pytest.fail('worker does not clean candidate on SIGTERM')
        handlers[tool.signal.SIGTERM](tool.signal.SIGTERM, None)
    monkeypatch.setattr(tool, 'validate_with_backend', terminate)
    args = tool.build_parser().parse_args(['--run', '--state-dir', str(tmp_path),
                                          '--out', str(tmp_path / 'candidate.cookies.txt')])
    result = tool.run_refresh(args)
    assert not result['success'] and result['error_type'] == 'terminated'
    assert not args.out.exists() and socket.closed


def test_linux_private_dir_and_root_browser_guard(tool, tmp_path, monkeypatch):
    if os.name != 'posix':
        pytest.skip('Linux ownership and mode')
    tmp_path.chmod(0o755)
    with pytest.raises(tool.RefreshError, match='unsafe_state_dir'):
        tool.write_candidate(tool.normalize_cookies([cookie()]), tmp_path / 'candidate.cookies.txt')
    monkeypatch.setattr(tool.os, 'geteuid', lambda: 0)
    with pytest.raises(tool.RefreshError, match='nonroot_linux_required'):
        tool._assert_worker_user()


@pytest.mark.parametrize('data', [b'# Netscape HTTP Cookie File\n.bad.com\tTRUE\t/\tTRUE\t\tx\ty\n',
    b'# Netscape HTTP Cookie File\n.bilibili.com\tFALSE\t/\tTRUE\t\tx\ty\n',
    b'# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tTRUE\t-1\tx\ty\n',
    b'# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tTRUE\t\tx\tsecret\r\n',
    b'x' * (1024 * 1024 + 1)], ids=['external_domain', 'domain_mismatch', 'negative_expiry',
                                         'carriage_return', 'over_size'])
def test_raw_invalid_bytes_never_escape_parser(tool, data, capsys):
    with pytest.raises(tool.RefreshError) as error:
        tool.validate_cookie_bytes(data)
    assert 'secret' not in str(error.value)
    assert capsys.readouterr() == ('', '')
