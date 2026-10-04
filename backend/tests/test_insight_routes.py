from collections import defaultdict
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.llm_service import LLMSummaryResult, LLMServiceError, LLMTextResult
from app.services.subtitle_service import SubtitleDocument

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limit(monkeypatch):
    monkeypatch.setattr("app.main._window", defaultdict(list))


def _auth_headers():
    r = client.post(
        "/api/auth/register",
        json={"email": f"insight-{uuid4()}@example.com", "password": "password123"},
    )
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _doc():
    return SubtitleDocument("视频", "en", False, ["en", "zh-Hans"], "hello world")


@pytest.mark.parametrize("path", ["/api/subtitle", "/api/subtitle/translate", "/api/summary"])
def test_insight_routes_require_login(path):
    body = {"url": "https://example.com/v"}
    if path.endswith("translate"):
        body["target_language"] = "zh-CN"
    r = client.post(path, json=body)
    assert r.status_code == 401
    assert r.json()["detail"]["error_type"] == "login_required"


def test_subtitle_route(monkeypatch):
    monkeypatch.setattr("app.routes.insight_common.fetch_subtitle_document", lambda url, language: _doc())
    r = client.post("/api/subtitle", json={"url": "https://example.com/v"}, headers=_auth_headers())
    assert r.status_code == 200
    assert r.json()["text"] == "hello world"
    assert r.json()["available_languages"] == ["en", "zh-Hans"]


def test_translate_route(monkeypatch):
    monkeypatch.setattr("app.routes.insight_common.fetch_subtitle_document", lambda url, language: _doc())
    monkeypatch.setattr(
        "app.routes.subtitle.translate_text",
        lambda text, target, source_language: LLMTextResult("你好，世界", "mock", "mock-model"),
    )
    r = client.post(
        "/api/subtitle/translate",
        json={"url": "https://example.com/v", "target_language": "zh-CN"},
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    assert r.json()["text"] == "你好，世界"


def test_summary_route(monkeypatch):
    monkeypatch.setattr("app.routes.insight_common.fetch_subtitle_document", lambda url, language: _doc())
    monkeypatch.setattr(
        "app.routes.summary.summarize_text",
        lambda text, title, output_language: LLMSummaryResult("摘要", ["一", "二", "三"], "mock", "mock-model"),
    )
    r = client.post(
        "/api/summary",
        json={"url": "https://example.com/v", "output_language": "zh-CN"},
        headers=_auth_headers(),
    )
    assert r.status_code == 200
    assert r.json()["summary"] == "摘要"
    assert r.json()["key_points"] == ["一", "二", "三"]


def test_unconfigured_llm_maps_to_503(monkeypatch):
    monkeypatch.setattr("app.routes.insight_common.fetch_subtitle_document", lambda url, language: _doc())
    monkeypatch.setattr(
        "app.routes.subtitle.translate_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(LLMServiceError("llm_unconfigured", "未配置")),
    )
    r = client.post(
        "/api/subtitle/translate",
        json={"url": "https://example.com/v", "target_language": "zh-CN"},
        headers=_auth_headers(),
    )
    assert r.status_code == 503
    assert r.json()["detail"]["error_type"] == "llm_unconfigured"
