"""mc_0016 on nonce-owned disposable PG only. No source or payment network calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os

import pytest
from sqlalchemy import text
from sqlmodel import Session

from admin_pg_helpers import BASE, add_membership, admin_client, login, make_user, run
from test_pg_job_repository import case  # noqa: F401

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
REASON = '经管理员核实后调整会员权益'


def patch(client, csrf, user, mode='enabled', expires=None, revision='0', key='member-key-0000001', **headers):
    return client.patch(BASE + f'/users/{user}/membership', json={
        'mode': mode, 'expires_at': expires, 'reason': REASON, 'expected_revision': revision},
        headers={'X-CSRF-Token': csrf, 'Idempotency-Key': key, **headers})


def counts(case):
    with case.migration.connect() as connection:
        return (connection.scalar(text('SELECT count(*) FROM app.membershipcontroloperation')),
                connection.scalar(text("SELECT count(*) FROM app.adminaudit WHERE action='users.membership'")))


def test_permanent_grant_without_payment_row_is_audited_and_initializes_free_payment(case):
    make_user(case)
    target = make_user(case, 'target@example.invalid', grant=False)
    with admin_client(case) as client:
        csrf = login(client)
        response = patch(client, csrf, target)
        assert response.status_code == 200, response.text
        body = response.json()
        member = body['membership']
        assert body['changed'] and body['audit_id'] and body['as_of'].endswith('Z')
        assert member['effective'] and member['effective_permanent']
        assert member['status'] == 'free' and member['expires_at'] is None
        assert member['control_mode'] == 'enabled' and member['control_revision'] == '1' and member['revision'] == '1'
        assert member['effective_expires_at'] is None and member['effective_reason'] == 'admin_enabled'
        assert client.get(BASE + f'/users/{target}').json()['membership'] == member
        audit = client.get(BASE + '/audit/logs', params={'action': 'users.membership'}).json()['items'][0]
        assert audit['operation'] == 'users.membership'
        assert audit['change'] == {'control_mode_before': 'auto', 'control_mode_after': 'enabled',
            'control_expires_at_before': None, 'control_expires_at_after': None,
            'control_revision_before': '0', 'control_revision_after': '1'}
    assert counts(case) == (1, 1)


def test_control_sequence_preserves_payment_facts_and_versions_each_change(case):
    admin = make_user(case)
    target = make_user(case, 'target@example.invalid', grant=False)
    add_membership(case, target, 'active', 3600)
    run(case, "UPDATE app.membership SET entitlement_source='pi_original' WHERE user_id=:u", u=target)
    with case.migration.connect() as connection:
        before = connection.execute(text('SELECT status,expires_at,entitlement_source FROM app.membership WHERE user_id=:u'), {'u': target}).one()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat().replace('+00:00', 'Z')
    with admin_client(case) as client:
        csrf = login(client)
        for revision, mode, deadline in [('0','enabled',None), ('1','enabled',future),
                                         ('2','disabled',None), ('3','auto',None)]:
            response = patch(client, csrf, target, mode, deadline, revision, 'sequence-key-0000' + revision)
            assert response.status_code == 200, response.text
            member = response.json()['membership']
            assert member['control_revision'] == member['revision'] == str(int(revision) + 1)
            assert member['effective'] == (mode != 'disabled')
    with case.migration.connect() as connection:
        after = connection.execute(text('SELECT status,expires_at,entitlement_source FROM app.membership WHERE user_id=:u'), {'u': target}).one()
        assert after == before
        assert connection.scalar(text('SELECT actor_user_id FROM app.membershipcontrol WHERE user_id=:u'), {'u': target}) == admin
    assert counts(case) == (4, 4)


def test_noop_and_same_key_replay_do_not_bump_versions_or_duplicate_audit(case):
    target = make_user(case)
    with admin_client(case) as client:
        csrf = login(client)
        first = patch(client, csrf, target, mode='auto')
        assert first.status_code == 200 and first.json()['changed'] is False
        assert first.json()['membership']['control_revision'] == '0'
        replay = patch(client, csrf, target, mode='auto')
        assert replay.status_code == 200 and replay.json() == first.json()
        assert patch(client, csrf, target, mode='disabled').status_code == 409
        assert patch(client, csrf, target, key='new-key-0000000002').status_code == 200
        stale = patch(client, csrf, target, mode='disabled', key='new-key-0000000003')
        assert stale.status_code == 409 and stale.json()['detail']['error_type'] == 'revision_conflict'
    assert counts(case) == (2, 2)


def test_same_key_other_target_and_other_admin_are_conflicts(case):
    first = make_user(case)
    second = make_user(case, 'second@example.invalid')
    with admin_client(case) as client:
        csrf = login(client)
        assert patch(client, csrf, first).status_code == 200
        conflict = patch(client, csrf, second)
        assert conflict.status_code == 409 and conflict.json()['detail']['error_type'] == 'idempotency_conflict'
    with admin_client(case) as client:
        csrf = login(client, 'second@example.invalid')
        conflict = patch(client, csrf, first)
        assert conflict.status_code == 409 and conflict.json()['detail']['error_type'] == 'idempotency_conflict'
    assert counts(case) == (1, 1)


@pytest.mark.parametrize('bad', ['2000-01-01T00:00:00Z', '2026-10-29T12:00:00+08:00'])
def test_invalid_deadline_leaves_no_control_operation_or_audit(case, bad):
    target = make_user(case)
    with admin_client(case) as client:
        csrf = login(client)
        assert patch(client, csrf, target, expires=bad).status_code == 422
    assert counts(case) == (0, 0)


def test_viewer_origin_csrf_and_missing_key_rejected(case):
    target = make_user(case)
    make_user(case, 'viewer@example.invalid', role='viewer')
    with admin_client(case) as client:
        csrf = login(client)
        assert patch(client, csrf, target, Origin='https://untrusted.invalid').status_code == 403
        assert patch(client, 'wrong', target).status_code == 403
        missing = patch(client, csrf, target, key='')
        assert missing.status_code == 422 and missing.json()['detail']['error_type'] == 'idempotency_key_required'
        assert patch(client, csrf, target, key='too-short').status_code == 422
        assert patch(client, csrf, target, key='invalid whitespace 0001').status_code == 422
        assert patch(client, csrf, 'missing-user').status_code == 404
    with admin_client(case) as client:
        csrf = login(client, 'viewer@example.invalid')
        me = client.get(BASE + '/auth/me').json()
        assert 'memberships:write' not in me['permissions']
        assert me['capabilities']['membership_control_write']['ready'] is True
        assert patch(client, csrf, target).status_code == 403
    assert counts(case) == (0, 0)


def test_revoked_admin_cannot_replay_prior_result(case):
    target = make_user(case)
    with admin_client(case) as client:
        csrf = login(client)
        assert patch(client, csrf, target).status_code == 200
        run(case, 'UPDATE app.admingrant SET active=false WHERE user_id=:u', u=target)
        assert patch(client, csrf, target).status_code == 401
    assert counts(case) == (1, 1)


def test_concurrent_control_cas_has_one_winner(case):
    target = make_user(case)
    with admin_client(case) as client:
        csrf = login(client)
        with ThreadPoolExecutor(2) as pool:
            a = pool.submit(patch, client, csrf, target, 'enabled', None, '0', 'cas-first-key-0001')
            b = pool.submit(patch, client, csrf, target, 'disabled', None, '0', 'cas-second-key-0002')
            results = [a.result(timeout=10), b.result(timeout=10)]
    assert sorted(r.status_code for r in results) == [200, 409]
    assert next(r for r in results if r.status_code == 409).json()['detail']['error_type'] == 'revision_conflict'
    assert counts(case) == (1, 1)


def test_same_key_concurrent_different_targets_rejected_without_retrying_write(case):
    first = make_user(case)
    second = make_user(case, 'second@example.invalid', grant=False)
    with admin_client(case) as client:
        csrf = login(client)
        with ThreadPoolExecutor(2) as pool:
            a = pool.submit(patch, client, csrf, first)
            b = pool.submit(patch, client, csrf, second)
            results = [a.result(timeout=10), b.result(timeout=10)]
    assert sorted(r.status_code for r in results) == [200, 409]
    assert next(r for r in results if r.status_code == 409).json()['detail']['error_type'] == 'idempotency_conflict'
    assert counts(case) == (1, 1)


def test_admin_expiry_python_sql_overview_lists_and_support_projection_agree(case):
    from app.services import admin_queries, membership
    from admin_pg_helpers import admin_settings
    admin = make_user(case)
    target = make_user(case, 'target@example.invalid', grant=False)
    add_membership(case, target, 'active', 86400)
    at = datetime(2030, 1, 1, tzinfo=timezone.utc)
    run(case, 'UPDATE app.membership SET expires_at=:e WHERE user_id=:u', e=at.timestamp() + 86400, u=target)
    run(case, "INSERT INTO app.membershipcontrol (user_id,mode,expires_at,revision,updated_at,actor_user_id) "
              "VALUES (:u,'enabled',:at,1,now(),:a)", u=target, at=at, a=admin)
    query = admin_queries.parse_list_query(admin_queries.RESOURCES['adminListUsers'], {'effective_vip': 'true'}, admin_settings())
    with case.application.connect() as connection:
        exact = admin_queries.user_detail(connection, at, target, admin)
        earlier = admin_queries.user_detail(connection, at - timedelta(microseconds=1), target, admin)
        assert exact['membership']['effective'] is False
        assert exact['membership']['effective_reason'] == 'admin_expired'
        assert earlier['membership']['effective'] is True
        assert admin_queries.overview(connection, at)['effective_vip_total'] == 0
        assert admin_queries.overview(connection, at - timedelta(microseconds=1))['effective_vip_total'] == 1
        assert admin_queries.list_users(connection, at, query, admin)[0] == []
    with Session(case.application) as session:
        assert membership.entitlement(session, target, at).effective is False
        assert membership.entitlement(session, target, at - timedelta(microseconds=1)).effective is True


def test_download_snapshot_revision_fences_admin_enable_disable_enable_aba(case):
    from app.services.download_submission import read_access_snapshot
    target = make_user(case)
    with admin_client(case) as client:
        csrf = login(client)
        before = read_access_snapshot(case.application, target)
        snapshots = [before]
        for revision, mode in [('0','enabled'),('1','disabled'),('2','enabled')]:
            assert patch(client, csrf, target, mode=mode, revision=revision, key='aba-key-000000000' + revision).status_code == 200
            snapshots.append(read_access_snapshot(case.application, target))
    assert [s.membership_revision for s in snapshots] == [0, 1, 2, 3]
    assert snapshots[1].max_height is None and snapshots[3].max_height is None
    assert snapshots[2].max_height is not None


def test_commit_ack_loss_resolves_original_result_without_reexecution(case, monkeypatch):
    from app.services.db_transactions import LocalSession
    target = make_user(case)
    with admin_client(case) as client:
        csrf = login(client)
        original = Session.commit
        injected = []
        def lose_ack(session):
            original(session)
            if isinstance(session, LocalSession) and not injected:
                injected.append(True)
                raise OSError('synthetic lost commit acknowledgement')
        monkeypatch.setattr(Session, 'commit', lose_ack)
        first = patch(client, csrf, target)
        assert first.status_code == 200, first.text
        assert patch(client, csrf, target).json() == first.json()
    assert injected == [True] and counts(case) == (1, 1)


def test_unknown_uncommitted_result_stays_uncertain_and_original_request_can_resolve(case, monkeypatch):
    from app.services.db_transactions import LocalSession
    target = make_user(case)
    with admin_client(case) as client:
        csrf = login(client)
        original = Session.commit
        def lose_commit(session):
            if isinstance(session, LocalSession):
                raise OSError('synthetic unknown commit')
            return original(session)
        monkeypatch.setattr(Session, 'commit', lose_commit)
        unknown = patch(client, csrf, target)
        assert unknown.status_code == 503 and unknown.json()['detail']['error_type'] == 'transaction_uncertain'
        assert counts(case) == (0, 0)
        monkeypatch.setattr(Session, 'commit', original)
        assert patch(client, csrf, target).status_code == 200
    assert counts(case) == (1, 1)


def test_unknown_commit_resolver_rechecks_live_admin_before_returning_original_result(case, monkeypatch):
    from app.services.db_transactions import LocalSession
    target = make_user(case)
    with admin_client(case) as client:
        csrf = login(client)
        original = Session.commit
        injected = []
        def revoke_after_commit(session):
            original(session)
            if isinstance(session, LocalSession) and not injected:
                injected.append(True)
                run(case, 'UPDATE app.admingrant SET active=false WHERE user_id=:u', u=target)
                raise OSError('synthetic acknowledgement loss concurrent with revocation')
        monkeypatch.setattr(Session, 'commit', revoke_after_commit)
        unknown = patch(client, csrf, target)
        assert unknown.status_code == 503 and unknown.json()['detail']['error_type'] == 'transaction_uncertain'
        assert 'membership' not in unknown.json()
        assert counts(case) == (1, 1)  # committed once, but resolver refuses to expose a revoked admin's result
        monkeypatch.setattr(Session, 'commit', original)
        run(case, 'UPDATE app.admingrant SET active=true WHERE user_id=:u', u=target)
        resolved = patch(client, csrf, target)
        assert resolved.status_code == 200
    assert counts(case) == (1, 1)


def test_admin_disable_cannot_bypass_reissue_live_payment_block(case):
    from test_pg_admin_reissue import setup_ticket, verified_then_reissue
    user = setup_ticket(case)
    add_membership(case, user, 'active', 3600)
    run(case, "UPDATE app.membership SET entitlement_source='pi_other' WHERE user_id=:u", u=user)
    with admin_client(case) as client:
        csrf = login(client)
        assert patch(client, csrf, user, mode='disabled').status_code == 200
    detail, result = verified_then_reissue(case, user)
    assert detail['membership']['effective'] is False
    assert detail['actions']['reissue']['reason'] == 'membership_active'
    assert result.status_code == 409 and result.json()['detail']['error_type'] == 'membership_active'
