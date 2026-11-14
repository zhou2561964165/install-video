"""Dedicated U3 offline runner; child mode guards before importing tests/app."""
import os
import socket
import sys
from pathlib import Path
import hashlib
import importlib.metadata
import json
import threading

roots = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR') if key in os.environ}
os.environ.clear()
os.environ.update(roots)
os.environ.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', DB_URL='sqlite:///:memory:', BILIBILI_COOKIE_FILE='')
sys.dont_write_bytecode = True
workspace = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(workspace / 'backend'))

def forbidden(*args, **kwargs):
    raise AssertionError('U3 offline network denied')

socket.getaddrinfo = forbidden
socket.socket.connect_ex = forbidden
original_connect, original_pair = socket.socket.connect, socket.socketpair
ipc = threading.local()
def connect(sock, address):
    if getattr(ipc, 'active', False) and isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
        return original_connect(sock, address)
    return forbidden()
def socketpair(*args, **kwargs):
    ipc.active = True
    try:
        return original_pair(*args, **kwargs)
    finally:
        ipc.active = False
socket.socket.connect, socket.socketpair = connect, socketpair

if sys.argv[1] == '--child':
    import runpy
    tests = runpy.run_path(str(workspace / 'backend/tests/production/test_outbound_budget_group.py'))
    tests['_child_scenario'](sys.argv[2])
    raise SystemExit(0)

taskdir = Path(__file__).parent
product = ['backend/app/services/' + name + '.py' for name in (
    'outbound_policy', 'outbound_budget', 'outbound_httpx', 'source_network',
    'subtitle_sources', 'bilibili_subtitle_source', 'bilibili_api_source',
    'bilibili_session', 'subtitle_service', 'ytdlp_service', 'download_budget_codec')]
files = product + ['pyproject.toml', 'uv.lock', 'backend/tests/production/test_outbound_budget_group.py']
def hashes():
    return {name: hashlib.sha256((workspace / name).read_bytes()).hexdigest() for name in files}
receipt = {'executable': sys.executable, 'python': sys.version,
           'versions': {name: importlib.metadata.version(name) for name in ('pytest', 'httpx', 'httpcore', 'yt-dlp')},
           'before': hashes(), 'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'targets': sys.argv[2:], 'network_policy': 'pre-import DNS/connect/connect_ex denied; stdlib socketpair IPC only'}
import pytest
class Tee:
    def __init__(self, stream, log): self.stream, self.log = stream, log
    def write(self, value): self.log.write(value); return self.stream.write(value)
    def flush(self): self.log.flush(); self.stream.flush()
    def isatty(self): return False
logpath = taskdir / sys.argv[1]
with logpath.open('x', encoding='utf-8') as log:
    out, err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = Tee(out, log), Tee(err, log)
        code = pytest.main(['--noconftest', '-p', 'no:cacheprovider', '-q', '--tb=short', *sys.argv[2:]])
    finally:
        sys.stdout, sys.stderr = out, err
receipt.update(exit=int(code), after=hashes())
with logpath.with_suffix('.receipt.json').open('x', encoding='utf-8') as output:
    json.dump(receipt, output, indent=2)
raise SystemExit(code)
