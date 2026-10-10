"""New loopback HTTP boundary, budget and cleanup checks; old guard tests reused."""
import importlib.util
import json
from pathlib import Path
import socket

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "docs/acceptance-reports/2026-10-09-online-formal-flow/scripts/online_guard_faults.py"


def load():
    assert SCRIPT.is_file(), "Zero-paid loopback HTTP runner is not implemented"
    spec = importlib.util.spec_from_file_location("online_guard_faults_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_plan_does_not_open_socket(monkeypatch, capsys):
    module = load()
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("Default plan opened a socket"))
    module.main([])
    plan = json.loads(capsys.readouterr().out)
    assert plan["socket_started"] is False and plan["paid_model_calls"] == 0
    assert plan["maximum_loopback_posts"] == 20


def test_loopback_uses_real_http_and_stops_before_third_request():
    module = load()
    with module.FakeUpstream(maximum_posts=2) as upstream:
        with module.LoopbackTransport(upstream) as client:
            for _ in range(2):
                response = client.post(upstream.endpoint, headers={}, json={"model": "offline-model"})
                assert response.status_code == 200
                assert response.json()["model"] == "offline-model"
            with pytest.raises(RuntimeError, match="cap"):
                client.post(upstream.endpoint, headers={}, json={"model": "offline-model"})
        assert upstream.received_posts == 2
    assert upstream.shutdown_verified is True
    assert not upstream.thread.is_alive()


@pytest.mark.parametrize("url", ["https://example.com/chat/completions", "http://localhost:123/chat/completions",
    "http://127.0.0.1:1/chat/completions", "http://127.0.0.1@evil.invalid/chat/completions"])
def test_non_stub_destination_is_rejected_without_http(url):
    module = load()
    with module.FakeUpstream(maximum_posts=1) as upstream:
        with module.LoopbackTransport(upstream) as client:
            with pytest.raises(ValueError):
                client.post(url, headers={}, json={"model": "offline-model"})
        assert upstream.received_posts == 0
    assert upstream.shutdown_verified is True


def test_exception_also_shuts_down_listener_and_thread():
    module = load()
    upstream = module.FakeUpstream()
    with pytest.raises(RuntimeError, match="case exception"):
        with upstream:
            raise RuntimeError("case exception")
    assert upstream.shutdown_verified is True
    assert not upstream.thread.is_alive()


def test_stub_cap_cannot_exceed_zero_paid_allocation():
    module = load()
    with pytest.raises(ValueError):
        module.FakeUpstream(maximum_posts=21)
