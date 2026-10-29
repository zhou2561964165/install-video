"""Narrow read-only Stripe adapter. Construct only outside database work."""
from collections.abc import Mapping
from typing import Protocol


class ReadOnlyCheckoutProvider(Protocol):
    def retrieve_session(self, session_id: str) -> Mapping: ...
    def list_sessions(self, params: Mapping) -> Mapping: ...


class _StripeCheckoutReader:
    __slots__ = ('_sessions',)

    def __init__(self, client):
        self._sessions = client.v1.checkout.sessions

    def retrieve_session(self, session_id):
        return self._sessions.retrieve(session_id, {'expand': ['line_items']})

    def list_sessions(self, params):
        # Explicit pages only: never iterate the SDK's auto paging iterator.
        return self._sessions.list(dict(params))


def build_read_only_provider(*, api_key: str, timeout_seconds: int) -> ReadOnlyCheckoutProvider:
    if type(api_key) is not str or not api_key or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 15:
        raise ValueError('invalid_read_provider_configuration')
    import stripe
    client = stripe.StripeClient(api_key, max_network_retries=0,
        http_client=stripe.RequestsClient(timeout=timeout_seconds))
    return _StripeCheckoutReader(client)
