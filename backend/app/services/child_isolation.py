"""External gate G3/G4 (worker side): run the download child as the firewalled download user.

Configured by DOWNLOAD_CHILD_USER + SOURCE_EGRESS_PROXY (both or neither; unset keeps the 'ytdlp'
executor unavailable). The child starts through setpriv as that user with no groups, no
capabilities in any set and no_new_privs, so it cannot read the worker's environment or files
and the G2 firewall (by uid) leaves it only the controlled proxy. The worker needs
CAP_SETUID/CAP_SETGID (to start it) and CAP_KILL (to stop it) and is a member of the user's group.

Attempt directories are shared with the child while it runs (group + setgid, 2770) and locked
(worker group, 0750) after it has been reaped and swept, before sealing: from then on the
download user cannot reach the files by path. `sweep` kills any download-user process left in
this worker's cgroup (e.g. one that left the child's process group with setsid).
"""
from __future__ import annotations

from dataclasses import dataclass
import errno
import os
from pathlib import Path
import select
import signal
import subprocess
import sys

from .egress_evidence import PROXY_ENV, proxy_url_ok

SETPRIV = '/usr/bin/setpriv'
_SWEEP_ROUNDS = 20
_EXIT_WAIT_SECONDS = 30.0  # a killed process in uninterruptible I/O may take a while; below TimeoutStopSec
_PREFLIGHT_SECONDS = 30
_BACKEND = Path(__file__).resolve().parents[2]
_PROBE = 'from app.services import egress_evidence as e; print(e.isolated_now())'


class IsolationError(Exception):
    """A fixed code; the worker refuses to run (exit 2) rather than fall back to an unisolated child."""


@dataclass(frozen=True)
class IsolationConfig:
    user: str
    uid: int
    gid: int
    proxy_url: str
    setpriv: str = SETPRIV

    def command_prefix(self) -> list[str]:
        # No --bounding-set: dropping it needs CAP_SETPCAP, which the worker deliberately lacks.
        return [self.setpriv, f'--reuid={self.uid}', f'--regid={self.gid}', '--clear-groups',
                '--inh-caps=-all', '--ambient-caps=-all', '--no-new-privs', '--']

    def child_env(self) -> dict[str, str]:
        return {PROXY_ENV: self.proxy_url}


def configure(user: str, proxy: str, *, getpwnam=None, setpriv_path: str = SETPRIV, euid: int | None = None,
              posix: bool | None = None) -> IsolationConfig | None:
    if not user and not proxy:
        return None
    if not user or not proxy:
        raise IsolationError('isolation_config_incomplete')
    if not (os.name != 'nt' if posix is None else posix):
        raise IsolationError('isolation_unsupported')
    if not os.path.isfile(setpriv_path):
        raise IsolationError('isolation_setpriv_missing')
    if getpwnam is None:
        import pwd
        getpwnam = pwd.getpwnam
    try:
        entry = getpwnam(user)
    except KeyError:
        raise IsolationError('isolation_user_missing') from None
    if euid is None:
        euid = os.geteuid()
    if entry.pw_uid == 0 or entry.pw_gid == 0 or entry.pw_uid == euid:
        raise IsolationError('isolation_user_invalid')
    if not proxy_url_ok(proxy):
        raise IsolationError('isolation_proxy_invalid')
    return IsolationConfig(user, entry.pw_uid, entry.pw_gid, proxy, setpriv_path)


def from_settings(settings) -> IsolationConfig | None:
    return configure(settings.download_child_user, settings.source_egress_proxy)


def preflight(config: IsolationConfig, *, runner=subprocess.run) -> None:
    """Before leasing anything: one isolated probe child must report its own evidence (True)."""
    env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(_BACKEND), 'PYTHONDONTWRITEBYTECODE': '1',
           **config.child_env()}
    try:
        done = runner(config.command_prefix() + [sys.executable, '-c', _PROBE], capture_output=True, text=True,
                      env=env, cwd=str(_BACKEND), timeout=_PREFLIGHT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        raise IsolationError('isolation_preflight_failed') from None
    if done.returncode != 0 or done.stdout != 'True\n':
        raise IsolationError('isolation_preflight_failed')


def share_attempt_dir(path, config: IsolationConfig) -> None:
    try:
        os.chown(path, -1, config.gid)
        os.chmod(path, 0o2770)
    except OSError:
        raise IsolationError('isolation_share_failed') from None


def lock_attempt_dir(path) -> None:
    try:
        os.chown(path, -1, os.getgid())
        os.chmod(path, 0o750)
    except FileNotFoundError:
        pass  # removed meanwhile (cleaner/orphan round): nothing is left for the download user to reach
    except OSError:
        raise IsolationError('isolation_lock_failed') from None


def _read(path: str) -> str:
    with open(path, encoding='ascii', errors='replace') as handle:
        return handle.read()


def proc_shows_all(mountinfo: str) -> bool:
    """Whether the /proc mount lists every user's processes (no hidepid / ProtectProc=invisible)."""
    for line in mountinfo.splitlines():
        mount, _, rest = line.partition(' - ')
        fields, tail = mount.split(), rest.split()
        if len(fields) < 5 or fields[4] != '/proc' or len(tail) < 3 or tail[0] != 'proc':
            continue
        for option in tail[2].split(','):
            name, _, value = option.partition('=')
            if name == 'hidepid' and value not in ('0', 'off'):
                return False
        return True
    return False


def _live_uid(pid: int) -> int | None:
    """Real uid of a live (non-zombie) process; None for a zombie (it can no longer act)."""
    uid, state = None, ''
    for line in _read(f'/proc/{pid}/status').splitlines():
        if line.startswith('Uid:'):
            uid = int(line.split()[1])
        elif line.startswith('State:'):
            state = line.split()[1]
    return None if state == 'Z' else uid


def _sweep_round(config: IsolationConfig, own: str) -> list[int]:
    handles = []
    for entry in os.listdir('/proc'):
        if not entry.isdigit() or int(entry) == os.getpid():
            continue
        pid = int(entry)
        try:
            handle = os.pidfd_open(pid)
        except ProcessLookupError:
            continue  # exited meanwhile
        except OSError as error:
            if error.errno == errno.ESRCH:
                continue
            raise IsolationError('isolation_sweep_failed') from None  # e.g. no pidfd support (ENOSYS)
        keep = False
        try:
            try:
                if _live_uid(pid) != config.uid or _read(f'/proc/{pid}/cgroup') != own:
                    continue
                signal.pidfd_send_signal(handle, 0)  # still the process we inspected
            except (FileNotFoundError, ProcessLookupError):
                continue  # gone: nothing to stop
            except OSError:
                continue  # unreadable status of a process that is not ours
            try:
                signal.pidfd_send_signal(handle, signal.SIGKILL)
            except ProcessLookupError:
                continue
            except OSError:
                raise IsolationError('isolation_kill_denied') from None
            keep = True
            handles.append(handle)
        finally:
            if not keep:
                os.close(handle)
    return handles


def sweep(config: IsolationConfig) -> int:
    """SIGKILL every live process of the download user in this worker's cgroup and wait for each.

    Each candidate is held by a pidfd while it is checked; the check counts only if the process
    is still alive afterwards (a recycled pid is never signalled). Rounds repeat until one finds
    nothing (a forking escapee cannot outrun it), and the function returns only once every killed
    process has exited, so no stray writer survives into seal. Anything it cannot see through,
    signal or outwait is an IsolationError. Returns how many processes were killed.
    """
    if os.name == 'nt':
        return 0
    if not proc_shows_all(_read('/proc/self/mountinfo')):
        raise IsolationError('isolation_proc_hidden')  # the download user's processes would be invisible
    own = _read('/proc/self/cgroup')
    killed = 0
    for _ in range(_SWEEP_ROUNDS):
        handles = _sweep_round(config, own)
        if not handles:
            return killed
        killed += len(handles)
        try:
            for handle in handles:
                # A pidfd becomes readable when its process exits.
                if not select.select([handle], [], [], _EXIT_WAIT_SECONDS)[0]:
                    raise IsolationError('isolation_sweep_failed')
        finally:
            for handle in handles:
                os.close(handle)
    raise IsolationError('isolation_sweep_failed')
