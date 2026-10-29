"""U3 synthetic accounting; concurrency scenarios run in guarded subprocesses."""
from dataclasses import replace
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from app.services import outbound_budget as mod
from app.services.outbound_budget import (BudgetLimits, BudgetProfile, BudgetReason,
    OutboundBudget, OutboundBudgetError, RequestLimits)
from app.services.outbound_policy import OutboundPurpose

RUNNER = Path(r'E:\install_video\.planning\2026-10-24-production-execution\run_b5_budget_group_offline.py')

class Clock:
    def __init__(self): self.value, self.calls = 100.0, 0
    def __call__(self):
        self.calls += 1
        if isinstance(self.value, Exception): raise self.value
        return self.value

def budget(clock, **changes):
    return OutboundBudget(replace(BudgetLimits(), **changes), clock=clock)

def group(*nodes):
    return mod.OutboundBudgetGroup(nodes)

def counts(node):
    saved = node.snapshot()
    return saved.requests, saved.redirects, saved.raw_bytes, saved.decoded_bytes, saved.children

@pytest.mark.parametrize('bad', [(), [], [True], (True,), (None,), (object(),)])
def test_invalid_group_input_is_static(bad):
    with pytest.raises(ValueError, match='Invalid outbound budget group'):
        mod.OutboundBudgetGroup(bad)

def test_group_type_limit_and_clock_identity_without_sampling():
    clock = Clock()
    a = budget(clock)
    before, calls = a.checkpoint(), clock.calls
    group(a, a, a)
    assert clock.calls == calls
    for value in [(a,) * 9, (group(a),), (a, budget(Clock()))]:
        with pytest.raises(ValueError): mod.OutboundBudgetGroup(value)
    class Derived(OutboundBudget): pass
    with pytest.raises(ValueError): group(Derived(BudgetLimits(), clock=clock))
    assert a.checkpoint() == before

def test_alias_and_ancestor_overlap_deduplicate_and_siblings_reject():
    clock = Clock()
    root = budget(clock, children=2)
    child = root.child(replace(BudgetLimits(), children=1))
    leaf = child.child(BudgetLimits())
    other = root.child(BudgetLimits())
    before = root.checkpoint()
    with pytest.raises(ValueError): group(child, other)
    assert root.checkpoint() == before
    group(root, leaf, child, leaf).request_scope().begin_request().consume(raw_bytes=2, decoded_bytes=3)
    assert [counts(n)[:4] for n in (root, child, leaf)] == [(1, 0, 2, 3)] * 3
    assert counts(other)[:4] == (0, 0, 0, 0)

@pytest.mark.parametrize('redirect', [False, True])
def test_request_rejection_is_joint_and_blocks_other_leaf(redirect):
    clock = Clock()
    left = budget(clock)
    right = budget(clock, requests=1, redirects=0 if redirect else 5)
    scope = group(left, right).request_scope()
    if not redirect: scope.begin_request().close()
    before = counts(left), counts(right)
    with pytest.raises(OutboundBudgetError): scope.begin_request(redirect=redirect)
    assert (counts(left), counts(right)) == before
    for item in (left, right):
        with pytest.raises(OutboundBudgetError): item.begin_request()

@pytest.mark.parametrize('which', ['raw_bytes', 'decoded_bytes'])
def test_second_tree_total_failure_never_partially_consumes(which):
    clock = Clock()
    left, right = budget(clock), budget(clock, **{which: 2})
    response = group(left, right).request_scope().begin_request()
    response.consume(raw_bytes=1, decoded_bytes=1)
    with pytest.raises(OutboundBudgetError): response.consume(raw_bytes=2, decoded_bytes=2)
    assert counts(left)[2:4] == counts(right)[2:4] == (1, 1)

@pytest.mark.parametrize('method', ['consume', 'remaining_raw_bytes', 'remaining_decoded_bytes'])
def test_phase_checked_by_response_and_shared_across_redirect(method):
    clock = Clock()
    a, b = budget(clock), budget(clock)
    scope = group(a, b).request_scope(RequestLimits(seconds=2))
    response = scope.begin_request(redirect=True)
    clock.value = 102
    with pytest.raises(OutboundBudgetError) as error: getattr(response, method)()
    assert error.value.code == 'source_timeout'
    for n in (a, b):
        with pytest.raises(OutboundBudgetError): group(n).request_scope()

def test_local_cap_preserves_healthy_ancestors_and_siblings():
    clock = Clock()
    root = budget(clock, children=2)
    leaf, sibling = root.child(BudgetLimits()), root.child(BudgetLimits())
    other = budget(clock)
    response = group(leaf, other).request_scope(RequestLimits(response_decoded_bytes=2)).begin_request()
    with pytest.raises(OutboundBudgetError): response.consume(decoded_bytes=3)
    assert root.checkpoint().blocked is None
    sibling.begin_request().close()
    assert leaf._blocked is BudgetReason.RESPONSE_DECODED_BYTES
    assert other._blocked is BudgetReason.RESPONSE_DECODED_BYTES

def test_real_ancestor_limit_blocks_its_other_children():
    clock = Clock()
    root = budget(clock, requests=1, children=2)
    one, two = root.child(BudgetLimits()), root.child(BudgetLimits())
    one.begin_request().close()
    with pytest.raises(OutboundBudgetError): group(one, budget(clock)).request_scope().begin_request()
    assert root.checkpoint().blocked is BudgetReason.REQUESTS
    with pytest.raises(OutboundBudgetError): two.begin_request()

def test_purpose_reason_priority_and_existing_block_not_overwritten():
    clock = Clock()
    a, b = budget(clock), budget(clock)
    a._purpose = OutboundPurpose.SOURCE
    r = group(a, b).request_scope(RequestLimits(response_raw_bytes=1), purpose='subtitle').begin_request()
    with pytest.raises(OutboundBudgetError) as error: r.consume(raw_bytes=2)
    assert error.value.code == 'subtitle_too_large'
    assert error.value.__context__ is None
    a._blocked, b._blocked = BudgetReason.RAW_BYTES, BudgetReason.DEADLINE
    for nodes in [(a, b), (b, a)]:
        with pytest.raises(OutboundBudgetError) as error: group(*nodes).remaining_seconds()
        assert error.value.code == 'source_timeout'
    assert a._blocked is BudgetReason.RAW_BYTES
    assert b._blocked is BudgetReason.DEADLINE

def test_mixed_default_purpose_and_explicit_purpose_are_frozen():
    clock = Clock()
    a, b = budget(clock), budget(clock)
    a._purpose = OutboundPurpose.SOURCE
    mixed = group(a, b)
    assert mixed._purpose is OutboundPurpose.METADATA
    response = mixed.request_scope(RequestLimits(response_raw_bytes=1)).begin_request()
    with pytest.raises(OutboundBudgetError) as error: response.consume(raw_bytes=2)
    assert error.value.code == 'source_too_large'

def test_remaining_caps_tighten_and_close_is_local():
    clock = Clock()
    a, b = budget(clock, raw_bytes=5), budget(clock, response_raw_bytes=3)
    scope = group(a, b).request_scope(RequestLimits(seconds=100, response_raw_bytes=100, response_decoded_bytes=2))
    assert scope.remaining_seconds() == 30
    r = scope.begin_request()
    assert r.remaining_raw_bytes() == 3 and r.remaining_decoded_bytes() == 2
    r.consume(raw_bytes=3, decoded_bytes=2)
    assert r.remaining_raw_bytes() == r.remaining_decoded_bytes() == 0
    r.consume()
    r.close(); r.close()
    with pytest.raises(OutboundBudgetError): r.consume()
    scope.begin_request().close()
    assert counts(a)[:4] == (2, 0, 3, 2)

@pytest.mark.parametrize('bad', [True, -1, 1.5])
def test_bad_charge_no_mutation(bad):
    clock = Clock()
    a, b = budget(clock), budget(clock)
    s = group(a, b).request_scope()
    r = s.begin_request()
    before = counts(a), counts(b)
    with pytest.raises(ValueError): r.consume(raw_bytes=bad)
    with pytest.raises(ValueError): s.begin_request(redirect=1 if bad is True else bad)
    assert (counts(a), counts(b)) == before
    r.consume(raw_bytes=1)

@pytest.mark.parametrize('bad', [None, True, {}, 'subtitle'])
def test_bad_scope_limits_no_mutation(bad):
    clock = Clock()
    a = budget(clock)
    with pytest.raises(ValueError): group(a).request_scope(bad)
    assert counts(a) == (0, 0, 0, 0, 0)

def test_invalid_scope_purpose_is_safe_and_nonmutating():
    clock = Clock()
    a = budget(clock)
    with pytest.raises(ValueError) as caught: group(a).request_scope(purpose='signed-secret')
    assert caught.value.__context__ is caught.value.__cause__ is None
    assert 'signed-secret' not in str(caught.value)
    assert counts(a) == (0, 0, 0, 0, 0)

@pytest.mark.parametrize('bad', [True, float('nan'), float('inf'), RuntimeError('signed-secret')])
def test_clock_failure_is_safe_joint_terminal_and_no_watermark_advance(bad):
    clock = Clock()
    a, b = budget(clock), budget(clock)
    s = group(a, b).request_scope()
    prior = a._last_now, b._last_now
    clock.value = bad
    with pytest.raises(ValueError) as error: s.begin_request()
    assert 'signed-secret' not in str(error.value)
    assert error.value.__context__ is error.value.__cause__ is None
    assert (a._last_now, b._last_now) == prior
    assert a._blocked is b._blocked is BudgetReason.CLOSED
    clock.value = 100
    assert counts(a)[:4] == counts(b)[:4] == (0, 0, 0, 0)

def test_single_and_group_watermarks_reject_rollback_both_directions():
    clock = Clock()
    a, b = budget(clock), budget(clock)
    clock.value = 102
    a.snapshot()
    clock.value = 101
    with pytest.raises(ValueError): group(a, b).remaining_seconds()
    assert (a._last_now, b._last_now) == (102, 100)
    clock.value = 103
    c, d = budget(clock), budget(clock)
    clock.value = 104
    group(c, d).remaining_seconds()
    clock.value = 103
    with pytest.raises(ValueError): d.snapshot()
    assert c._last_now == d._last_now == 104

def test_scope_sampling_once_and_valid_time_advances_on_cap_rejection():
    clock = Clock()
    a, b = budget(clock, requests=1), budget(clock)
    s = group(a, b).request_scope()
    prior = clock.calls
    s.begin_request().close()
    assert clock.calls == prior + 1
    clock.value = 101
    with pytest.raises(OutboundBudgetError): s.begin_request()
    assert a._last_now == b._last_now == 101

def test_children_and_restore_watermarks_and_original_codec_roundtrip():
    from app.services.download_budget_codec import BudgetEnvelope, encode_budget, decode_budget
    clock = Clock()
    download = OutboundBudget(BudgetProfile.download_parent(), purpose='source', clock=clock)
    direct = OutboundBudget(BudgetProfile.direct_parent(), clock=clock)
    child = direct.child(BudgetProfile.resolve())
    view = group(download, child)
    assert not any(hasattr(view, key) for key in ('child', 'checkpoint', 'restore'))
    view.request_scope().begin_request().consume(raw_bytes=2, decoded_bytes=3)
    envelope = BudgetEnvelope(download.checkpoint(), direct.checkpoint())
    payload = encode_budget(envelope, resolve_attempts_used=1)
    assert decode_budget(1, payload, resolve_attempts_used=1) == envelope
    clock.value = 101
    dl = OutboundBudget.restore(envelope.download_parent, elapsed_seconds=1, clock=clock)
    dr = OutboundBudget.restore(envelope.direct_resolve_parent, elapsed_seconds=1, clock=clock)
    group(dl, dr.resume_child(0)).request_scope().begin_request().close()
    assert dl._last_now == dr._last_now == 101
    assert dl.snapshot().children == 0
    assert dr.snapshot().children == 1
    assert 'last_now' not in payload

def test_child_clock_rollback_never_attaches():
    clock = Clock()
    parent = budget(clock, children=1)
    samples = iter([101.0, 100.0])
    parent._clock = lambda: next(samples)
    with pytest.raises(ValueError): parent.child(BudgetLimits())
    assert parent._children == [] and parent._last_now == 101

def test_eight_distinct_roots_and_clock_identity_bound_method():
    clock = Clock()
    nodes = tuple(budget(clock) for _ in range(8))
    mod.OutboundBudgetGroup(nodes).request_scope().begin_request().close()
    assert all(counts(node)[0] == 1 for node in nodes)
    a = budget(clock.__call__)
    b = budget(clock.__call__)
    with pytest.raises(ValueError): group(a, b)

def test_rejected_child_and_response_terminal_roundtrip_cannot_revive():
    clock = Clock()
    root = budget(clock, children=1)
    leaf = root.child(BudgetLimits())
    with pytest.raises(OutboundBudgetError):
        group(leaf).request_scope(RequestLimits(response_raw_bytes=1)).begin_request().consume(raw_bytes=2)
    restored = OutboundBudget.restore(root.checkpoint(), elapsed_seconds=0, clock=clock)
    with pytest.raises(OutboundBudgetError): group(restored.resume_child(0)).request_scope()
    restored.begin_request().close()

def test_group_clock_failure_closes_response_without_partial_bytes():
    clock = Clock()
    a, b = budget(clock), budget(clock)
    response = group(a, b).request_scope().begin_request()
    response.consume(raw_bytes=1)
    clock.value = 99
    with pytest.raises(ValueError): response.consume(raw_bytes=1)
    response.close()
    clock.value = 100
    assert counts(a)[2] == counts(b)[2] == 1
    with pytest.raises(OutboundBudgetError): response.remaining_raw_bytes()

@pytest.mark.parametrize('kind', ['deadline', 'response_raw', 'response_decoded'])
def test_ancestor_absolute_and_response_limits_are_not_widened(kind):
    clock = Clock()
    limits = {'seconds': 1} if kind == 'deadline' else {'response_' + kind.removeprefix('response_') + '_bytes': 1}
    root = budget(clock, children=1, **limits)
    leaf = root.child(BudgetLimits())
    other = budget(clock)
    s = group(leaf, other).request_scope(RequestLimits(seconds=100, response_raw_bytes=100, response_decoded_bytes=100))
    r = s.begin_request()
    if kind == 'deadline':
        clock.value = 101
        with pytest.raises(OutboundBudgetError): s.remaining_seconds()
        assert root._blocked is BudgetReason.DEADLINE
    else:
        delta = {'raw_bytes' if kind == 'response_raw' else 'decoded_bytes': 2}
        with pytest.raises(OutboundBudgetError): r.consume(**delta)
        assert root._blocked is None

def test_existing_reason_wins_and_all_real_violations_are_recorded():
    clock = Clock()
    a, b = budget(clock, requests=1), budget(clock, requests=1)
    scope = group(a, b).request_scope()
    scope.begin_request().close()
    a._blocked = BudgetReason.DECODED_BYTES
    with pytest.raises(OutboundBudgetError) as error: scope.begin_request()
    assert error.value.code == 'source_too_large'
    assert a._blocked is BudgetReason.DECODED_BYTES and b._blocked is BudgetReason.REQUESTS

def test_constructor_invalid_clock_and_restore_regression_have_safe_context():
    clock = Clock()
    root = budget(clock, children=1)
    root.child(BudgetLimits())
    state = root.checkpoint()
    clock.value = RuntimeError('signed-secret')
    with pytest.raises(ValueError) as caught: budget(clock)
    assert caught.value.__context__ is caught.value.__cause__ is None
    samples = iter([200.0, 199.0])
    with pytest.raises(ValueError): OutboundBudget.restore(state, elapsed_seconds=0, clock=lambda: next(samples))

@pytest.mark.parametrize('scenario', ['reverse', 'mixed', 'mixed_bytes', 'snapshot', 'close'])
def test_guarded_concurrency_subprocess(scenario):
    result = subprocess.run([sys.executable, '-B', str(RUNNER), '--child', scenario],
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr

def _child_scenario(scenario):
    class AdvancingClock(Clock):
        def __call__(self):
            self.value += .001
            return super().__call__()
    clock = AdvancingClock() if scenario == 'reverse' else Clock()
    a, b = budget(clock, requests=1000, raw_bytes=1000), budget(clock, requests=1000, raw_bytes=1000)
    errors = []
    def guarded(fn):
        try: fn()
        except BaseException as error: errors.append(error)
    def launch(*functions):
        threads = [threading.Thread(target=guarded, args=(fn,), daemon=True) for fn in functions]
        for thread in threads: thread.start()
        for thread in threads: thread.join(4)
        assert not any(thread.is_alive() for thread in threads), 'thread timeout'
        assert not errors, errors
    if scenario == 'reverse':
        barrier = threading.Barrier(2)
        def drive(view):
            barrier.wait(2)
            for _ in range(100):
                item = view.request_scope().begin_request()
                item.consume(raw_bytes=1, decoded_bytes=1); item.close()
        launch(lambda: drive(group(a, b)), lambda: drive(group(b, a)))
        assert counts(a)[:4] == counts(b)[:4] == (200, 0, 200, 200)
    elif scenario in ('mixed', 'mixed_bytes'):
        a = budget(clock, requests=17 if scenario == 'mixed' else 1000, raw_bytes=17)
        barrier = threading.Barrier(2)
        def drive(joint):
            barrier.wait(2)
            for _ in range(30):
                try:
                    item = group(a, b).request_scope().begin_request() if joint else a.begin_request()
                    item.consume(raw_bytes=1); item.close()
                except OutboundBudgetError: break
        launch(lambda: drive(True), lambda: drive(False))
        if scenario == 'mixed':
            assert counts(a)[0] == 17 and counts(a)[2] <= 17
            assert counts(b)[0] <= 17 and counts(b)[2] <= 17
        else:
            assert counts(a)[0] <= 1000 and counts(a)[2] == 17
            assert counts(b)[2] <= 17
    elif scenario == 'close':
        item = group(a, b).request_scope().begin_request()
        barrier = threading.Barrier(2)
        def consume():
            barrier.wait(2)
            try: item.consume(raw_bytes=1)
            except OutboundBudgetError: pass
        def close(): barrier.wait(2); item.close(); item.close()
        launch(consume, close)
        assert counts(a)[2] == counts(b)[2] in (0, 1)
        assert a._blocked is b._blocked is None
    elif scenario == 'snapshot':
        entered, release, attempted, observed = [threading.Event() for _ in range(4)]
        original = OutboundBudget.__setattr__
        first = min((a, b), key=id)
        def pause(self, name, value):
            original(self, name, value)
            if self is first and name == '_requests' and value == 1:
                entered.set(); assert release.wait(3)
        OutboundBudget.__setattr__ = pause
        def write(): group(a, b).request_scope().begin_request().close()
        def read():
            assert entered.wait(2); attempted.set()
            assert first.snapshot().requests == 1
            assert first.checkpoint().requests == 1
            observed.set()
        try:
            writer = threading.Thread(target=lambda: guarded(write), daemon=True)
            reader = threading.Thread(target=lambda: guarded(read), daemon=True)
            writer.start(); reader.start()
            assert attempted.wait(2)
            assert not observed.wait(.05)
        finally:
            release.set(); writer.join(3); reader.join(3)
            OutboundBudget.__setattr__ = original
        assert observed.is_set() and not errors and not writer.is_alive() and not reader.is_alive()
        assert counts(a)[0] == counts(b)[0] == 1
