"""Support tickets Task 11 (user side): the built user frontend (E:\\install_video\\frontend\\dist) against the real
business app on a throwaway SQLite database; a headless Chromium logs in, opens support from the membership page,
appeals an unpaid-looking order and reads "my tickets" at 1440 and 360 widths. Evidence goes to the support
integration directory. Run explicitly (USER_SUPPORT_BROWSER=1); no payment provider or model is contacted."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

import pytest

from user_support_constants import EMAIL, PASSWORD

DIST = Path(r'E:\install_video\frontend\dist')
PLAYWRIGHT = Path(r'C:\Users\zxk\.codex\mcp\mermaid-reinstall-ace9b4f684be4ae3b4b0a3183aec5179\node_modules\playwright')
CHROMIUM = Path(r'C:\Users\zxk\AppData\Local\ms-playwright\chromium_headless_shell-1248\chrome-headless-shell-win64'
                r'\chrome-headless-shell.exe')
EVIDENCE = Path(r'E:\install_video\.planning\2026-10-28-support\integration')
TESTS = Path(__file__).resolve().parent
# Never forwarded to the server: it must not see payment or model credentials from the caller's shell.
STRIPPED = ('STRIPE_', 'OPENAI', 'DEEPSEEK', 'ANTHROPIC', 'LLM_', 'ADMIN_STRIPE')

pytestmark = pytest.mark.skipif(os.environ.get('USER_SUPPORT_BROWSER') != '1' or not (
    DIST.exists() and PLAYWRIGHT.exists() and CHROMIUM.exists()), reason='explicit browser integration run only')


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def test_user_support_flow_in_the_browser():
    port = _free_port()
    origin = f'http://127.0.0.1:{port}'
    workdir = Path(tempfile.mkdtemp(prefix='support-user-it-'))
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(STRIPPED)}
    env.update(DB_URL=f'sqlite:///{(workdir / "support.db").as_posix()}', FRONTEND_DIST=str(DIST),
               JWT_SECRET='synthetic-integration-secret-' + os.urandom(8).hex(),
               PYTHONPATH=os.pathsep.join((str(TESTS.parent), str(TESTS))))
    evidence = EVIDENCE / ('user-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    evidence.mkdir(parents=True)
    server_log, browser_log = evidence / 'server.log', evidence / 'browser.log'
    with server_log.open('wb') as server_out:
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'user_support_server:app', '--host', '127.0.0.1',
                                   '--port', str(port), '--log-level', 'warning'], cwd=str(workdir), env=env,
                                  stdout=server_out, stderr=subprocess.STDOUT)
    try:
        with browser_log.open('wb') as browser_out:
            code = subprocess.run(['node', str(TESTS / 'integration' / 'user_support_browser.cjs'), origin, str(evidence),
                                   EMAIL, PASSWORD, str(PLAYWRIGHT), str(CHROMIUM)], stdout=browser_out,
                                  stderr=subprocess.STDOUT, timeout=420, env=env).returncode
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
    assert result['failed'] == [] and result['total'] >= 15
    assert 'Traceback' not in log, log[-2000:]
