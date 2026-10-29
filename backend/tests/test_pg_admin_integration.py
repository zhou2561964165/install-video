"""Admin M1 Task 12 + support tickets Task 11: the built admin frontend (52fd/admin/dist) against the real backend.

One uvicorn process serves /api/admin/v1 and /admin/ on 127.0.0.1 (same origin, like production) over a
nonce PG database filled with synthetic data; a headless Chromium (Playwright) logs in and walks every page
at 1440 and 360 widths, then works a support ticket (verify with the synthetic payment reader -> re-issue) and
checks a viewer cannot write. Evidence (screenshots, results.json) goes to the support integration directory.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys

import pytest

from test_pg_job_repository import case  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not os.environ.get('B3B_PG_OWNERSHIP'), reason='explicit owned PG window required')
DIST = Path(r'C:\Users\zxk\.codex\worktrees\52fd\install_video\admin\dist')
PLAYWRIGHT = Path(r'C:\Users\zxk\.codex\mcp\mermaid-reinstall-ace9b4f684be4ae3b4b0a3183aec5179\node_modules\playwright')
CHROMIUM = Path(r'C:\Users\zxk\AppData\Local\ms-playwright\chromium_headless_shell-1248\chrome-headless-shell-win64'
                r'\chrome-headless-shell.exe')
EVIDENCE = Path(r'E:\install_video\.planning\2026-10-28-support\integration')
TESTS = Path(__file__).resolve().parent


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


@pytest.mark.skipif(not (DIST.exists() and PLAYWRIGHT.exists() and CHROMIUM.exists()), reason='frontend build or browser missing')
def test_admin_frontend_against_real_backend(case):
    from app.admin import seed_synthetic
    seed_synthetic.seed(case.migration)
    port = _free_port()
    origin = f'http://127.0.0.1:{port}'
    env = dict(os.environ, DB_URL=case.application.url.render_as_string(hide_password=False),
               ADMIN_COOKIE_PATH='/api/admin/v1', ADMIN_ALLOWED_ORIGINS=origin, ADMIN_COOKIE_SECURE='false',
               ADMIN_CSRF_SECRET=secrets.token_urlsafe(48), ADMIN_DIST=str(DIST),
               # Synthetic payment verification only: the server module swaps in a fake reader; no Stripe call.
               ADMIN_FAKE_STRIPE='1', ADMIN_STRIPE_READ_KEY='rk_test_synthetic_integration', STRIPE_LIVEMODE='false',
               PYTHONPATH=os.pathsep.join((str(TESTS.parent), str(TESTS))))
    evidence = EVIDENCE / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    evidence.mkdir(parents=True)
    server_log, browser_log = evidence / 'server.log', evidence / 'browser.log'
    # Logs go to files, never to unread pipes: a full pipe would block the server (and lose output on timeout).
    with server_log.open('wb') as server_out:
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'admin_integration_server:app', '--host', '127.0.0.1',
                                   '--port', str(port), '--log-level', 'warning'], cwd=str(TESTS), env=env,
                                  stdout=server_out, stderr=subprocess.STDOUT)
    try:
        with browser_log.open('wb') as browser_out:
            code = subprocess.run(['node', str(TESTS / 'integration' / 'admin_m1_browser.cjs'), origin, str(evidence),
                                   seed_synthetic.ADMIN_EMAIL, seed_synthetic.ADMIN_PASSWORD, str(PLAYWRIGHT),
                                   str(CHROMIUM), seed_synthetic.VIEWER_EMAIL, seed_synthetic.VIEWER_PASSWORD,
                                   seed_synthetic.REISSUE_TICKET], stdout=browser_out, stderr=subprocess.STDOUT, timeout=420,
                                  env=env).returncode
    except subprocess.TimeoutExpired:
        code = 'timeout'
    finally:
        server.terminate()
        try:
            server.wait(timeout=20)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
    log = server_log.read_text('utf8', 'replace')
    browser = browser_log.read_text('utf8', 'replace')
    summary = [line for line in browser.splitlines() if line.startswith('{"total"')]
    assert code == 0 and summary, (code, browser[-3000:], log[-2000:])
    result = json.loads(summary[-1])
    assert result['failed'] == [] and result['total'] >= 35
    assert 'Traceback' not in log, log[-2000:]
