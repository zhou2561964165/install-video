"""B2 quota ownership, frozen DB UTC acceptance and real process arbitration."""
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, select

from b2_pg_helpers import clear, compete, engine, operation, user
from app.models import DownloadOperation, Quota, QuotaCharge
from app.services import quota


@pytest.fixture
def pg(monkeypatch):
    instance = engine()
    monkeypatch.setattr(quota.settings, 'membership_unlimited_downloads', False)
    monkeypatch.setattr(quota, 'is_unlimited_user', lambda _: False)
    try:
        with Session(instance) as session:
            user(session)
            user(session, 'b2-other')
            session.commit()
        yield instance
    finally:
        clear(instance)
        instance.dispose()


@pytest.mark.parametrize('existing_row', [False, True])
def test_two_independent_processes_user_limit_one(pg, existing_row):
    if existing_row:
        with Session(pg) as session:
            day = session.exec(text("SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD')")).one()[0]
            session.add(Quota(user_id='b2-user', date=day, downloads_used=0, limit=1))
            session.commit()
    assert compete('quota', [('b2-user','b2-op-one'),('b2-user','b2-op-two')]) == [200,429]
    with Session(pg) as session:
        rows = session.exec(select(Quota)).all()
        assert len(rows) == 1 and rows[0].downloads_used == rows[0].limit == 1
        assert len(session.exec(select(QuotaCharge)).all()) == 1
        assert len(session.exec(select(DownloadOperation)).all()) == 1


def test_repeated_charge_one_fact_one_increment(pg):
    with Session(pg) as session:
        op = operation(session)
        first = quota.charge_submission(session, op.user_id, op.id, op.accepted_at)
        second = quota.charge_submission(session, op.user_id, op.id, op.accepted_at)
        assert first is second
        session.commit()
    with Session(pg) as session:
        op = session.get(DownloadOperation,'b2-op')
        quota.charge_submission(session,op.user_id,op.id,op.accepted_at)
        session.commit()
    with Session(pg) as session:
        assert session.exec(select(Quota)).one().downloads_used == 1


@pytest.mark.parametrize('unlimited', ['membership','development'])
def test_unlimited_preserves_configured_limit_and_counts(pg, monkeypatch, unlimited):
    if unlimited == 'membership':
        monkeypatch.setattr(quota.settings,'membership_unlimited_downloads',True)
    else:
        monkeypatch.setattr(quota,'is_unlimited_user',lambda uid: uid=='b2-user')
    with Session(pg) as session:
        op = operation(session)
        session.add(Quota(user_id=op.user_id,date=op.quota_day.isoformat(),downloads_used=5,limit=1))
        session.flush()
        quota.charge_submission(session,op.user_id,op.id,op.accepted_at)
        session.commit()
    with Session(pg) as session:
        row = session.exec(select(Quota)).one()
        assert row.downloads_used == 6 and row.limit == 1


def test_recovery_after_midnight_keeps_database_acceptance_day(pg):
    with Session(pg) as session:
        accepted = session.exec(text("SELECT date_trunc('day',clock_timestamp()) - interval '1 microsecond'")).one()[0]
        op = operation(session,accepted_at=accepted)
        quota.charge_submission(session,op.user_id,op.id,op.accepted_at)
        session.commit()
    with Session(pg) as session:
        op = session.get(DownloadOperation,'b2-op')
        quota.charge_submission(session,op.user_id,op.id,op.accepted_at)
        session.commit()
    with Session(pg) as session:
        row = session.exec(select(Quota)).one()
        assert row.date == accepted.date().isoformat() and row.downloads_used == 1


@pytest.mark.parametrize('change', ['user','day','time','naive'])
def test_wrong_operation_binding_rejects_without_charge(pg, change):
    with Session(pg) as session:
        op = operation(session)
        userid, accepted = op.user_id, op.accepted_at
        if change == 'user':
            userid = 'b2-other'
        elif change == 'day':
            from datetime import timedelta
            op.quota_day += timedelta(days=1)
        elif change == 'time':
            from datetime import timedelta
            accepted += timedelta(seconds=1)
        else:
            accepted = accepted.replace(tzinfo=None)
        with pytest.raises(HTTPException) as caught:
            quota.charge_submission(session,userid,op.id,accepted)
        assert caught.value.status_code == 409
    with Session(pg) as session:
        assert not session.exec(select(QuotaCharge)).all()
        assert not session.exec(select(Quota)).all()


def test_charge_does_not_commit_caller_transaction(pg):
    with Session(pg) as session:
        op = operation(session)
        quota.charge_submission(session,op.user_id,op.id,op.accepted_at)
        session.rollback()
    with Session(pg) as session:
        assert not session.exec(select(QuotaCharge)).all()
        assert not session.exec(select(Quota)).all()


def test_legacy_pg_wrapper_fails_closed_without_fabricating_operation(pg):
    with Session(pg) as session, pytest.raises(RuntimeError, match='require charge_submission'):
        quota.check_and_reserve(session,'b2-user')
