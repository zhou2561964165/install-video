"""External gate G4: the download child's own evidence that it runs isolated (stdlib only).

The runtime source network opens only inside a child that (1) holds no capability and cannot
gain one (empty inheritable/permitted/effective/ambient sets and NoNewPrivs; the bounding set
needs CAP_SETPCAP to shrink and adds nothing here), (2) has no root uid/gid and no supplementary
groups, and (3) is demonstrably fenced by the host
firewall: a datagram to a documentation address (TEST-NET-1, never routed) is refused locally
with EPERM. The proxy URL is the only network endpoint the child is given (worker-side check
shared here so both sides accept exactly the same form).
"""
import os
import re
import socket

PROXY_ENV = 'SOURCE_EGRESS_PROXY'
_PROXY = re.compile(r'http://127\.0\.0\.1:([1-9][0-9]{0,4})\Z')
_PROBE_TARGET = ('192.0.2.1', 9)  # TEST-NET-1 (RFC 5737), discard port
_CAPS = ('CapInh', 'CapPrm', 'CapEff', 'CapAmb')


def proxy_url_ok(value) -> bool:
    found = _PROXY.fullmatch(value) if type(value) is str else None
    return found is not None and int(found.group(1)) <= 65535


def egress_blocked() -> bool:
    """True only when the host firewall refuses this process's direct datagram (EPERM)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.sendto(b'\0', _PROBE_TARGET)
    except PermissionError:
        return True
    except OSError:
        return False  # unreachable for another reason: not evidence of the fence
    return False


def isolated(status: str, probe) -> bool:
    """`status` is /proc/self/status text; `probe` runs only for an unprivileged process."""
    fields = {}
    for line in status.splitlines():
        name, _, value = line.partition(':')
        fields[name] = value.split()
    try:
        uids = [int(value) for value in fields['Uid']]
        gids = [int(value) for value in fields['Gid']]
        caps = [int(fields[name][0], 16) for name in _CAPS]
        no_new_privs = fields['NoNewPrivs'] == ['1']
        groups = fields['Groups']
    except (KeyError, IndexError, ValueError):
        return False
    if (len(uids) != 4 or len(gids) != 4 or 0 in uids or 0 in gids or groups or any(caps)
            or not no_new_privs):
        return False
    try:
        return probe() is True
    except Exception:
        return False


def isolated_now() -> bool:
    if os.name == 'nt':
        return False
    try:
        with open('/proc/self/status', encoding='ascii', errors='replace') as handle:
            status = handle.read()
    except OSError:
        return False
    return isolated(status, egress_blocked)
