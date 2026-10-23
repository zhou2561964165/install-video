"""Synthetic-only scheduler policy/transaction tests; never contact a browser."""
import importlib.util
import json
from pathlib import Path
import sys
import hashlib
from types import SimpleNamespace
import contextlib
import io
import inspect
import re
import tempfile
import unittest
import posixpath
import stat

if __name__ == '__main__':
    # No optional dependencies are needed for the server's synthetic verification.
    class _Raises:
        def __init__(self, kind, match=None):
            self.kind, self.match = kind, match
        def __enter__(self):
            return self
        def __exit__(self, kind, value, traceback):
            if kind is None:
                raise AssertionError('expected exception')
            if not isinstance(value, self.kind):
                return False
            if self.match and not re.search(self.match, str(value)):
                raise AssertionError('exception message mismatch')
            return True
    def _parametrize(name, values):
        def decorate(function):
            function.synthetic_parameters = (name, values)
            return function
        return decorate
    pytest = SimpleNamespace(raises=_Raises, skip=lambda reason: (_ for _ in ()).throw(unittest.SkipTest(reason)),
        fail=lambda reason: (_ for _ in ()).throw(AssertionError(reason)),
        mark=SimpleNamespace(parametrize=_parametrize))
else:
    import pytest

SPEC = importlib.util.spec_from_file_location(
    'bili_scheduler', Path(__file__).resolve().parents[2] / 'tools/schedule_bili_session_refresh.py')
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def cookie(expiry=10000, token='synthetic'):
    return ('# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tTRUE\t'
            + str(expiry) + '\tX-BILI-SEC-TOKEN\t' + token + '\n').encode()


def test_default_is_read_free(monkeypatch, capsys):
    monkeypatch.setattr(mod, 'load_runtime', lambda: pytest.fail('runtime loaded'))
    assert mod.main([]) == 0
    assert json.loads(capsys.readouterr().out)['dry_run'] is True


@pytest.mark.parametrize('bad', [{'lead_seconds': True}, {'lead_seconds': 0},
    {'unknown': 1}, {'max_failure_retries': 2}, {'max_daily_api': 10000},
    {'minimum_available_mib': 512}, {'browser_timeout_seconds': 100}])
def test_policy_rejects_unsafe_values(bad):
    with pytest.raises(mod.SafeError):
        mod.validate_policy(bad)


def test_policy_defaults():
    assert mod.validate_policy({}) == mod.DEFAULT_POLICY


@pytest.mark.parametrize('expiry', [0, 100, 10000])
def test_parse_expired_and_session_signal(expiry):
    info = mod.parse_cookie(cookie(expiry))
    assert info['expiry'] == (expiry or None)
    assert 'synthetic' not in json.dumps(info)


@pytest.mark.parametrize('data', [b'', cookie().replace(b'synthetic', b''),
    cookie().replace(b'.bilibili.com', b'.evil.example'),
    cookie().replace(b'10000', b'nope'), cookie() + cookie().split(b'\n')[1] + b'\n'])
def test_parse_rejects_bad_cookie(data):
    with pytest.raises(mod.SafeError):
        mod.parse_cookie(data)


def test_absolute_expiry_minus_lead():
    plan = mod.plan_next(mod.new_state(100), mod.parse_cookie(cookie()), 100, mod.DEFAULT_POLICY)
    assert plan == {'status': 'armed', 'next_at': 8200, 'reason': 'expiry_lead'}


def test_missing_and_expired_cookie_due_once():
    for info in [None, mod.parse_cookie(cookie(50))]:
        assert mod.plan_next(mod.new_state(100), info, 100, mod.DEFAULT_POLICY)['next_at'] == 102


def test_unknown_expiry_needs_operator():
    assert mod.plan_next(mod.new_state(100), mod.parse_cookie(cookie(0)), 100,
                         mod.DEFAULT_POLICY)['status'] == 'needs_operator'


def test_unchanged_cookie_wakes_after_expiry():
    state = mod.new_state(9000)
    state['unchanged_expiry'] = 10000
    assert mod.plan_next(state, mod.parse_cookie(cookie()), 9000,
                         mod.DEFAULT_POLICY)['next_at'] == 10060


def test_failure_has_exactly_one_retry():
    state = mod.new_state(100)
    first = mod.failure_plan(state, 'browser_failed', 100, mod.DEFAULT_POLICY)
    assert first['next_at'] == 1000
    assert state['failure_retries'] == 1
    assert mod.failure_plan(state, 'browser_failed', 1000, mod.DEFAULT_POLICY)['next_at'] is None


@pytest.mark.parametrize('reason', ['verification_requires_user', 'budget_exhausted',
    'ambiguous_transaction', 'protected_state_changed', 'cleanup_failed'])
def test_manual_failures_never_retry(reason):
    assert mod.failure_plan(mod.new_state(100), reason, 100,
                            mod.DEFAULT_POLICY)['status'] == 'needs_operator'


def test_budget_reservation_persists_before_stage():
    state = mod.new_state(100)
    saved = []
    mod.reserve(state, 'navigation', 100, mod.DEFAULT_POLICY,
                lambda value: saved.append(json.loads(json.dumps(value))))
    assert saved[0]['counts']['navigation'] == 1
    state['counts']['navigation'] = 8
    with pytest.raises(mod.SafeError, match='budget_exhausted'):
        mod.reserve(state, 'navigation', 100, mod.DEFAULT_POLICY, saved.append)


def test_day_rollover_resets_only_budget():
    state = mod.new_state(100)
    state.update(failure_retries=1, status='needs_operator')
    state['counts']['api'] = 8
    mod.reserve(state, 'api', 100 + 86400, mod.DEFAULT_POLICY, lambda _: None)
    assert state['counts']['api'] == 1
    assert state['status'] == 'needs_operator' and state['failure_retries'] == 1


def test_timer_only_absolute_no_block(tmp_path):
    commands = []
    timer = mod.Timer(tmp_path / 'timer.d/next.conf', commands.append, enforce_owner=False)
    timer.apply({'status': 'armed', 'next_at': 1800000000, 'reason': 'expiry_lead'})
    text = timer.path.read_text()
    assert text == '[Timer]\nOnCalendar=\nOnCalendar=2027-01-15 08:00:00 UTC\n'
    assert commands == [['systemctl', 'daemon-reload'], ['systemctl', '--no-block',
                         'restart', mod.TIMER_NAME]]
    timer.apply({'status': 'needs_operator', 'next_at': None, 'reason': 'manual'})
    assert commands[-1] == ['systemctl', '--no-block', 'stop', mod.TIMER_NAME]


def test_timer_refuses_symlink(tmp_path):
    target = tmp_path / 'outside'
    target.mkdir()
    link = tmp_path / 'timer.d'
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip('Windows symlink privilege unavailable')
    with pytest.raises(mod.SafeError):
        mod.Timer(link / 'next.conf', lambda _: None, enforce_owner=False).apply(
            {'status': 'armed', 'next_at': 1800000000})


def test_public_state_omits_private_fields():
    state = mod.new_state(100)
    state['transaction'] = {'new_sha256': 'secret-digest'}
    assert 'secret-digest' not in json.dumps(mod.public_state(state))


class FakeRuntime:
    def __init__(self, directory, now, *, unchanged=False, failure=None):
        self.data = cookie(now + 1000, 'old-synthetic')
        self.original = self.data
        self.new_data = self.data if unchanged else cookie(now + 10000, 'new-synthetic')
        self.candidate = directory / 'candidate.cookies.txt'
        self.calls = []
        self.failure = failure
        self.tool = SimpleNamespace(RefreshError=type('RefreshError', (Exception,), {}))
        self.root = SimpleNamespace(SafeError=type('RootError', (Exception,), {}))
        self.browser = SimpleNamespace(refresh=self.refresh, close=self.close, closed=True, statuses=[])

    def refresh(self):
        self.calls.append('navigation')
        self.browser.closed = False
        self.browser.statuses = [412, 200]
        if self.failure == 'captcha':
            raise mod.SafeError('verification_requires_user')
        if self.failure == 'interrupted':
            raise mod.SafeError('interrupted')
        return self.new_data

    def close(self):
        self.calls.append('close')
        self.browser.closed = True

    def admission(self):
        self.calls.append('admission')
        if self.failure == 'admission':
            raise mod.SafeError('insufficient_memory')

    def protected(self):
        return {'current_pid': 42, 'current_config': 'synthetic'}

    def cookie_snapshot(self):
        return {'data': self.data, 'sha256': hashlib.sha256(self.data).hexdigest()}

    def info(self):
        self.calls.append('info')
        return mod.parse_cookie(self.data)

    def write_candidate(self, data):
        self.candidate.write_bytes(data)

    def validate(self, kind, run_id):
        self.calls.append(kind)
        if kind == self.failure:
            if kind == 'api' and getattr(self, 'concurrent', False):
                self.data = cookie(2000000000, 'other-root-writer')
            raise mod.SafeError('candidate_backend_rejected' if kind == 'metadata' else 'post_publish_api_rejected')

    def publish(self, data, old):
        assert self.cookie_snapshot()['sha256'] == old['sha256']
        self.calls.append('publish')
        self.data = data
        if self.failure == 'publish_interrupted' and data == self.new_data:
            raise mod.SafeError('interrupted')

    def remove_candidate(self, data):
        assert self.candidate.read_bytes() == data
        self.candidate.unlink()

    def prune_logs(self):
        pass


def transaction_fixture(tmp_path, monkeypatch, **kwargs):
    now = 1800000000
    monkeypatch.setattr(mod.time, 'time', lambda: now)
    directory = tmp_path / 'state'
    directory.mkdir(mode=0o700)
    store = mod.Store(directory, enforce_owner=False)
    runtime = FakeRuntime(tmp_path, now, **kwargs)
    state = mod.new_state(now)
    return now, store, runtime, state


def test_successful_transaction_reserves_in_order(tmp_path, monkeypatch):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch)
    saved = []
    save = store.save
    def observed(value):
        saved.append(json.loads(json.dumps(value)))
        save(value)
    store.save = observed
    result, info = mod.refresh_transaction(runtime, state, store, mod.DEFAULT_POLICY, now)
    assert result['success'] and result['renewed']
    assert result['document_statuses'] == [412, 200]
    assert state['counts'] == {'navigation': 1, 'metadata': 1, 'api': 1}
    assert runtime.data == runtime.new_data
    assert runtime.calls.index('navigation') < runtime.calls.index('metadata') < runtime.calls.index('publish') < runtime.calls.index('api')
    assert any(v['counts']['navigation'] == 1 and v['counts']['metadata'] == 0 for v in saved)
    assert state['transaction'] is None and not store.recovery.exists() and not runtime.candidate.exists()
    assert info['expiry'] == now + 10000


def test_unchanged_does_not_spend_metadata_or_api(tmp_path, monkeypatch):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch, unchanged=True)
    result, info = mod.refresh_transaction(runtime, state, store, mod.DEFAULT_POLICY, now)
    assert result['success'] and result['renewed'] is False
    assert state['counts'] == {'navigation': 1, 'metadata': 0, 'api': 0}
    assert mod.plan_next(state, info, now, mod.DEFAULT_POLICY)['next_at'] == now + 1060


@pytest.mark.parametrize('failure', ['metadata', 'api', 'captcha', 'interrupted', 'admission', 'publish_interrupted'])
def test_failure_preserves_original_and_cleans(tmp_path, monkeypatch, failure):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch, failure=failure)
    result, info = mod.refresh_transaction(runtime, state, store, mod.DEFAULT_POLICY, now)
    assert not result['success'] and info is None
    assert runtime.data == runtime.original and state['transaction'] is None
    assert not store.recovery.exists() and not runtime.candidate.exists() and runtime.browser.closed
    if failure == 'admission':
        assert state['counts'] == {'navigation': 0, 'metadata': 0, 'api': 0}
    if failure in ('captcha', 'interrupted'):
        assert mod.failure_plan(state, result['reason'], now, mod.DEFAULT_POLICY)['next_at'] is None


def test_concurrent_rotation_refuses_rollback_and_retains_recovery(tmp_path, monkeypatch):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch, failure='api')
    runtime.concurrent = True
    result, _ = mod.refresh_transaction(runtime, state, store, mod.DEFAULT_POLICY, now)
    assert not result['success'] and result['production_cookie_updated'] is None
    assert b'other-root-writer' in runtime.data
    assert store.recovery.read_bytes() == runtime.original and state['transaction']
    assert mod.plan_next(state, runtime.info(), now, mod.DEFAULT_POLICY)['next_at'] is None


def test_not_due_run_only_rearms_absolute_timer(tmp_path, monkeypatch):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch)
    runtime.data = cookie(now + 10000)
    plans = []
    result = mod.execute('run', state, store, SimpleNamespace(apply=plans.append), runtime,
                         mod.DEFAULT_POLICY, now)
    assert result['last_result']['not_due'] and result['last_result']['skip_reason'] == 'not_due'
    assert result['next_refresh_at'] == now + 8200
    assert runtime.calls == ['info']
    assert len(plans) == 1


def test_schedule_only_never_runs_admission_or_source(tmp_path, monkeypatch):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch)
    result = mod.execute('schedule', state, store, SimpleNamespace(apply=lambda _: None), runtime,
                         mod.DEFAULT_POLICY, now)
    assert result['next_refresh_at'] == now + 2
    assert runtime.calls == ['info']


def test_pause_and_recovery_cannot_read_cookie_or_clear(tmp_path, monkeypatch):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch)
    state['transaction'] = {'phase': 'unknown_recovery'}
    plans = []
    result = mod.execute('run', state, store, SimpleNamespace(apply=plans.append), runtime,
                         mod.DEFAULT_POLICY, now)
    assert result['needs_operator'] and result['next_refresh_at'] is None and runtime.calls == []
    with pytest.raises(mod.SafeError, match='ambiguous_transaction'):
        mod.execute('schedule', state, store, SimpleNamespace(apply=plans.append), runtime,
                    mod.DEFAULT_POLICY, now, clear_pause=True)


def test_daily_cap_stops_timer_without_future_day_rearm(tmp_path, monkeypatch):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch)
    state['counts']['navigation'] = 8
    result = mod.execute('run', state, store, SimpleNamespace(apply=lambda _: None), runtime,
                         mod.DEFAULT_POLICY, now)
    assert result['needs_operator'] and result['next_refresh_at'] is None
    assert runtime.calls == ['info']


def test_clear_pause_retains_daily_budget(tmp_path, monkeypatch):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch)
    state.update(status='needs_operator', failure_retries=1)
    state['counts']['navigation'] = 8
    result = mod.execute('schedule', state, store, SimpleNamespace(apply=lambda _: None), runtime,
                         mod.DEFAULT_POLICY, now, clear_pause=True)
    assert result['needs_operator'] and result['counts']['navigation'] == 8


def test_timer_failure_durably_pauses_and_attempts_stop(tmp_path, monkeypatch):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch)
    plans = []
    def failing(plan):
        plans.append(plan)
        if plan['next_at']:
            raise OSError('synthetic timer failure')
    with pytest.raises(mod.SafeError, match='timer_update_failed'):
        mod.execute('schedule', state, store, SimpleNamespace(apply=failing), runtime,
                    mod.DEFAULT_POLICY, now)
    assert store.read(now)['status'] == 'needs_operator'
    assert plans[-1]['next_at'] is None


@pytest.mark.parametrize('bad', [{'retry_at': 'secret'}, {'counts': {'navigation': -1}},
    {'status': 'garbage'}, {'next_at': True}, {'failure_retries': 2}])
def test_corrupt_state_refused(bad):
    state = mod.new_state(100)
    state.update(bad)
    with pytest.raises(mod.SafeError):
        mod.validate_state(state)


class FakeResponse:
    def __init__(self, data=b'{}'):
        self.data = data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, count=-1):
        return self.data if count < 0 else self.data[:count]


@pytest.mark.parametrize('challenge', [False, True])
def test_normal_browser_owns_one_page_and_blocks_media_only_there(challenge):
    opens, calls = [], []
    page_id = 'synthetic-owned-page'
    class Opener:
        def open(self, request, **kwargs):
            address = request if isinstance(request, str) else request.full_url
            opens.append(address)
            if '/json/new?' in address:
                assert request.method == 'PUT'
                return FakeResponse(json.dumps({'id': page_id,
                    'webSocketDebuggerUrl': 'ws://127.0.0.1:9222/devtools/page/' + page_id}).encode())
            assert address == 'http://127.0.0.1:9222/json/close/' + page_id
            return FakeResponse()
    class Cdp:
        def __init__(self, socket, deadline, observer):
            self.observer = observer
        def call(self, method, **params):
            calls.append((method, params))
            if method == 'Page.navigate':
                assert params == {'url': mod.TARGET}
                for status in (412, 200):
                    self.observer.on_event({'method': 'Network.responseReceived', 'params': {
                        'type': 'Document', 'frameId': 'main', 'response': {'url': mod.TARGET, 'status': status}}})
                return {'frameId': 'main'}
            if method == 'Runtime.evaluate':
                return {'result': {'value': {'href': mod.TARGET, 'bvid': 'BV1JSh265EQm',
                    'aid': 42, 'has_video_title': True, 'challenge': challenge}}}
            if method == 'Network.getCookies':
                assert params['urls'] == [mod.TARGET, 'https://api.bilibili.com/']
                return {'cookies': ['synthetic-cookie-input']}
            return {}
    tool = SimpleNamespace(Cdp=Cdp, _PAGE_EVIDENCE_JS='synthetic_evidence',
        normalize_cookies=lambda data: cookie(2000000000))
    def connect(endpoint, **kwargs):
        assert endpoint == 'ws://127.0.0.1:9222/devtools/page/' + page_id
        assert kwargs['proxy'] is None
        return FakeResponse()
    browser = mod.NormalBrowser(tool, 35, opener_factory=Opener, connect_factory=connect)
    try:
        if challenge:
            with pytest.raises(mod.SafeError, match='verification_requires_user'):
                browser.refresh()
        else:
            assert browser.refresh() == cookie(2000000000)
            assert browser.statuses == [412, 200]
    finally:
        browser.close()
    assert sum(method == 'Page.navigate' for method, _ in calls) == 1
    assert any(method == 'Network.setBlockedURLs' for method, _ in calls)
    assert ('Fetch.enable', {'patterns': [{'resourceType': 'Media', 'requestStage': 'Request'}]}) in calls
    assert all(not method.startswith('Browser.') and method != 'Target.getTargets' for method, _ in calls)
    assert len(opens) == 2 and browser.closed


def test_unknown_recovery_is_retained_and_not_manual_clearable(tmp_path, monkeypatch):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch)
    store.recovery.write_bytes(b'synthetic-recovery')
    state = store.read(now)
    assert state['transaction']['phase'] == 'unknown_recovery'
    with pytest.raises(mod.SafeError, match='ambiguous_transaction'):
        mod.execute('schedule', state, store, SimpleNamespace(apply=lambda _: None), runtime,
                    mod.DEFAULT_POLICY, now, clear_pause=True)
    assert store.recovery.read_bytes() == b'synthetic-recovery'


def test_paused_next_day_does_not_auto_resume():
    state = mod.new_state(100)
    state['status'] = 'needs_operator'
    state['counts']['navigation'] = 8
    assert mod.plan_next(state, mod.parse_cookie(cookie(2000000000)), 100 + 86400,
                         mod.DEFAULT_POLICY)['next_at'] is None


def test_retry_deadline_not_pulled_forward():
    state = mod.new_state(100)
    mod.failure_plan(state, 'insufficient_memory', 100, mod.DEFAULT_POLICY)
    assert mod.plan_next(state, mod.parse_cookie(cookie(500)), 101,
                         mod.DEFAULT_POLICY)['next_at'] == 1000


def test_state_store_contains_no_cookie_values(tmp_path, monkeypatch):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch)
    mod.refresh_transaction(runtime, state, store, mod.DEFAULT_POLICY, now)
    saved = store.path.read_bytes()
    assert b'old-synthetic' not in saved and b'new-synthetic' not in saved
    if mod.os.name == 'posix':
        assert store.path.stat().st_mode & 0o777 == 0o600


def test_cleanup_failure_rolls_back_and_pauses(tmp_path, monkeypatch):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch)
    def fail():
        raise mod.SafeError('cleanup_failed')
    runtime.prune_logs = fail
    result, _ = mod.refresh_transaction(runtime, state, store, mod.DEFAULT_POLICY, now)
    assert not result['success'] and runtime.data == runtime.original
    assert mod.failure_plan(state, result['reason'], now, mod.DEFAULT_POLICY)['next_at'] is None


def test_retention_only_removes_stopped_exact_scheduler_files(tmp_path, monkeypatch):
    if mod.os.name != 'posix':
        pytest.skip('root POSIX retention ownership checks')
    if mod.os.geteuid() != 0:
        pytest.skip('root POSIX retention ownership checks')
    monkeypatch.setattr(mod, 'DEPLOY', tmp_path)
    outputs = []
    for index in range(66):
        path = tmp_path / ('install-video-bili-refresh-scheduler-1800000000-' + format(index, '012x') + '-metadata-output.json')
        path.write_bytes(b'{}')
        path.chmod(0o600)
        outputs.append(path)
    unrelated = tmp_path / 'install-video-bili-refresh-other-output.json'
    unrelated.write_bytes(b'unrelated')
    commands = []
    runtime = mod.Runtime.__new__(mod.Runtime)
    runtime.root = SimpleNamespace(own_unit_state=lambda unit: {'ActiveState': 'inactive', 'cgroup_empty': True},
        command=lambda args, **kwargs: commands.append(args))
    runtime.prune_logs()
    assert sum(path.exists() for path in outputs) == 64
    assert unrelated.read_bytes() == b'unrelated'
    assert len(commands) == 2
    assert all(args[:2] == ['systemctl', 'reset-failed'] and len(args) == 3 for args in commands)


def test_retention_never_deletes_live_or_unsafe_files(tmp_path, monkeypatch):
    if mod.os.name != 'posix' or mod.os.geteuid() != 0:
        pytest.skip('root POSIX retention ownership checks')
    monkeypatch.setattr(mod, 'DEPLOY', tmp_path)
    for index in range(65):
        path = tmp_path / ('install-video-bili-refresh-scheduler-1800000000-' + format(index, '012x') + '-api-output.json')
        path.write_bytes(b'{}')
        path.chmod(0o600)
    runtime = mod.Runtime.__new__(mod.Runtime)
    runtime.root = SimpleNamespace(own_unit_state=lambda unit: {'ActiveState': 'active', 'cgroup_empty': False},
        command=lambda *args, **kwargs: pytest.fail('live reset'))
    with pytest.raises(mod.SafeError, match='cleanup_failed'):
        runtime.prune_logs()
    assert len(list(tmp_path.iterdir())) == 65


def test_admission_has_only_one_finite_retry_then_pause(tmp_path, monkeypatch):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch, failure='admission')
    plans = []
    timer = SimpleNamespace(apply=plans.append)
    first = mod.execute('run', state, store, timer, runtime, mod.DEFAULT_POLICY, now)
    assert first['status'] == 'armed' and first['next_refresh_at'] == now + 900
    assert state['failure_retries'] == 1 and 'navigation' not in runtime.calls
    monkeypatch.setattr(mod.time, 'time', lambda: now + 900)
    second = mod.execute('run', state, store, timer, runtime, mod.DEFAULT_POLICY, now + 900)
    assert second['status'] == 'needs_operator' and second['next_refresh_at'] is None
    assert 'navigation' not in runtime.calls and plans[-1]['next_at'] is None


def test_preexisting_candidate_never_deleted(tmp_path, monkeypatch):
    now, store, runtime, state = transaction_fixture(tmp_path, monkeypatch)
    runtime.candidate.write_bytes(b'other-synthetic-candidate')
    result, _ = mod.refresh_transaction(runtime, state, store, mod.DEFAULT_POLICY, now)
    assert not result['success'] and result['reason'] == 'ambiguous_transaction'
    assert runtime.candidate.read_bytes() == b'other-synthetic-candidate'
    assert 'navigation' not in runtime.calls


class ConfigFS:
    """Descriptor-backed synthetic POSIX tree: no real config/credential reads."""
    O_DIRECTORY = 0x10000
    O_NOFOLLOW = 0x20000
    O_NONBLOCK = 0x40000
    O_RDONLY = 0
    def __init__(self):
        self.nodes, self.handles, self.next_fd, self.on_read = {}, {}, 10, None
        self.link = '/etc/caddy/acli.d'
        self.target = '/var/lib/acli/caddy-manager/generations/generation.1Vsq97'
        self.path = self.link + '/sites/hermes-webui.caddy'
        self.add('/', 'dir')
        for path in ['/etc', '/etc/caddy', '/var', '/var/lib', '/var/lib/acli',
                     '/var/lib/acli/caddy-manager', '/var/lib/acli/caddy-manager/generations',
                     self.target, self.target + '/sites']:
            self.add(path, 'dir')
        self.add(self.link, 'link', target=self.target)
        self.add(self.target + '/sites/hermes-webui.caddy', 'file', data=b'synthetic config')
    def add(self, path, kind, **values):
        node = {'kind': kind, 'uid': 0, 'gid': 0, 'mode': 0o755 if kind == 'dir' else 0o644,
                'inode': len(self.nodes) + 1, 'data': b'', 'stamp': 1}
        node.update(values)
        self.nodes[path] = node
        return node
    def address(self, path, dir_fd=None):
        return posixpath.normpath(path if path.startswith('/') else posixpath.join(self.handles[dir_fd][0], path))
    def info(self, node):
        kind = {'dir': stat.S_IFDIR, 'file': stat.S_IFREG, 'link': stat.S_IFLNK, 'fifo': stat.S_IFIFO}[node['kind']]
        return SimpleNamespace(st_mode=kind | node['mode'], st_uid=node['uid'], st_gid=node['gid'],
            st_dev=1, st_ino=node['inode'], st_nlink=1, st_mtime_ns=node['stamp'],
            st_ctime_ns=node['stamp'], st_size=node.get('size', len(node['data'])))
    def stat(self, path, *, dir_fd=None, follow_symlinks=False):
        return self.info(self.nodes[self.address(path, dir_fd)])
    def open(self, path, flags, *, dir_fd=None):
        path = self.address(path, dir_fd)
        node = self.nodes[path]
        if node['kind'] == 'link':
            raise OSError('synthetic nofollow')
        self.next_fd += 1
        self.handles[self.next_fd] = [path, node, 0]
        return self.next_fd
    def fstat(self, fd):
        return self.info(self.handles[fd][1])
    def readlink(self, path, *, dir_fd=None):
        return self.nodes[self.address(path, dir_fd)]['target']
    def read(self, fd, count):
        handle = self.handles[fd]
        data = handle[1]['data'][handle[2]:handle[2] + count]
        handle[2] += len(data)
        if self.on_read:
            action, self.on_read = self.on_read, None
            action()
        return data
    def close(self, fd):
        del self.handles[fd]


def config_snapshot(fs):
    return mod.protected_config_snapshot(fs.path, approved_paths=[fs.path], filesystem=fs)


def test_approved_caddy_root_symlink_snapshot():
    fs = ConfigFS()
    result = config_snapshot(fs)
    assert result['resolved_path'] == fs.target + '/sites/hermes-webui.caddy'
    assert result['sha256'] == hashlib.sha256(b'synthetic config').hexdigest()
    assert any(item['kind'] == 'symlink' and item['path'] == fs.link for item in result['bindings'])
    assert not fs.handles


@pytest.mark.parametrize('place', ['file', 'directory', 'alias_parent', 'root'])
def test_protected_config_rejects_writable_chain(place):
    fs = ConfigFS()
    path = {'file': fs.target + '/sites/hermes-webui.caddy', 'directory': fs.target,
            'alias_parent': '/etc/caddy', 'root': '/'}[place]
    fs.nodes[path]['mode'] |= 0o020
    with pytest.raises(mod.SafeError):
        config_snapshot(fs)
    assert not fs.handles


@pytest.mark.parametrize('target', ['/tmp/generation.test', '/var/lib/acli/caddy-manager/generations/other',
    '/var/lib/acli/caddy-manager/generations/generation.test/extra',
    '/var/lib/acli/caddy-manager/generations/generation.test/../../outside'])
def test_caddy_link_cannot_escape_approved_generation_boundary(target):
    fs = ConfigFS()
    fs.nodes[fs.link]['target'] = target
    with pytest.raises(mod.SafeError, match='unsafe_path'):
        config_snapshot(fs)
    assert not fs.handles


def test_protected_link_switch_during_read_is_rejected():
    fs = ConfigFS()
    new_target = '/var/lib/acli/caddy-manager/generations/generation.next'
    fs.add(new_target, 'dir')
    fs.add(new_target + '/sites', 'dir')
    fs.add(new_target + '/sites/hermes-webui.caddy', 'file', data=b'synthetic config')
    fs.on_read = lambda: fs.nodes[fs.link].update(target=new_target, stamp=2)
    with pytest.raises(mod.SafeError, match='protected_state_changed'):
        config_snapshot(fs)
    assert not fs.handles


def test_same_content_new_link_identity_changes_snapshot():
    fs = ConfigFS()
    before = config_snapshot(fs)
    fs.nodes[fs.link]['inode'] += 100
    after = config_snapshot(fs)
    assert before['sha256'] == after['sha256'] and before != after


def test_protected_huge_file_is_rejected_before_read():
    fs = ConfigFS()
    fs.nodes[fs.target + '/sites/hermes-webui.caddy']['size'] = 4 * mod.MAX_BYTES + 1
    fs.on_read = lambda: pytest.fail('huge file was read')
    with pytest.raises(mod.SafeError, match='unsafe_file'):
        config_snapshot(fs)
    assert not fs.handles


def test_protected_unknown_alias_and_unapproved_path_rejected():
    fs = ConfigFS()
    fs.add('/var/lib/acli/caddy-manager/other', 'link', target=fs.target)
    fs.nodes[fs.link]['target'] = '/var/lib/acli/caddy-manager/other'
    with pytest.raises(mod.SafeError):
        config_snapshot(fs)
    with pytest.raises(mod.SafeError):
        mod.protected_config_snapshot(fs.path, approved_paths=['/etc/other'], filesystem=fs)
    assert not fs.handles


@pytest.mark.parametrize('data', [b'', b'OTHER_SECRET=synthetic\n', b'BILIBILI_API_ENABLED=0\n',
    b' BILIBILI_API_ENABLED = "FALSE" \n', b"BILIBILI_API_ENABLED='no'\n"])
def test_production_api_flag_false_or_absent(data):
    assert mod.parse_api_enabled(data) is False


@pytest.mark.parametrize('data', [b'BILIBILI_API_ENABLED=1\n', b'BILIBILI_API_ENABLED=true\n',
    b'BILIBILI_API_ENABLED="YES"\n', b"BILIBILI_API_ENABLED='True'\n"])
def test_production_api_flag_true(data):
    assert mod.parse_api_enabled(data) is True


@pytest.mark.parametrize('data', [b'BILIBILI_API_ENABLED=on', b'BILIBILI_API_ENABLED=${SECRET}',
    b'BILIBILI_API_ENABLED=true #comment', b'export BILIBILI_API_ENABLED=true',
    b'BILIBILI_API_ENABLED=true\nBILIBILI_API_ENABLED=false', b'BILIBILI_API_ENABLED=',
    b'BILIBILI_API_ENABLED', b'BILIBILI_API_ENABLED=" true "', b'\xff'])
def test_production_api_flag_ambiguous_syntax_fails_closed(data):
    with pytest.raises(mod.SafeError, match='invalid_api_mode'):
        mod.parse_api_enabled(data)


def test_metadata_worker_gets_only_normalized_production_flag(monkeypatch):
    calls = []
    monkeypatch.setattr(mod, 'private_read', lambda path: b'BILIBILI_API_ENABLED=true\nPRIVATE_KEY=synthetic-secret\n')
    runtime = mod.Runtime.__new__(mod.Runtime)
    runtime.root = SimpleNamespace(PYTHON='/synthetic/python', ENVFILE='/synthetic/demo.env', API_CHECK='synthetic_api',
        run_isolated=lambda unit, command, **options: (calls.append((command, options)) or
            ({'success': True}, {'ExecMainStatus': '0', 'cleanup_cgroup_empty': True})),
        command=lambda *args, **kwargs: None)
    runtime.validate('metadata', '1800000000-000000000000')
    code = calls[0][0][-1]
    assert "os.environ['BILIBILI_API_ENABLED']='true'" in code
    assert 'synthetic-secret' not in code and calls[0][1]['envfile'] is False
    assert code.index("os.environ['BILIBILI_API_ENABLED']") < code.index('spec_from_file_location')


def test_runtime_protected_binds_approved_caddy_alias_without_other_reads(monkeypatch):
    fs = ConfigFS()
    original = mod.protected_config_snapshot
    monkeypatch.setattr(mod, 'protected_config_snapshot',
        lambda path, **kwargs: original(path, filesystem=fs, **kwargs))
    monkeypatch.setattr(mod, 'protected_metadata', lambda path: json.dumps({'config_hashes': {fs.path: 'historical'}}).encode())
    monkeypatch.setattr(mod, 'private_read', lambda path: b'SYNTHETIC_ENV=1\n')
    runtime = mod.Runtime.__new__(mod.Runtime)
    runtime.root = SimpleNamespace(ENVFILE='/synthetic/demo.env', command=lambda *args: SimpleNamespace(
        returncode=0, stdout='MainPID=42\nActiveState=active\nSubState=running'))
    before = runtime.protected()
    assert before['config_bindings'][fs.path]['resolved_path'].startswith(fs.target)
    assert before['config_hashes'][fs.path] != 'historical'
    fs.nodes[fs.link]['stamp'] = 2
    assert before != runtime.protected()


@pytest.mark.parametrize('place', ['symlink', 'file', 'directory'])
def test_protected_config_requires_root_ownership(place):
    fs = ConfigFS()
    target = {'symlink': fs.link, 'file': fs.target + '/sites/hermes-webui.caddy', 'directory': fs.target}[place]
    fs.nodes[target]['uid'] = 1000
    with pytest.raises(mod.SafeError):
        config_snapshot(fs)
    assert not fs.handles


def test_protected_file_growth_and_metadata_change_during_read_rejected():
    fs = ConfigFS()
    node = fs.nodes[fs.target + '/sites/hermes-webui.caddy']
    node['size'] = 1
    node['data'] = b'x' * (4 * mod.MAX_BYTES + 1)
    with pytest.raises(mod.SafeError, match='unsafe_file'):
        config_snapshot(fs)
    assert not fs.handles
    node.update(size=1, data=b'x')
    fs.on_read = lambda: node.update(stamp=2)
    with pytest.raises(mod.SafeError, match='protected_state_changed'):
        config_snapshot(fs)
    assert not fs.handles


def test_new_trusted_generation_between_runs_changes_binding():
    fs = ConfigFS()
    before = config_snapshot(fs)
    target = '/var/lib/acli/caddy-manager/generations/generation.next'
    fs.add(target, 'dir')
    fs.add(target + '/sites', 'dir')
    fs.add(target + '/sites/hermes-webui.caddy', 'file', data=b'synthetic config')
    fs.nodes[fs.link].update(target=target, stamp=2)
    after = config_snapshot(fs)
    assert before != after and before['sha256'] == after['sha256']
    assert after['resolved_path'] == target + '/sites/hermes-webui.caddy'


def test_api_worker_keeps_production_environment_file(monkeypatch):
    calls = []
    monkeypatch.setattr(mod, 'private_read', lambda *args: pytest.fail('API env read outside isolated worker'))
    runtime = mod.Runtime.__new__(mod.Runtime)
    runtime.root = SimpleNamespace(PYTHON='/synthetic/python', API_CHECK='synthetic_api',
        run_isolated=lambda unit, command, **options: (calls.append((command, options)) or
            ({'success': True}, {'ExecMainStatus': '0', 'cleanup_cgroup_empty': True})),
        command=lambda *args, **kwargs: None)
    runtime.validate('api', '1800000000-000000000000')
    assert calls[0][0][-1] == 'synthetic_api' and calls[0][1]['envfile'] is True


def test_native_root_descriptor_checks_in_own_deployment_scratch():
    if mod.os.name != 'posix' or mod.os.geteuid() != 0:
        pytest.skip('root POSIX descriptor test; synthetic tree covers all platforms')
    # Root orchestrator runs this offline test. Only this private scratch tree
    # is created/deleted; no real config, credential, env or DB content is read.
    with tempfile.TemporaryDirectory(prefix='scheduler-config-synthetic-', dir=mod.DEPLOY) as folder:
        base = Path(folder)
        base.chmod(0o700)
        path = base / 'synthetic.caddy'
        path.write_bytes(b'synthetic native config')
        path.chmod(0o600)
        snapshot = mod.protected_config_snapshot(str(path), approved_paths=[str(path)])
        assert snapshot['sha256'] == hashlib.sha256(b'synthetic native config').hexdigest()
        assert snapshot['resolved_path'] == str(path)
        path.chmod(0o620)
        with pytest.raises(mod.SafeError, match='unsafe_file'):
            mod.protected_config_snapshot(str(path), approved_paths=[str(path)])
        path.chmod(0o600)
        with path.open('wb') as handle:
            handle.truncate(4 * mod.MAX_BYTES + 1)
        with pytest.raises(mod.SafeError, match='unsafe_file'):
            mod.protected_config_snapshot(str(path), approved_paths=[str(path)])
        alias = base / 'unapproved-alias'
        alias.symlink_to(path)
        with pytest.raises(mod.SafeError, match='unsafe_path'):
            mod.protected_config_snapshot(str(alias), approved_paths=[str(alias)])


if __name__ == '__main__':
    class _MonkeyPatch:
        def __init__(self):
            self.restore = []
        def setattr(self, target, key, value):
            self.restore.append((target, key, getattr(target, key)))
            setattr(target, key, value)
        def undo(self):
            for target, key, value in reversed(self.restore):
                setattr(target, key, value)
    suite = unittest.TestSuite()
    for name, function in list(globals().items()):
        if name.startswith('test_') and callable(function):
            parameters = getattr(function, 'synthetic_parameters', (None, [None]))
            for value in parameters[1]:
                def run(function=function, key=parameters[0], value=value):
                    patch = _MonkeyPatch()
                    buffer = io.StringIO()
                    try:
                        with tempfile.TemporaryDirectory(prefix='bili-scheduler-synthetic-') as folder:
                            args = {'tmp_path': Path(folder), 'monkeypatch': patch,
                                'capsys': SimpleNamespace(readouterr=lambda: SimpleNamespace(out=buffer.getvalue()))}
                            if key:
                                args[key] = value
                            with contextlib.redirect_stdout(buffer):
                                function(**{p: args[p] for p in inspect.signature(function).parameters})
                    finally:
                        patch.undo()
                suite.addTest(unittest.FunctionTestCase(run, description=name))
    outcome = unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(0 if outcome.wasSuccessful() else 1)
