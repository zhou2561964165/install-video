"""Admin M1 Task 3: admin sub-application skeleton — request ids, error shape, 503 gate, separate entry."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from admin_pg_helpers import BASE, admin_client
from test_pg_job_repository import case  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
BACKEND = Path(__file__).resolve().parents[1]


def test_every_response_has_request_id_matching_error_body(case):
    with admin_client(case) as client:
        response = client.get(BASE + '/no-such-resource')
    assert response.status_code == 404
    body = response.json()['detail']
    assert body['error_type'] == 'not_found' and body['error']
    assert body['request_id'] == response.headers['X-Request-ID'] and len(body['request_id']) >= 16


def test_unavailable_config_returns_503_admin_unavailable(case):
    with admin_client(case, csrf_secret=None) as client:
        response = client.get(BASE + '/meta')
    assert response.status_code == 503
    assert response.json()['detail']['error_type'] == 'admin_unavailable'
    assert response.json()['detail']['request_id'] == response.headers['X-Request-ID']


def test_unknown_method_uses_admin_error_shape(case):
    with admin_client(case) as client:
        response = client.delete(BASE + '/no-such-resource')
    assert response.status_code in (404, 405)
    assert set(response.json()['detail']) >= {'error_type', 'error', 'request_id'}


def test_admin_main_does_not_import_business_app():
    code = 'import sys, app.admin_main; print("app.main" in sys.modules, "app.services.ytdlp_service" in sys.modules)'
    done = subprocess.run([sys.executable, '-c', code], cwd=str(BACKEND), capture_output=True, text=True, timeout=120,
                          env=dict(os.environ, PYTHONPATH=str(BACKEND)))
    assert done.returncode == 0, done.stderr[-500:]
    assert done.stdout.split() == ['False', 'False']


def test_admin_entry_refuses_stale_schema(case):
    case.migrate(action='downgrade', target='b6_0013')
    with pytest.raises(Exception):
        with admin_client(case, check_schema=True):
            pass
