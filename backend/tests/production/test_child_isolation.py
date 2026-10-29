"""External gate G3/G4: download child isolation (worker side) and the child's isolation evidence.

Unit tests run anywhere (stdlib only). The `root_isolation` tests need Linux root with setpriv and
nft and IV_ISOLATION_ROOT=1 (WSL via run_c3_linux.sh): they create a no-login test user and a
temporary nftables table that lets only that user reach one loopback port, like the server's G2.
"""
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid

import pytest

from app.services import child_isolation, egress_evidence, execution_supervisor as supervisor, executors

PROXY = 'http://127.0.0.1:4750'


class Entry:
    def __init__(self, uid, gid):
        self.pw_uid, self.pw_gid = uid, gid


def lookup(uid=994, gid=994):
    def getpwnam(name):
        if name != 'iv-fetch':
            raise KeyError(name)
        return Entry(uid, gid)
    return getpwnam


def configure(user='iv-fetch', proxy=PROXY, **overrides):
    options = dict(getpwnam=lookup(), setpriv_path=__file__, euid=1000, posix=True)
    options.update(overrides)
    return child_isolation.configure(user, proxy, **options)


def refused(code, **kwargs):
    with pytest.raises(child_isolation.IsolationError) as caught:
        configure(**kwargs)
    assert str(caught.value) == code


def test_unconfigured_isolation_is_off():
    assert configure(user='', proxy='') is None


@pytest.mark.parametrize('user,proxy', [('iv-fetch', ''), ('', PROXY)])
def test_half_configured_isolation_is_refused(user, proxy):
    refused('isolation_config_incomplete', user=user, proxy=proxy)


def test_isolation_needs_posix_and_setpriv(tmp_path):
    refused('isolation_unsupported', posix=False)
    refused('isolation_setpriv_missing', setpriv_path=str(tmp_path / 'absent'))


def test_isolation_user_must_exist_and_differ_from_root_and_the_worker():
    refused('isolation_user_missing', user='nobody-here')
    refused('isolation_user_invalid', getpwnam=lookup(uid=0))
    refused('isolation_user_invalid', getpwnam=lookup(uid=1000))  # the worker's own uid


@pytest.mark.parametrize('proxy', [
    'http://localhost:4750', 'https://127.0.0.1:4750', 'http://127.0.0.1:4750/', 'http://127.0.0.1',
    'http://127.0.0.1:0', 'http://127.0.0.1:70000', 'http://u:p@127.0.0.1:4750', 'http://127.0.0.2:4750',
    'http://[::1]:4750', 'http://127.0.0.1:4750 ', 'http://127.0.0.1:04750',
])
def test_only_a_plain_ipv4_loopback_http_proxy_is_accepted(proxy):
    # The G2 firewall admits only 127.0.0.1:<port>/tcp for the download user.
    refused('isolation_proxy_invalid', proxy=proxy)


def test_configured_isolation_drops_every_privilege_before_the_child_starts():
    config = configure()
    assert (config.user, config.uid, config.gid, config.proxy_url) == ('iv-fetch', 994, 994, PROXY)
    assert config.command_prefix() == [
        __file__, '--reuid=994', '--regid=994', '--clear-groups', '--inh-caps=-all',
        '--ambient-caps=-all', '--no-new-privs', '--']
    # No bounding-set drop: that needs CAP_SETPCAP, which the worker does not hold (review C1).
    assert not any(part.startswith('--bounding-set') for part in config.command_prefix())
    assert config.child_env() == {egress_evidence.PROXY_ENV: PROXY}


STATUS = '''Name:\tpython3
Uid:\t994\t994\t994\t994
Gid:\t994\t994\t994\t994
Groups:\t
CapInh:\t0000000000000000
CapPrm:\t0000000000000000
CapEff:\t0000000000000000
CapBnd:\t0000000000000000
CapAmb:\t0000000000000000
NoNewPrivs:\t1
'''


def test_isolation_evidence_needs_no_privilege_and_blocked_direct_egress():
    assert egress_evidence.isolated(STATUS, lambda: True)
    assert not egress_evidence.isolated(STATUS, lambda: False)  # direct egress went out


@pytest.mark.parametrize('old,new', [
    ('Uid:\t994\t994\t994\t994', 'Uid:\t0\t0\t0\t0'),
    ('Uid:\t994\t994\t994\t994', 'Uid:\t994\t0\t994\t994'),
    ('CapEff:\t0000000000000000', 'CapEff:\t0000000000000080'),
    ('CapPrm:\t0000000000000000', 'CapPrm:\t00000000000000c0'),
    ('CapInh:\t0000000000000000', 'CapInh:\t0000000000000020'),
    ('CapAmb:\t0000000000000000', 'CapAmb:\t0000000000000080'),
    ('Gid:\t994\t994\t994\t994', 'Gid:\t994\t0\t994\t994'),
    ('Groups:\t\n', 'Groups:\t994 27\n'),
    ('Groups:\t\n', ''),
    ('NoNewPrivs:\t1', 'NoNewPrivs:\t0'),
    ('NoNewPrivs:\t1\n', ''),
    ('CapAmb:\t0000000000000000\n', ''),
])
def test_any_privilege_or_missing_field_is_not_evidence(old, new):
    called = []
    assert not egress_evidence.isolated(STATUS.replace(old, new), lambda: called.append(1) or True)
    assert not called  # the probe runs only once the process itself is unprivileged


def test_the_bounding_set_alone_does_not_matter():
    # With no_new_privs and empty inheritable/permitted/effective/ambient sets nothing can be regained.
    assert egress_evidence.isolated(STATUS.replace('CapBnd:\t0000000000000000', 'CapBnd:\t000001ffffffffff'),
                                    lambda: True)


def test_a_probe_failure_is_not_evidence():
    def broken():
        raise RuntimeError('probe')
    assert not egress_evidence.isolated(STATUS, broken)


def test_unfiltered_process_is_not_egress_blocked():
    # This test process is not under the G2 firewall: the documentation-address datagram is sendable.
    assert egress_evidence.egress_blocked() is False


@pytest.mark.parametrize('value,ok', [(PROXY, True), (None, False), ('', False), ('http://127.0.0.1:65535', True),
                                      ('http://127.0.0.1:65536', False), ('http://localhost:4750', False)])
def test_proxy_url_check_is_shared_by_worker_and_child(value, ok):
    assert egress_evidence.proxy_url_ok(value) is ok


def test_ytdlp_is_available_only_with_isolation():
    assert not executors.available('ytdlp')
    assert executors.available('ytdlp', isolated=True)
    assert not executors.available('shell', isolated=True)


def test_supervisor_starts_an_isolated_child_through_the_privilege_drop(tmp_path, monkeypatch):
    seen = {}

    class Started:
        pid, returncode = 4242, 0
        stdin = stdout = None

        def __init__(self, argv, **kwargs):
            seen['argv'], seen['env'] = argv, kwargs['env']
            raise RuntimeError('stop before reading')

    monkeypatch.setattr(supervisor.subprocess, 'Popen', Started)
    monkeypatch.setattr(supervisor.child_isolation, 'sweep', lambda config: seen.setdefault('swept', config))
    directory = tmp_path / 'attempt'
    directory.mkdir()
    request = supervisor.ExecutionRequest(job_id=str(uuid.uuid4()), epoch=1, attempt_id=str(uuid.uuid4()),
        url='https://source.synthetic.invalid/v', format_id='synthetic', attempt_dir=str(directory),
        max_bytes=10, deadline_seconds=5.0, executor='ytdlp')
    with pytest.raises(RuntimeError):
        supervisor.start(request, isolation=configure())
    prefix = configure().command_prefix()
    assert seen['swept'] == configure()  # no download-user process may remain before a new child starts
    assert seen['argv'][:len(prefix)] == prefix
    assert seen['argv'][len(prefix):] == [sys.executable, '-m', 'app.worker_child']
    assert seen['env'][egress_evidence.PROXY_ENV] == PROXY
    with pytest.raises(RuntimeError):
        supervisor.start(request)
    assert seen['argv'] == [sys.executable, '-m', 'app.worker_child']
    assert egress_evidence.PROXY_ENV not in seen['env']


@pytest.mark.skipif(os.name == 'nt', reason='POSIX process groups')
def test_an_isolated_child_that_cannot_be_signalled_is_an_isolation_failure(tmp_path, monkeypatch):
    # Without CAP_KILL the worker cannot stop a child running as another user: never ignore that.
    monkeypatch.setenv('DOWNLOAD_WORKER_ALLOW_FAKE', '1')
    directory = tmp_path / 'attempt'
    directory.mkdir()
    request = supervisor.ExecutionRequest(job_id=str(uuid.uuid4()), epoch=1, attempt_id=str(uuid.uuid4()),
        url='https://source.synthetic.invalid/v', format_id='synthetic', attempt_dir=str(directory),
        max_bytes=10, deadline_seconds=5.0, executor='fake:hang')
    run = supervisor.start(request)
    run._isolation = configure()  # an isolated run (the child itself is a plain local one here)

    def denied(pid, sig):
        raise PermissionError(1, 'denied')
    real = os.killpg
    monkeypatch.setattr(supervisor.os, 'killpg', denied)
    try:
        with pytest.raises(child_isolation.IsolationError):
            run.reap()
        with pytest.raises(child_isolation.IsolationError):
            run.terminate(grace=0.2)
    finally:
        monkeypatch.setattr(supervisor.os, 'killpg', real)
        run.terminate(grace=0.2)
        run.reap()


def test_preflight_requires_the_isolated_probe_to_report_evidence():
    config = configure()
    calls = []

    def runner(output, code=0):
        def run(argv, **kwargs):
            calls.append((argv, kwargs['env'], kwargs['cwd']))
            return subprocess.CompletedProcess(argv, code, stdout=output, stderr='')
        return run
    child_isolation.preflight(config, runner=runner('True\n'))
    argv, env, cwd = calls[0]
    assert argv[:len(config.command_prefix())] == config.command_prefix()
    assert env[egress_evidence.PROXY_ENV] == PROXY and 'DB_URL' not in env
    for output, code in [('False\n', 0), ('', 1), ('True\n', 1), ('True\nTrue\n', 0)]:
        with pytest.raises(child_isolation.IsolationError) as caught:
            child_isolation.preflight(config, runner=runner(output, code))
        assert str(caught.value) == 'isolation_preflight_failed'

    def hung(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 1)
    with pytest.raises(child_isolation.IsolationError):
        child_isolation.preflight(config, runner=hung)


linux = pytest.mark.skipif(os.name == 'nt' or not hasattr(os, 'pidfd_open'), reason='Linux pidfd')


@linux
def test_sweep_without_pidfd_support_is_an_isolation_failure(monkeypatch):
    import errno

    def unsupported(pid, flags=0):
        raise OSError(errno.ENOSYS, 'no pidfd')
    monkeypatch.setattr(child_isolation.os, 'pidfd_open', unsupported)
    with pytest.raises(child_isolation.IsolationError):
        child_isolation.sweep(configure())


@pytest.mark.skipif(os.name == 'nt', reason='POSIX process groups')
def test_an_isolated_run_never_signals_a_reaped_leaders_group_again(tmp_path, monkeypatch):
    # With CAP_KILL a recycled pgid could belong to anyone: after the leader is reaped only the
    # uid/cgroup-filtered sweep is used (review I4).
    monkeypatch.setenv('DOWNLOAD_WORKER_ALLOW_FAKE', '1')
    directory = tmp_path / 'attempt'
    directory.mkdir()
    request = supervisor.ExecutionRequest(job_id=str(uuid.uuid4()), epoch=1, attempt_id=str(uuid.uuid4()),
        url='https://source.synthetic.invalid/v', format_id='synthetic', attempt_dir=str(directory),
        max_bytes=100, deadline_seconds=5.0, executor='fake:ok:10')
    run = supervisor.start(request)
    started = time.monotonic()
    while run.result() is None and time.monotonic() - started < 30:
        run.poll()
        time.sleep(0.02)
    run._isolation = configure()
    signalled, swept = [], []
    monkeypatch.setattr(supervisor.os, 'killpg', lambda pid, sig: signalled.append(sig))
    monkeypatch.setattr(supervisor.child_isolation, 'sweep', lambda config: swept.append(config))
    run.reap()
    run.reap()
    assert signalled == [] and swept == [configure(), configure()]


MOUNT = '25 30 0:22 / /proc rw,nosuid,nodev,noexec,relatime shared:12 - proc proc {}\n'
OTHER = '26 30 0:5 / /dev rw,nosuid shared:2 - devtmpfs udev rw,size=1g\n'


@pytest.mark.parametrize('options,visible', [
    ('rw', True), ('rw,hidepid=0', True), ('rw,hidepid=off', True),
    ('rw,hidepid=2', False), ('rw,hidepid=1', False), ('rw,hidepid=invisible', False),
    ('rw,hidepid=noaccess', False), ('rw,hidepid=ptraceable', False), ('rw,subset=pid', True),
])
def test_sweep_needs_a_proc_that_shows_other_users_processes(options, visible):
    # Review M3: with hidepid (or systemd ProtectProc=invisible) the sweep would see no download-user
    # process and silently find nothing.
    assert child_isolation.proc_shows_all(OTHER + MOUNT.format(options)) is visible


def test_without_a_proc_mount_nothing_is_assumed_visible():
    assert child_isolation.proc_shows_all(OTHER) is False


@linux
def test_sweep_refuses_a_hiding_proc(monkeypatch):
    monkeypatch.setattr(child_isolation, 'proc_shows_all', lambda text: False)
    with pytest.raises(child_isolation.IsolationError) as caught:
        child_isolation.sweep(configure())
    assert str(caught.value) == 'isolation_proc_hidden'


@linux
def test_locking_a_directory_that_is_already_gone_is_not_a_failure(tmp_path):
    # Re-review N1: another process may remove the attempt directory first; it is unreachable then.
    child_isolation.lock_attempt_dir(tmp_path / 'gone')


def test_a_killed_process_gets_a_generous_bounded_exit_wait():
    # Re-review N2: a process in uninterruptible I/O (fsync of a large file) may take a while to die.
    assert 30 <= child_isolation._EXIT_WAIT_SECONDS < 60


# --- Linux root: real privilege drop, firewall and sweep -------------------------------------

ROOT = (os.name != 'nt' and os.environ.get('IV_ISOLATION_ROOT') == '1' and hasattr(os, 'geteuid')
        and os.geteuid() == 0 and shutil.which('nft') and shutil.which('setpriv'))
root_isolation = pytest.mark.skipif(not ROOT, reason='needs Linux root with setpriv/nft and IV_ISOLATION_ROOT=1')
TEST_USER = 'ivisotest'
TABLE = 'iv_isolation_test'
BACKEND = Path(supervisor.__file__).resolve().parents[2]


@pytest.fixture
def isolated_user():
    if subprocess.run(['id', '-u', TEST_USER], capture_output=True).returncode != 0:
        subprocess.run(['useradd', '--system', '--no-create-home', '--home-dir', '/nonexistent',
                        '--shell', '/usr/sbin/nologin', TEST_USER], check=True)
    import pwd
    entry = pwd.getpwnam(TEST_USER)
    rules = (f'table inet {TABLE} {{\n chain output {{\n type filter hook output priority filter; policy accept;\n'
             f' meta skuid {entry.pw_uid} ip daddr 127.0.0.1 tcp dport 4750 accept\n'
             f' meta skuid {entry.pw_uid} drop\n }}\n}}\n')
    subprocess.run(['nft', '-f', '-'], input=rules.encode(), check=True)
    config = child_isolation.configure(TEST_USER, PROXY, setpriv_path=shutil.which('setpriv'))
    try:
        yield config
    finally:
        subprocess.run(['nft', 'delete', 'table', 'inet', TABLE], check=False)


def reachable(tmp_path, mode=0o755):
    # pytest recreates --basetemp as 0700: the dropped child must be able to traverse to tmp_path.
    os.chmod(tmp_path.parent, 0o755)
    os.chmod(tmp_path, mode)


def as_child(config, code, **kwargs):
    env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': os.environ.get('PYTHONPATH', ''), **config.child_env()}
    return subprocess.run(config.command_prefix() + [sys.executable, '-c', code], capture_output=True,
                          text=True, env=env, cwd=str(BACKEND), timeout=30, **kwargs)


@root_isolation
def test_isolated_child_has_evidence_only_under_the_firewall(isolated_user):
    probe = 'from app.services import egress_evidence as e; print(e.isolated_now())'
    assert as_child(isolated_user, probe).stdout.strip() == 'True'
    subprocess.run(['nft', 'delete', 'table', 'inet', TABLE], check=True)
    assert as_child(isolated_user, probe).stdout.strip() == 'False'  # unprivileged but not firewalled
    assert egress_evidence.isolated_now() is False  # root itself is never evidence


@root_isolation
def test_isolated_child_cannot_read_the_worker_environment(isolated_user):
    code = f'open("/proc/{os.getpid()}/environ").read()'
    done = as_child(isolated_user, code)
    assert done.returncode != 0 and 'PermissionError' in done.stderr


@root_isolation
def test_shared_then_locked_attempt_directory(isolated_user, tmp_path):
    reachable(tmp_path)
    directory = tmp_path / 'attempt'
    directory.mkdir(mode=0o700)
    child_isolation.share_attempt_dir(directory, isolated_user)
    write = (f'import os; os.umask(0o002); open("{directory}/media.part", "xb").write(b"x"); '
             f'os.mkdir("{directory}/scratch")')
    assert as_child(isolated_user, write).returncode == 0
    part = directory / 'media.part'
    assert part.stat().st_gid == isolated_user.gid and part.stat().st_mode & 0o020
    child_isolation.lock_attempt_dir(directory)
    info = directory.stat()
    assert info.st_gid == os.getgid() and info.st_mode & 0o7777 == 0o750
    done = as_child(isolated_user, f'open("{part}", "ab").write(b"y")')
    assert done.returncode != 0 and 'PermissionError' in done.stderr
    assert part.read_bytes() == b'x'


@root_isolation
def test_sweep_kills_an_isolated_process_that_left_its_group(isolated_user, tmp_path):
    marker = tmp_path / 'escaped.pid'
    reachable(tmp_path, 0o777)
    code = (f'import os, time; os.setsid(); open("{marker}", "w").write(str(os.getpid())); time.sleep(120)')
    escaped = subprocess.Popen(isolated_user.command_prefix() + [sys.executable, '-c', code], cwd=str(BACKEND),
                               env={'PATH': '/usr/bin:/bin'})
    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    pid = int(marker.read_text())
    try:
        assert child_isolation.sweep(isolated_user) >= 1
        escaped.wait(timeout=10)
        assert escaped.returncode == -signal.SIGKILL
    finally:
        if escaped.poll() is None:
            os.kill(pid, signal.SIGKILL)
    assert child_isolation.sweep(isolated_user) == 0


@root_isolation
def test_isolated_fake_download_runs_as_the_download_user(isolated_user, tmp_path, monkeypatch):
    monkeypatch.setenv('DOWNLOAD_WORKER_ALLOW_FAKE', '1')
    reachable(tmp_path)
    directory = tmp_path / 'attempt'
    directory.mkdir(mode=0o700)
    child_isolation.share_attempt_dir(directory, isolated_user)
    request = supervisor.ExecutionRequest(job_id=str(uuid.uuid4()), epoch=1, attempt_id=str(uuid.uuid4()),
        url='https://source.synthetic.invalid/v', format_id='synthetic', attempt_dir=str(directory),
        max_bytes=1000, deadline_seconds=30.0, executor='fake:ok:100')
    run = supervisor.start(request, isolation=isolated_user)
    started = time.monotonic()
    while run.result() is None and time.monotonic() - started < 30:
        run.poll()
        time.sleep(0.05)
    outcome = run.result()
    run.reap()
    assert outcome is not None and outcome.ok
    part = directory / 'media.part'
    assert part.stat().st_uid == isolated_user.uid and part.stat().st_size == 100
    assert part.stat().st_mode & 0o020  # group-writable: the worker can remove what the child left


WORKER_USER = 'ivisoworker'


@pytest.fixture
def worker_like():
    if subprocess.run(['id', '-u', WORKER_USER], capture_output=True).returncode != 0:
        subprocess.run(['useradd', '--system', '--no-create-home', '--home-dir', '/nonexistent',
                        '--shell', '/usr/sbin/nologin', WORKER_USER], check=True)
    import pwd
    return pwd.getpwnam(WORKER_USER)


@root_isolation
def test_a_worker_holding_only_the_units_three_capabilities_starts_an_isolated_child(isolated_user, worker_like):
    # Mirrors the systemd unit (review C1): a non-root parent with ambient SETUID/SETGID/KILL only.
    caps = '+setuid,+setgid,+kill'
    probe = 'from app.services import egress_evidence as e; print(e.isolated_now())'
    inner = (f'import subprocess, sys; done = subprocess.run({isolated_user.command_prefix()!r} + '
             f'[sys.executable, "-c", {probe!r}], capture_output=True, text=True, '
             f'env={{"PATH": "/usr/bin:/bin", "PYTHONPATH": {os.environ.get("PYTHONPATH", "")!r}, '
             f'"SOURCE_EGRESS_PROXY": {PROXY!r}}}); print(done.returncode, done.stdout.strip(), done.stderr.strip()[-200:])')
    done = subprocess.run(['setpriv', f'--reuid={worker_like.pw_uid}', f'--regid={worker_like.pw_gid}',
                           '--clear-groups', f'--inh-caps={caps}', f'--ambient-caps={caps}',
                           f'--bounding-set=-all,{caps}', '--no-new-privs', '--',
                           sys.executable, '-c', inner], capture_output=True, text=True, cwd=str(BACKEND), timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.split()[:2] == ['0', 'True'], done.stdout


@root_isolation
def test_preflight_passes_only_under_the_firewall(isolated_user):
    child_isolation.preflight(isolated_user)
    subprocess.run(['nft', 'delete', 'table', 'inet', TABLE], check=True)
    with pytest.raises(child_isolation.IsolationError):
        child_isolation.preflight(isolated_user)


def _alive_uid(uid):
    found = []
    for entry in os.listdir('/proc'):
        if entry.isdigit():
            try:
                status = open(f'/proc/{entry}/status').read()
            except OSError:
                continue
            fields = dict(line.split(':', 1) for line in status.splitlines() if ':' in line)
            if int(fields['Uid'].split()[0]) == uid and not fields['State'].strip().startswith('Z'):
                found.append(int(entry))
    return found


@root_isolation
def test_sweep_kills_a_forking_escapee_and_waits_for_it(isolated_user, tmp_path):
    reachable(tmp_path, 0o777)
    marker = tmp_path / 'forked'
    code = (f'import os, time\nos.setsid()\nfor i in range(20):\n    if os.fork() == 0:\n        break\n'
            f'open("{marker}", "a").write("x")\ntime.sleep(120)')
    escaped = subprocess.Popen(isolated_user.command_prefix() + [sys.executable, '-c', code], cwd=str(BACKEND),
                               env={'PATH': '/usr/bin:/bin'})
    deadline = time.monotonic() + 15
    while (not marker.exists() or len(marker.read_text()) < 21) and time.monotonic() < deadline:
        time.sleep(0.05)
    try:
        assert child_isolation.sweep(isolated_user) >= 21
        assert _alive_uid(isolated_user.uid) == []  # gone when sweep returns, not merely signalled
    finally:
        for pid in _alive_uid(isolated_user.uid):
            os.kill(pid, signal.SIGKILL)
        escaped.wait(timeout=10)


@root_isolation
def test_sweep_that_cannot_kill_is_an_isolation_failure(isolated_user, tmp_path, monkeypatch):
    escaped = subprocess.Popen(isolated_user.command_prefix() + [sys.executable, '-c', 'import time; time.sleep(60)'],
                               cwd=str(BACKEND), env={'PATH': '/usr/bin:/bin'})
    time.sleep(0.5)
    real = signal.pidfd_send_signal

    def denied(fd, sig, *args):
        if sig == signal.SIGKILL:
            raise PermissionError(1, 'denied')
        return real(fd, sig, *args)
    monkeypatch.setattr(child_isolation.signal, 'pidfd_send_signal', denied)
    try:
        with pytest.raises(child_isolation.IsolationError):
            child_isolation.sweep(isolated_user)
    finally:
        monkeypatch.setattr(child_isolation.signal, 'pidfd_send_signal', real)
        escaped.kill()
        escaped.wait(timeout=10)


def _sleeper(config):
    return subprocess.Popen(config.command_prefix() + [sys.executable, '-c', 'import os, time; os.setsid(); time.sleep(120)'],
                            cwd=str(BACKEND), env={'PATH': '/usr/bin:/bin'})


@root_isolation
def test_sweep_repeats_until_a_round_finds_nothing(isolated_user, monkeypatch):
    # A process born after a round has listed /proc (an escapee's late fork) must not survive.
    first, late = _sleeper(isolated_user), []
    time.sleep(0.5)
    real = child_isolation._sweep_round

    def round_then_fork(config, own):
        handles = real(config, own)
        if not late:
            late.append(_sleeper(isolated_user))
            time.sleep(0.5)
        return handles
    monkeypatch.setattr(child_isolation, '_sweep_round', round_then_fork)
    try:
        assert child_isolation.sweep(isolated_user) == 2
        assert _alive_uid(isolated_user.uid) == []
    finally:
        for process in [first] + late:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)


@root_isolation
def test_sweep_that_cannot_outwait_a_killed_process_is_an_isolation_failure(isolated_user, monkeypatch):
    sleeper = _sleeper(isolated_user)
    time.sleep(0.5)
    monkeypatch.setattr(child_isolation.select, 'select', lambda *args: ([], [], []))  # exit never observed
    try:
        with pytest.raises(child_isolation.IsolationError):
            child_isolation.sweep(isolated_user)
    finally:
        if sleeper.poll() is None:
            sleeper.kill()
        sleeper.wait(timeout=10)
