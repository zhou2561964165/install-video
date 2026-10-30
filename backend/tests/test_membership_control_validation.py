"""Wire validation is independent of PostgreSQL and provider integrations."""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError


def test_request_trims_reason_and_requires_explicit_nullable_expiry():
    from app.admin.schemas import MembershipPatch
    body = MembershipPatch(mode='enabled', expires_at=None, reason='  管理员核对后永久启用会员  ', expected_revision='0')
    assert body.reason == '管理员核对后永久启用会员'
    with pytest.raises(ValidationError):
        MembershipPatch(mode='enabled', reason='管理员核对后永久启用会员', expected_revision='0')


@pytest.mark.parametrize('changes', [
    {'mode': 'other'}, {'expires_at': '2026-10-30T00:00:00+08:00'},
    {'mode': 'disabled', 'expires_at': '2026-10-30T00:00:00Z'},
    {'mode': 'auto', 'expires_at': '2026-10-30T00:00:00Z'},
    {'expected_revision': '01'}, {'expected_revision': '-1'}, {'reason': '          '},
    {'unexpected': 'field'},
])
def test_request_rejects_invalid_control_inputs(changes):
    from app.admin.schemas import MembershipPatch
    data = dict(mode='enabled', expires_at=None, reason='管理员核对后永久启用会员', expected_revision='0')
    with pytest.raises(ValidationError):
        MembershipPatch(**(data | changes))


def test_deadline_compared_to_operation_clock_after_replay_lookup():
    from app.services.admin_membership import validate_deadline
    from app.admin.errors import AdminError
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    assert validate_deadline('enabled', None, now) is None
    assert validate_deadline('enabled', now + timedelta(seconds=1), now) == now + timedelta(seconds=1)
    with pytest.raises(AdminError) as caught:
        validate_deadline('enabled', now, now)
    assert caught.value.status == 422


def test_equivalent_utc_deadlines_are_normalized_for_idempotency_digest():
    from app.admin.schemas import MembershipPatch
    data = dict(mode='enabled', reason='管理员核对后指定期限启用会员', expected_revision='0')
    plain = MembershipPatch(**data, expires_at='2030-01-01T00:00:00Z')
    fractional = MembershipPatch(**data, expires_at='2030-01-01T00:00:00.000000Z')
    assert plain.model_dump() == fractional.model_dump()


def test_revision_accepts_bigint_max_but_rejects_overflow():
    from app.admin.schemas import MembershipPatch
    data = dict(mode='enabled', expires_at=None, reason='管理员核对后永久启用会员')
    assert MembershipPatch(**data, expected_revision='9223372036854775807').expected_revision == '9223372036854775807'
    for revision in ('9223372036854775808', '9999999999999999999', '1' * 5000):
        with pytest.raises(ValidationError):
            MembershipPatch(**data, expected_revision=revision)


def test_permanent_and_maximum_finite_deadline_do_not_need_epoch_sentinel():
    from app.admin.schemas import MembershipPatch
    from app.services.admin_membership import validate_deadline
    from app.services.membership_policy import resolve
    from types import SimpleNamespace
    data = dict(mode='enabled', reason='管理员核对后指定期限启用会员', expected_revision='0')
    now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    for deadline in (None, '9999-12-31T23:59:59.999999Z'):
        body = MembershipPatch(**data, expires_at=deadline)
        actual = datetime.fromisoformat(body.expires_at.replace('Z', '+00:00')) if body.expires_at else None
        validate_deadline(body.mode, actual, now)
        result = resolve(None, SimpleNamespace(mode=body.mode, expires_at=actual), now)
        assert result.effective is True
        assert result.permanent == (deadline is None)
        assert result.expires_at == actual


def test_membership_write_is_exactly_admin_only_and_capability_gated():
    from app.admin.config import AdminSettings
    from app.admin.deps import READ_PERMISSIONS, effective_permissions, ready_capabilities
    ready = ready_capabilities(AdminSettings())
    assert 'membership_control_write' in ready
    assert effective_permissions('admin', ready) == READ_PERMISSIONS | {
        'support:read', 'support:write', 'memberships:write'}
    assert effective_permissions('viewer', ready) == READ_PERMISSIONS | {'support:read'}
    assert 'memberships:write' not in effective_permissions('admin')
    assert effective_permissions('unknown', ready) == frozenset()
