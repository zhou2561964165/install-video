"""Synchronous, bounded source HTTP through an operator configured proxy.

This module does not perform DNS pinning: the reviewed Smokescreen deployment
must do that and the environment must prohibit direct egress. A readiness flag
records operator acknowledgement, not proof of either environmental property.
No existing business caller is switched by importing this module.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
import json
import math
import re
from urllib.parse import urlsplit, urlunsplit
import zlib

import httpx

from .outbound_budget import BudgetReason, OutboundBudget, OutboundBudgetError, OutboundBudgetGroup, RequestLimits
from .outbound_policy import (
    DEFAULT_POLICY, OutboundError, OutboundPolicy, OutboundPolicyError,
    OutboundPurpose, OutboundUnavailableError, PolicyReason,
    validate_redirect, validate_url,
)


_READ_SIZE = 64 * 1024
_HEADER_KEY = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
_HEADERS = frozenset({
    'accept', 'accept-language', 'user-agent', 'referer', 'range', 'if-range',
    'if-none-match', 'if-modified-since',
})
_CREDENTIALS = frozenset({'cookie', 'authorization'})
_REDIRECTS = frozenset({301, 302, 303, 307, 308})
_ENTITY_HEADERS = frozenset({'content-type'})
_API_HEADER_LIMITS = {
    'origin': 2048,
    'x-youtube-client-name': 64,
    'x-youtube-client-version': 128,
    'x-goog-visitor-id': 2048,
}


class ControlledHttpError(Exception):
    """Safe terminal HTTP adapter errors, alongside core OutboundError.

    Consumers must handle both bases before any legacy catch-all fallback.
    This layer never retries; source_status can guide a later platform-specific
    verification/rate-limit classification without exposing the upstream URL.
    """

    retryable = False

    def public_detail(self):
        return {'error_type': self.code, 'error': self.message}


class ControlledHttpStatusError(ControlledHttpError):
    """Upstream failure: HTTP 502 outward; original status is separate data."""

    code = 'source_http_error'
    message = '来源返回失败状态'
    status_code = 502

    def __init__(self, source_status):
        if type(source_status) is not int or not 400 <= source_status <= 999:
            raise ValueError('Invalid source HTTP status') from None
        self.source_status = source_status
        super().__init__(self.message)

    def public_detail(self):
        return super().public_detail() | {'source_status': self.source_status}


class ControlledHttpBusyError(ControlledHttpError):
    """Bounded pool wait failed; admission/Retry-After belongs to its caller."""

    code = 'source_busy'
    message = '来源处理繁忙'
    status_code = 503

    def __init__(self):
        super().__init__(self.message)


def _blocked():
    return OutboundPolicyError(PolicyReason.URL_SYNTAX)


def _safe_call(action, *, deadline=None):
    """Translate at the boundary, then raise outside the original except suite.

    `raise ... from None` alone hides display but retains __context__ containing
    a signed URL. Never return the raw exception or attach it to our errors.
    """
    failure = None
    try:
        result = action()
    except OutboundError as exc:
        failure = exc
    except httpx.PoolTimeout:
        failure = ControlledHttpBusyError()
    except httpx.TimeoutException:
        failure = OutboundBudgetError(BudgetReason.DEADLINE)
    except (httpx.HTTPError, httpx.StreamError, httpx.InvalidURL, zlib.error, ValueError, UnicodeError):
        failure = OutboundUnavailableError()
    # Both successful processing and failed I/O/decoding can cross the phase.
    # Check outside the original exception suite, before returning output, to
    # poison an expired phase without retaining raw exception context.
    if deadline is not None:
        deadline.remaining_seconds()
    if failure is not None:
        raise failure from None
    return result


def _close_quietly(close):
    # Closing never enables retries; preserve a terminal policy/budget error.
    try:
        close()
    except Exception:
        pass


def _headers(values, *, operator=False, extra=frozenset()):
    if values is None:
        return {}
    if not isinstance(values, dict) or len(values) > 32:
        raise _blocked() from None
    result = {}
    total = 0
    for key, value in values.items():
        if (not isinstance(key, str) or not _HEADER_KEY.fullmatch(key)
                or not isinstance(value, str)
                or any(ord(char) < 32 or ord(char) >= 127 for char in value)):
            raise _blocked() from None
        key = key.lower()
        if key not in _HEADERS | extra | (_CREDENTIALS if operator else frozenset()) or key in result:
            raise _blocked() from None
        total += len(key) + len(value)
        if total > 16 * 1024:
            raise _blocked() from None
        if key == 'referer':
            target = validate_url(value, OutboundPurpose.SOURCE, initial=False)
            parts = urlsplit(target.url)
            value = urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
        result[key] = value
    return result


@dataclass(frozen=True)
class ProxyChannel:
    """Operator-only fixed HTTP(S) proxy and deployment acknowledgement.

    Credentials may exist only in this fixed proxy URL; they are passed to
    HTTPX's proxy configuration, never included in source request headers.
    """

    proxy_url: str | None = field(repr=False)
    readiness_confirmed: bool = False


@dataclass(frozen=True)
class HttpxBounds:
    """Operator bounds, independently tightened by each shared budget."""

    io_timeout: float = 10.0
    max_connections: int = 4
    max_keepalive_connections: int = 2
    keepalive_expiry: float = 5.0

    def __post_init__(self):
        if (any(isinstance(value, bool) or not isinstance(value, (float, int))
                or not math.isfinite(value) or value <= 0
                for value in (self.io_timeout, self.keepalive_expiry))
                or type(self.max_connections) is not int or self.max_connections < 1
                or type(self.max_keepalive_connections) is not int
                or not 0 <= self.max_keepalive_connections <= self.max_connections):
            raise ValueError('Invalid controlled HTTP bounds') from None


def _proxy_url(channel):
    valid = False
    if isinstance(channel, ProxyChannel) and channel.readiness_confirmed is True:
        value = channel.proxy_url
        if isinstance(value, str) and not any(ord(c) < 33 or ord(c) >= 127 or c == '\\' for c in value):
            try:
                parts = urlsplit(value)
                valid = (parts.scheme in ('http', 'https') and bool(parts.hostname)
                         and parts.port is not None and parts.path in ('', '/')
                         and not parts.query and not parts.fragment)
            except ValueError:
                pass
    if not valid:
        raise OutboundUnavailableError() from None
    return value


class ControlledResponse:
    """Narrow response. No public raw HTTPX request, client or send method.

    get/head return a buffered, closed response; stream yields an open response
    that must remain inside its context. iter_bytes yields decoded chunks and
    is single use; read/content buffer only within the shared decoded budget.
    headers preserve wire semantics (Content-Length/Encoding describe raw
    bytes); text uses UTF-8 replacement. Status codes are returned unchanged.
    effective_url is internal, possibly signed metadata, never public detail.
    header_items preserves duplicate values using HTTPX's parsed text encoding
    and normalized names. A bridge exposing decoded bodies must remove wire
    Content-Encoding/old Content-Length itself to prevent double decoding;
    identity Range responses retain their wire headers. This metadata copy
    does not add a header/informational-response resource bound.
    raise_for_status raises ControlledHttpStatusError for status >= 400;
    callers should classify source_status (e.g. 412/429) before generic errors.
    """

    def __init__(self, raw, allowance, budget, *, effective_url, head=False, on_close=None):
        self.status_code = raw.status_code
        self.headers = httpx.Headers(raw.headers)
        self._header_items = tuple(self.headers.multi_items())
        self._effective_url = effective_url
        self._raw = raw
        self._allowance = allowance
        self._budget = budget
        self._head = head
        self._closed = self._used = False
        self._content = None
        self._on_close = on_close

    @property
    def effective_url(self) -> str:
        """Validated final target for internal relative-URL resolution only."""
        return self._effective_url

    def header_items(self) -> tuple[tuple[str, str], ...]:
        """Immutable metadata snapshot; duplicate fields are not comma joined."""
        return self._header_items

    def check_deadline(self) -> None:
        """Check the original phase, including after EOF or explicit close."""
        try:
            self._budget.remaining_seconds()
        except (OutboundError, ValueError) as error:
            # An active caller exception may contain a signed URL. Bare
            # rethrow preserves the approved scope error without that chain.
            error.__context__ = error.__cause__ = None
            raise

    def _decode(self, chunks):
        encoding = self.headers.get('content-encoding', 'identity').strip().lower()
        if encoding not in ('identity', 'gzip', 'deflate'):
            raise OutboundUnavailableError() from None
        decoder = None if encoding == 'identity' else zlib.decompressobj(31 if encoding == 'gzip' else 15)
        saw_member = False
        for raw in chunks:
            # HTTPcore HTTP/1.1 reads at most 64KiB at a time; do not copy or
            # decode an over-budget chunk. This fixed pre-read is documented.
            self._allowance.consume(raw_bytes=len(raw))
            if decoder is None:
                self._allowance.consume(decoded_bytes=len(raw))
                if raw:
                    yield raw
                continue
            data = raw
            while data:
                self._budget.remaining_seconds()
                if decoder.eof:
                    if encoding != 'gzip':
                        raise OutboundUnavailableError() from None
                    decoder = zlib.decompressobj(31)
                # Zero means unlimited to zlib. One extra byte is an explicit,
                # bounded probe and is charged before any consumer sees it.
                size = min(_READ_SIZE, self._allowance.remaining_decoded_bytes() + 1)
                output = _safe_call(lambda: decoder.decompress(data, size), deadline=self._budget)
                self._allowance.consume(decoded_bytes=len(output))
                if output:
                    yield output
                data = decoder.unused_data if decoder.eof else decoder.unconsumed_tail
                saw_member = saw_member or decoder.eof
        if decoder is not None and (not saw_member or not decoder.eof):
            raise OutboundUnavailableError() from None

    def iter_bytes(self):
        if self._content is not None:
            if self._content:
                yield self._content
            return
        if self._closed or self._used:
            raise OutboundBudgetError(BudgetReason.CLOSED) from None
        self._used = True
        try:
            if self._head:
                return
            iterator = self._raw.iter_raw()

            def chunks():
                while True:
                    # Cooperative checkpoint. HTTPcore captures read timeout
                    # at body iteration start; changing extensions here would
                    # NOT tighten each socket read. Supervisor hard deadline
                    # is a separate required gate before production enablement.
                    self._budget.remaining_seconds()
                    try:
                        chunk = _safe_call(lambda: next(iterator), deadline=self._budget)
                    except StopIteration:
                        # Completing chunked framing/EOF may itself perform a
                        # blocking read, so completion is also a checkpoint.
                        self._budget.remaining_seconds()
                        break
                    self._budget.remaining_seconds()
                    yield chunk

            yield from self._decode(chunks())
        finally:
            self.close()

    def read(self):
        if self._content is None:
            self._content = b''.join(self.iter_bytes())
        return self._content

    @property
    def content(self):
        return self.read()

    @property
    def text(self):
        return self.content.decode('utf-8', errors='replace')

    def json(self):
        return _safe_call(lambda: json.loads(self.content))

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ControlledHttpStatusError(self.status_code) from None
        return self

    def close(self):
        if not self._closed:
            self._closed = True
            _close_quietly(self._raw.close)
            self._allowance.close()
            callback, self._on_close = self._on_close, None
            if callback is not None:
                callback(self)


class ControlledHttpxClient:
    """Source GET/HEAD, plus explicitly bounded POST through exchange only.

    Constructor options are trusted operator inputs. POST is disabled unless
    request_body_limit is a positive integer, at most 1MiB. Upload bytes are
    bounded by the shared request ceiling times this fixed per-request cap;
    no persistent budget fields or automatic retry are added.

    No public HTTPX client escapes this adapter. HTTPTransport handles proxy,
    CONNECT, TLS/Host/SNI and pooling; this module does not implement a proxy.
    Using the transport directly also avoids HTTPX Client's cookie jar and its
    INFO log of signed source URLs. No automatic redirect or fallback exists.
    Not thread safe: a future worker owns one instance per execution scope.
    """

    def __init__(self, channel, *, policy=DEFAULT_POLICY,
                 purpose=OutboundPurpose.METADATA, operator_headers=None,
                 credential_origin=None, bounds=HttpxBounds(),
                 accept_encoding='gzip, deflate, identity',
                 request_body_limit: int | None = None,
                 api_headers: frozenset[str] = frozenset(),
                 request_header_limit: int = 16 * 1024):
        proxy = _proxy_url(channel)
        if (request_body_limit is not None
                and (type(request_body_limit) is not int or not 1 <= request_body_limit <= 1024 * 1024)):
            raise ValueError('Invalid controlled HTTP body limit') from None
        if (type(request_header_limit) is not int or not 1 <= request_header_limit <= 16 * 1024
                or type(api_headers) is not frozenset
                or any(type(key) is not str or key not in _API_HEADER_LIMITS for key in api_headers)
                or (api_headers and request_body_limit is None)):
            raise ValueError('Invalid controlled HTTP header configuration') from None
        self._request_body_limit = request_body_limit
        self._api_headers = api_headers
        self._request_header_limit = request_header_limit
        if accept_encoding not in ('gzip, deflate, identity', 'identity'):
            raise ValueError('Invalid controlled HTTP encoding') from None
        if not isinstance(policy, OutboundPolicy) or not isinstance(bounds, HttpxBounds):
            raise ValueError('Invalid controlled HTTP configuration') from None
        bad_purpose = False
        try:
            purpose = OutboundPurpose(purpose)
        except (TypeError, ValueError):
            bad_purpose = True
        if bad_purpose or purpose is OutboundPurpose.PROVIDER:
            raise OutboundPolicyError(PolicyReason.PROVIDER_SCOPE) from None
        self._policy, self._purpose, self._bounds = policy, purpose, bounds
        self._accept_encoding = accept_encoding
        self._headers = _headers(operator_headers, operator=True)
        self._credential_origin = None
        if credential_origin is not None:
            approved = validate_url(credential_origin, purpose, policy, initial=False)
            parts = urlsplit(approved.url)
            if approved.scheme != 'https' or parts.path != '/' or parts.query or urlsplit(credential_origin).fragment:
                raise _blocked() from None
            self._credential_origin = approved.origin
        if self._headers.keys() & _CREDENTIALS and self._credential_origin is None:
            raise _blocked() from None
        self._closed = False
        self._responses = set()
        self._transport = _safe_call(lambda: httpx.HTTPTransport(
            proxy=proxy, verify=True, trust_env=False, retries=0,
            http1=True, http2=False,
            limits=httpx.Limits(max_connections=bounds.max_connections,
                               max_keepalive_connections=bounds.max_keepalive_connections,
                               keepalive_expiry=bounds.keepalive_expiry),
        ))

    def get(self, url, *, budget, headers=None, request_limits=None):
        with self.stream('GET', url, budget=budget, headers=headers, request_limits=request_limits) as response:
            response.read()
            return response

    def head(self, url, *, budget, headers=None, request_limits=None):
        with self.stream('HEAD', url, budget=budget, headers=headers, request_limits=request_limits) as response:
            response.read()
            return response

    @contextmanager
    def exchange(self, method, url, *, budget, data=None, headers=None, request_limits=None):
        """Hold one live GET/HEAD or explicitly enabled bytes-only POST.

        The internal bridge owns this context and its client; it must not exit
        before returning a live response to its consumer. GET/HEAD bodies and
        invalid or oversized POST bodies are rejected before a request scope.
        """
        with self._exchange(method, url, budget=budget, data=data, headers=headers,
                            request_limits=request_limits, allow_post=True) as response:
            yield response

    @contextmanager
    def stream(self, method, url, *, budget, headers=None, request_limits=None):
        with self._exchange(method, url, budget=budget, headers=headers,
                            request_limits=request_limits) as response:
            yield response

    def _post_headers(self, values):
        """Validate only the finite, explicitly enabled POST metadata fields."""
        result = _headers(values, extra=_ENTITY_HEADERS | self._api_headers)
        for key, value in result.items():
            if key == 'content-type':
                parts = [part.strip().lower() for part in value.split(';')]
                if (len(value) > 128 or parts[0] not in (
                        'application/json', 'application/x-www-form-urlencoded')
                        or (len(parts) != 1 and (len(parts) != 2 or parts[1] != 'charset=utf-8'))):
                    raise _blocked() from None
                result[key] = '; '.join(parts)
            elif key in self._api_headers:
                if len(value) > _API_HEADER_LIMITS[key]:
                    raise _blocked() from None
                if key == 'origin':
                    origin = validate_url(value, self._purpose, self._policy, initial=False)
                    parts = urlsplit(origin.url)
                    if (origin.scheme != 'https' or parts.path != '/' or parts.query
                            or urlsplit(value).fragment):
                        raise _blocked() from None
                    result[key] = urlunsplit((parts.scheme, parts.netloc, '', '', ''))
        return result

    @contextmanager
    def _exchange(self, method, url, *, budget, data=None, headers=None,
                  request_limits=None, allow_post=False):
        if self._closed:
            raise OutboundUnavailableError() from None
        post_operation = method == 'POST'
        if method not in ('GET', 'HEAD', 'POST') or (post_operation and not allow_post):
            raise _blocked() from None
        if post_operation:
            if (self._request_body_limit is None or type(data) is not bytes
                    or len(data) > self._request_body_limit):
                raise _blocked() from None
        elif data is not None:
            raise _blocked() from None
        if not (isinstance(budget, OutboundBudget) or type(budget) is OutboundBudgetGroup):
            raise ValueError('A shared outbound budget is required') from None
        target = validate_url(url, self._purpose, self._policy)
        request_headers = self._headers | (self._post_headers(headers) if post_operation else _headers(headers))
        if target.origin != self._credential_origin:
            request_headers = {key: value for key, value in request_headers.items() if key not in _CREDENTIALS}
        request_headers['accept-encoding'] = self._accept_encoding
        if (len(request_headers) > 32 or sum(len(key) + len(value) for key, value in request_headers.items())
                > self._request_header_limit):
            raise _blocked() from None
        scope = budget.request_scope(RequestLimits() if request_limits is None else request_limits,
                                     purpose=self._purpose)
        redirects = 0
        while True:
            # Every hop is independently validated; HTTPX never follows it.
            target = validate_url(target.url, self._purpose, self._policy, initial=False)
            allowance = scope.begin_request(redirect=redirects > 0)
            raw = None
            try:
                seconds = min(self._bounds.io_timeout, scope.remaining_seconds())
                request = _safe_call(lambda: httpx.Request(
                    method, target.url, headers=request_headers, content=data,
                    extensions={'timeout': dict.fromkeys(('connect', 'read', 'write', 'pool'), seconds)},
                ))
                def send():
                    # Retain ownership before the helper's successful-result
                    # deadline check: finally must close even if it expires.
                    nonlocal raw
                    raw = self._transport.handle_request(request)
                    return raw

                _safe_call(send, deadline=scope)
                scope.remaining_seconds()
                if raw.status_code in _REDIRECTS:
                    location = raw.headers.get('location')
                    if location is None:
                        raise OutboundPolicyError(PolicyReason.REDIRECT) from None
                    next_target = validate_redirect(target, location, self._policy)
                    if post_operation and target.scheme == 'https' and next_target.scheme == 'http':
                        raise OutboundPolicyError(PolicyReason.DOWNGRADE) from None
                    if (raw.status_code in (307, 308) and method == 'POST'
                            and target.origin != next_target.origin):
                        # Even an empty POST is not authorized for replay to a
                        # new origin. Stripping header credentials is not enough.
                        raise OutboundUnavailableError() from None
                    if redirects >= 5:
                        raise OutboundBudgetError(BudgetReason.REDIRECTS, self._purpose) from None
                    if ((raw.status_code == 303 and method != 'HEAD')
                            or (raw.status_code in (301, 302) and method == 'POST')):
                        method, data = 'GET', None
                        request_headers = {key: value for key, value in request_headers.items()
                                           if key not in _ENTITY_HEADERS}
                    if target.origin != next_target.origin:
                        request_headers = {key: value for key, value in request_headers.items()
                                           if key not in _CREDENTIALS | self._api_headers}
                    target = next_target
                    redirects += 1
                    continue
                response = _safe_call(lambda: ControlledResponse(
                    raw, allowance, scope, effective_url=target.url,
                    head=method == 'HEAD', on_close=self._responses.discard,
                ), deadline=scope)
                try:
                    self._responses.add(response)
                    yield response
                finally:
                    response.close()
                return
            finally:
                if raw is not None:
                    _close_quietly(raw.close)
                allowance.close()

    def close(self):
        if not self._closed:
            self._closed = True
            # response.close removes itself; iterate a snapshot, not the set.
            for response in tuple(self._responses):
                response.close()
            _close_quietly(self._transport.close)

    def __enter__(self):
        if self._closed:
            raise OutboundUnavailableError() from None
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
