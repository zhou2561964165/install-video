"""Admin M1 Task 6: list-query parsing/pagination, meta, overview and system status (nonce-owned PG)."""
import os
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from admin_pg_helpers import BASE, add_job, add_membership, admin_client, admin_settings, login, make_user
from test_pg_job_repository import case  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
CONTRACT = Path(os.environ.get('ADMIN_CONTRACT_PATH', r'C:\Users\zxk\.codex\worktrees\52fd\install_video\docs\production'
                               r'\admin-api-v1.openapi.yaml'))


def contract_lists():
    document = yaml.safe_load(CONTRACT.read_text(encoding='utf8'))
    parameters = document['components']['parameters']
    found = {}
    for item in document['paths'].values():
        operation = item.get('get')
        if not operation or not operation['operationId'].startswith('adminList'):
            continue
        query = [parameters[p['$ref'].split('/')[-1]] if '$ref' in p else p for p in operation.get('parameters', [])]
        query = {p['name']: p.get('schema', {}) for p in query if p.get('in') == 'query'}
        found[operation['operationId']] = (query.pop('sort')['enum'],
                                           {name: schema for name, schema in query.items() if name not in ('page', 'page_size')})
    return found


def test_list_query_parsing_and_pagination(case):
    from app.models import User
    from app.services import admin_queries
    from app.admin.errors import AdminError
    for index in range(3):
        make_user(case, f'p{index}@example.invalid', grant=False)
    settings = admin_settings()
    spec = admin_queries.RESOURCES['adminListUsers']
    user = User.__table__
    with admin_queries.read_snapshot(case.application) as (connection, as_of):
        assert as_of.tzinfo is not None
        query = admin_queries.parse_list_query(spec, {'page': '2', 'page_size': '2', 'sort': 'email:asc'}, settings)
        rows, total = admin_queries.paginate(connection, select(user.c.id, user.c.email), query,
                                             {'email': user.c.email, 'created_at': user.c.created_at}, user.c.id)
        assert total == 3 and [row.email for row in rows] == ['p2@example.invalid']
        far = admin_queries.parse_list_query(spec, {'page': '5', 'page_size': '2'}, settings)
        rows, total = admin_queries.paginate(connection, select(user.c.id), far, {'created_at': user.c.created_at}, user.c.id)
        assert rows == [] and total == 3
    for bad in ({'page_size': '101'}, {'page': '0'}, {'page_size': 'x'}, {'sort': 'password:asc'},
                {'page': '\u00b2'}, {'page': '\u0661'}, {'page_size': '\u00b2'}, {'page': str(10 ** 19)},
                {'page': '9' * 5000},
                {'nickname': 'a'}, {'enabled': 'yes'}, {'email': 'a' * 255}):
        with pytest.raises(AdminError) as caught:
            admin_queries.parse_list_query(spec, bad, settings)
        assert caught.value.status == 422 and caught.value.field_errors


def test_overview_counts_and_legacy_unset_group(case):
    admin = make_user(case)
    other = make_user(case, 'other@example.invalid', grant=False)
    add_membership(case, admin, 'active', 3600)
    add_membership(case, other, 'active', -60)
    add_job(case, 'j1', other)
    add_job(case, 'j2', other, internal_state='legacy_hold')
    add_job(case, 'j3', other, version=2, status='queued', internal_state='queued')
    with admin_client(case) as client:
        login(client)
        overview = client.get(BASE + '/overview').json()
    assert (overview['users_total'], overview['effective_vip_total'], overview['retained_server_jobs_total']) == (2, 1, 3)
    assert {item['state']: item['count'] for item in overview['jobs_by_internal_state']} == {
        'legacy_unset': 1, 'legacy_hold': 1, 'queued': 1}
    assert {item['state']: item['count'] for item in overview['jobs_by_public_status']} == {'done': 2, 'queued': 1}
    assert overview['as_of'].endswith('Z') and set(overview['scope']) >= {'users', 'effective_vip', 'jobs'}


def test_system_status_unknown_without_samples(case):
    make_user(case)
    with admin_client(case) as client:
        login(client)
        status = client.get(BASE + '/system/status').json()
    components = {item['component']: item for item in status['components']}
    assert components['database']['status'] == 'ok' and components['database']['checked_at'].endswith('Z')
    for name in ('download_worker', 'billing_worker', 'artifact_store'):
        assert (components[name]['status'], components[name]['reason_code'], components[name]['checked_at']) == (
            'unknown', 'no_reliable_sample', None)
    assert status['download_submission_ready']['ready'] is False
    assert status['capabilities']['billing_amounts']['ready'] is False


def test_meta_lists_exact_filters_and_sorts(case):
    make_user(case, role='viewer')
    with admin_client(case) as client:
        login(client)
        meta = client.get(BASE + '/meta').json()
    assert (meta['api_version'], meta['contract_version']) == ('v1', '1.0.0-proposal.20261029.1')
    assert meta['pagination'] == {'default_page': 1, 'default_page_size': 20, 'max_page_size': 100}
    assert (meta['quota_day_timezone'], meta['quota_day_semantics']) == ('UTC', 'accepted_at_utc_date')
    assert meta['limits']['session_ttl_seconds'] == 900 and meta['features']['account_access_write']['ready'] is False
    expected = contract_lists()
    queries = {item['resource']: item for item in meta['queries']}
    assert set(queries) == set(expected)
    for resource, (sorts, filters) in expected.items():
        assert queries[resource]['sort_values'] == sorts, resource
        served = {item['name']: item for item in queries[resource]['filters']}
        assert set(served) == set(filters), resource
        for name, schema in filters.items():
            if 'enum' in schema:
                assert served[name]['kind'] == 'enum' and served[name]['allowed_values'] == [str(v) for v in schema['enum']]
            else:
                assert 'allowed_values' not in served[name]
    domains = {item['domain'] for item in meta['state_dictionaries']}
    # Exactly the domains the admin frontend renders (AdminStateTag domain=...).
    assert {'job.public_status', 'job.internal_state', 'job.attempt', 'membership.status', 'checkout.state',
            'reconciliation', 'audit.outcome', 'system.status'} <= domains


def test_meta_and_overview_need_session(case):
    with admin_client(case) as client:
        for path in ('/meta', '/overview', '/system/status'):
            assert client.get(BASE + path).status_code == 401


def test_overview_permission_required(case, monkeypatch):
    from app.admin import deps
    make_user(case, role='viewer')
    monkeypatch.setitem(deps.ROLE_PERMISSIONS, 'viewer', frozenset({'users:read'}))
    with admin_client(case) as client:
        login(client)
        assert client.get(BASE + '/overview').status_code == 403
        assert client.get(BASE + '/system/status').status_code == 403
        assert client.get(BASE + '/meta').status_code == 200  # meta needs a session, not a business permission


def test_huge_or_unicode_page_is_422_not_500(case):
    make_user(case)
    with admin_client(case) as client:
        login(client)
        for page in ('\u00b2', str(10 ** 19), '1000000000'):
            response = client.get(BASE + '/users', params={'page': page})
            assert response.status_code == 422, (page, response.status_code)
        assert client.get(BASE + '/users', params={'page': '999999999'}).json()['items'] == []
