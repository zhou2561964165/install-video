"""Bounded process-local reuse for authenticated content operations.

cachetools owns TTL/LRU eviction; Future owns result/error delivery. This adapter
adds account/config/content keys, bounded admission and defensive result copies.
It does not retry, cancel producers, persist content or coordinate processes.
"""
import copy
import hashlib
import json
import threading
import time
from concurrent.futures import Future, TimeoutError
from dataclasses import asdict, is_dataclass
from typing import Callable, TypeVar

from cachetools import TTLCache
from fastapi import HTTPException

from ..config import settings

T = TypeVar('T')
CACHE_VERSION = 'h009-v1'


class ReuseBusy(RuntimeError):
    pass


def _json_default(value):
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if is_dataclass(value):
        return asdict(value)
    raise TypeError('unsupported cache value')


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(',', ':'), default=_json_default).encode('utf-8')).hexdigest()


class RequestCache:
    def __init__(self, *, max_bytes: int, max_entries: int, ttl: float,
                 max_inflight: int, max_waiters: int, wait_seconds: float,
                 timer: Callable = time.monotonic):
        self._cache = TTLCache(maxsize=max_bytes, ttl=ttl, timer=timer,
                               getsizeof=lambda entry: entry[0])
        self._ttl = ttl
        self._max_entries = max_entries
        self._max_inflight = max_inflight
        self._max_waiters = max_waiters
        self._wait_seconds = wait_seconds
        self._lock = threading.Lock()
        self._pending: dict[str, Future] = {}
        self._waiters = 0

    def lookup(self, key: str):
        """Read only: export must never start an expensive producer."""
        with self._lock:
            try:
                return copy.deepcopy(self._cache[key][1])
            except KeyError:
                return None

    def run(self, key: str, producer: Callable[[], T]) -> T:
        with self._lock:
            try:
                return copy.deepcopy(self._cache[key][1])
            except KeyError:
                pass  # TTL can elapse at lookup; treat expiry as a normal miss.
            future = self._pending.get(key)
            owner = future is None
            if owner:
                if len(self._pending) >= self._max_inflight:
                    raise ReuseBusy('内容处理繁忙，请稍后重试。')
                future = Future()
                self._pending[key] = future
            else:
                if self._waiters >= self._max_waiters:
                    raise ReuseBusy('等待请求过多，请稍后重试。')
                self._waiters += 1

        if not owner:
            try:
                try:
                    return copy.deepcopy(future.result(timeout=self._wait_seconds))
                except TimeoutError:
                    if future.done():
                        # The producer itself may have raised TimeoutError.
                        return copy.deepcopy(future.result())
                    raise ReuseBusy('相同请求仍在处理中，请稍后重试。') from None
            finally:
                with self._lock:
                    self._waiters -= 1

        try:
            value = copy.deepcopy(producer())
            try:
                size = max(1, len(json.dumps(value, ensure_ascii=False,
                                           default=_json_default).encode('utf-8')))
            except (TypeError, ValueError):
                size = self._cache.maxsize + 1
            with self._lock:
                if self._ttl > 0 and size <= self._cache.maxsize:
                    self._cache.expire()
                    while len(self._cache) >= self._max_entries:
                        self._cache.popitem()
                    self._cache[key] = (size, value)
                future.set_result(value)
                del self._pending[key]
            return copy.deepcopy(value)
        except BaseException as exc:
            # Wake all joined callers on every exit; failures are never cached.
            with self._lock:
                if not future.done():
                    future.set_exception(exc)
                self._pending.pop(key, None)
            raise


_stores_lock = threading.Lock()
_stores: dict[str, tuple[tuple, RequestCache]] = {}


def _store(namespace: str) -> RequestCache:
    ttl = (settings.subtitle_cache_ttl_seconds if namespace == 'subtitle'
           else settings.insight_result_cache_ttl_seconds)
    limits = (settings.insight_cache_max_bytes, settings.insight_cache_max_entries,
              ttl, settings.insight_cache_max_inflight, settings.insight_cache_max_waiters,
              settings.insight_cache_wait_seconds)
    with _stores_lock:
        previous = _stores.get(namespace)
        if previous is None or previous[0] != limits:
            _stores[namespace] = (limits, RequestCache(
                max_bytes=limits[0], max_entries=limits[1], ttl=limits[2],
                max_inflight=limits[3], max_waiters=limits[4], wait_seconds=limits[5]))
        return _stores[namespace][1]


def _key(namespace: str, user_id: str, parameters) -> str:
    # Hash config including credentials to invalidate on credential rotation;
    # only the digest is retained, never the token/key/endpoint or source text.
    config = {name: value for name, value in vars(settings).items()
              if name.startswith(('llm_', 'summary_', 'subtitle_'))}
    return fingerprint((CACHE_VERSION, namespace, user_id, parameters, config))


def lookup_reused(namespace: str, user_id: str, parameters):
    return _store('subtitle' if namespace == 'subtitle' else 'result').lookup(_key(namespace, user_id, parameters))


def reuse(namespace: str, user_id: str, parameters, producer: Callable[[], T]) -> T:
    key = _key(namespace, user_id, parameters)
    try:
        return _store('subtitle' if namespace == 'subtitle' else 'result').run(key, producer)
    except ReuseBusy as exc:
        raise HTTPException(status_code=503, detail={
            'error_type': 'request_busy', 'error': str(exc),
        }) from exc
