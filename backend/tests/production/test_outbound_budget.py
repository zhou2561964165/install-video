"""Real counter and concurrency behavior with an injected monotonic clock."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from app.services.outbound_budget import BudgetLimits, BudgetProfile, OutboundBudget, OutboundBudgetError


class Clock:
    def __init__(self):
        self.now = 100.0
    def __call__(self):
        return self.now


def limits(**changes):
    return replace(BudgetLimits(seconds=30, requests=4, redirects=2, raw_bytes=20, decoded_bytes=30, response_raw_bytes=12, response_decoded_bytes=15, children=2), **changes)


def test_raw_and_decoded_are_independent_and_exact_boundaries_are_allowed():
    budget = OutboundBudget(limits())
    response = budget.begin_request()
    response.consume(raw_bytes=12, decoded_bytes=1)
    response.consume(decoded_bytes=14)
    assert budget.snapshot().raw_bytes == 12
    assert budget.snapshot().decoded_bytes == 15
    with pytest.raises(OutboundBudgetError) as caught:
        response.consume(decoded_bytes=1)
    assert (caught.value.code, caught.value.status_code) == ('source_too_large', 422)
    assert budget.snapshot().decoded_bytes == 15
    with pytest.raises(OutboundBudgetError):
        response.consume(raw_bytes=0)


def test_parent_child_charge_is_atomic_on_parent_and_child_failures():
    parent = OutboundBudget(limits(raw_bytes=10))
    child = parent.child(limits(raw_bytes=8))
    response = child.begin_request()
    response.consume(raw_bytes=7, decoded_bytes=2)
    with pytest.raises(OutboundBudgetError):
        response.consume(raw_bytes=2, decoded_bytes=3)
    assert (parent.snapshot().raw_bytes, parent.snapshot().decoded_bytes) == (7, 2)
    sibling = parent.child(limits())
    second = sibling.begin_request()
    with pytest.raises(OutboundBudgetError):
        second.consume(raw_bytes=4, decoded_bytes=1)
    assert (sibling.snapshot().raw_bytes, sibling.snapshot().decoded_bytes) == (0, 0)
    assert parent.snapshot().raw_bytes == 7


def test_subsequent_response_and_retry_cannot_reset_aggregate_bytes():
    budget = OutboundBudget(limits(raw_bytes=15, decoded_bytes=18))
    budget.begin_request().consume(raw_bytes=10, decoded_bytes=12)
    response = budget.begin_request()
    response.consume(raw_bytes=5, decoded_bytes=6)
    with pytest.raises(OutboundBudgetError):
        budget.begin_request().consume(raw_bytes=1)
    assert (budget.snapshot().raw_bytes, budget.snapshot().decoded_bytes) == (15, 18)


def test_parent_deadline_clips_late_child_and_same_object_resume_cannot_extend_it():
    clock = Clock()
    parent = OutboundBudget(limits(seconds=10), clock=clock)
    clock.now += 8
    child = parent.child(limits(seconds=30))
    assert child.remaining_seconds() == 2
    clock.now += 2
    with pytest.raises(OutboundBudgetError) as caught:
        child.begin_request()
    assert (caught.value.code, caught.value.status_code) == ('source_timeout', 504)
    assert parent.snapshot().requests == 0
    with pytest.raises(OutboundBudgetError):
        parent.child(limits())


def test_nested_requests_redirects_and_child_creation_share_parent_caps():
    parent = OutboundBudget(limits(requests=3, redirects=1))
    first = parent.child(limits())
    first.begin_request()
    first.begin_request(redirect=True)
    second = parent.child(limits())
    second.begin_request()
    with pytest.raises(OutboundBudgetError):
        second.begin_request()
    assert second.snapshot().requests == 1
    assert parent.snapshot().requests == 3
    fresh = OutboundBudget(limits(redirects=1))
    fresh.begin_request(redirect=True)
    with pytest.raises(OutboundBudgetError):
        fresh.begin_request(redirect=True)
    assert fresh.snapshot().requests == 1


def test_two_resolves_cap_cannot_be_reset_by_new_children():
    budget = OutboundBudget(BudgetProfile.direct_parent())
    budget.child(BudgetProfile.resolve())
    budget.child(BudgetProfile.resolve())
    with pytest.raises(OutboundBudgetError):
        budget.child(BudgetProfile.resolve())


def test_concurrent_siblings_cannot_overspend_parent_request_or_byte_budget():
    parent = OutboundBudget(limits(requests=41, raw_bytes=37, decoded_bytes=37, children=80))
    children = [parent.child(limits(requests=20)) for _ in range(80)]
    def spend(child):
        try:
            child.begin_request().consume(raw_bytes=1, decoded_bytes=1)
            return True
        except OutboundBudgetError:
            return False
    with ThreadPoolExecutor(max_workers=12) as executor:
        successes = sum(executor.map(spend, children))
    assert successes == 37
    assert parent.snapshot().requests <= 41
    assert parent.snapshot().raw_bytes == 37
    assert sum(child.snapshot().raw_bytes for child in children) == 37


def test_bounded_decoder_allowance_uses_response_child_and_parent_remaining():
    parent = OutboundBudget(limits(decoded_bytes=9))
    response = parent.child(limits()).begin_request()
    assert response.remaining_decoded_bytes() == 9
    response.consume(decoded_bytes=8)
    assert response.remaining_decoded_bytes() == 1
    with pytest.raises(OutboundBudgetError):
        response.consume(decoded_bytes=2)


def test_checkpoint_recovery_subtracts_downtime_and_keeps_all_ancestor_counters():
    clock = Clock()
    original = OutboundBudget(limits(seconds=10), clock=clock)
    child = original.child(limits())
    child.begin_request().consume(raw_bytes=5, decoded_bytes=6)
    clock.now += 2
    state = original.checkpoint()
    recovered = OutboundBudget.restore(state, elapsed_seconds=3, clock=Clock())
    assert recovered.remaining_seconds() == 5
    resumed = recovered.resume_child(0)
    assert (recovered.snapshot().requests, resumed.snapshot().requests) == (1, 1)
    assert resumed.remaining_seconds() == 5
    resumed.begin_request().consume(raw_bytes=3)
    assert recovered.snapshot().raw_bytes == 8
    assert recovered.snapshot().children == 1
    assert original.snapshot().raw_bytes == 5
    with pytest.raises(OutboundBudgetError):
        OutboundBudget.restore(state, elapsed_seconds=8, clock=Clock()).begin_request()


def test_checkpoint_inflight_response_fails_closed_instead_of_resetting_response_cap():
    original = OutboundBudget(limits())
    original.begin_request().consume(raw_bytes=4)
    restored = OutboundBudget.restore(original.checkpoint(), elapsed_seconds=0)
    assert restored.snapshot().raw_bytes == 4
    # Recovery opens a *new* counted HTTP request; the old stream is never resumed.
    restored.begin_request().consume(raw_bytes=2)
    assert restored.snapshot().requests == 2


def test_subtitle_byte_error_and_explicit_close_are_terminal():
    budget = OutboundBudget(limits(response_decoded_bytes=1), purpose='subtitle')
    response = budget.begin_request()
    with pytest.raises(OutboundBudgetError) as caught:
        response.consume(decoded_bytes=2)
    assert caught.value.code == 'subtitle_too_large'
    with pytest.raises(OutboundBudgetError):
        budget.begin_request()
    response.close()
    with pytest.raises(OutboundBudgetError):
        response.consume(decoded_bytes=1)


def test_raw_read_allowance_prevents_unbounded_wire_reads():
    parent = OutboundBudget(limits(raw_bytes=9))
    response = parent.child(limits(response_raw_bytes=7)).begin_request()
    assert response.remaining_raw_bytes() == 7
    response.consume(raw_bytes=6)
    assert response.remaining_raw_bytes() == 1


def test_concurrent_request_admission_stops_exactly_at_parent_cap():
    parent = OutboundBudget(limits(requests=17, children=70))
    children = [parent.child(limits()) for _ in range(70)]
    def admit(child):
        try:
            child.begin_request()
            return True
        except OutboundBudgetError:
            return False
    with ThreadPoolExecutor(max_workers=16) as executor:
        assert sum(executor.map(admit, children)) == 17
    assert parent.snapshot().requests == 17
    assert sum(child.snapshot().requests for child in children) == 17


def test_real_bounded_zlib_output_exhausts_decoded_budget_before_wire_budget():
    import zlib
    wire = zlib.compress(b'x' * 1024 * 1024)
    budget = OutboundBudget(limits(raw_bytes=2048, decoded_bytes=4096,
        response_raw_bytes=2048, response_decoded_bytes=4096))
    response = budget.begin_request()
    response.consume(raw_bytes=len(wire))
    decoder = zlib.decompressobj()
    output = decoder.decompress(wire, response.remaining_decoded_bytes())
    response.consume(decoded_bytes=len(output))
    assert len(output) == 4096
    assert response.remaining_decoded_bytes() == 0
    # Explicit one-byte overrun detection is bounded; max_length=0 is unsafe.
    with pytest.raises(OutboundBudgetError):
        response.consume(decoded_bytes=len(decoder.decompress(decoder.unconsumed_tail, 1)))
    assert budget.snapshot().raw_bytes == len(wire)
    assert budget.snapshot().decoded_bytes == 4096


def test_default_resolve_counts_http_sends_and_download_preserves_exact_2gib_boundary():
    resolve = OutboundBudget(BudgetProfile.resolve())
    for _ in range(64):
        resolve.begin_request()
    with pytest.raises(OutboundBudgetError):
        resolve.begin_request()
    download = OutboundBudget(BudgetProfile.download_attempt(), purpose='media')
    download.begin_request().consume(raw_bytes=2147483648, decoded_bytes=2147483648)
    with pytest.raises(OutboundBudgetError):
        download.begin_request().consume(raw_bytes=1)
    assert download.snapshot().raw_bytes == 2147483648


def test_restore_does_not_extend_deadline_while_rebuilding_branches():
    original = OutboundBudget(limits(seconds=10))
    original.child(limits())
    state = replace(original.checkpoint(), remaining_seconds=8)
    class AdvancingClock:
        def __init__(self):
            self.now = 100
            self.advance = True
        def __call__(self):
            value = self.now
            if self.advance:
                self.now += 1
            return value
    clock = AdvancingClock()
    restored = OutboundBudget.restore(state, elapsed_seconds=3, clock=clock)
    clock.advance = False
    clock.now = 104
    # Only one second remains: recovery processing cannot extend 100+5.
    assert restored.remaining_seconds() == 1


@pytest.mark.parametrize('changes', [{'seconds': 0}, {'seconds': float('inf')}, {'seconds': float('nan')}, {'requests': -1}, {'requests': True}, {'raw_bytes': 0}, {'redirects': -1}, {'children': -1}])
def test_nonfinite_or_invalid_configuration_is_rejected(changes):
    with pytest.raises(ValueError, match='Invalid outbound budget configuration'):
        limits(**changes)


def test_negative_charges_and_unknown_recovery_elapsed_are_rejected_without_mutation():
    budget = OutboundBudget(limits())
    response = budget.begin_request()
    for value in (-1, True, 1.5):
        with pytest.raises(ValueError):
            response.consume(raw_bytes=value)
    assert budget.snapshot().raw_bytes == 0
    for elapsed in (-1, float('nan'), float('inf')):
        with pytest.raises(ValueError):
            OutboundBudget.restore(budget.checkpoint(), elapsed_seconds=elapsed)


def test_checkpoint_remaining_never_exceeds_limit_under_float_rounding():
    # At this monotonic value (t0 + 1800) - t0 == 1800.0000000000146; a checkpoint taken in the
    # same clock tick must still be persistable (the codec rejects remaining > limits.seconds).
    from app.services import download_budget_codec as codec
    now = 129819.3713624486
    from app.services.outbound_policy import OutboundPurpose
    budget = OutboundBudget(BudgetProfile.download_parent(), purpose=OutboundPurpose.SOURCE, clock=lambda: now)
    saved = budget.checkpoint()
    assert saved.remaining_seconds <= saved.limits.seconds
    envelope = codec.BudgetEnvelope(saved, OutboundBudget(BudgetProfile.direct_parent(), clock=lambda: now).checkpoint())
    assert codec.decode_budget(codec.VERSION, codec.encode_budget(envelope)) is not None
