# backend/tests/test_rate_limit.py
from collections import defaultdict

from fastapi.testclient import TestClient

from app.main import app


def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.setattr("app.main._settings_rate_limit", 1)
    monkeypatch.setattr("app.main._window", defaultdict(list))
    # 直接发两个请求，第二个应被限流（客户端 IP 固定为 testclient）
    from app.services import ytdlp_service

    monkeypatch.setattr(ytdlp_service, "extract_info", lambda url: {"title": "t", "formats": []})
    c = TestClient(app)
    first = c.post("/api/parse", json={"url": "https://example.com/v"})
    second = c.post("/api/parse", json={"url": "https://example.com/v"})
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"]["error_type"] == "quota"
