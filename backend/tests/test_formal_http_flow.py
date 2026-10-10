"""Real localhost gate tests; no environment files, app database or paid vendor."""
from contextlib import ExitStack, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import socket
import threading

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-09-online-formal-flow/scripts/formal_http_flow.py"


@pytest.fixture
def flow():
    spec = importlib.util.spec_from_file_location("formal_http_gate_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def counted_http(*, proxy=False):
    """Proxy trap and target both stay local; count requests received over a socket."""
    counts = {"posts": 0, "other": 0}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def finish_response(self, status, body):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            with lock:
                counts["posts"] += 1
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            body = json.dumps({"received_at": "proxy" if proxy else "owned_target"}).encode()
            self.finish_response(502 if proxy else 200, body)

        def do_CONNECT(self):
            with lock:
                counts["other"] += 1
            self.finish_response(502, b'{}')

        def do_GET(self):
            with lock:
                counts["other"] += 1
            self.finish_response(502, b'{}')

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", counts
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive(), "Local test HTTP server did not stop"


def state():
    return {"lock": threading.Lock(), "posts": 0, "transport_reservations": 0,
            "events": [], "mode": "normal"}


def test_proxy_environment_and_lowercase_no_proxy_cannot_redirect_owned_post(flow, monkeypatch):
    with counted_http() as (target, target_count), counted_http(proxy=True) as (proxy, proxy_count):
        for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
            monkeypatch.setenv(name, proxy)
        monkeypatch.setenv("NO_PROXY", "")
        monkeypatch.setenv("no_proxy", "example.invalid")
        endpoint = target + "/v1/chat/completions"
        gate = flow.LoopbackGate(endpoint, state(), httpx)
        # Passing trust_env cannot undo the gate's required proxy isolation.
        client = gate.client(timeout=2, trust_env=True)
        try:
            response = client.post(endpoint, json={"model": "synthetic-local"})
            assert response.status_code == 200
            assert response.json() == {"received_at": "owned_target"}
        finally:
            client.close()
        assert target_count["posts"] == 1
        assert proxy_count == {"posts": 0, "other": 0}


def test_21st_post_is_refused_before_http_and_shared_cap_counts_all_clients(flow):
    with counted_http() as (target, target_count):
        endpoint = target + "/v1/chat/completions"
        shared_state = state()
        gate = flow.LoopbackGate(endpoint, shared_state, httpx)
        first, second = gate.client(timeout=2), gate.client(timeout=2)
        try:
            for _ in range(10):
                assert first.post(endpoint, json={"model": "synthetic-local"}).status_code == 200
            for _ in range(10):
                assert second.post(endpoint, json={"model": "synthetic-local"}).status_code == 200
            with pytest.raises(RuntimeError):
                second.post(endpoint, json={"model": "synthetic-local"})
        finally:
            first.close()
            second.close()
        assert target_count["posts"] == 20
        assert shared_state["transport_reservations"] == 20


def test_non_owned_url_is_rejected_before_any_server_receives_post(flow):
    with counted_http() as (target, target_count), counted_http() as (foreign, foreign_count):
        endpoint = target + "/v1/chat/completions"
        shared_state = state()
        gate = flow.LoopbackGate(endpoint, shared_state, httpx)
        client = gate.client(timeout=2)
        try:
            with pytest.raises(RuntimeError):
                client.post(foreign + "/v1/chat/completions", json={"model": "synthetic-local"})
        finally:
            client.close()
        assert target_count["posts"] == foreign_count["posts"] == 0
        assert shared_state["transport_reservations"] == 0


def test_initialization_failure_closes_both_owned_servers_and_threads(flow):
    threads, ports = [], []
    with pytest.raises(RuntimeError, match="injected startup failure"):
        with ExitStack() as stack:
            for _ in range(2):
                server = flow.start_http(stack, BaseHTTPRequestHandler, threads)
                ports.append(server.server_port)
                # Confirm an actual owned listener exists before the failure.
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.settimeout(0.2)
                    assert probe.connect_ex(("127.0.0.1", server.server_port)) == 0
            raise RuntimeError("injected startup failure after both HTTP servers")
    assert len(threads) == 2 and all(not thread.is_alive() for thread in threads)
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            assert probe.connect_ex(("127.0.0.1", port)) != 0
