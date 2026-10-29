"""Explicit synchronous HTTPX source scope, not a yt-dlp/parse safety switch.

The runtime factory opens only inside an isolated download child (external gate G4):
a valid controlled proxy in the environment and the child's own isolation evidence
(egress_evidence). Everywhere else, including the API process, it stays closed.
An explicitly injected context only covers the HTTPX consumers that use it.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from http.cookiejar import CookieJar
from os import environ, getpid
from threading import get_ident

import httpx

from . import egress_evidence
from .outbound_budget import BudgetProfile, OutboundBudget, OutboundBudgetGroup, RequestLimits
from .outbound_httpx import ControlledHttpxClient, HttpxBounds, ProxyChannel
from .outbound_policy import DEFAULT_POLICY, OutboundPolicy, OutboundPurpose, OutboundUnavailableError, validate_url
from .bilibili_session import apply_session_cookies

_SOURCE_HEADERS = frozenset({
    'accept', 'accept-language', 'user-agent', 'referer', 'range', 'if-range',
    'if-none-match', 'if-modified-since',
})
_current = ContextVar('source_network_context', default=None)


def source_headers(headers: dict | None) -> dict[str, str]:
    """Extractor headers are untrusted; credentials never become operator input."""
    if headers is None:
        return {}
    if not isinstance(headers, dict):
        raise OutboundUnavailableError() from None
    return {key: value for key, value in headers.items()
            if isinstance(key, str) and key.lower() in _SOURCE_HEADERS}


@dataclass(frozen=True)
class SourceNetworkContext:
    """Single-thread operation dependencies; all HTTP calls share one budget."""

    channel: ProxyChannel = field(repr=False)
    budget: OutboundBudget | OutboundBudgetGroup = field(repr=False)
    policy: OutboundPolicy = DEFAULT_POLICY
    _thread: int = field(default_factory=lambda: get_ident(), init=False, repr=False)
    _process: int = field(default_factory=lambda: getpid(), init=False, repr=False)

    def __post_init__(self):
        if (not (isinstance(self.budget, OutboundBudget) or type(self.budget) is OutboundBudgetGroup)
                or not isinstance(self.policy, OutboundPolicy)):
            raise ValueError('Invalid source network context') from None

    def check_owner(self):
        if get_ident() != self._thread or getpid() != self._process:
            raise OutboundUnavailableError() from None

    @contextmanager
    def stream(self, url: str, *, purpose: OutboundPurpose, headers=None, cookies=None,
               follow_redirects=True, max_bytes: int, phase_seconds: float,
               io_timeout: float, identity_only=False):
        with self.exchange('GET', url, purpose=purpose, headers=headers, cookies=cookies,
                follow_redirects=follow_redirects, max_bytes=max_bytes,
                phase_seconds=phase_seconds, io_timeout=io_timeout,
                identity_only=identity_only) as response:
            yield response

    @contextmanager
    def exchange(self, method: str, url: str, *, purpose: OutboundPurpose, data=None,
                 headers=None, cookies=None, follow_redirects=True, max_bytes: int,
                 phase_seconds: float, io_timeout: float, identity_only=False):
        """Hold a live GET/HEAD response; this context does not enable POST.

        The frozen budget is reused unchanged, including an explicitly supplied
        group. Request scopes are transient; no high-level child is allocated.
        """
        self.check_owner()
        if method not in ('GET', 'HEAD') or data is not None:
            raise OutboundUnavailableError() from None
        if type(follow_redirects) is not bool or type(identity_only) is not bool:
            raise ValueError('Invalid source network request') from None
        limits = RequestLimits(seconds=phase_seconds, response_raw_bytes=max_bytes,
                               response_decoded_bytes=max_bytes)
        policy = self.policy if follow_redirects else replace(self.policy, follow_redirects=False)
        target = validate_url(url, purpose, policy, initial=False)
        credential_headers, origin = {}, None
        if cookies is not None:
            if not isinstance(cookies, CookieJar):
                raise ValueError('Invalid source cookie jar') from None
            # The lower session layer applies the original strict jar to this
            # concrete URL and refuses non-official origins.
            request = httpx.Request(method, target.url)
            apply_session_cookies(request, cookies)
            if target.scheme == 'https' and 'cookie' in request.headers:
                credential_headers['Cookie'] = request.headers['cookie']
                origin = str(httpx.URL(target.url).copy_with(path='/', query=None, fragment=None))
        with ControlledHttpxClient(self.channel, policy=policy, purpose=purpose,
                operator_headers=credential_headers, credential_origin=origin,
                bounds=HttpxBounds(io_timeout=io_timeout),
                accept_encoding='identity' if identity_only else 'gzip, deflate, identity') as client:
            with client.stream(method, target.url, budget=self.budget,
                               headers=source_headers(headers), request_limits=limits) as response:
                yield response


def current_source_network() -> SourceNetworkContext | None:
    network = _current.get()
    if network is not None:
        network.check_owner()
    return network


@contextmanager
def source_network_scope(network: SourceNetworkContext | None):
    previous = current_source_network()
    if network is None:
        network = previous
    if network is not None:
        if not isinstance(network, SourceNetworkContext):
            raise ValueError('Invalid source network context') from None
        network.check_owner()
    if previous is not None and previous is not network:
        raise OutboundUnavailableError() from None
    token = _current.set(network)
    try:
        yield network
    finally:
        _current.reset(token)


def make_runtime_source_network(budget: OutboundBudget | OutboundBudgetGroup | None = None) -> SourceNetworkContext:
    """Open only with a controlled loopback proxy and this process's isolation evidence.

    The evidence (no capabilities, no_new_privs, not root, direct egress refused by the host
    firewall) is re-checked on every call; the proxy resolves names and refuses private
    targets (G1), the firewall leaves this user nothing but the proxy (G2) and the supervisor
    enforces the attempt deadline (G3). Without a budget, one download-attempt root is used.
    """
    proxy = environ.get(egress_evidence.PROXY_ENV)
    if not egress_evidence.proxy_url_ok(proxy) or not egress_evidence.isolated_now():
        raise OutboundUnavailableError() from None
    if budget is None:
        budget = OutboundBudget(BudgetProfile.download_attempt())
    return SourceNetworkContext(ProxyChannel(proxy, readiness_confirmed=True), budget)
