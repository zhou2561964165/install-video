"""Read an operator Netscape jar into memory; child snapshots use only private stdin.

This module deliberately has no yt-dlp dependency. Callers retain cookie domain,
path and secure policy; no caller should construct a global Cookie header.
"""
import io
import os
import re
import stat
import time
from contextlib import contextmanager
from contextvars import ContextVar
from http.cookiejar import CookieJar, DefaultCookiePolicy, MozillaCookieJar
from urllib.parse import urlsplit

import httpx

from ..config import settings

_MAX_BYTES = 1024 * 1024
MAX_SNAPSHOT_BYTES = 16 * 1024
_NO_SNAPSHOT = object()
_snapshot = ContextVar('bilibili_cookie_snapshot', default=_NO_SNAPSHOT)
_FILE_ERROR = 'B站访问凭据不可用，请管理员更新安全的Cookie文件后重试。'
_EXPIRED_ERROR = 'B站访问凭据已过期，请管理员更新Cookie文件后重试。'


class SessionError(RuntimeError):
    """Safe public message: never include a filename, cookie row or parser error."""


def _official_host(host: str) -> bool:
    return any(host == root or host.endswith('.' + root) for root in ('bilibili.com', 'b23.tv'))


def is_bilibili_url(url: str) -> bool:
    try:
        if not isinstance(url, str) or any(ord(c) <= 32 for c in url) or '\\' in url:
            return False
        parsed = urlsplit(url)
        return (parsed.scheme in {'http', 'https'} and parsed.username is None
                and parsed.password is None and parsed.port in {None, 80, 443}
                and _official_host((parsed.hostname or '').lower()))
    except ValueError:
        return False


def apply_session_cookies(request: httpx.Request, cookies) -> None:
    """Reapply the original jar policy to one request, after HTTPX builds it."""
    for name in ("Cookie", "Cookie2", "Authorization", "Proxy-Authorization"):
        request.headers.pop(name, None)
    if is_bilibili_url(str(request.url)):
        # HTTPX build_request copies CookieJar into a default-policy jar. Using
        # the original jar here preserves its strict host-only/domain rules.
        httpx.Cookies(cookies).set_cookie_header(request)


def session_enabled(url: str) -> bool:
    snapshot = _snapshot.get()
    if snapshot is not _NO_SNAPSHOT:
        return is_bilibili_url(url) and snapshot is not None
    return is_bilibili_url(url) and bool(settings.bilibili_cookie_file)


def _validate_metadata(metadata, *, posix: bool, current_uid: int) -> None:
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_BYTES:
        raise SessionError(_FILE_ERROR)
    # 0640 root:video-demo is intentional; group members may read, never write.
    if posix and (metadata.st_uid not in {0, current_uid} or metadata.st_mode & 0o027):
        raise SessionError(_FILE_ERROR)


def _read_file(path: str) -> str:
    try:
        before = os.lstat(path)
        posix = os.name == 'posix'
        current_uid = os.getuid() if posix else 0
        _validate_metadata(before, posix=posix, current_uid=current_uid)
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, 'rb') as handle:
            opened = os.fstat(handle.fileno())
            _validate_metadata(opened, posix=posix, current_uid=current_uid)
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise SessionError(_FILE_ERROR)
            raw = handle.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            raise SessionError(_FILE_ERROR)
        return raw.decode('utf-8-sig')
    except (OSError, UnicodeError, ValueError):
        raise SessionError(_FILE_ERROR) from None


def cookie_jar_for_url(url: str) -> CookieJar:
    snapshot = _snapshot.get()
    if snapshot is not _NO_SNAPSHOT:
        return _jar_from_text(snapshot) if snapshot is not None and is_bilibili_url(url) else CookieJar()
    if not session_enabled(url):
        return CookieJar()
    return _jar_from_text(_read_file(settings.bilibili_cookie_file))


def _jar_from_text(text: str) -> CookieJar:
    policy = DefaultCookiePolicy(strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain)
    result = CookieJar(policy=policy)
    # MozillaCookieJar prints malformed original rows on some parser failures.
    # Validate before using its mature parser, supplying only canonical rows.
    lines = text.splitlines()
    if not lines or not re.match(r'^# (?:Netscape )?HTTP Cookie File', lines[0]):
        raise SessionError(_FILE_ERROR)
    canonical = ['# Netscape HTTP Cookie File']
    now = time.time()
    for line in lines[1:]:
        if not line or (line.startswith('#') and not line.startswith('#HttpOnly_')):
            continue
        fields = line.removeprefix('#HttpOnly_').split('\t')
        if len(fields) != 7:
            raise SessionError(_FILE_ERROR)
        domain, subdomains, path, secure, expires, name, value = fields
        if (subdomains not in {'TRUE', 'FALSE'} or secure not in {'TRUE', 'FALSE'}
                or domain.startswith('.') != (subdomains == 'TRUE')
                or not re.fullmatch(r'\.?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+', domain)
                or not path.startswith('/') or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name)
                or any(ord(c) < 32 or ord(c) == 127 for c in path + value)
                or (expires and not re.fullmatch(r'[0-9]{1,12}', expires))):
            raise SessionError(_FILE_ERROR)
        if not _official_host(domain.lstrip('.').lower()):
            continue
        expiry = int(expires) if expires else 0
        if expiry and expiry <= now:
            if name.lower() == 'x-bili-sec-token':
                raise SessionError(_EXPIRED_ERROR)
            continue
        fields[4] = str(expiry) if expiry else ''
        canonical.append('\t'.join(fields))
    parsed = MozillaCookieJar()
    # Validation above covers the parser's field-count, boolean-domain and expiry
    # failure cases; no redirection of process-global stdout/stderr is needed.
    parsed._really_load(io.StringIO('\n'.join(canonical) + '\n'), '<memory>', True, False)
    for cookie in parsed:
        result.set_cookie(cookie)
    if not list(result):
        raise SessionError(_FILE_ERROR)
    return result


def cookie_snapshot_for_url(url: str) -> str | None:
    """Parent-only safe file reader; a bounded private stdin snapshot, never a filename."""
    if not session_enabled(url):
        return None
    jar = cookie_jar_for_url(url)
    lines = ['# Netscape HTTP Cookie File']
    for cookie in jar:
        lines.append('\t'.join((cookie.domain, 'TRUE' if cookie.domain_initial_dot else 'FALSE',
            cookie.path, 'TRUE' if cookie.secure else 'FALSE', str(cookie.expires or ''),
            cookie.name, cookie.value)))
    text = '\n'.join(lines) + '\n'
    if len(text.encode('utf8')) > MAX_SNAPSHOT_BYTES:
        raise SessionError(_FILE_ERROR)
    return text


@contextmanager
def cookie_snapshot_scope(snapshot: str | None):
    """Child-private scope: None is explicitly anonymous and never opens a cookie file."""
    if snapshot is not None:
        valid = False
        try:
            valid = type(snapshot) is str and len(snapshot.encode('utf8')) <= MAX_SNAPSHOT_BYTES
        except UnicodeError:
            pass
        if not valid:
            raise SessionError(_FILE_ERROR)
        _jar_from_text(snapshot)  # same strict parser as the operator file, with safe errors
    token = _snapshot.set(snapshot)
    try:
        yield
    finally:
        _snapshot.reset(token)
