"""B4 isolated PG composition tests; never use a live source or user account."""
import hashlib
import json
import multiprocessing
import os
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, event, func, text
from sqlmodel import Session, select

from b2_pg_helpers import engine
from app.models import (DownloadAccess, DownloadIdempotency, DownloadOperation, Job, Membership,
                        Quota, QuotaCharge, ResourceCounter, ResourceReservation, User)
from app.schemas import DownloadRequest, DownloadResponse
from app.services import download_submission as service, quota
from app.services.download_submission import AccessSnapshot, DirectResult, submit_download
from app.services.outbound_httpx import ControlledHttpStatusError
from app.services.outbound_budget import BudgetProfile
from app.services.outbound_policy import OutboundPolicyError

REQUEST = DownloadRequest(url='https://source.synthetic.invalid/video', format_id='synthetic', force_server=True)
SNAPSHOT = AccessSnapshot(720, 0, 'synthetic')


def clear(instance):
    with Session(instance) as session:
        ids = select(DownloadOperation.id).where(DownloadOperation.user_id.startswith('b4-'))
        jobs = select(Job.id).where(Job.user_id.startswith('b4-'))
        session.exec(delete(DownloadIdempotency).where(DownloadIdempotency.user_id.startswith('b4-')))
        session.exec(delete(DownloadAccess).where(DownloadAccess.job_id.in_(jobs)))
        session.exec(delete(ResourceReservation).where(ResourceReservation.operation_id.in_(ids)))
        session.exec(delete(QuotaCharge).where(QuotaCharge.user_id.startswith('b4-')))
        session.exec(delete(DownloadOperation).where(DownloadOperation.user_id.startswith('b4-')))
        session.exec(delete(Job).where(Job.user_id.startswith('b4-')))
        session.exec(delete(Quota).where(Quota.user_id.startswith('b4-')))
        session.exec(delete(Membership).where(Membership.user_id.startswith('b4-')))
        session.exec(delete(User).where(User.id.startswith('b4-')))
        session.exec(delete(ResourceCounter).where(ResourceCounter.scope.startswith('user:b4-')))
        session.exec(text("UPDATE app.resourcecounter SET used=0 WHERE scope='global'"))
        session.commit()


@pytest.fixture
def pg(monkeypatch):
    instance = engine()
    monkeypatch.setattr(service.settings, 'membership_unlimited_downloads', False)
    monkeypatch.setattr(service.settings, 'default_quota_limit', 20)
    monkeypatch.setattr(service.settings, 'download_admission_global_limit', 32)
    monkeypatch.setattr(service.settings, 'download_admission_user_limit', 2)
    monkeypatch.setattr(service.settings, 'download_idempotency_max_entries', 10000)
    monkeypatch.setattr(service, 'is_unlimited_user', lambda _: False)
    monkeypatch.setattr(quota, 'is_unlimited_user', lambda _: False)
    try:
        with Session(instance) as session:
            session.add_all([User(id=uid, email=uid+'@synthetic.invalid', password_hash='synthetic-no-login')
                             for uid in ('b4-user', 'b4-other')])
            session.commit()
        yield instance
    finally:
        clear(instance)
        instance.dispose()


def post(pg, key='same', request=REQUEST, **kwargs):
    return submit_download(pg, 'b4-user', request, key, SNAPSHOT, **kwargs)


def facts(pg):
    with Session(pg) as session:
        return {model.__tablename__: len(session.exec(select(model)).all()) for model in
                (DownloadOperation, DownloadIdempotency, QuotaCharge, Quota, Job, DownloadAccess, ResourceReservation)}


def assert_charge(pg, count=1, slots=1):
    with Session(pg) as session:
        assert len(session.exec(select(QuotaCharge)).all()) == count
        assert sum(row.downloads_used for row in session.exec(select(Quota)).all()) == count
        assert session.get(ResourceCounter, ('admission_slots', 'global')).used == slots


def fake_direct(request, budget):
    for response in budget.begin_get():
        response.consume(raw_bytes=4, decoded_bytes=6)
        response.close()
    return DirectResult(DownloadResponse(mode='direct', url='https://cdn.synthetic.invalid/file'))


def test_snapshot_is_immutable():
    snapshot = AccessSnapshot(720, 0, 'synthetic')
    with pytest.raises(AttributeError):
        snapshot.max_height = None


def test_server_acceptance_and_same_key_replay_are_one_atomic_submission(pg):
    first = post(pg)
    assert first.mode == 'server'
    assert post(pg) == first
    assert facts(pg) == {'downloadoperation': 1, 'downloadidempotency': 1, 'quotacharge': 1,
                        'quota': 1, 'job': 1, 'downloadaccess': 1, 'resourcereservation': 2}
    assert_charge(pg)
    with Session(pg) as session:
        op = session.exec(select(DownloadOperation)).one()
        receipt = session.exec(select(DownloadIdempotency)).one()
        assert op.job_id == op.job_id_tombstone == first.job_id
        assert receipt.operation_id == op.id and receipt.state == 'complete'
        assert op.quota_day == op.accepted_at.date()
        assert op.deadline_at - op.accepted_at == timedelta(minutes=30)
        assert op.resolve_deadline_at - op.accepted_at == timedelta(seconds=60)


def test_no_key_each_post_is_independent(pg):
    assert post(pg, None).job_id != post(pg, None).job_id
    assert_charge(pg, 2, 2)
    assert facts(pg)['downloadidempotency'] == 0


def test_direct_charge_and_slot_committed_before_callback_then_released(pg):
    calls = []
    def source(req, budget):
        assert_charge(pg)
        with Session(pg) as session:
            assert session.exec(select(DownloadIdempotency)).one().state == 'pending'
            assert session.exec(select(Job)).first() is None
        calls.append('GET')
        return fake_direct(req, budget)
    request = REQUEST.model_copy(update={'force_server': False})
    response = post(pg, request=request, trusted_resolver=source)
    assert response.mode == 'direct' and calls == ['GET']
    assert post(pg, request=request, trusted_resolver=lambda *_: pytest.fail('must replay')) == response
    assert_charge(pg, slots=0)
    with Session(pg) as session:
        op = session.exec(select(DownloadOperation)).one()
        data = service.codec.decode_budget(op.budget_version, op.budget_checkpoint_json, resolve_attempts_used=1)
        assert data.download_parent.requests == data.direct_resolve_parent.requests == 1
        assert data.download_parent.raw_bytes == data.direct_resolve_parent.raw_bytes == 4
        assert op.state == 'direct_ready' and op.resolve_owner is None


@pytest.mark.parametrize('kind', ['none', 'timeout', 'connection'])
def test_fallback_reuses_operation_slot_charge_and_consumed_budget(pg, kind):
    def source(req, budget):
        fake_direct(req, budget)
        if kind == 'timeout':
            raise TimeoutError('synthetic-sensitive')
        if kind == 'connection':
            raise ConnectionError('synthetic-sensitive')
        return DirectResult()
    request = REQUEST.model_copy(update={'force_server': False})
    response = post(pg, request=request, trusted_resolver=source)
    assert response.mode == 'server'
    assert_charge(pg)
    assert facts(pg)['job'] == facts(pg)['downloadoperation'] == 1
    with Session(pg) as session:
        op = session.exec(select(DownloadOperation)).one()
        state = service.codec.decode_budget(1, op.budget_checkpoint_json, resolve_attempts_used=1)
        assert state.download_parent.requests == state.direct_resolve_parent.requests == 1
        assert state.download_parent.raw_bytes == 4


@pytest.mark.parametrize('kind', ['412', '401', '403', 'policy', 'session', 'unexpected'])
def test_source_denial_never_falls_back_and_preserves_charge(pg, kind):
    calls = []
    def source(req, budget):
        calls.append('GET')
        fake_direct(req, budget)
        if kind.isdigit():
            raise ControlledHttpStatusError(int(kind))
        if kind == 'policy':
            raise OutboundPolicyError()
        if kind == 'session':
            raise service.SessionError('synthetic expired session')
        raise RuntimeError('synthetic-secret-url')
    request = REQUEST.model_copy(update={'force_server': False})
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            post(pg, request=request, trusted_resolver=source)
        assert error.value.status_code == 422 and error.value.headers['Idempotency-Status'] == 'complete'
        assert 'synthetic-secret' not in str(error.value.detail)
    assert calls == ['GET']
    assert_charge(pg, slots=0)
    assert facts(pg)['job'] == 0


def test_initial_policy_rejection_precedes_receipt_charge_and_callback(pg):
    with pytest.raises(HTTPException) as error:
        post(pg, request=REQUEST.model_copy(update={'url': 'http://127.0.0.1/private'}))
    assert error.value.status_code == 422
    assert all(count == 0 for count in facts(pg).values())


def test_default_direct_resolver_is_closed_before_acceptance(pg):
    with pytest.raises(HTTPException) as error:
        post(pg, request=REQUEST.model_copy(update={'force_server': False}))
    assert error.value.detail['error_type'] == 'outbound_unavailable'
    assert all(count == 0 for count in facts(pg).values())


@pytest.mark.parametrize('change', ['revision', 'expiry', 'format'])
def test_fresh_access_snapshot_change_rejects_without_acceptance(pg, change):
    snapshot = SNAPSHOT
    with Session(pg) as session:
        if change == 'revision':
            session.add(Membership(user_id='b4-user', revision=1))
        elif change == 'expiry':
            session.add(Membership(user_id='b4-user', status='active', expires_at=9999999999))
        session.commit()
    if change == 'format':
        snapshot = AccessSnapshot(720, 0, 'different')
    with pytest.raises(HTTPException) as error:
        submit_download(pg, 'b4-user', REQUEST, 'same', snapshot)
    assert error.value.detail['error_type'] == 'submission_changed'
    assert all(count == 0 for count in facts(pg).values())


@pytest.mark.parametrize('table', ['downloadoperation', 'resourcereservation', 'quotacharge', 'job', 'downloadaccess'])
@pytest.mark.parametrize('when', ['before', 'after'])
def test_each_acceptance_write_failure_rolls_back_every_partial_fact(pg, table, when):
    def fail(conn, cursor, statement, parameters, context, many):
        if statement.lower().startswith('insert into '+table):
            raise RuntimeError('synthetic write failure')
    event.listen(pg, when+'_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='synthetic write failure'):
            post(pg)
    finally:
        event.remove(pg, when+'_cursor_execute', fail)
    assert all(count == 0 for count in facts(pg).values())
    with Session(pg) as session:
        assert all(row.used == 0 for row in session.exec(select(ResourceCounter)).all())


def test_server_commit_ack_loss_recovers_stable_complete_facts(pg, monkeypatch):
    original = Session.commit
    calls = []
    def ack_lost(session):
        calls.append('commit')
        original(session)
        if len(calls) == 1:
            raise ConnectionError('synthetic ACK loss')
    monkeypatch.setattr(Session, 'commit', ack_lost)
    response = post(pg)
    assert response.mode == 'server' and calls == ['commit']
    assert_charge(pg)
    assert facts(pg)['job'] == facts(pg)['downloadoperation'] == 1


@pytest.mark.parametrize('key', [None, 'key'])
def test_direct_terminal_commit_ack_loss_never_probes_twice(pg, monkeypatch, key):
    original = Session.commit
    commits, gets = [], []
    def ack_lost(session):
        commits.append('commit')
        original(session)
        if len(commits) == 3:
            raise ConnectionError('synthetic terminal ACK loss')
    def source(req, budget):
        gets.append('GET')
        return fake_direct(req, budget)
    monkeypatch.setattr(Session, 'commit', ack_lost)
    response = post(pg, key=key, request=REQUEST.model_copy(update={'force_server': False}), trusted_resolver=source)
    assert response.mode == 'direct' and gets == ['GET'] and len(commits) == 3
    assert_charge(pg, slots=0)


def test_unknown_resolver_refuses_partial_or_mismatched_facts(pg):
    post(pg)
    with Session(pg) as session:
        op = session.exec(select(DownloadOperation)).one()
        receipt = session.exec(select(DownloadIdempotency)).one()
        resolve = lambda **kw: service.inspect_operation(session, op.id, user_id='b4-user', request=REQUEST,
                                                           key='same', receipt_id=receipt.id, **kw)
        assert resolve().state.value == 'committed'
        access = session.get(DownloadAccess, op.job_id)
        access.max_height = None
        session.add(access)
        session.flush()
        assert resolve().state.value == 'unknown'
        assert service.inspect_operation(session, 'absent', user_id='b4-user', request=REQUEST,
                                          key=None).state.value == 'unknown'
        session.rollback()


def pending(pg, key='pending'):
    opid, receiptid, owner = 'b4-pending-op', 'b4-pending-receipt', 'b4-owner'
    request = REQUEST.model_copy(update={'force_server': False})
    decision = service.run_local_transaction(pg, opid, lambda session: service.accept_submission(
        session, 'b4-user', request, key, SNAPSHOT, operation_id=opid, receipt_id=receiptid, owner=owner, resolver_ready=True),
        lambda *_: service.CommitResolution(service.ResolutionState.UNKNOWN))
    return request, decision.token


def test_real_pending_receipt_replay_never_starts_a_second_resolve(pg):
    request, token = pending(pg)
    with pytest.raises(HTTPException) as error:
        post(pg, key='pending', request=request, trusted_resolver=lambda *_: pytest.fail('no second GET'))
    assert error.value.status_code == 409 and error.value.detail['error_type'] == 'idempotency_in_progress'
    assert_charge(pg)
    assert facts(pg)['job'] == 0


@pytest.mark.parametrize('change', ['owner', 'epoch', 'state', 'lease'])
def test_stale_resolve_identity_cannot_publish_or_release_slot(pg, change):
    request, token = pending(pg)
    with Session(pg) as session:
        op = session.get(DownloadOperation, token.operation_id)
        if change == 'owner':
            op.resolve_owner = 'other-owner'
        elif change == 'epoch':
            op.resolve_epoch += 1
        elif change == 'state':
            op.state = 'needs_review'
        else:
            op.resolve_lease_deadline = op.accepted_at
        session.add(op)
        session.commit()
    with Session(pg) as session:
        with pytest.raises(HTTPException) as error:
            service.fallback_to_server(session, token, service.codec.initial_budget())
        assert error.value.detail['error_type'] == 'resolve_lost'
        session.rollback()
    assert_charge(pg)
    assert facts(pg)['job'] == 0


def test_identity_map_cannot_hide_new_epoch(pg):
    request, token = pending(pg)
    with Session(pg, expire_on_commit=False) as held:
        stale = held.get(DownloadOperation, token.operation_id)
        held.commit()
        with Session(pg) as other:
            op = other.get(DownloadOperation, token.operation_id)
            op.resolve_epoch += 1
            other.add(op)
            other.commit()
        assert stale.resolve_epoch == 1
        with pytest.raises(HTTPException) as error:
            service.fallback_to_server(held, token, service.codec.initial_budget())
        assert error.value.detail['error_type'] == 'resolve_lost'
        held.rollback()
    assert_charge(pg)


def test_direct_checkpoint_tightens_coarse_clock_and_wait_without_budget_reset(pg):
    request, token = pending(pg)
    with Session(pg) as session:
        download, direct, child = service.begin_resolve(session, token)
        session.commit()
    # Windows monotonic and DB wall clock can round differently. Even a larger
    # live remaining_seconds must be clipped against persisted time and DBnow.
    envelope = service.codec.initial_budget()
    from dataclasses import replace
    live = service.codec.BudgetEnvelope(envelope.download_parent,
        replace(direct.checkpoint(), remaining_seconds=BudgetProfile.direct_parent().seconds))
    with Session(pg) as session:
        before = session.get(DownloadOperation, token.operation_id)
        before_at = before.budget_checkpoint_at
        old = service.codec.decode_budget(1, before.budget_checkpoint_json)
        session.commit()
        op, receipt, now = service._locked_resolve(session, token)
        service._cas_checkpoint(session, op, token, live, now)
        session.commit()
    with Session(pg) as session:
        op = session.get(DownloadOperation, token.operation_id)
        after = service.codec.decode_budget(1, op.budget_checkpoint_json)
        assert after.download_parent.remaining_seconds <= old.download_parent.remaining_seconds
        assert after.direct_resolve_parent.remaining_seconds <= old.direct_resolve_parent.remaining_seconds
        assert after.download_parent.remaining_seconds > 1700
        assert op.budget_checkpoint_at >= before_at


def test_terminal_slot_release_is_once_and_fallback_cannot_reopen(pg):
    request, token = pending(pg)
    with Session(pg) as session:
        download, direct, child = service.begin_resolve(session, token)
        session.commit()
    accounting = service.ResolveAccounting(download, direct, child)
    response = fake_direct(request, accounting).response
    with Session(pg) as session:
        service.complete_direct(session, token, response, accounting.checkpoint())
        session.commit()
    for action in (lambda session: service.complete_direct(session, token, response, accounting.checkpoint()),
                   lambda session: service.fallback_to_server(session, token, accounting.checkpoint())):
        with Session(pg) as session:
            with pytest.raises(HTTPException) as error:
                action(session)
            assert error.value.detail['error_type'] == 'resolve_lost'
            session.rollback()
    assert_charge(pg, slots=0)
    assert facts(pg)['job'] == 0


def test_no_key_path_never_acquires_receipt_resource(pg):
    statements = []
    def observe(conn, cursor, statement, params, context, many):
        if 'FOR UPDATE' in statement:
            statements.append((statement, params))
    event.listen(pg, 'before_cursor_execute', observe)
    try:
        post(pg, key=None)
    finally:
        event.remove(pg, 'before_cursor_execute', observe)
    assert all('receipt_entries' not in str(params) for _, params in statements)
    first_resource = next(index for index, (sql, _) in enumerate(statements) if 'resourcecounter' in sql)
    first_user = next(index for index, (sql, _) in enumerate(statements) if 'FROM "user"' in sql)
    first_membership = next(index for index, (sql, _) in enumerate(statements) if 'FROM membership' in sql)
    first_operation = next(index for index, (sql, _) in enumerate(statements) if 'FROM downloadoperation' in sql)
    assert first_resource < first_user < first_membership < first_operation


@pytest.mark.parametrize('deadline', ['lease', 'attempt'])
def test_final_direct_sql_cas_rechecks_deadline_after_post_lock_work(pg, deadline):
    request, token = pending(pg)
    with Session(pg) as session:
        download, direct, child = service.begin_resolve(session, token)
        session.commit()
    accounting = service.ResolveAccounting(download, direct, child)
    response = fake_direct(request, accounting).response
    with Session(pg) as session:
        op = session.get(DownloadOperation, token.operation_id)
        now = session.exec(select(func.clock_timestamp())).one()
        if deadline == 'lease':
            op.resolve_lease_deadline = now + timedelta(seconds=0.3)
        else:
            op.resolve_attempt_deadline = now + timedelta(seconds=0.3)
        session.add(op)
        session.commit()
    with Session(pg) as session:
        def delayed_checkpoint():
            # Executes after _locked_resolve has checked an unexpired row.
            session.exec(text('SELECT pg_sleep(0.4)'))
            return accounting.checkpoint()
        with pytest.raises(HTTPException) as error:
            service.complete_direct(session, token, response, delayed_checkpoint)
        assert error.value.detail['error_type'] == 'resolve_lost'
        session.rollback()
    with Session(pg) as session:
        assert session.get(DownloadOperation, token.operation_id).state == 'resolving'
        assert session.exec(select(DownloadIdempotency)).one().state == 'pending'
    assert_charge(pg)


def test_derived_direct_target_rejected_without_fallback(pg):
    request = REQUEST.model_copy(update={'force_server': False})
    def source(req, accounting):
        fake_direct(req, accounting)
        return DirectResult(DownloadResponse(mode='direct', url='http://169.254.169.254/latest'))
    with pytest.raises(HTTPException) as error:
        post(pg, request=request, trusted_resolver=source)
    assert error.value.detail['error_type'] == 'outbound_blocked'
    assert_charge(pg, slots=0)
    assert facts(pg)['job'] == 0


def test_pg_http_route_fails_closed_before_any_legacy_source_or_dispatch(pg, monkeypatch):
    from app.routes.download import download, ytdlp_service, job_manager
    monkeypatch.setattr(ytdlp_service, 'restrict_format', lambda *_: pytest.fail('unguarded format probe'))
    monkeypatch.setattr(ytdlp_service, 'get_direct_url', lambda *_: pytest.fail('unguarded direct probe'))
    monkeypatch.setattr(job_manager, 'submit_download', lambda *_: pytest.fail('API must not dispatch'))
    with Session(pg) as session:
        user = session.get(User, 'b4-user')
        with pytest.raises(HTTPException) as error:
            download(REQUEST, session, user, 'route')
        assert error.value.detail['error_type'] == 'outbound_unavailable'
    assert all(value == 0 for value in facts(pg).values())


def test_http_durable_submission_replays_one_job_without_legacy_dispatch(pg, monkeypatch):
    from app.routes import download as route
    monkeypatch.setattr(route.settings, 'pg_cutover_read_only', False)
    monkeypatch.setattr(route, '_verify_source_format', lambda *_: 'synthetic[height<=720]')
    monkeypatch.setattr(route.job_manager, 'submit_download', lambda *_: pytest.fail('in-process dispatch'))
    monkeypatch.setattr(route.ytdlp_service, 'restrict_format', lambda *_: pytest.fail('unguarded metadata'))
    answers = []
    for _ in range(2):
        with Session(pg) as session:
            user = session.get(User, 'b4-user')
            answers.append(route.download(REQUEST, session, user, 'http-stable'))
    assert answers[0].mode == 'server' and answers[0].job_id == answers[1].job_id
    assert facts(pg)['job'] == 1
    assert_charge(pg, slots=1)


def test_http_membership_change_during_broker_wait_does_not_charge(pg, monkeypatch):
    from app.routes import download as route
    monkeypatch.setattr(route.settings, 'pg_cutover_read_only', False)
    def changed(*_):
        with Session(pg) as other:
            other.add(Membership(user_id='b4-user', status='active', expires_at=4_000_000_000,
                                 revision=1))
            other.commit()
        return 'synthetic[height<=720]'
    monkeypatch.setattr(route, '_verify_source_format', changed)
    with Session(pg) as session:
        user = session.get(User, 'b4-user')
        with pytest.raises(HTTPException) as failure:
            route.download(REQUEST, session, user, 'http-membership-change')
    assert failure.value.detail['error_type'] == 'submission_changed'
    assert all(value == 0 for value in facts(pg).values())


@pytest.mark.parametrize('corruption', ['unknown_version', 'bad_json', 'attempt_mismatch'])
def test_unknown_or_corrupt_persisted_budget_never_resets_or_probes(pg, corruption):
    request, token = pending(pg)
    with Session(pg) as session:
        op = session.get(DownloadOperation, token.operation_id)
        if corruption == 'unknown_version':
            op.budget_version = 2
        elif corruption == 'bad_json':
            op.budget_checkpoint_json = '{"secret_url":"must-not-read"}'
        else:
            op.resolve_attempts_used = 1
        session.add(op)
        session.commit()
    with Session(pg) as session:
        with pytest.raises(ValueError, match='Invalid persisted download budget'):
            service.begin_resolve(session, token)
        session.rollback()
    assert_charge(pg)
    assert facts(pg)['job'] == 0


def test_fallback_across_utc_midnight_keeps_original_charge_day(pg, monkeypatch):
    with Session(pg) as session:
        midnight = session.exec(text("SELECT date_trunc('day',clock_timestamp()) + interval '1 day'")).one()[0]
    accepted = midnight - timedelta(seconds=1)
    monkeypatch.setattr(service, '_now', lambda _: accepted)
    request, token = pending(pg)
    with Session(pg) as session:
        download, direct, child = service.begin_resolve(session, token)
        session.commit()
    monkeypatch.setattr(service, '_now', lambda _: midnight)
    with Session(pg) as session:
        response = service.fallback_to_server(session, token,
                        service.codec.BudgetEnvelope(download.checkpoint(), direct.checkpoint()))
        session.commit()
    assert response.response.mode == 'server'
    with Session(pg) as session:
        op = session.get(DownloadOperation, token.operation_id)
        charge = session.get(QuotaCharge, op.id)
        assert op.quota_day == charge.quota_day == accepted.date()
        assert session.exec(select(Quota)).one().date == accepted.date().isoformat()
    assert_charge(pg)


def abrupt_worker(when, table, output):
    instance = engine()
    def kill(conn, cursor, statement, params, context, many):
        if statement.lower().startswith('insert into '+table):
            os._exit(71)
    if when != 'committed':
        event.listen(instance, when+'_cursor_execute', kill)
    else:
        original = Session.commit
        def committed(session):
            original(session)
            os._exit(72)
        Session.commit = committed
    submit_download(instance, 'b4-user', REQUEST, 'crash', SNAPSHOT)
    os._exit(73)


@pytest.mark.parametrize('when', ['before', 'after', 'committed'])
def test_real_api_process_exit_before_or_after_server_commit(pg, when):
    context = multiprocessing.get_context('spawn')
    process = context.Process(target=abrupt_worker, args=(when, 'job', None))
    try:
        process.start()
        process.join(20)
        assert process.exitcode == (72 if when == 'committed' else 71)
        if when == 'committed':
            response = post(pg, key='crash')
            assert response.mode == 'server'
            assert_charge(pg)
        else:
            assert all(value == 0 for value in facts(pg).values())
            with Session(pg) as session:
                assert all(row.used == 0 for row in session.exec(select(ResourceCounter)).all())
    finally:
        if process.is_alive():
            process.terminate()
            process.join(10)


def competing_post(key, format_id, barrier, output, user_id='b4-user', receipt_limit=10000):
    instance = engine()
    service.settings.membership_unlimited_downloads = False
    service.settings.default_quota_limit = 1
    service.settings.download_idempotency_max_entries = receipt_limit
    barrier.wait(15)
    try:
        response = submit_download(instance, user_id, REQUEST.model_copy(update={'format_id': format_id}), key,
                                   AccessSnapshot(720, 0, format_id))
        output.put({'status': 200, 'job': response.job_id, 'pid': os.getpid()})
    except HTTPException as error:
        output.put({'status': error.status_code, 'pid': os.getpid()})
    finally:
        instance.dispose()


@pytest.mark.parametrize('kind', ['same', 'different_payload', 'different_key'])
def test_independent_process_receipt_and_first_day_quota_arbitration(pg, kind):
    context = multiprocessing.get_context('spawn')
    barrier, output = context.Barrier(2), context.Queue()
    pairs = [('key', 'synthetic'), ('other' if kind == 'different_key' else 'key',
                                  'other' if kind == 'different_payload' else 'synthetic')]
    processes = [context.Process(target=competing_post, args=(*pair, barrier, output)) for pair in pairs]
    try:
        for process in processes:
            process.start()
        results = [output.get(timeout=30) for _ in processes]
        for process in processes:
            process.join(15)
            assert process.exitcode == 0
        assert len({row['pid'] for row in results}) == 2
        assert sorted(row['status'] for row in results) == ([200, 200] if kind == 'same' else
            [200, 409] if kind == 'different_payload' else [200, 429])
        if kind == 'same':
            assert len({row['job'] for row in results}) == 1
        assert_charge(pg)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(10)
        output.close()


def test_server_submission_creates_claimable_v2_job(pg):
    # C1 Task 3: B4's server path creates a v2 Job that the lease repository can claim.
    from app.services import job_repository
    first = post(pg)
    with Session(pg) as session:
        job = session.get(Job, first.job_id)
        op = session.exec(select(DownloadOperation).where(DownloadOperation.job_id == first.job_id)).one()
        assert (job.execution_version, job.internal_state, job.attempts_used, job.attempts_limit) == (2, 'queued', 0, 3)
        assert job.run_deadline_at == op.deadline_at == op.accepted_at + timedelta(minutes=30)
        token = job_repository.claim_next(session, 'b4-worker')
        # Roll back: proves claimability without leaving a jobattempt (RESTRICT, no runtime DELETE)
        # that B4's per-test cleanup could not remove.
        session.rollback()
    assert token is not None and token.job_id == first.job_id and token.epoch == 1
