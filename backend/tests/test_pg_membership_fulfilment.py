"""Support tickets Task 4: the shared paid-checkout fulfilment (payment notifications and re-issue) on PG."""
import os
import time

import pytest
from sqlalchemy import text
from sqlmodel import Session

from test_pg_job_repository import case, db  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
DAY = 86400


def seed(case, *, user='u1', expires_offset=None, checkout='co1'):
    db(case, 'INSERT INTO app."user" (id,email,password_hash,created_at) VALUES (:u,:e,\'x\',now()) ON CONFLICT DO NOTHING',
       u=user, e=user + '@example.invalid')
    if expires_offset is not None:
        db(case, "INSERT INTO app.membership (user_id,status,expires_at,cancel_at_period_end,revision) "
                 "VALUES (:u,'active',extract(epoch from now()) + :o,false,0)", u=user, o=expires_offset)
    else:
        db(case, "INSERT INTO app.membership (user_id,status,expires_at,cancel_at_period_end,revision) "
                 "VALUES (:u,'free',0,false,0)", u=user)
    db(case, "INSERT INTO app.billingcheckout (id,user_id,price_id,mode,duration_days,origin,created_at,expires_at,state,"
             "fulfilled,reconcile_attempts,revision) VALUES (:c,:u,'price','payment',30,'https://s.invalid',"
             "extract(epoch from now()),0,'open',false,0,0)", c=checkout, u=user)


def run(case, payment_intent='pi_1', user='u1', checkout='co1'):
    from app.models import BillingCheckout, Membership
    from app.services.membership_fulfilment import fulfil_paid_checkout
    with Session(case.application) as session:
        account = session.get(Membership, user)
        attempt = session.get(BillingCheckout, checkout)
        now_ts = time.time()
        allowed = fulfil_paid_checkout(session, account, attempt, payment_intent, now_ts=now_ts)
        session.commit()
        return allowed, now_ts, account.status, account.expires_at, account.entitlement_source, attempt.fulfilled, attempt.state


def test_extends_from_now_when_expired(case):
    seed(case)
    allowed, now_ts, status, expires, source, fulfilled, state = run(case)
    assert allowed and status == 'active' and source == 'pi_1' and fulfilled and state == 'paid'
    assert abs(expires - (now_ts + 30 * DAY)) < 5


def test_extends_from_current_expiry_when_later(case):
    seed(case, expires_offset=5 * DAY)
    with case.migration.connect() as connection:
        before = connection.scalar(text("SELECT expires_at FROM app.membership WHERE user_id='u1'"))
    _, _, _, expires, _, _, _ = run(case)
    assert abs(expires - (before + 30 * DAY)) < 1


def test_revoked_binding_not_allowed(case):
    seed(case)
    db(case, "INSERT INTO app.billingpayment (payment_intent,user_id,source_id,revoked) VALUES ('pi_1','u1','pi_1',true)")
    allowed, _, status, expires, _, fulfilled, _ = run(case)
    assert (allowed, status, expires, fulfilled) == (False, 'expired', 0, True)


def test_binding_to_other_user_raises(case):
    from app.services.membership_fulfilment import PaymentBindingError
    seed(case)
    seed(case, user='u2', checkout='co2')
    db(case, "INSERT INTO app.billingpayment (payment_intent,user_id,source_id,revoked) VALUES ('pi_1','u2','pi_1',false)")
    with pytest.raises(PaymentBindingError) as caught:
        run(case)
    assert caught.value.code == 'payment_binding_mismatch'


def test_missing_payment_intent_raises(case):
    from app.services.membership_fulfilment import PaymentBindingError
    seed(case)
    with pytest.raises(PaymentBindingError) as caught:
        run(case, payment_intent=None)
    assert caught.value.code == 'payment_binding_absent'
