"""C4 Task 4: GET /api/file/{job_id} on PostgreSQL end to end (real worker publish -> HTTP GET/Range)."""
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from test_pg_download_worker import media, worker  # noqa: F401  (fixtures)
from test_pg_job_repository import case, db, submit  # noqa: F401  (fixtures/helpers)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
OWNER = 'c1-slot'


@pytest.fixture
def published(case, worker, media, submit):
    job = submit('k1').job_id
    assert worker.run_once(case.application, media, 'w1', executor='fake:ok:5000',
                           heartbeat_seconds=0.3, poll_seconds=0.02) == 'published'
    return job


@pytest.fixture
def client(case, media, monkeypatch):
    from app.db import get_session
    from app.models import User
    from app.routes import download
    from app.services.auth import get_current_user
    monkeypatch.setattr(download.settings, 'media_root', media)
    monkeypatch.setattr(download, 'max_height', lambda session, user_id: None)  # VIP-equivalent for these tests
    current = {'user': User(id=OWNER, email='c1-slot@synthetic.invalid', password_hash='x')}
    app = FastAPI()
    app.include_router(download.router)

    def session_override():
        with Session(case.application) as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = lambda: current['user']
    with TestClient(app) as test_client:
        test_client.current = current
        yield test_client


def read_leases(case, job):
    with case.migration.connect() as connection:
        return connection.execute(text('SELECT ended_at IS NOT NULL AS ended FROM app.filereadlease WHERE job_id=:j'),
                                  {'j': job}).all()


def test_get_streams_published_file_and_ends_lease(case, client, published):
    response = client.get(f'/api/file/{published}')
    assert response.status_code == 200 and response.content == b'\0' * 5000
    assert response.headers['accept-ranges'] == 'bytes' and response.headers['etag'].startswith('"sha256-')
    assert response.headers['content-disposition'].startswith('attachment;')
    assert [row.ended for row in read_leases(case, published)] == [True]


def test_range_request_is_partial(case, client, published):
    response = client.get(f'/api/file/{published}', headers={'Range': 'bytes=100-199'})
    assert response.status_code == 206 and len(response.content) == 100
    assert response.headers['content-range'] == 'bytes 100-199/5000'


def test_expired_file_is_gone(case, client, published):
    db(case, "UPDATE app.job SET expires_at = now() - interval '1 second' WHERE id=:j", j=published)
    response = client.get(f'/api/file/{published}')
    assert response.status_code == 410 and response.json()['detail']['error_type'] == 'file_expired'
    assert read_leases(case, published) == []


def test_other_users_file_is_not_found(case, client, published):
    from app.models import User
    client.current['user'] = User(id='someone-else', email='x@synthetic.invalid', password_hash='x')
    response = client.get(f'/api/file/{published}')
    assert response.status_code == 404 and response.json()['detail']['error_type'] == 'file_missing'


def test_missing_media_root_is_unavailable(case, client, published, monkeypatch):
    from app.routes import download
    monkeypatch.setattr(download.settings, 'media_root', None)
    response = client.get(f'/api/file/{published}')
    assert response.status_code == 503 and response.json()['detail']['error_type'] == 'file_storage_unavailable'


# C4 review C1: the request session is closed before streaming: no pooled connection is held by a download.
def test_durable_read_holds_no_connection_while_streaming(case, client, published, media):
    import anyio
    from starlette.requests import Request
    from app.models import User
    from app.routes import download
    request = Request({'type': 'http', 'method': 'GET', 'headers': [], 'path': f'/api/file/{published}',
                       'query_string': b''})
    session = Session(case.application)
    response = download._durable_file(request, session, User(id=OWNER, email='o@synthetic.invalid',
                                                             password_hash='x'), published)
    assert case.application.pool.checkedout() == 0  # nothing held while the body has not even started

    async def drain():
        async for _ in response.body_iterator:
            pass
    anyio.run(drain)
    assert [row.ended for row in read_leases(case, published)] == [True]


# C4 review I5: the real membership path (not monkeypatched) refuses a free user above the free height.
def test_real_membership_height_limit_is_forbidden(case, client, published, monkeypatch):
    from app.routes import download
    from app.services import membership
    monkeypatch.setattr(download, 'max_height', membership.max_height)
    monkeypatch.setattr(membership, 'is_unlimited_user', lambda user_id: False)
    monkeypatch.setattr(membership.settings, 'membership_free_max_height', 480)
    response = client.get(f'/api/file/{published}')
    assert response.status_code == 403 and response.json()['detail']['error_type'] == 'membership_required'


def test_unusable_media_root_is_unavailable(case, client, published, media, monkeypatch):
    from app.routes import download
    monkeypatch.setattr(download.settings, 'media_root', media.parent / 'not-mounted')
    response = client.get(f'/api/file/{published}')
    assert response.status_code == 503 and response.json()['detail']['error_type'] == 'file_storage_unavailable'


# C6b: a verified imported v1 file streams through the same route with Range, without a read lease.
def test_legacy_file_streams_with_range_and_no_lease(case, client, submit, tmp_path, monkeypatch):
    from app.routes import download
    submit('k-owner')  # creates the owner account
    old = (tmp_path / 'old').resolve()
    (old / 'legacy-1').mkdir(parents=True)
    (old / 'legacy-1' / 'clip.mp4').write_bytes(b'0123456789')
    db(case, "INSERT INTO app.job (id,url,title,status,progress,file_path,file_size,created_at,updated_at,expires_at,"
             "user_id,legacy_check) VALUES ('legacy-1','https://source.synthetic.invalid/v','Clip','done',100.0,:p,10,"
             "now(),now(),now() + interval '1 hour',:u,'verified')", p=str(old / 'legacy-1' / 'clip.mp4'), u=OWNER)
    monkeypatch.setattr(download.settings, 'temp_dir', old)
    whole = client.get('/api/file/legacy-1')
    assert whole.status_code == 200 and whole.content == b'0123456789'
    assert whole.headers['etag'].startswith('"legacy-legacy-1-') and 'Clip.mp4' in whole.headers['content-disposition']
    part = client.get('/api/file/legacy-1', headers={'Range': 'bytes=2-5'})
    assert part.status_code == 206 and part.content == b'2345'
    assert read_leases(case, 'legacy-1') == []



def test_legacy_if_range_with_a_stale_etag_sends_the_whole_file(case, client, submit, tmp_path, monkeypatch):
    from app.routes import download
    submit('k-owner')
    old = (tmp_path / 'old').resolve()
    (old / 'legacy-2').mkdir(parents=True)
    (old / 'legacy-2' / 'clip.mp4').write_bytes(b'abcdefghij')
    db(case, "INSERT INTO app.job (id,url,status,progress,file_path,file_size,created_at,updated_at,expires_at,"
             "user_id,legacy_check) VALUES ('legacy-2','https://source.synthetic.invalid/v','done',100.0,:p,10,"
             "now(),now(),now() + interval '1 hour',:u,'verified')", p=str(old / 'legacy-2' / 'clip.mp4'), u=OWNER)
    monkeypatch.setattr(download.settings, 'temp_dir', old)
    stale = client.get('/api/file/legacy-2', headers={'Range': 'bytes=2-5', 'If-Range': '"legacy-legacy-2-stale"'})
    assert stale.status_code == 200 and stale.content == b'abcdefghij'
