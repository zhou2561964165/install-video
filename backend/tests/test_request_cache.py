from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event

import pytest

from app.services import request_cache as module
from app.services.request_cache import RequestCache, ReuseBusy


def cache(**kwargs):
    return RequestCache(**({'max_bytes': 1024, 'max_entries': 2, 'ttl': 10,
                            'max_inflight': 2, 'max_waiters': 2, 'wait_seconds': 1} | kwargs))


def test_internal_fingerprint_handles_all_python_string_code_points():
    assert len(module.fingerprint({'value': '\ud800'})) == 64
    assert module.fingerprint({'value': '\ud800'}) != module.fingerprint({'value': '\ud801'})


def test_expiry_between_contains_and_lookup_does_not_raise_key_error():
    class Clock:
        crossing = False
        calls = 0
        def __call__(self):
            if not self.crossing:
                return 0
            self.calls += 1
            return 9 if self.calls == 1 else 11
    clock = Clock()
    store = cache(timer=clock)
    store.run('same', lambda: 'cached')
    clock.crossing = True
    assert store.run('same', lambda: 'new') in {'cached', 'new'}


def test_ttl_and_lru_reuse_are_bounded_and_values_are_not_shared():
    clock = [0]
    store = cache(timer=lambda: clock[0])
    original = {'points': ['one']}
    assert store.run('a', lambda: original) == original
    original['points'].append('producer mutation')
    copy = store.run('a', lambda: pytest.fail('must hit'))
    assert copy == {'points': ['one']}
    copy['points'].append('caller mutation')
    assert store.run('a', lambda: pytest.fail('must hit')) == {'points': ['one']}
    store.run('b', lambda: 2)
    store.run('a', lambda: pytest.fail('must hit'))
    store.run('c', lambda: 3)
    assert store.run('b', lambda: 'evicted') == 'evicted'
    clock[0] = 11
    assert store.run('a', lambda: 'expired') == 'expired'


def test_large_values_return_without_poisoning_other_cache_entries():
    store = cache()
    store.run('small', lambda: 'cached')
    assert store.run('huge', lambda: 'x' * 2000) == 'x' * 2000
    assert store.run('huge', lambda: 'new') == 'new'
    assert store.run('small', lambda: pytest.fail('small should remain')) == 'cached'


def test_byte_budget_also_evicts_entries():
    store = RequestCache(max_bytes=10, max_entries=20, ttl=10, max_inflight=2,
                         max_waiters=2, wait_seconds=1)
    store.run('one', lambda: '12345')
    store.run('two', lambda: '67890')
    assert store.run('one', lambda: 'new') == 'new'


def test_ttl_zero_disables_completed_cache_only():
    store = RequestCache(max_bytes=1024, max_entries=2, ttl=0, max_inflight=2,
                         max_waiters=2, wait_seconds=1)
    assert store.run('a', lambda: 1) == 1
    assert store.run('a', lambda: 2) == 2


def observed_wait(monkeypatch):
    joined = Event()
    class ObservedFuture(Future):
        def result(self, timeout=None):
            joined.set()
            return super().result(timeout)
    monkeypatch.setattr(module, 'Future', ObservedFuture)
    return joined


@pytest.mark.parametrize('fail', [False, True])
@pytest.mark.parametrize('ttl', [0, 10])
def test_one_owner_shares_result_or_error_without_retry(monkeypatch, fail, ttl):
    joined = observed_wait(monkeypatch)
    store = cache(ttl=ttl)
    entered, release = Event(), Event()
    calls = []
    error = ValueError('upstream failed')
    def produce():
        calls.append(1)
        entered.set()
        assert release.wait(2)
        if fail:
            raise error
        return {'points': ['result']}
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(store.run, 'same', produce)
        assert entered.wait(1)
        second = pool.submit(store.run, 'same', produce)
        try:
            assert joined.wait(1)
        finally:
            release.set()
        if fail:
            for future in [first, second]:
                with pytest.raises(ValueError, match='upstream failed'):
                    future.result(2)
            assert store.run('same', lambda: 'manual retry') == 'manual retry'
        else:
            assert first.result(2) == second.result(2) == {'points': ['result']}
            assert first.result(2) is not second.result(2)
    assert calls == [1]


def test_wait_timeout_does_not_evict_owner_or_start_another_operation(monkeypatch):
    joined = observed_wait(monkeypatch)
    store = RequestCache(max_bytes=1024, max_entries=2, ttl=10, max_inflight=1,
                         max_waiters=1, wait_seconds=0.01)
    entered, release = Event(), Event()
    def produce():
        entered.set()
        assert release.wait(2)
        return 'done'
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(store.run, 'same', produce)
        assert entered.wait(1)
        try:
            with pytest.raises(ReuseBusy):
                store.run('same', lambda: pytest.fail('duplicate owner'))
            with pytest.raises(ReuseBusy):
                store.run('different', lambda: pytest.fail('over capacity'))
        finally:
            release.set()
        assert first.result(2) == 'done'
    assert store.run('same', lambda: pytest.fail('owner was lost')) == 'done'


def test_waiter_limit_does_not_block_owner_cleanup(monkeypatch):
    joined = observed_wait(monkeypatch)
    store = RequestCache(max_bytes=1024, max_entries=2, ttl=10, max_inflight=1,
                         max_waiters=1, wait_seconds=1)
    entered, release = Event(), Event()
    def produce():
        entered.set()
        assert release.wait(2)
        return 'done'
    with ThreadPoolExecutor(2) as pool:
        owner = pool.submit(store.run, 'same', produce)
        assert entered.wait(1)
        waiter = pool.submit(store.run, 'same', produce)
        try:
            assert joined.wait(1)
            with pytest.raises(ReuseBusy):
                store.run('same', lambda: pytest.fail('extra waiter'))
        finally:
            release.set()
        assert owner.result(2) == waiter.result(2) == 'done'


def test_distinct_key_can_progress_while_owner_is_blocked():
    store = cache()
    entered, release = Event(), Event()
    def produce():
        entered.set()
        assert release.wait(2)
        return 'first'
    with ThreadPoolExecutor(1) as pool:
        owner = pool.submit(store.run, 'first', produce)
        assert entered.wait(1)
        try:
            assert store.run('second', lambda: 'second') == 'second'
        finally:
            release.set()
        assert owner.result(2) == 'first'
