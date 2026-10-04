"""Bounded retries for idempotent HTTP GET operations."""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

import httpx

_Result = TypeVar("_Result")
_TRANSIENT_STATUS_CODES = {502, 503, 504}


def retry_get(
    get: Callable[[], _Result],
    *,
    max_retries: int,
    backoff_seconds: float,
    sleep: Callable[[float], None] | None = None,
) -> _Result:
    """Run a GET callback, retrying only transient network and gateway failures.

    ``max_retries`` counts additional attempts after the first call.
    """
    if max_retries < 0:
        raise ValueError("max_retries must be non-negative")
    sleeper = sleep or time.sleep
    retry_index = 0
    while True:
        try:
            return get()
        except (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
            httpx.HTTPStatusError,
        ) as exc:
            retryable = isinstance(
                exc,
                (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError),
            ) or (
                isinstance(exc, httpx.HTTPStatusError)
                and exc.response.status_code in _TRANSIENT_STATUS_CODES
            )
            if not retryable or retry_index >= max_retries:
                raise
            sleeper(backoff_seconds * (2**retry_index))
            retry_index += 1
