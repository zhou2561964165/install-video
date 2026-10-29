"""Only the explicitly opted-in task PG. No .env, old SQLite fixture or migration."""
from datetime import timedelta
import json
import os
import re
from pathlib import Path

from sqlalchemy import URL, func, text
from sqlmodel import Session, select

from app import db
from app.models import DownloadOperation, Quota, QuotaCharge, ResourceCounter, ResourceReservation, User


def engine():
    marker = os.environ.get('B2_PG_CONTROL')
    if not marker:
        import pytest
        pytest.skip('B2_PG_CONTROL explicit isolated task PG opt-in required')
    path = Path(marker).resolve()
    expected = Path(r'E:\install_video\.planning\2026-10-24-production-execution\postgres-runtime\control.json').resolve()
    assert path == expected
    control = json.loads(path.read_text('utf8'))
    assert control['host'] == '127.0.0.1' and control['port'] == 62328
    assert control['database'] == 'pv_verify' and control['roles']['application'] == 'pv_app'
    # Default: the frozen pv_verify reference (b1b_0003). Opt-in: a nonce database owned by this
    # run at the current head (C1+), so newer schemas never modify pv_verify.
    database, expected_head = os.environ.get('B2_PG_DATABASE', 'pv_verify'), 'b1b_0003'
    if database != 'pv_verify':
        assert re.fullmatch(r'pv_b3b_[0-9a-f]{12}_[0-9a-f]{8}', database)
        ownership = json.loads(Path(os.environ['B3B_PG_OWNERSHIP']).read_text('utf8'))
        assert any(item['database'] == database and not item['dropped'] for item in ownership['databases'])
        expected_head = os.environ['B2_PG_HEAD']
    secrets = json.loads((path.parent / 'private/credentials.json').read_text('utf8'))
    url = URL.create('postgresql+psycopg', username='pv_app', password=secrets['application'],
                     host='127.0.0.1', port=control['port'], database=database)
    result = db.build_engine(url, role='api')
    del secrets, url
    with result.connect() as connection:
        assert connection.scalar(text('SHOW server_version')) == '18.6'
        assert connection.scalar(text('SHOW transaction_isolation')) == 'read committed'
        assert connection.scalar(text('SELECT version_num FROM app.alembic_version')) == expected_head
    return result


def user(session, name='b2-user'):
    row = User(id=name, email=name+'@synthetic.invalid', password_hash='synthetic-no-login')
    session.add(row)
    session.flush()
    return row


def operation(session, opid='b2-op', userid='b2-user', accepted_at=None):
    now = accepted_at or session.exec(select(func.clock_timestamp())).one()
    # Schema service tests do not consume source budgets or perform network I/O.
    row = DownloadOperation(id=opid, user_id=userid, canonical_payload='{}', fingerprint='b'*64,
        canonical_format_id='synthetic', membership_revision=0, quota_day=now.date(),
        state='resolving', accepted_at=now, deadline_at=now+timedelta(minutes=30),
        resolve_deadline_at=now+timedelta(seconds=60), resolve_attempts_limit=2,
        budget_version=1, budget_checkpoint_json='{"synthetic_no_source_execution":true}',
        budget_checkpoint_at=now)
    session.add(row)
    session.flush()
    return row


def clear(engine):
    with Session(engine) as session:
        for model, column in ((ResourceReservation, ResourceReservation.operation_id),
                              (QuotaCharge, QuotaCharge.operation_id),
                              (DownloadOperation, DownloadOperation.id), (Quota, Quota.user_id), (User, User.id)):
            from sqlalchemy import delete
            session.exec(delete(model).where(column.startswith('b2-')))
        session.exec(text("DELETE FROM app.resourcecounter WHERE scope LIKE 'user:b2-%'"))
        # Only B2 synthetic tests operate in this exclusive, empty cluster.
        session.exec(text("UPDATE app.resourcecounter SET used=0 WHERE scope='global'"))
        # A missing-seed test rolls back, so the original seeds always remain.
        session.commit()


def competing_worker(kind, uid, opid, barrier, output):
    """Each spawned process builds its own engine and uses a separate DB connection."""
    from fastapi import HTTPException
    from app.services.db_transactions import CommitResolution, ResolutionState, lock_user, run_local_transaction
    from app.services.quota import charge_submission
    from app.services.resource_capacity import CapacityDemand, lock_capacity_counters, reserve_capacity
    from app.services import resource_capacity
    from app.services import quota
    instance = engine()
    resource_capacity.settings.download_admission_global_limit = 1
    resource_capacity.settings.download_admission_user_limit = 2
    quota.settings.default_quota_limit = 1
    quota.settings.membership_unlimited_downloads = False
    barrier.wait(timeout=15)
    def action(session):
        demands = (CapacityDemand('admission_slots', 'user:'+uid), CapacityDemand('admission_slots', 'global'))
        if kind == 'capacity':
            lock_capacity_counters(session, demands)
        lock_user(session, uid)
        op = operation(session, opid, uid)
        if kind == 'capacity':
            reserve_capacity(session, demands, operation_id=opid)
        else:
            charge_submission(session, uid, opid, op.accepted_at)
        return 200
    try:
        result = run_local_transaction(instance, opid, action,
            lambda *_: CommitResolution(ResolutionState.UNKNOWN))
        output.put({'status': result, 'pid': os.getpid()})
    except HTTPException as error:
        output.put({'status': error.status_code, 'error_type': error.detail['error_type'], 'pid': os.getpid()})
    except Exception:
        output.put({'status': 'unexpected', 'pid': os.getpid()})
    finally:
        instance.dispose()


def compete(kind, inputs):
    import multiprocessing
    context = multiprocessing.get_context('spawn')
    barrier, output = context.Barrier(2), context.Queue()
    processes = [context.Process(target=competing_worker, args=(kind, uid, opid, barrier, output))
                 for uid, opid in inputs]
    try:
        for process in processes:
            process.start()
        results = [output.get(timeout=30) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        assert len({item['pid'] for item in results}) == 2
        return sorted(item['status'] for item in results)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)
        output.close()


def release_race_worker(role, ready, continue_release, output):
    """Pause releasing process after immutable user discovery, before counters."""
    from sqlalchemy import event
    from app.services import resource_capacity as cap
    instance = engine()
    demands = (cap.CapacityDemand('admission_slots','global'),
               cap.CapacityDemand('admission_slots','user:b2-user'))
    try:
        if role == 'release':
            def pause_after_discovery(conn, cursor, statement, parameters, context, many):
                if statement.startswith('SELECT downloadoperation.user_id'):
                    ready.set()
                    assert continue_release.wait(15)
            event.listen(instance,'after_cursor_execute',pause_after_discovery)
            with Session(instance) as session:
                cap.release_capacity(session,'b2-op',('admission_slots',))
                session.commit()
        else:
            assert ready.wait(15)
            with Session(instance) as session:
                cap.reserve_capacity(session, demands, operation_id='b2-op')
                session.commit()
            continue_release.set()
        output.put({'status':'ok','pid':os.getpid()})
    except Exception:
        continue_release.set()
        output.put({'status':'failed','pid':os.getpid()})
    finally:
        instance.dispose()


def race_release():
    import multiprocessing
    context = multiprocessing.get_context('spawn')
    ready, continued, output = context.Event(), context.Event(), context.Queue()
    processes = [context.Process(target=release_race_worker,args=(role,ready,continued,output))
                 for role in ('release','reserve')]
    try:
        for process in processes:
            process.start()
        results = [output.get(timeout=30) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        assert len({item['pid'] for item in results}) == 2
        assert all(item['status']=='ok' for item in results)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)
        output.close()
