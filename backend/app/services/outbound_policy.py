"""Pure outbound policy. No DNS, sockets, HTTP, environment or application I/O.

An allowed URL and address set are inputs to a future pinning transport, not an
SSRF fix by themselves. That transport must preserve Host/SNI/TLS verification,
connect only to a returned numeric address, and enforce OS isolation separately.
"""

from dataclasses import dataclass, field
from enum import Enum
import ipaddress
import re
from typing import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit


class OutboundPurpose(str, Enum):
    SOURCE = 'source'
    METADATA = 'metadata'
    MEDIA = 'media'
    SUBTITLE = 'subtitle'
    ASR = 'asr'
    PROVIDER = 'provider'


class PolicyReason(str, Enum):
    URL_SYNTAX = 'url_syntax'
    PORT = 'port'
    ADDRESS = 'address'
    HOST_SCOPE = 'host_scope'
    DNS_EMPTY = 'dns_empty'
    DNS_LIMIT = 'dns_limit'
    DNS_FAILURE = 'dns_failure'
    REDIRECT = 'redirect'
    DOWNGRADE = 'downgrade'
    PROVIDER_SCOPE = 'provider_scope'


_ERRORS = {
    'invalid_url': (400, '链接格式无效'),
    'outbound_blocked': (422, '来源地址不符合安全策略'),
    'outbound_unavailable': (503, '安全访问通道暂不可用'),
    'source_timeout': (504, '来源处理超时'),
    'source_too_large': (422, '来源内容超过大小限制'),
    'subtitle_too_large': (422, '字幕内容超过大小限制'),
    'source_budget_exhausted': (422, '来源处理预算已耗尽'),
}


class OutboundError(Exception):
    """Terminal classification; adapters must not catch this to retry/fallback.

    Only fixed codes/reasons are accepted. Do not attach an original exception,
    URL, provider response, headers or resolver data to this exception.
    """

    retryable = False

    def __init__(self, code: str, reason: str):
        if code not in _ERRORS or reason not in _SAFE_REASONS:
            raise ValueError('Invalid outbound error classification') from None
        self.code = code
        self.reason = reason
        self.status_code, self.message = _ERRORS[code]
        super().__init__(self.message)
        self.__suppress_context__ = True

    def public_detail(self) -> dict[str, str]:
        return {'error_type': self.code, 'error': self.message}


_SAFE_REASONS = {item.value for item in PolicyReason} | {
    'unavailable', 'deadline', 'requests', 'redirects', 'raw_bytes',
    'decoded_bytes', 'response_raw_bytes', 'response_decoded_bytes',
    'children', 'closed',
}


class OutboundPolicyError(OutboundError):
    def __init__(self, reason: PolicyReason = PolicyReason.ADDRESS, *, invalid: bool = False):
        if not isinstance(reason, PolicyReason):
            raise ValueError('Invalid outbound error classification') from None
        super().__init__('invalid_url' if invalid else 'outbound_blocked', reason.value)


class OutboundUnavailableError(OutboundError):
    def __init__(self):
        super().__init__('outbound_unavailable', 'unavailable')


Origin = tuple[str, str, int]
_IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
_Network = ipaddress.IPv4Network | ipaddress.IPv6Network

# Explicit union with runtime ipaddress classification: stable across Python
# classification updates, including public-looking metadata and transition IPs.
_SPECIAL = tuple(ipaddress.ip_network(value) for value in (
    '0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
    '169.254.0.0/16', '172.16.0.0/12', '192.0.0.0/24', '192.0.2.0/24',
    '192.88.99.0/24', '192.168.0.0/16', '198.18.0.0/15',
    '198.51.100.0/24', '203.0.113.0/24', '224.0.0.0/4', '240.0.0.0/4',
    '168.63.129.16/32', '::/96', '64:ff9b::/96', '64:ff9b:1::/48',
    '100::/64', '2001::/23', '2001:db8::/32', '2002::/16',
    '3fff::/20', '5f00::/16', 'fc00::/7', 'fe80::/10', 'ff00::/8',
))
_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')
_NUMERIC_LABEL = re.compile(r'(?:[0-9]+|0x[0-9a-f]+)\Z', re.IGNORECASE)
_PORT = re.compile(r'[1-9][0-9]{0,4}\Z')


def _unsafe_text(value: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 or ch.isspace() or ch == '\\' for ch in value)


def _normalize_host(host: str) -> str:
    if host.endswith('.'):
        host = host[:-1]
    try:
        ascii_host = host.encode('idna').decode('ascii').lower()
    except (UnicodeError, ValueError):
        raise ValueError('Invalid host') from None
    if len(ascii_host) > 253 or not ascii_host or any(not _LABEL.fullmatch(label) for label in ascii_host.split('.')):
        raise ValueError('Invalid host') from None
    return ascii_host


@dataclass(frozen=True)
class OutboundPolicy:
    max_url_bytes: int = 8192
    allowed_ports: frozenset[int] = frozenset({80, 443})
    max_dns_answers: int = 64
    denied_cidrs: tuple[str, ...] = field(default=(), repr=False)
    allowed_host_roots: tuple[str, ...] = ()
    downgrade_origins: frozenset[Origin] = frozenset()
    provider_origins: frozenset[Origin] = frozenset()
    follow_redirects: bool = True
    _denied: tuple[_Network, ...] = field(init=False, repr=False)

    def __post_init__(self):
        try:
            for number in (self.max_url_bytes, self.max_dns_answers):
                if type(number) is not int or number <= 0:
                    raise ValueError
            if not self.allowed_ports or any(type(port) is not int or not 1 <= port <= 65535 for port in self.allowed_ports):
                raise ValueError
            if type(self.follow_redirects) is not bool:
                raise ValueError
            denied = tuple(ipaddress.ip_network(value, strict=True) for value in self.denied_cidrs)
            roots = tuple(_normalize_host(value) for value in self.allowed_host_roots)
            for origin in (*self.downgrade_origins, *self.provider_origins):
                scheme, host, port = origin
                if scheme != 'https' or type(port) is not int or not 1 <= port <= 65535:
                    raise ValueError
                if ':' in host:
                    if str(ipaddress.IPv6Address(host)) != host:
                        raise ValueError
                elif _normalize_host(host) != host:
                    raise ValueError
            object.__setattr__(self, 'allowed_ports', frozenset(self.allowed_ports))
            object.__setattr__(self, 'denied_cidrs', tuple(self.denied_cidrs))
            object.__setattr__(self, 'allowed_host_roots', roots)
            object.__setattr__(self, 'downgrade_origins', frozenset(self.downgrade_origins))
            object.__setattr__(self, 'provider_origins', frozenset(self.provider_origins))
            object.__setattr__(self, '_denied', denied)
        except (TypeError, ValueError, UnicodeError):
            raise ValueError('Invalid outbound policy configuration') from None


DEFAULT_POLICY = OutboundPolicy()


@dataclass(frozen=True)
class CanonicalTarget:
    url: str = field(repr=False)
    scheme: str
    host: str = field(repr=False)
    port: int
    purpose: OutboundPurpose
    _policy: OutboundPolicy = field(repr=False, compare=False)
    literal_ip: _IPAddress | None = field(default=None, repr=False)

    @property
    def origin(self) -> Origin:
        return self.scheme, self.host, self.port


def _contains(ip: _IPAddress, networks: tuple[_Network, ...]) -> bool:
    return any(ip.version == network.version and ip in network for network in networks)


def _public_ip(ip: _IPAddress, policy: OutboundPolicy) -> _IPAddress | None:
    if _contains(ip, policy._denied):
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if (_contains(ip, _SPECIAL) or _contains(ip, policy._denied)
            or not ip.is_global or ip.is_loopback or ip.is_private
            or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved):
        return None
    return ip


def validate_url(
    url: str, purpose: OutboundPurpose | str,
    policy: OutboundPolicy = DEFAULT_POLICY, *, initial: bool = True,
) -> CanonicalTarget:
    """Normalize syntax, then apply policy without resolving anything.

    initial=False maps malformed extractor/redirect URLs to outbound_blocked.
    url is a sensitive transport value; CanonicalTarget repr omits it and host.
    Path/query are never unquoted. A single DNS trailing dot is normalized.
    """
    try:
        purpose = OutboundPurpose(purpose)
    except (ValueError, TypeError):
        raise ValueError('Invalid outbound purpose') from None
    malformed = False
    try:
        if not isinstance(url, str) or not url or _unsafe_text(url) or len(url.encode('utf-8')) > policy.max_url_bytes:
            raise ValueError
        parts = urlsplit(url)
        if parts.scheme.lower() not in ('http', 'https') or not parts.netloc or '@' in parts.netloc or '%' in parts.netloc:
            raise ValueError
        authority = parts.netloc
        literal = None
        if authority.startswith('['):
            closing = authority.find(']')
            if closing < 0:
                raise ValueError
            host = authority[1:closing]
            literal = ipaddress.IPv6Address(host)
            host = str(literal)
            suffix = authority[closing + 1:]
            if suffix and not suffix.startswith(':'):
                raise ValueError
            port_text = suffix[1:] if suffix else None
        else:
            if authority.count(':') > 1 or '[' in authority or ']' in authority:
                raise ValueError
            raw_host, colon, port_text = authority.partition(':')
            port_text = port_text if colon else None
            host = _normalize_host(raw_host)
            try:
                literal = ipaddress.IPv4Address(host)
            except ValueError:
                if all(_NUMERIC_LABEL.fullmatch(label) for label in host.split('.')):
                    raise ValueError from None
        scheme = parts.scheme.lower()
        port = 443 if scheme == 'https' else 80
        if port_text is not None:
            if not _PORT.fullmatch(port_text) or not 1 <= int(port_text) <= 65535:
                raise ValueError
            port = int(port_text)
        authority_host = f'[{host}]' if ':' in host else host
        authority = authority_host if port == (443 if scheme == 'https' else 80) else f'{authority_host}:{port}'
        canonical = urlunsplit((scheme, authority, parts.path or '/', parts.query, ''))
        if len(canonical.encode('utf-8')) > policy.max_url_bytes:
            raise ValueError
    except (ValueError, UnicodeError, TypeError, AttributeError):
        malformed = True
    # Raise outside the parser's except block: even __context__ must not retain
    # an ipaddress/IDNA/urllib error containing attacker-controlled authority.
    if malformed:
        raise OutboundPolicyError(PolicyReason.URL_SYNTAX, invalid=initial) from None
    if port not in policy.allowed_ports:
        raise OutboundPolicyError(PolicyReason.PORT) from None
    if literal is not None and _public_ip(literal, policy) is None:
        raise OutboundPolicyError(PolicyReason.ADDRESS) from None
    if policy.allowed_host_roots and not any(host == root or host.endswith('.' + root) for root in policy.allowed_host_roots):
        raise OutboundPolicyError(PolicyReason.HOST_SCOPE) from None
    if purpose is OutboundPurpose.PROVIDER and (scheme, host, port) not in policy.provider_origins:
        raise OutboundPolicyError(PolicyReason.PROVIDER_SCOPE) from None
    return CanonicalTarget(canonical, scheme, host, port, purpose, policy, literal)


def select_public_addresses(
    target: CanonicalTarget, answers: Iterable[str], policy: OutboundPolicy | None = None,
) -> tuple[str, ...]:
    """Filter bounded synthetic/resolver A/AAAA data for numeric IP pinning.

    No resolution or connection occurs here. Each new connection must obtain a
    fresh answer set and use only this returned set, never hostname fallback.
    Mapping public IPv4-mapped IPv6 to IPv4 prevents alternate route semantics.
    An empty, over-limit or failed answer iteration closes the target.
    """
    policy = target._policy if policy is None else policy
    target = validate_url(target.url, target.purpose, policy, initial=False)
    allowed: list[str] = []
    dns_failed = False
    try:
        for index, answer in enumerate(answers):
            if index >= policy.max_dns_answers:
                raise OutboundPolicyError(PolicyReason.DNS_LIMIT)
            try:
                if not isinstance(answer, str) or '%' in answer or _unsafe_text(answer):
                    continue
                ip = ipaddress.ip_address(answer)
            except ValueError:
                continue
            public = _public_ip(ip, policy)
            if public is None:
                continue
            if target.literal_ip is not None and public != _public_ip(target.literal_ip, policy):
                raise OutboundPolicyError(PolicyReason.ADDRESS)
            value = str(public)
            if value not in allowed:
                allowed.append(value)
    except OutboundPolicyError:
        raise
    except Exception:
        dns_failed = True
    if dns_failed:
        raise OutboundPolicyError(PolicyReason.DNS_FAILURE) from None
    if not allowed:
        raise OutboundPolicyError(PolicyReason.DNS_EMPTY) from None
    return tuple(allowed)


def validate_redirect(
    current: CanonicalTarget, location: str, policy: OutboundPolicy | None = None,
) -> CanonicalTarget:
    """Revalidate each Location; the budget must separately charge the hop.

    HTTPS downgrade exceptions match the exact *source* origin configured by
    the operator. Platform adapters may prohibit all redirects independently.
    """
    policy = current._policy if policy is None else policy
    if not policy.follow_redirects:
        raise OutboundPolicyError(PolicyReason.REDIRECT) from None
    malformed = False
    try:
        if not isinstance(location, str) or not location or _unsafe_text(location) or len(location.encode('utf-8')) > policy.max_url_bytes:
            raise ValueError
        joined = urljoin(current.url, location)
    except (ValueError, UnicodeError):
        malformed = True
    if malformed:
        raise OutboundPolicyError(PolicyReason.URL_SYNTAX) from None
    target = validate_url(joined, current.purpose, policy, initial=False)
    if current.scheme == 'https' and target.scheme == 'http' and current.origin not in policy.downgrade_origins:
        raise OutboundPolicyError(PolicyReason.DOWNGRADE) from None
    return target
