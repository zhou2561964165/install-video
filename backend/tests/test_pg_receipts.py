"""Receipt compatibility, protected history and rejection composition on PG."""
import json
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from test_pg_download_submission import pg, post, facts, assert_charge, REQUEST, SNAPSHOT, fake_direct
from app.models import DownloadIdempotency, DownloadOperation, Job, JobStatus, Quota, ResourceCounter
from app.models import Membership
from app.schemas import DownloadResponse
from app.services import download_submission as service


@pytest.mark.parametrize('key', ['', 'a' * 129, 'with space', '\n', '非ASCII'])
def test_invalid_key_does_not_accept(pg, key):
    with pytest.raises(HTTPException) as error:
        post(pg, key)
    assert error.value.status_code == 422
    assert all(count == 0 for count in facts(pg).values())


def test_existing_key_replays_when_slot_and_receipt_capacity_full(pg, monkeypatch):
    monkeypatch.setattr(service.settings, 'download_admission_global_limit', 1)
    monkeypatch.setattr(service.settings, 'download_idempotency_max_entries', 1)
    response = post(pg)
    assert post(pg) == response
    with pytest.raises(HTTPException) as error:
        post(pg, 'new')
    assert error.value.detail['error_type'] == 'idempotency_unavailable'
    assert_charge(pg)


def test_quota_rejection_receipt_has_no_operation_slot_or_partial_charge(pg, monkeypatch):
    monkeypatch.setattr(service.settings, 'default_quota_limit', 0)
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            post(pg)
        assert error.value.status_code == 429
        assert error.value.headers == {'Idempotency-Status': 'complete'}
    state = facts(pg)
    assert state['downloadidempotency'] == 1
    assert all(value == 0 for name, value in state.items() if name != 'downloadidempotency')
    with Session(pg) as session:
        assert session.exec(select(DownloadIdempotency)).one().operation_id is None
        assert session.get(ResourceCounter, ('receipt_entries', 'global')).used == 1
        assert session.get(ResourceCounter, ('admission_slots', 'global')).used == 0


def test_capacity_rejection_completes_error_without_new_operation(pg, monkeypatch):
    monkeypatch.setattr(service.settings, 'download_admission_global_limit', 1)
    original = post(pg)
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            post(pg, 'new')
        assert error.value.status_code == 503 and error.value.detail['error_type'] == 'download_capacity'
        assert error.value.headers['Idempotency-Status'] == 'complete'
    assert post(pg) == original
    assert facts(pg)['downloadoperation'] == 1 and facts(pg)['downloadidempotency'] == 2
    assert_charge(pg)


def test_preaccept_error_commit_ack_loss_resolves_receipt_not_absence(pg, monkeypatch):
    monkeypatch.setattr(service.settings, 'default_quota_limit', 0)
    original = Session.commit
    calls = []
    def ack_lost(session):
        original(session)
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError('synthetic ACK loss')
    monkeypatch.setattr(Session, 'commit', ack_lost)
    with pytest.raises(HTTPException) as error:
        post(pg)
    assert error.value.status_code == 429 and calls == [1]
    assert facts(pg)['downloadidempotency'] == 1 and facts(pg)['downloadoperation'] == 0


@pytest.mark.parametrize('state', ['pending', 'uncertain'])
def test_legacy_protected_receipts_never_expire_or_create_operation(pg, state):
    payload, fingerprint = service.canonical_request(REQUEST)
    with Session(pg) as session:
        session.add(DownloadIdempotency(id='b4-legacy', user_id='b4-user', key='same', fingerprint=fingerprint,
                    state=state, created_at=0, expires_at=0))
        session.get(ResourceCounter, ('receipt_entries', 'global')).used = 1
        session.commit()
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            post(pg)
        assert error.value.status_code == (409 if state == 'pending' else 503)
    assert facts(pg)['downloadoperation'] == facts(pg)['quotacharge'] == facts(pg)['job'] == 0
    with Session(pg) as session:
        row = session.get(DownloadIdempotency, 'b4-legacy')
        assert row.state == state and row.created_at == row.expires_at == 0 and row.operation_id is None
        assert session.get(ResourceCounter, ('receipt_entries', 'global')).used == 1


def test_complete_ttl_deletes_once_releases_counter_and_key_keeps_operation_history(pg):
    first = post(pg)
    with Session(pg) as session:
        receipt = session.exec(select(DownloadIdempotency)).one()
        oldid = receipt.id
        receipt.expires_at = 0
        session.add(receipt)
        session.commit()
    second = post(pg)
    assert first.job_id != second.job_id
    assert_charge(pg, 2, 2)
    with Session(pg) as session:
        assert session.get(DownloadIdempotency, oldid) is None
        assert len(session.exec(select(DownloadOperation)).all()) == 2
        assert len(session.exec(select(DownloadIdempotency)).all()) == 1
        assert session.get(ResourceCounter, ('receipt_entries', 'global')).used == 1


@pytest.mark.parametrize('change', ['expired', 'missing', 'error'])
def test_server_replay_expired_missing_410_error_keeps_original_job_id(pg, change):
    response = post(pg)
    with Session(pg) as session:
        job = session.get(Job, response.job_id)
        if change == 'error':
            job.status = JobStatus.error
        elif change == 'expired':
            job.expires_at = session.exec(select(func.clock_timestamp())).one() - timedelta(seconds=1)
        else:
            # Reflect a cleaner-cleared reference while preserving opaque tombstone.
            op = session.exec(select(DownloadOperation)).one()
            op.job_id = None
            session.add(op)
            access = session.get(__import__('app.models', fromlist=['DownloadAccess']).DownloadAccess, job.id)
            session.delete(access)
            session.flush()
            session.delete(job)
        session.commit()
    if change == 'error':
        assert post(pg) == response
    else:
        with pytest.raises(HTTPException) as error:
            post(pg)
        assert error.value.status_code == 410
    assert_charge(pg)


def test_direct_replay_never_renews_window_or_calls_resolver(pg):
    request = REQUEST.model_copy(update={'force_server': False})
    post(pg, request=request, trusted_resolver=fake_direct)
    with Session(pg) as session:
        row = session.exec(select(DownloadIdempotency)).one()
        row.direct_expires_at = 0
        session.add(row)
        session.commit()
    with pytest.raises(HTTPException) as error:
        post(pg, request=request, trusted_resolver=lambda *_: pytest.fail('expired replay must not GET'))
    assert error.value.status_code == 410
    assert_charge(pg, slots=0)


def test_key_user_isolation(pg):
    first = post(pg)
    second = service.submit_download(pg, 'b4-other', REQUEST, 'same', SNAPSHOT)
    assert first.job_id != second.job_id
    assert_charge(pg, 2, 2)


@pytest.mark.parametrize('mode', ['server', 'direct'])
def test_old_key_replay_survives_membership_revision_change_and_direct_adapter_outage(pg, mode):
    request = REQUEST.model_copy(update={'force_server': mode == 'server'})
    response = post(pg, request=request, trusted_resolver=fake_direct)
    with Session(pg) as session:
        member = session.get(Membership, 'b4-user')
        member.revision += 1
        session.add(member)
        session.commit()
    assert post(pg, request=request) == response
    assert_charge(pg, slots=1 if mode == 'server' else 0)


@pytest.mark.parametrize('state', ['pending', 'uncertain'])
def test_legacy_pending_and_uncertain_semantics_precede_snapshot_change(pg, state):
    payload, fingerprint = service.canonical_request(REQUEST)
    with Session(pg) as session:
        session.add(Membership(user_id='b4-user', revision=9))
        session.add(DownloadIdempotency(id='b4-legacy', user_id='b4-user', key='same', fingerprint=fingerprint,
                    state=state, created_at=0))
        session.get(ResourceCounter, ('receipt_entries', 'global')).used = 1
        session.commit()
    with pytest.raises(HTTPException) as error:
        post(pg)
    assert error.value.detail['error_type'] == ('idempotency_in_progress' if state == 'pending' else 'idempotency_uncertain')
    assert facts(pg)['downloadoperation'] == 0


def test_existing_replay_commit_ack_loss_returns_original_response(pg, monkeypatch):
    response = post(pg)
    original = Session.commit
    calls = []
    def ack_lost(session):
        original(session)
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError('synthetic old-key replay ACK loss')
    monkeypatch.setattr(Session, 'commit', ack_lost)
    assert post(pg) == response
    assert calls == [1]
    assert_charge(pg)


def test_new_key_reclaims_other_expired_complete_receipt_at_full_capacity(pg, monkeypatch):
    monkeypatch.setattr(service.settings, 'download_idempotency_max_entries', 1)
    first = post(pg, key='old')
    with Session(pg) as session:
        row = session.exec(select(DownloadIdempotency)).one()
        oldid = row.id
        row.expires_at = 0
        session.add(row)
        session.commit()
    second = post(pg, key='new')
    assert first.job_id != second.job_id
    assert_charge(pg, 2, 2)
    with Session(pg) as session:
        assert session.get(DownloadIdempotency, oldid) is None
        assert session.exec(select(DownloadIdempotency)).one().key == 'new'
        assert session.get(ResourceCounter, ('receipt_entries', 'global')).used == 1


def test_legacy_uncertain_response_is_preserved_verbatim(pg):
    _, fingerprint = service.canonical_request(REQUEST)
    detail = {'error_type': 'idempotency_uncertain', 'error': '下载提交状态未确定，请保留原请求标识，勿重复提交新任务'}
    with Session(pg) as session:
        session.add(DownloadIdempotency(id='b4-legacy', user_id='b4-user', key='same', fingerprint=fingerprint,
            state='uncertain', created_at=0, status_code=503, response_json=json.dumps({'detail': detail})))
        session.get(ResourceCounter, ('receipt_entries', 'global')).used = 1
        session.commit()
    with pytest.raises(HTTPException) as error:
        post(pg)
    assert error.value.status_code == 503 and error.value.detail == detail and error.value.headers is None
    assert facts(pg)['downloadoperation'] == 0


def test_two_users_new_keys_compete_after_other_user_expired_receipt_cleanup(pg):
    import multiprocessing
    from test_pg_download_submission import competing_post
    _, fingerprint = service.canonical_request(REQUEST)
    with Session(pg) as session:
        session.add(DownloadIdempotency(id='b4-old-complete', user_id='b4-other', key='old',
            fingerprint=fingerprint, state='complete', created_at=0, expires_at=0,
            status_code=503, response_json='{"detail":{"error_type":"download_capacity","error":"synthetic"}}'))
        session.get(ResourceCounter, ('receipt_entries', 'global')).used = 1
        session.commit()
    context = multiprocessing.get_context('spawn')
    barrier, output = context.Barrier(2), context.Queue()
    processes = [context.Process(target=competing_post, args=('new', 'synthetic', barrier, output, uid, 1))
                 for uid in ('b4-user', 'b4-other')]
    try:
        for process in processes:
            process.start()
        results = [output.get(timeout=30) for _ in processes]
        for process in processes:
            process.join(15)
            assert process.exitcode == 0
        assert len({row['pid'] for row in results}) == 2
        assert sorted(row['status'] for row in results) == [200, 503]
        assert_charge(pg)
        with Session(pg) as session:
            assert session.get(DownloadIdempotency, 'b4-old-complete') is None
            assert len(session.exec(select(DownloadIdempotency)).all()) == 1
            assert session.get(ResourceCounter, ('receipt_entries', 'global')).used == 1
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(10)
        output.close()
