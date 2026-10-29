"""Admin M1 Task 8: jobs list/detail — safe projection only (nonce-owned PG)."""
import json
import os

import pytest

from admin_pg_helpers import BASE, add_job, admin_client, login, make_user, run
from test_pg_job_repository import case  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
SENTINEL = 'RAW-ERROR-SENTINEL /srv/media/abs/path.mp4'


def published(case, job_id, user_id):
    """A v2 job that succeeded with a visible, manifested attempt."""
    add_job(case, job_id, user_id, version=2, status='queued', internal_state='queued')
    run(case, "INSERT INTO app.jobattempt (id,job_id,epoch,owner,attempt_index,state,started_at,ended_at,error_code,bytes_used) "
              "VALUES (:a,:j,1,'w1',1,'succeeded',now() - interval '1 minute',now(),NULL,4096)", a=job_id + '-a1', j=job_id)
    run(case, "INSERT INTO app.artifactmanifest (attempt_id,job_id,epoch,relative_path,byte_size,sha256,media_format,"
              "media_check,created_at) VALUES (:a,:j,1,:p,4096,repeat('c',64),'mp4','signature',now())",
        a=job_id + '-a1', j=job_id, p=f'{job_id}/1-{job_id}-a1/media.mp4')
    run(case, "UPDATE app.job SET internal_state='succeeded', status='done', visible_attempt_id=:a, "
              "media_state='available', completed_at=now() WHERE id=:j", a=job_id + '-a1', j=job_id)


def test_job_detail_never_leaks_raw_error_or_paths(case):
    admin = make_user(case)
    add_job(case, 'j-err', admin, status='error', error_type='http_403', error=SENTINEL)
    published(case, 'j-ok', admin)
    with admin_client(case) as client:
        login(client)
        failed = client.get(BASE + '/jobs/j-err').json()
        ok = client.get(BASE + '/jobs/j-ok').json()
        listing = client.get(BASE + '/jobs').json()
    dumped = json.dumps([failed, ok, listing])
    for leak in ('SENTINEL', '/srv/media', 'token=SECRET', '?v=1', 'w1', 'media.mp4', 'cccc'):
        assert leak not in dumped, leak
    assert failed['error_type'] == 'http_403' and failed['error_message'] and SENTINEL not in failed['error_message']
    assert ok['artifact'] == {'media_state': 'available', 'byte_size': '4096', 'media_format': 'mp4',
                              'media_check': 'signature', 'completed_at': ok['artifact']['completed_at']}
    assert ok['artifact']['completed_at'].endswith('Z')
    assert [(a['attempt_index'], a['state'], a['error_code']) for a in ok['attempts']] == [(1, 'succeeded', None)]
    assert ok['as_of'].endswith('Z') and ok['run_deadline_at'].endswith('Z')


def test_source_host_lowercase_no_userinfo_port(case):
    admin = make_user(case)
    add_job(case, 'j1', admin, url='https://User:Pass@Video.Example.invalid:8443/watch?v=1&token=SECRET')
    add_job(case, 'j2', admin, url='not a url')
    with admin_client(case) as client:
        login(client)
        hosts = {item['id']: item['source_host'] for item in client.get(BASE + '/jobs').json()['items']}
    assert hosts == {'j1': 'video.example.invalid', 'j2': None}


def test_unknown_error_type_generic_message(case):
    admin = make_user(case)
    add_job(case, 'j1', admin, status='error', error_type='something_new', error='boom')
    add_job(case, 'j2', admin)
    with admin_client(case) as client:
        login(client)
        unknown = client.get(BASE + '/jobs/j1').json()
        clean = client.get(BASE + '/jobs/j2').json()
    assert unknown['error_message'] == '任务失败，原因未归类'
    assert clean['error_type'] is None and clean['error_message'] is None
    assert clean['artifact'] == {'media_state': None, 'byte_size': None, 'media_format': None, 'media_check': None,
                                 'completed_at': None}  # legacy: nothing forged


def test_every_worker_code_has_a_safe_message():
    from app.services import admin_queries
    from app.services.download_worker import CHILD_ERROR_CODES
    from app.services.job_repository import NEEDS_REVIEW, RETRYABLE
    assert (CHILD_ERROR_CODES | RETRYABLE | NEEDS_REVIEW | {'run_deadline_exceeded'}) <= set(admin_queries.ERROR_MESSAGES)


def test_legacy_unset_filters_null_internal_state_and_response_stays_null(case):
    admin = make_user(case)
    add_job(case, 'v1-null', admin)
    add_job(case, 'v1-hold', admin, internal_state='legacy_hold')
    add_job(case, 'v2', admin, version=2, status='queued', internal_state='queued')
    with admin_client(case) as client:
        login(client)
        unset = client.get(BASE + '/jobs', params={'internal_state': 'legacy_unset'}).json()
        version = client.get(BASE + '/jobs', params={'execution_version': '2'}).json()
    assert [(item['id'], item['internal_state']) for item in unset['items']] == [('v1-null', None)]
    assert [item['id'] for item in version['items']] == ['v2'] and version['items'][0]['execution_version'] == 2


def test_job_filters_and_sort_stable(case):
    admin = make_user(case)
    other = make_user(case, 'other@example.invalid', grant=False)
    for index in range(3):
        add_job(case, f'j{index}', admin)
    add_job(case, 'jx', other, status='error', error_type='network')
    run(case, "UPDATE app.job SET created_at = '2026-01-01T00:00:00Z'")  # identical sort keys: id breaks ties
    with admin_client(case) as client:
        login(client)
        mine = client.get(BASE + '/jobs', params={'user_id': admin, 'sort': 'created_at:desc'}).json()
        errors = client.get(BASE + '/jobs', params={'public_status': 'error'}).json()
        assert client.get(BASE + '/jobs', params={'public_status': 'broken'}).status_code == 422
        assert client.get(BASE + '/jobs/missing').status_code == 404
    assert [item['id'] for item in mine['items']] == ['j0', 'j1', 'j2'] and mine['total'] == 3
    assert [item['id'] for item in errors['items']] == ['jx'] and errors['items'][0]['public_status'] == 'error'
