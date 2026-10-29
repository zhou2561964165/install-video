"""B2 counter arbitration and one-time reservation/release on real PG."""
import pytest
from fastapi import HTTPException
from sqlalchemy import delete, event, text, update
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from b2_pg_helpers import clear, compete, engine, operation, race_release, user
from app.models import DownloadIdempotency, DownloadOperation, ResourceCounter, ResourceReservation
from app.services import resource_capacity as cap
from app.services.db_transactions import lock_user


@pytest.fixture
def pg(monkeypatch):
    instance = engine()
    monkeypatch.setattr(cap.settings, 'download_admission_global_limit', 32)
    monkeypatch.setattr(cap.settings, 'download_admission_user_limit', 2)
    monkeypatch.setattr(cap.settings, 'download_idempotency_max_entries', 2)
    try:
        with Session(instance) as session:
            user(session)
            user(session, 'b2-other')
            session.commit()
        yield instance
    finally:
        with Session(instance) as session:
            session.exec(delete(DownloadIdempotency).where(DownloadIdempotency.id.startswith('b2-')))
            session.commit()
        clear(instance)
        instance.dispose()


def demands(uid='b2-user'):
    return (cap.CapacityDemand('admission_slots', 'user:'+uid), cap.CapacityDemand('admission_slots', 'global'))


def accepted(pg):
    with Session(pg) as session:
        cap.lock_capacity_counters(session, demands())
        lock_user(session, 'b2-user')
        operation(session)
        cap.reserve_capacity(session, demands(), operation_id='b2-op')
        session.commit()


def test_two_independent_processes_global_capacity_one(pg):
    assert compete('capacity', [('b2-user', 'b2-op-one'), ('b2-other', 'b2-op-two')]) == [200, 503]
    with Session(pg) as session:
        assert session.get(ResourceCounter, ('admission_slots', 'global')).used == 1
        assert len(session.exec(select(DownloadOperation)).all()) == 1


def test_same_operation_reserve_and_release_once(pg):
    accepted(pg)
    with Session(pg) as session:
        cap.reserve_capacity(session, demands(), operation_id='b2-op')
        session.commit()
    for _ in range(2):
        with Session(pg) as session:
            cap.release_capacity(session, 'b2-op', ('admission_slots',))
            session.commit()
    with Session(pg) as session:
        assert all(row.used == 0 for row in session.exec(select(ResourceCounter)).all())
        facts = session.exec(select(ResourceReservation)).all()
        assert len(facts) == 2 and all(row.released and row.released_at for row in facts)
        assert session.get(DownloadOperation, 'b2-op').capacity_reserved is False
    with Session(pg) as session, pytest.raises(HTTPException):
        cap.reserve_capacity(session, demands(), operation_id='b2-op')


def test_underflow_rejects_and_rolls_back_whole_release(pg):
    accepted(pg)
    with Session(pg) as session:
        session.exec(update(ResourceCounter).where(ResourceCounter.scope == 'user:b2-user').values(used=0))
        session.commit()
    with Session(pg) as session, pytest.raises(HTTPException):
        cap.release_capacity(session, 'b2-op', ('admission_slots',))
    with Session(pg) as session:
        assert session.get(ResourceCounter, ('admission_slots', 'global')).used == 1
        assert all(not row.released for row in session.exec(select(ResourceReservation)).all())
        assert session.get(DownloadOperation, 'b2-op').capacity_reserved


def test_global_missing_fails_closed_without_upsert(pg):
    with Session(pg) as session:
        session.exec(delete(ResourceCounter).where(ResourceCounter.resource == 'admission_slots'))
        with pytest.raises(HTTPException) as caught:
            cap.lock_capacity_counters(session, demands())
        assert caught.value.detail['error_type'] == 'download_capacity'
        session.rollback()


def test_dictionary_lock_order_no_count_inventory(pg):
    statements, keys = [], []
    def trace(connection, cursor, statement, parameters, context, many):
        statements.append(statement.lower())
        if 'FOR UPDATE' in statement and 'resourcecounter' in statement:
            keys.append((parameters['resource_1'], parameters['scope_1']))
    event.listen(pg, 'before_cursor_execute', trace)
    try:
        with Session(pg) as session:
            cap.lock_capacity_counters(session, (cap.CapacityDemand('receipt_entries','global'), *demands()))
    finally:
        event.remove(pg, 'before_cursor_execute', trace)
    assert keys == sorted(keys) and len(keys) == 3
    assert not any('count(' in statement for statement in statements)


def test_domain_then_new_resource_rejected_tracking_cleared(pg):
    with Session(pg) as session:
        lock_user(session, 'b2-user')
        with pytest.raises(RuntimeError, match='before domain'):
            cap.lock_capacity_counters(session, demands())
        session.rollback()
        assert not any(key.startswith('b2_') for key in session.info)
        cap.lock_capacity_counters(session, demands())


def test_wrong_user_scope_reservation_rollback(pg):
    with Session(pg) as session:
        cap.lock_capacity_counters(session, demands('b2-other'))
        operation(session)
        with pytest.raises(HTTPException):
            cap.reserve_capacity(session, demands('b2-other'), operation_id='b2-op')
    with Session(pg) as session:
        assert session.get(ResourceCounter, ('admission_slots', 'global')).used == 0
        assert session.get(DownloadOperation, 'b2-op') is None


@pytest.mark.parametrize('units', [0, -1, True, 100001, 1.5])
def test_units_are_positive_bounded_integer(pg, units):
    with Session(pg) as session, pytest.raises(ValueError):
        cap.lock_capacity_counters(session, (cap.CapacityDemand('admission_slots','global',units),))


def test_receipt_has_independent_counter_and_underflow_rejected(pg):
    with Session(pg) as session:
        cap.reserve_receipt_entry(session)
        cap.reserve_receipt_entry(session)
        session.commit()
    with Session(pg) as session, pytest.raises(HTTPException) as caught:
        cap.reserve_receipt_entry(session)
    assert caught.value.detail['error_type'] == 'idempotency_unavailable'
    with Session(pg) as session:
        cap.release_receipt_entry(session)
        cap.release_receipt_entry(session)
        session.commit()
    with Session(pg) as session, pytest.raises(HTTPException):
        cap.release_receipt_entry(session)
    with Session(pg) as session:
        assert session.get(ResourceCounter, ('admission_slots','global')).used == 0
        assert session.get(ResourceCounter, ('receipt_entries','global')).used == 0


def test_prelock_resource_then_user_then_new_op(pg):
    accepted(pg)
    with Session(pg) as session:
        assert session.get(ResourceCounter, ('admission_slots','user:b2-user')).used == 1
        assert session.get(ResourceCounter, ('admission_slots','global')).used == 1


def test_release_rereads_reservation_committed_after_early_discovery(pg):
    with Session(pg) as session:
        operation(session)
        session.commit()
    race_release()
    with Session(pg) as session:
        assert all(row.used==0 for row in session.exec(select(ResourceCounter)).all())
        facts = session.exec(select(ResourceReservation)).all()
        assert len(facts)==2 and all(row.released for row in facts)
        assert not session.get(DownloadOperation,'b2-op').capacity_reserved


@pytest.mark.parametrize('scope', ['global','user:b2-user'])
def test_admission_requires_both_scopes(pg, scope):
    with Session(pg) as session:
        operation(session)
        with pytest.raises(HTTPException):
            cap.reserve_capacity(session,(cap.CapacityDemand('admission_slots',scope),),operation_id='b2-op')


def test_terminal_operation_cannot_be_reserved(pg):
    with Session(pg) as session:
        op=operation(session)
        op.state='failed'
        session.flush()
        with pytest.raises(HTTPException):
            cap.reserve_capacity(session,demands(),operation_id='b2-op')


def test_user_capacity_limit_preserves_existing_global_slot(pg, monkeypatch):
    monkeypatch.setattr(cap.settings,'download_admission_user_limit',1)
    accepted(pg)
    with Session(pg) as session, pytest.raises(HTTPException):
        cap.lock_capacity_counters(session,demands())
        operation(session,opid='b2-second')
        cap.reserve_capacity(session,demands(),operation_id='b2-second')
    with Session(pg) as session:
        assert session.get(ResourceCounter,('admission_slots','global')).used==1
        assert session.get(ResourceCounter,('admission_slots','user:b2-user')).used==1
        assert session.get(DownloadOperation,'b2-second') is None


def test_pair_units_must_match(pg):
    with Session(pg) as session:
        operation(session)
        with pytest.raises(HTTPException):
            cap.reserve_capacity(session,(cap.CapacityDemand('admission_slots','global',2),
                cap.CapacityDemand('admission_slots','user:b2-user',1)),operation_id='b2-op')


def test_first_user_lock_after_operation_lock_rejected(pg):
    with Session(pg) as session:
        operation(session)
        cap.reserve_capacity(session,demands(),operation_id='b2-op')
        with pytest.raises(RuntimeError,match='before operation'):
            lock_user(session,'b2-user')


def test_reservation_units_conflict_never_changes_counter(pg):
    accepted(pg)
    with Session(pg) as session, pytest.raises(HTTPException):
        cap.reserve_capacity(session, (cap.CapacityDemand('admission_slots','global',2),
            cap.CapacityDemand('admission_slots','user:b2-user',2)), operation_id='b2-op')
    with Session(pg) as session:
        assert session.get(ResourceCounter, ('admission_slots','global')).used == 1
        assert session.get(ResourceCounter, ('admission_slots','user:b2-user')).used == 1
        assert all(row.units==1 for row in session.exec(select(ResourceReservation)).all())


def test_cached_reservation_cannot_reopen_after_other_session_release(pg):
    accepted(pg)
    with Session(pg) as original:
        cached_op = original.get(DownloadOperation,'b2-op')
        cached_fact = original.get(ResourceReservation,('b2-op','admission_slots','global'))
        assert cached_op.capacity_reserved and not cached_fact.released
        with Session(pg) as other:
            cap.release_capacity(other,'b2-op',('admission_slots',))
            other.commit()
        with pytest.raises(HTTPException):
            cap.reserve_capacity(original,demands(),operation_id='b2-op')
        original.rollback()
    with Session(pg) as session:
        assert not session.get(DownloadOperation,'b2-op').capacity_reserved
        assert all(row.released for row in session.exec(select(ResourceReservation)).all())
        assert all(row.used==0 for row in session.exec(select(ResourceCounter)).all())


def test_cached_active_operation_refreshed_after_other_session_terminal(pg):
    with Session(pg) as session:
        operation(session)
        session.commit()
    with Session(pg) as original:
        cached_op = original.get(DownloadOperation,'b2-op')
        assert cached_op.state=='resolving'
        with Session(pg) as other:
            other.exec(update(DownloadOperation).where(DownloadOperation.id=='b2-op').values(state='failed'))
            other.commit()
        with pytest.raises(HTTPException):
            cap.reserve_capacity(original,demands(),operation_id='b2-op')
        original.rollback()
    with Session(pg) as session:
        assert not session.exec(select(ResourceReservation)).all()
        assert session.get(DownloadOperation,'b2-op').state=='failed'


def test_savepoint_rollback_restores_only_still_held_lock_tracking(pg):
    with Session(pg) as session:
        cap.lock_capacity_counters(session,(cap.CapacityDemand('admission_slots','global'),))
        with pytest.raises(RuntimeError,match='synthetic savepoint abort'):
            with session.begin_nested():
                cap.lock_capacity_counters(session,demands())
                lock_user(session,'b2-user')
                raise RuntimeError('synthetic savepoint abort')
        assert session.info['b2_capacity_locks']=={('admission_slots','global')}
        assert not session.info.get('b2_locked_users') and not session.info.get('b2_domain_started')
        # The actual PG row lock acquired inside the savepoint was released.
        with Session(pg) as other:
            other.exec(text('SELECT id FROM app."user" WHERE id=\'b2-user\' FOR UPDATE NOWAIT')).one()
        cap.lock_capacity_counters(session,(*demands(),cap.CapacityDemand('receipt_entries','global')))
        assert len(session.info['b2_capacity_locks'])==3


def test_receipt_insert_delete_and_counter_share_caller_transaction(pg):
    receipt_id = 'b2-receipt-atomic'
    receipt_demand = (cap.CapacityDemand('receipt_entries', 'global'),)

    def insert_receipt(session):
        cap.reserve_receipt_entry(session)
        lock_user(session, 'b2-user')
        session.add(DownloadIdempotency(id=receipt_id, user_id='b2-user', key='synthetic',
                                        fingerprint='b'*64, state='pending'))
        session.flush()

    def delete_receipt(session):
        cap.lock_capacity_counters(session, receipt_demand)
        lock_user(session, 'b2-user')
        deleted = session.exec(delete(DownloadIdempotency).where(
            DownloadIdempotency.id == receipt_id).returning(DownloadIdempotency.id)).first()
        if deleted is not None:
            cap.release_receipt_entry(session)
        return deleted

    def assert_state(present, used):
        with Session(pg) as check:
            assert (check.get(DownloadIdempotency, receipt_id) is not None) == present
            assert check.get(ResourceCounter, ('receipt_entries', 'global')).used == used

    with Session(pg) as session:
        insert_receipt(session)
        session.rollback()
    assert_state(False, 0)
    with Session(pg) as session:
        insert_receipt(session)
        session.commit()
    assert_state(True, 1)
    with Session(pg) as session:
        assert delete_receipt(session) == (receipt_id,)
        session.rollback()
    assert_state(True, 1)
    with Session(pg) as session:
        assert delete_receipt(session) == (receipt_id,)
        session.commit()
    assert_state(False, 0)
    with Session(pg) as session:
        assert delete_receipt(session) is None
        session.commit()
    assert_state(False, 0)


def test_savepoint_commit_keeps_outer_lock_tracking_and_real_locks(pg):
    with Session(pg) as session:
        cap.lock_capacity_counters(session, (cap.CapacityDemand('admission_slots', 'global'),))
        with session.begin_nested():
            cap.lock_capacity_counters(session, demands())
            lock_user(session, 'b2-user')
        assert session.info['b2_capacity_locks'] == {
            ('admission_slots', 'global'), ('admission_slots', 'user:b2-user')}
        assert session.info['b2_locked_users'] == {'b2-user'} and session.info['b2_domain_started']
        with Session(pg) as other, pytest.raises(OperationalError) as caught:
            other.exec(text('SELECT id FROM app."user" WHERE id=\'b2-user\' FOR UPDATE NOWAIT')).one()
        assert caught.value.orig.sqlstate == '55P03'
        with pytest.raises(RuntimeError, match='before domain'):
            cap.lock_capacity_counters(session, (cap.CapacityDemand('receipt_entries', 'global'),))
        session.rollback()
        assert not any(key in session.info for key in ('b2_capacity_locks', 'b2_locked_users', 'b2_domain_started'))
