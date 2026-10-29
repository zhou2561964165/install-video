"""B2 runner, real PG rollback/commit boundaries, no external business calls."""
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from b2_pg_helpers import clear, engine, operation, user
from app.models import QuotaCharge, User
from app.services import db_transactions as tx
from app.services.quota import charge_submission


@pytest.fixture
def pg():
    instance = engine()
    try:
        yield instance
    finally:
        clear(instance)
        instance.dispose()


class Abort(Exception):
    def __init__(self, state):
        self.sqlstate = state


def injected(state=None):
    return OperationalError('sensitive SQL', {'password': 'not-a-real-secret'}, Abort(state),
                            connection_invalidated=state is None)


@pytest.mark.parametrize('state', ['40P01', '40001', '55P03'])
def test_known_action_abort_retries_after_real_rollback(pg, state):
    tries, pauses = [], []
    def action(session):
        tries.append(session)
        user(session)
        if len(tries) < 3:
            raise injected(state)
        return 'complete'
    assert tx.run_local_transaction(pg, 'b2-op', action, lambda *_: pytest.fail('not unknown'),
                                    sleeper=pauses.append, jitter=lambda: 0) == 'complete'
    assert len({id(item) for item in tries}) == 3 and pauses == [.02, .1]
    with Session(pg) as session:
        assert len(session.exec(select(User)).all()) == 1


@pytest.mark.parametrize('state', ['40P01', '40001', '55P03'])
def test_retry_exhausted_safe_and_three_attempts(pg, state):
    tries, pauses = [], []
    def action(session):
        tries.append(1)
        user(session)
        raise injected(state)
    with pytest.raises(HTTPException) as caught:
        tx.run_local_transaction(pg, 'b2-op', action, lambda *_: None,
                                 sleeper=pauses.append, jitter=lambda: 1)
    assert len(tries) == 3 and pauses == [.04, .2]
    assert caught.value.status_code == 503 and caught.value.__suppress_context__
    assert caught.value.__context__ is caught.value.__cause__ is None
    assert 'sensitive' not in str(caught.value.detail)
    with Session(pg) as session:
        assert session.get(User, 'b2-user') is None


def test_commit_really_finishes_then_ack_lost_resolves_without_replay(pg, monkeypatch):
    real_commit, actions, resolved = Session.commit, [], []
    def lose_ack(session):
        real_commit(session)
        raise injected()
    def action(session):
        actions.append(1)
        user(session)
        op = operation(session)
        charge_submission(session, op.user_id, op.id, op.accepted_at)
        return 'original'
    def resolve(session, opid):
        resolved.append(session)
        assert session.exec(text('SHOW transaction_read_only')).one()[0] == 'on'
        charge = session.get(QuotaCharge, opid)
        assert charge and charge.delta == 1
        return tx.CommitResolution(tx.ResolutionState.COMMITTED, None)
    monkeypatch.setattr(Session, 'commit', lose_ack)
    assert tx.run_local_transaction(pg, 'b2-op', action, resolve) is None
    assert len(actions) == len(resolved) == 1


@pytest.mark.parametrize('resolver_kind', ['unknown', 'raises', 'invalid'])
def test_unknown_commit_never_replays(pg, monkeypatch, resolver_kind):
    actions = []
    def fail_commit(session):
        raise injected()
    def action(session):
        actions.append(1)
        user(session)
    def resolve(session, opid):
        # A fresh read finding no row still does NOT prove the failed COMMIT
        # rolled back. Only the explicit rollback fault test may say ROLLED_BACK.
        assert session.get(User,'b2-user') is None
        if resolver_kind == 'raises':
            raise injected()
        if resolver_kind == 'invalid':
            return 'rolled_back'
        return tx.CommitResolution(tx.ResolutionState.UNKNOWN)
    monkeypatch.setattr(Session, 'commit', fail_commit)
    with pytest.raises(HTTPException) as caught:
        tx.run_local_transaction(pg, 'b2-op', action, resolve)
    assert actions == [1]
    assert caught.value.detail['error_type'] == 'transaction_uncertain'
    assert caught.value.detail['operation_id'] == 'b2-op'
    assert caught.value.__suppress_context__
    assert caught.value.__context__ is caught.value.__cause__ is None


def test_explicit_rolled_back_after_unknown_can_retry(pg, monkeypatch):
    real_commit, calls, actions = Session.commit, [], []
    def fail_once(session):
        calls.append(1)
        if len(calls) == 1:
            Session.rollback(session)
            raise injected()
        real_commit(session)
    def action(session):
        actions.append(1)
        user(session)
        return 7
    def resolve(session, _):
        assert session.get(User, 'b2-user') is None
        # The fault injector explicitly completed rollback; absence alone is not proof.
        return tx.CommitResolution(tx.ResolutionState.ROLLED_BACK)
    monkeypatch.setattr(Session, 'commit', fail_once)
    assert tx.run_local_transaction(pg, 'b2-op', action, resolve, sleeper=lambda _: None) == 7
    assert len(actions) == 2


@pytest.mark.parametrize('method', ['commit', 'rollback'])
def test_action_cannot_end_runner_transaction(pg, method):
    def action(session):
        user(session)
        getattr(session, method)()
    with pytest.raises(RuntimeError, match='must not'):
        tx.run_local_transaction(pg, 'b2-op', action, lambda *_: None)
    with Session(pg) as session:
        assert session.get(User, 'b2-user') is None


def test_safe_http_rejection_rolls_back_without_retry(pg):
    actions = []
    def action(session):
        actions.append(1)
        user(session)
        raise HTTPException(429, detail={'error_type': 'quota', 'error': 'synthetic'})
    with pytest.raises(HTTPException) as caught:
        tx.run_local_transaction(pg, 'b2-op', action, lambda *_: None)
    assert caught.value.status_code == 429 and actions == [1]
    with Session(pg) as session:
        assert session.get(User, 'b2-user') is None


def test_integrity_conflict_specific_constraint_safe_no_context(pg):
    def action(session):
        user(session)
        operation(session)
        # The second identical primary key is a concrete PG unique conflict.
        session.exec(text("INSERT INTO app.quotacharge(operation_id,user_id,quota_day,delta,charged_at) "
                          "VALUES('b2-op','b2-user',CURRENT_DATE,1,clock_timestamp())"))
        session.exec(text("INSERT INTO app.quotacharge(operation_id,user_id,quota_day,delta,charged_at) "
                          "VALUES('b2-op','b2-user',CURRENT_DATE,1,clock_timestamp())"))
    with pytest.raises(HTTPException) as caught:
        tx.run_local_transaction(pg,'b2-op',action,lambda *_: pytest.fail('not unknown'))
    assert caught.value.status_code==409
    assert caught.value.detail['constraint_code']=='pk_quotacharge'
    assert caught.value.__context__ is caught.value.__cause__ is None


def test_synthetic_secret_exception_graph_discarded(pg):
    sentinel='B2_SYNTHETIC_SECRET_SENTINEL'
    def action(session):
        raise OperationalError(sentinel, {'credential':sentinel}, Abort('08006'))
    with pytest.raises(HTTPException) as caught:
        tx.run_local_transaction(pg,'b2-op',action,lambda *_: None)
    safe=caught.value
    assert safe.__context__ is safe.__cause__ is None
    assert sentinel not in str(safe.__dict__)


def test_failed_rollback_does_not_retry_action(pg, monkeypatch):
    real_rollback, attempts = Session.rollback, []
    def fail_rollback(session):
        real_rollback(session)
        raise RuntimeError('synthetic unconfirmed rollback')
    def action(session):
        attempts.append(1)
        user(session)
        raise injected('40001')
    monkeypatch.setattr(Session,'rollback',fail_rollback)
    with pytest.raises(HTTPException) as caught:
        tx.run_local_transaction(pg,'b2-op',action,lambda *_: pytest.fail('not commit'))
    assert attempts==[1]
    assert caught.value.status_code==503
    assert caught.value.__context__ is caught.value.__cause__ is None


def test_commit_known_abort_retries_only_after_confirmed_rollback(pg, monkeypatch):
    real_commit, actions, commits = Session.commit, [], []
    def fail_once(session):
        commits.append(1)
        if len(commits)==1:
            Session.rollback(session)
            raise injected('40001')
        real_commit(session)
    def action(session):
        actions.append(1)
        user(session)
        return 1
    monkeypatch.setattr(Session,'commit',fail_once)
    assert tx.run_local_transaction(pg,'b2-op',action,lambda *_: pytest.fail('known abort'),
                                    sleeper=lambda _: None)==1
    assert len(actions)==len(commits)==2


def test_unknown_integrity_diag_has_fixed_fallback(pg):
    from sqlalchemy.exc import IntegrityError
    class Detail(Exception):
        class diag:
            constraint_name='B2_SYNTHETIC_SECRET_SENTINEL'
    def action(session):
        raise IntegrityError('B2_SYNTHETIC_SECRET_SENTINEL', {}, Detail())
    with pytest.raises(HTTPException) as caught:
        tx.run_local_transaction(pg,'b2-op',action,lambda *_: None)
    assert caught.value.status_code==409
    assert 'constraint_code' not in caught.value.detail
    assert caught.value.__context__ is caught.value.__cause__ is None
    assert 'B2_SYNTHETIC_SECRET_SENTINEL' not in str(caught.value.__dict__)


def test_savepoint_handles_specific_unique_constraint_without_aborting_outer(pg):
    from sqlalchemy.exc import IntegrityError
    def action(session):
        user(session)
        try:
            with session.begin_nested():
                session.exec(text("INSERT INTO app.\"user\"(id,email,password_hash,created_at) "
                                  "VALUES('b2-user','duplicate@synthetic.invalid','synthetic',clock_timestamp())"))
        except IntegrityError as error:
            assert error.orig.diag.constraint_name=='pk_user'
        return session.get(User,'b2-user').id
    assert tx.run_local_transaction(pg,'b2-op',action,lambda *_: None)=='b2-user'
