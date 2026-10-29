"""C3 Task 2: real child processes, temporary attempt dirs, no DB. Run via run_c3_offline.py."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

import pytest

from app.services import execution_supervisor as supervisor


def request(tmp_path, executor, *, max_bytes=1_000_000, deadline=30.0):
    directory = tmp_path / 'attempt'
    directory.mkdir(exist_ok=True)
    return supervisor.ExecutionRequest(job_id=str(uuid.uuid4()), epoch=1, attempt_id=str(uuid.uuid4()),
        url='https://source.synthetic.invalid/v', format_id='synthetic', attempt_dir=str(directory),
        max_bytes=max_bytes, deadline_seconds=deadline, executor=executor)


def run_to_end(run, timeout=30.0):
    events, started = [], time.monotonic()
    while run.result() is None:
        events.extend(run.poll())
        if time.monotonic() - started > timeout:
            run.terminate(grace=2.0)
            pytest.fail('child did not finish')
        time.sleep(0.05)
    events.extend(run.poll())
    return events, run.result()


def alive(pid):
    if os.name == 'nt':
        # Bytes: tasklist prints its "no task" notice in the console code page (e.g. GBK), not UTF-8.
        output = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'], capture_output=True).stdout
        return re.search(rb'\s%d\s' % pid, output) is not None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # a zombie (killed, not yet reaped by a non-reaping parent/subreaper) still answers kill(pid, 0)
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z'
    except (OSError, IndexError):
        return True


def wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_successful_child_writes_part_and_reports(tmp_path):
    req = request(tmp_path, 'fake:ok:300000')
    events, outcome = run_to_end(supervisor.start(req))
    assert outcome.ok and outcome.ext == 'mp4' and outcome.media_check == 'verified' and outcome.code is None
    part = Path(req.attempt_dir) / 'media.part'
    assert part.stat().st_size == 300000
    progress = [event.bytes for event in events if event.kind == 'progress']
    assert progress and progress == sorted(progress) and progress[-1] == 300000


def test_child_exits_cleanly_after_done_while_its_stop_channel_is_open(tmp_path):
    # G5 finding: the supervisor keeps the child's stdin open (stop channel). On CPython 3.12 the
    # interpreter shutdown then aborted on the blocked stdin reader thread (_enter_buffered_busy,
    # SIGABRT) after 'done', turning a finished download into a protocol error.
    directory = tmp_path / 'attempt'
    directory.mkdir()
    request = dict(job_id=str(uuid.uuid4()), epoch=1, attempt_id=str(uuid.uuid4()),
                   url='https://source.synthetic.invalid/v', format_id='synthetic', attempt_dir=str(directory),
                   max_bytes=1000, deadline_seconds=30.0, executor='fake:ok:10')
    env = dict(os.environ, DOWNLOAD_WORKER_ALLOW_FAKE='1', PYTHONPATH=str(Path(supervisor.__file__).resolve().parents[2]))
    child = subprocess.Popen([sys.executable, '-m', 'app.worker_child'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=env, cwd=env['PYTHONPATH'])
    try:
        child.stdin.write(json.dumps(request).encode() + b'\n')
        child.stdin.flush()
        lines = []
        for line in child.stdout:
            lines.append(json.loads(line))
            if lines[-1]['type'] == 'done':
                break
        child.wait(timeout=10)  # stdin still open: the child must leave on its own
        assert lines[-1] == {'type': 'done', 'ext': 'mp4', 'media_check': 'verified'}
        assert child.returncode == 0 and child.stderr.read() == b''
    finally:
        if child.poll() is None:
            child.kill()
        child.stdin.close()
        child.wait(timeout=10)


def test_child_error_code_passed_through(tmp_path):
    events, outcome = run_to_end(supervisor.start(request(tmp_path, 'fake:error:http_412')))
    assert not outcome.ok and outcome.code == 'http_412'


def test_child_over_byte_limit_reports_file_too_large(tmp_path):
    req = request(tmp_path, 'fake:ok:5000', max_bytes=4096)
    events, outcome = run_to_end(supervisor.start(req))
    assert not outcome.ok and outcome.code == 'file_too_large'
    assert (Path(req.attempt_dir) / 'media.part').stat().st_size <= 4096


def test_crash_without_outcome_is_execution_crashed(tmp_path):
    events, outcome = run_to_end(supervisor.start(request(tmp_path, 'fake:crash')))
    assert not outcome.ok and outcome.code == 'execution_crashed'


@pytest.mark.parametrize('scenario', ['garbage', 'longline', 'flood', 'forged'])
def test_malformed_child_output_rejected(tmp_path, scenario):
    events, outcome = run_to_end(supervisor.start(request(tmp_path, f'fake:{scenario}')))
    assert not outcome.ok and outcome.code == 'execution_protocol_error'


@pytest.mark.skipif(importlib.util.find_spec('yt_dlp') is None,
                    reason='stdlib-only staging: the source stack is not installed (production installs it)')
def test_ytdlp_executor_is_unavailable_while_the_runtime_factory_is_closed(tmp_path):
    # B5 U5b: wired to download_attempt; without an explicit network the closed factory refuses
    # (with the source stack installed this is the factory path, not an import fallback).
    events, outcome = run_to_end(supervisor.start(request(tmp_path, 'ytdlp')))
    assert not outcome.ok and outcome.code == 'source_unavailable'


def test_unknown_executor_refused_before_spawn(tmp_path):
    with pytest.raises(ValueError):
        supervisor.start(request(tmp_path, 'shell'))


def test_fake_executor_requires_explicit_test_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv('DOWNLOAD_WORKER_ALLOW_FAKE', raising=False)
    with pytest.raises(ValueError):
        supervisor.start(request(tmp_path, 'fake:ok:10'))


def test_hung_child_tree_force_killed(tmp_path):
    req = request(tmp_path, 'fake:hang_tree')
    run = supervisor.start(req)
    marker = Path(req.attempt_dir) / 'grandchild.pid'
    started = time.monotonic()
    while not marker.exists() and time.monotonic() - started < 20:
        run.poll()
        time.sleep(0.05)
    grandchild = int(marker.read_text())
    assert alive(grandchild) and alive(run.pid)
    forced = run.terminate(grace=1.0)
    assert forced is True  # the child ignores the polite signal
    assert wait_for(lambda: not alive(run.pid) and not alive(grandchild))
    assert run.result() is not None and not run.result().ok


def test_polite_terminate_without_force(tmp_path):
    run = supervisor.start(request(tmp_path, 'fake:hang'))
    time.sleep(1.0)
    assert run.terminate(grace=10.0) is False
    assert not alive(run.pid)


def test_child_environment_has_no_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_URL', 'postgresql+psycopg://user:synthetic-secret@127.0.0.1/db')
    monkeypatch.setenv('STRIPE_SECRET_KEY', 'synthetic-secret')
    req = request(tmp_path, 'fake:env')
    events, outcome = run_to_end(supervisor.start(req))
    assert outcome.ok
    seen = json.loads((Path(req.attempt_dir) / 'env.json').read_text('utf8'))
    assert 'DB_URL' not in seen and 'STRIPE_SECRET_KEY' not in seen
    assert 'synthetic-secret' not in json.dumps(seen)
    assert seen.get('YTDLP_NO_PLUGINS') == '1'  # B5 U5b: plugin opt-out before any yt-dlp import


# C2 fix re-review M6: a child that exits successfully may leave group members (e.g. a merger)
# still writing; the worker reaps the whole group before sealing.
@pytest.mark.skipif(os.name == 'nt', reason='POSIX process groups; Windows needs Job Objects (ruling C3-4)')
def test_reap_kills_leftover_group_after_successful_exit(tmp_path):
    req = request(tmp_path, 'fake:ok_orphan:1000')
    run = supervisor.start(req)
    events, outcome = run_to_end(run)
    assert outcome.ok
    orphan = int((Path(req.attempt_dir) / 'grandchild.pid').read_text())
    assert alive(orphan)
    run.reap()
    assert wait_for(lambda: not alive(orphan))


def test_reap_after_clean_exit_is_harmless(tmp_path):
    run = supervisor.start(request(tmp_path, 'fake:ok:10'))
    events, outcome = run_to_end(run)
    assert outcome.ok
    run.reap()
    run.reap()  # idempotent
    assert run.result().ok


# C3 review I1: the protocol limits hold even when the parent is not polling, and nothing may follow
# a terminal message (no unbounded memory, no worker idling until its window expires).
def test_output_after_terminal_message_is_protocol_error(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, 'TERMINAL_EXIT_GRACE_SECONDS', 600.0)  # isolate the post-terminal check
    run = supervisor.start(request(tmp_path, 'fake:done_then_flood'))
    events, outcome = run_to_end(run, timeout=20)
    assert not outcome.ok and outcome.code == 'execution_protocol_error'
    assert wait_for(lambda: not alive(run.pid))


def test_unpolled_flood_is_rejected_without_polling(tmp_path):
    run = supervisor.start(request(tmp_path, 'fake:flood'))
    time.sleep(2.0)  # the parent is busy elsewhere (e.g. a slow heartbeat) and does not poll
    outcome = run.result()
    assert outcome is not None and outcome.code == 'execution_protocol_error'
    assert wait_for(lambda: not alive(run.pid))


def test_terminal_message_without_exit_is_protocol_error(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, 'TERMINAL_EXIT_GRACE_SECONDS', 0.5)
    run = supervisor.start(request(tmp_path, 'fake:done_then_hang'))
    events, outcome = run_to_end(run, timeout=20)
    assert not outcome.ok and outcome.code == 'execution_protocol_error'
    assert wait_for(lambda: not alive(run.pid))


# C3 review I2: when the worker dies, the child's stdin closes; the child then ends its whole group
# (e.g. B5's ffmpeg), not just itself.
@pytest.mark.skipif(os.name == 'nt', reason='POSIX process groups; Windows needs Job Objects (ruling C3-4)')
def test_parent_death_ends_child_group(tmp_path):
    req = request(tmp_path, 'fake:hang_tree_obedient')
    run = supervisor.start(req)
    marker = Path(req.attempt_dir) / 'grandchild.pid'
    assert wait_for(lambda: marker.exists() and marker.read_text().strip() != '', 20)
    grandchild = int(marker.read_text())
    assert alive(grandchild)
    run._process.stdin.close()  # exactly what the OS does to the pipe when the worker process dies
    assert wait_for(lambda: not alive(grandchild) and run._process.poll() is not None, 15)


def test_endless_unpolled_output_stays_bounded(tmp_path):
    # C3 review I1: memory stays bounded however long the child floods and the parent does not poll.
    run = supervisor.start(request(tmp_path, 'fake:flood_forever'))
    time.sleep(3.0)
    assert run._lines.qsize() <= supervisor._MAX_LINES + 1  # white-box: the buffer itself is bounded
    outcome = run.result()
    assert outcome is not None and outcome.code == 'execution_protocol_error'
    assert wait_for(lambda: not alive(run.pid))
