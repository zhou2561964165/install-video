"""Opt-in Linux namespace checks, never alter the host network namespace.

Run as root inside unshare --net with IV_SOURCE_BROKER_LINUX=1. Reuse an
already existing ivisotest account; no user creation or external requests.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time

import pytest

from app.services import child_isolation, source_broker

ENABLED = (os.name == 'posix' and hasattr(os, 'geteuid') and os.geteuid() == 0
           and os.environ.get('IV_SOURCE_BROKER_LINUX') == '1')
pytestmark = pytest.mark.skipif(not ENABLED, reason='Linux root in isolated network namespace only')


@pytest.fixture
def isolated():
    import pwd
    if os.stat('/proc/self/ns/net').st_ino == os.stat('/proc/1/ns/net').st_ino:
        pytest.fail('refusing to change host nftables')
    subprocess.run(['ip', 'link', 'set', 'lo', 'up'], check=True, capture_output=True)
    subprocess.run(['ip', 'route', 'replace', '192.0.2.0/24', 'dev', 'lo'], check=True, capture_output=True)
    account = pwd.getpwnam('ivisotest')
    name = 'source_broker_test'
    rules = (f'table inet {name} {{\n chain output {{\n type filter hook output priority 0; '
             f'policy accept;\n meta skuid {account.pw_uid} drop\n }}\n}}\n')
    done = subprocess.run(['nft', '-f', '-'], input=rules.encode(), capture_output=True)
    assert done.returncode == 0, done.stderr.decode()
    config = child_isolation.configure(account.pw_name, 'http://127.0.0.1:4750')
    child_isolation.preflight(config)
    try:
        yield config
    finally:
        child_isolation.sweep(config)
        subprocess.run(['nft', 'delete', 'table', 'inet', name], check=True, capture_output=True)


@pytest.fixture
def sandbox():
    directory = Path(tempfile.mkdtemp(prefix='source-broker-test-'))
    directory.chmod(0o755)
    try:
        yield directory
    finally:
        shutil.rmtree(directory)


def fake_child(monkeypatch, sandbox, body):
    path = sandbox / 'fake-source-child'
    path.write_text('#!/usr/bin/python3\n' + body, encoding='utf8')
    path.chmod(0o755)
    monkeypatch.setattr(source_broker.sys, 'executable', str(path))


def test_real_setpriv_receives_cookie_only_on_stdin_and_uses_ram_output(isolated, sandbox, monkeypatch):
    fake_child(monkeypatch, sandbox,
        'import json,os,sys\n'
        'value=json.loads(sys.stdin.buffer.readline())\n'
        'assert value["bili_cookie_snapshot"] == "private-snapshot"\n'
        'assert all("private-snapshot" not in x for x in sys.argv)\n'
        'assert all("private-snapshot" not in x for x in os.environ.values())\n'
        'assert os.readlink("/proc/self/fd/1").startswith("/memfd:")\n'
        'print(json.dumps({"version":1,"ok":True,"meta":{"uid":os.getuid()},"options":[]}))\n')
    meta, options = source_broker.run_source_child(isolated, 'https://example.com', 'private-snapshot')
    assert meta == {'uid': isolated.uid} and options == []
    assert child_isolation.sweep(isolated) == 0


def test_hard_output_limit_kills_unbounded_child(isolated, sandbox, monkeypatch):
    fake_child(monkeypatch, sandbox, 'import os\nwhile True: os.write(1,b"x"*65536)\n')
    with pytest.raises(source_broker.SourceBrokerError):
        source_broker.run_source_child(isolated, 'https://example.com', None)
    assert child_isolation.sweep(isolated) == 0


def test_timeout_kills_group_and_sweeps_escaped_descendant(isolated, sandbox, monkeypatch):
    fake_child(monkeypatch, sandbox,
        'import os,time\n'
        'if os.fork() == 0:\n os.setsid()\n time.sleep(120)\n'
        'time.sleep(120)\n')
    monkeypatch.setattr(source_broker, 'CHILD_SECONDS', 0.3)
    started = time.monotonic()
    with pytest.raises(source_broker.SourceBrokerError):
        source_broker.run_source_child(isolated, 'https://example.com', None)
    assert time.monotonic() - started < 10
    assert child_isolation.sweep(isolated) == 0


def test_unix_peer_credentials_socket_permissions_and_versioned_ready(isolated, sandbox):
    import pwd
    import multiprocessing
    api = pwd.getpwnam('zxk')
    path = sandbox / 'broker.sock'
    def serve():
        service = source_broker.Broker(isolated, api_uid=api.pw_uid, api_gid=api.pw_gid,
            snapshot_reader=lambda url: None,
            child_runner=lambda *args: ({'title': 'offline'}, [{'format_id': 'p360', 'height': 360}]))
        service.serve(path)
    server = multiprocessing.get_context('fork').Process(target=serve)
    server.start()
    try:
        deadline = time.monotonic() + 10
        while not path.exists() and server.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert path.exists() and stat.S_IMODE(path.stat().st_mode) == 0o660
        assert path.stat().st_gid == api.pw_gid
        assert source_broker.ping(path) is False  # root is not the configured API peer
        script = sandbox / 'client.py'
        script.write_text('from app.services import source_broker as b\n'
            'import sys\n'
            'assert b.ping(sys.argv[1])\n'
            'assert b.parse_video(sys.argv[1],"https://example.com")[0] == {"title":"offline"}\n'
            'assert b.verify_format(sys.argv[1],"https://example.com","p360",720) == "p360[height<=720]"\n'
            'print("offline-unix-ok")\n', encoding='utf8')
        done = subprocess.run(['/usr/bin/setpriv', f'--reuid={api.pw_uid}', f'--regid={api.pw_gid}',
            '--clear-groups', '--no-new-privs', '--', sys.executable, '-B', str(script), str(path)],
            capture_output=True, text=True, timeout=20)
        assert done.returncode == 0, done.stderr
        assert done.stdout.strip() == 'offline-unix-ok'
    finally:
        server.terminate()
        server.join(timeout=10)
        assert not server.is_alive()


@pytest.mark.parametrize('kind', ['file', 'symlink', 'foreign_socket'])
def test_broker_refuses_non_socket_and_foreign_owned_path(isolated, sandbox, kind):
    path = sandbox / 'broker.sock'
    holder = None
    if kind == 'file':
        path.write_text('keep')
    elif kind == 'symlink':
        path.symlink_to(sandbox / 'target')
    else:
        holder = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        holder.bind(str(path))
        os.chown(path, isolated.uid, isolated.gid)
    try:
        service = source_broker.Broker(isolated, api_uid=1000, api_gid=1000,
                                      snapshot_reader=lambda url: None)
        with pytest.raises(source_broker.SourceBrokerError):
            service.serve(path)
        assert path.lstat()
    finally:
        if holder is not None:
            holder.close()


def test_broker_death_ends_real_source_child(isolated, sandbox, monkeypatch):
    """Actual source_child main/watchdog; test-only execute blocks without source I/O."""
    import multiprocessing
    # Reuse installed pure Python dependencies, without installing anything into Linux.
    dependency_roots = [entry for entry in sys.path if entry.endswith('/.venv/Lib/site-packages')]
    assert dependency_roots
    marker_dir = sandbox / 'events'
    marker_dir.mkdir(mode=0o777)
    marker_dir.chmod(0o777)
    marker = marker_dir / 'ready'
    fake_child(monkeypatch, sandbox,
        'import os,sys,time\n'
        f'sys.path[:0]={dependency_roots!r}\n'
        'from app import source_child as child\n'
        'def blocked_execute(payload):\n'
        f' open({str(marker)!r},"w").write(str(os.getpid()))\n'
        ' time.sleep(120)\n'
        'child.execute=blocked_execute\n'
        'os._exit(child.main())\n')
    source_broker._prctl(36, 1)
    def run():
        source_broker.run_source_child(isolated, 'https://source.synthetic.invalid/video', None)
    parent = multiprocessing.get_context('fork').Process(target=run)
    parent.start()
    child_pid = None
    try:
        deadline = time.monotonic() + 30
        while not marker.exists() and parent.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        child_pid = int(marker.read_text())
        parent.kill()
        parent.join(timeout=5)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            pid, status = os.waitpid(child_pid, os.WNOHANG)
            if pid:
                assert os.WIFSIGNALED(status) and os.WTERMSIG(status) == signal.SIGKILL
                child_pid = None
                break
            time.sleep(0.02)
        assert child_pid is None
    finally:
        if parent.is_alive():
            parent.kill()
        parent.join(timeout=5)
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
                os.waitpid(child_pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass
