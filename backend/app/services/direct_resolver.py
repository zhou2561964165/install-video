"""B5 U6: guarded direct-link resolver for B4's submit_download(trusted_resolver=...).

Borrows B4's already-claimed download root and direct-resolve attempt (never begin_get, never
a new child) as one OutboundBudgetGroup, so each source request is charged atomically to both
trees, and resolves through ytdlp_service.resolve_direct (Generic extractor, metadata only).

Outcome classes (A contract §3): a single-file direct link -> direct; no such file, a transient
source failure (408/429/5xx, busy, timeout) or an exhausted budget without a refusal -> no direct
link, so B4 falls back to a server Job on the same slot; refusals (401/403/412, policy, Bilibili,
unavailable) propagate to fail_resolve and never fall back.

The default network factory is the closed runtime factory: until the environmental gate is
verified no route passes this resolver, and calling it fails closed before any I/O. Wiring
precondition (review M4): the stored canonical format id must carry the membership height
limit ([height<=N]); this resolver has no other view of it.
"""
from __future__ import annotations

from typing import Callable
from urllib.parse import urlsplit

from ..schemas import DownloadResponse
from .download_submission import DirectResult, ResolveAccounting
from .outbound_budget import OutboundBudgetGroup
from .outbound_httpx import ControlledHttpBusyError, ControlledHttpStatusError
from .outbound_policy import OutboundError, OutboundUnavailableError
from .source_network import SourceNetworkContext, make_runtime_source_network

_TRANSIENT_CODES = frozenset({'source_timeout', 'source_budget_exhausted'})
_PRIVATE_SUFFIXES = ('.local', '.internal', '.localhost', '.lan', '.home.arpa')


def _transient(error) -> bool:
    if isinstance(error, ControlledHttpBusyError):
        return True
    if isinstance(error, ControlledHttpStatusError):
        return error.source_status in (408, 429) or error.source_status >= 500
    return isinstance(error, OutboundError) and error.code in _TRANSIENT_CODES


def _browser_safe(url: str) -> bool:
    """The user's browser fetches a direct link: refuse names that only resolve on a private network."""
    host = (urlsplit(url).hostname or '').lower().rstrip('.')
    return '.' in host and host != 'localhost' and not host.endswith(_PRIVATE_SUFFIXES)


def guarded_resolver(network_factory: Callable[[OutboundBudgetGroup], SourceNetworkContext] | None = None):
    """A trusted_resolver(request, accounting) -> DirectResult; refusals propagate to fail_resolve."""
    factory = network_factory or make_runtime_source_network

    def resolve(request, accounting: ResolveAccounting) -> DirectResult:
        from . import ytdlp_service  # the only yt-dlp layer; imported on use
        download, child = accounting.source_budgets()
        network = factory(OutboundBudgetGroup((download, child)))
        transient = False
        try:
            found = ytdlp_service.resolve_direct(request.url, request.format_id, network=network)
        except (OutboundError, ControlledHttpStatusError, ControlledHttpBusyError) as error:
            if not _transient(error):
                raise
            transient = True
        if transient or found is None:
            return DirectResult()  # no direct link now: B4 falls back to a server Job on the same slot
        url, headers = found
        if not _browser_safe(url):
            raise OutboundUnavailableError() from None
        return DirectResult(DownloadResponse(mode='direct', url=url, headers=headers))
    return resolve
