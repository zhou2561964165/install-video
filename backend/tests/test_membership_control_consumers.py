"""Request-time enforcement with fake content/payment providers and an isolated SQLite test DB."""
from datetime import datetime, timedelta, timezone
import time

import pytest
from sqlmodel import Session

from app.db import engine
from app.models import Membership, MembershipControl
from app.services import membership
from test_membership_billing import setup  # noqa: F401 (existing synthetic-account/fake-provider fixture)


def control(uid, mode, expires=None):
    with Session(engine) as session:
        row = session.get(MembershipControl, uid)
        if row is None:
            row = MembershipControl(user_id=uid, mode=mode, expires_at=expires, revision=1,
                                    updated_at=datetime.now(timezone.utc), actor_user_id=uid)
        else:
            row.mode, row.expires_at = mode, expires
            row.revision += 1
        session.add(row)
        session.commit()


@pytest.mark.parametrize('mode,expires,effective', [
    ('enabled', None, True), ('enabled', -10, False), ('enabled', 3600, True), ('disabled', None, False),
])
def test_public_membership_and_checkout_follow_manual_control(setup, mode, expires, effective):
    client, headers, uid, calls, _ = setup
    deadline = None if expires is None else datetime.now(timezone.utc) + timedelta(seconds=expires)
    control(uid, mode, deadline)
    result = client.get('/api/membership', headers=headers)
    assert result.status_code == 200
    info = result.json()
    assert info['plan'] == ('vip' if effective else 'free')
    assert info['control_mode'] == mode and info['checkout_available'] is False
    assert info['effective_permanent'] == (mode == 'enabled' and expires is None)
    assert info['expires_at'] == info['effective_expires_at']
    assert '管理员手动管理' in info['checkout_unavailable_reason']
    rejected = client.post('/api/billing/checkout', headers=headers)
    assert rejected.status_code == 409 and rejected.json()['detail']['error_type'] == 'membership_managed'
    assert calls == []


def test_manual_expiry_does_not_fall_back_to_still_paid_membership(setup):
    _, _, uid, *_ = setup
    with Session(engine) as session:
        session.add(Membership(user_id=uid, status='active', expires_at=time.time() + 3600))
        session.commit()
    control(uid, 'enabled', datetime.now(timezone.utc) - timedelta(seconds=10))
    with Session(engine) as session:
        assert membership.is_vip(session, uid) is False
    control(uid, 'auto')
    with Session(engine) as session:
        assert membership.is_vip(session, uid) is True


@pytest.mark.parametrize('path', ['/api/subtitle', '/api/subtitle/export', '/api/subtitle/translate', '/api/summary'])
def test_disabled_member_rejected_before_content_or_cached_result(setup, monkeypatch, path):
    client, headers, uid, *_ = setup
    control(uid, 'disabled')
    def forbidden(*args, **kwargs):
        raise AssertionError('content/cache must not be accessed after the current entitlement was revoked')
    monkeypatch.setattr('app.routes.subtitle.load_cached_subtitle', forbidden)
    monkeypatch.setattr('app.routes.summary.load_cached_subtitle', forbidden)
    response = client.post(path, headers=headers, json={'url': 'https://example.invalid/v', 'format': 'srt'})
    assert response.status_code == 403
    assert response.json()['detail']['error_type'] == 'membership_required'


def test_paid_notification_updates_payment_fact_but_cannot_undo_manual_disable(setup):
    from test_membership_billing import event, intent, post_event
    client, headers, uid, *_ = setup
    checkout = intent(setup)
    control(uid, 'disabled')
    assert post_event(client, event(checkout)).status_code == 200
    with Session(engine) as session:
        assert session.get(Membership, uid).status == 'active'
        assert session.get(MembershipControl, uid).mode == 'disabled'
        assert membership.is_vip(session, uid) is False


def test_manual_enable_cannot_cause_payment_notification_to_be_discarded(setup):
    from test_membership_billing import event, intent, post_event
    client, _, uid, *_ = setup
    checkout = intent(setup)
    control(uid, 'enabled')
    assert post_event(client, event(checkout)).status_code == 200
    with Session(engine) as session:
        row = session.get(Membership, uid)
        assert row.status == 'active' and row.entitlement_source == 'pi_' + checkout.id
        assert session.get(MembershipControl, uid).mode == 'enabled'


def test_membership_info_uses_one_entitlement_instant_for_expiry_boundary(setup, monkeypatch):
    from app.services.membership_policy import Entitlement
    _, _, uid, *_ = setup
    calls = []
    boundary = datetime(2030, 1, 1, tzinfo=timezone.utc)
    def at_boundary(*args, **kwargs):
        calls.append(True)
        return Entitlement(False, 'admin_expired', boundary)
    def separate_clock(*args, **kwargs):
        raise AssertionError('membership response must use the same resolved entitlement for every field')
    monkeypatch.setattr(membership, 'entitlement', at_boundary)
    monkeypatch.setattr(membership, 'is_vip', separate_clock)
    monkeypatch.setattr(membership, 'max_height', separate_clock)
    with Session(engine) as session:
        info = membership.info(session, uid)
    assert calls == [True]
    assert info['plan'] == 'free' and info['status'] == 'expired'
    assert info['features']['subtitles'] is False and info['features']['max_height'] is not None
