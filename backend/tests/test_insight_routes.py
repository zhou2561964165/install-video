from collections import defaultdict
from uuid import uuid4

import pytest
pytestmark = pytest.mark.usefixtures("vip_entitlements")
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
    assert r.json()["format"] == "structured"
    assert r.json()["conclusion"] == ""


def test_summary_route_delivers_generated_title_and_closing_synthesis(monkeypatch):
    monkeypatch.setattr("app.routes.insight_common.fetch_subtitle_document", lambda url, language: _doc())
    points = ["## 条件与结果\n\n保留必要前提。\n\n### 一个阶段\n\n说明。"]
    monkeypatch.setattr(
        "app.routes.summary.summarize_text",
        lambda *args, **kwargs: LLMSummaryResult("高层概览", points, "mock", "mock-model",
            title="条件如何影响结果", conclusion="归纳主题间的关系，同时保留条件。"),
    )
    response = client.post("/api/summary", json={"url": "https://example.com/v"}, headers=_auth_headers())
    assert response.status_code == 200
    assert response.json()["title"] == "条件如何影响结果"
    assert response.json()["conclusion"] == "归纳主题间的关系，同时保留条件。"
    assert response.json()["key_points"] == points


@pytest.mark.parametrize("source_chars", [500, 2200, 20_000])
def test_short_and_medium_summary_still_reach_model(monkeypatch, source_chars):
    monkeypatch.setattr("app.config.settings.summary_max_source_chars", 20_000, raising=False)
    doc = SubtitleDocument("实际视频标题", "en", False, ["en"], "字" * source_chars)
    monkeypatch.setattr("app.routes.insight_common.fetch_subtitle_document", lambda url, language: doc)
    calls = []

    def summarize(text, title, output_language):
        calls.append((text, title, output_language))
        return LLMSummaryResult("摘要", ["要点"], "mock", "mock-model")

    monkeypatch.setattr("app.routes.summary.summarize_text", summarize)
    r = client.post(
        "/api/summary", json={"url": "https://example.com/v"}, headers=_auth_headers(),
    )
    assert r.status_code == 200
    assert calls == [(doc.text, doc.title, "zh-CN")]
    assert r.json()["title"] == doc.title


@pytest.mark.parametrize("source_chars,limit", [(20_001, 20_000), (35_000, 20_000), (101, 100)])
def test_explicit_public_cap_rejects_source_before_either_model_call(monkeypatch, source_chars, limit):
    monkeypatch.setattr("app.config.settings.summary_max_source_chars", limit, raising=False)
    doc = SubtitleDocument("实际视频标题", "en", False, ["en"], "字" * source_chars)
    monkeypatch.setattr("app.routes.insight_common.fetch_subtitle_document", lambda url, language: doc)
    calls = []

    def summarize(*args, **kwargs):
        calls.append((args, kwargs))
        return LLMSummaryResult("不应生成", ["不应生成"], "mock", "mock-model")

    monkeypatch.setattr("app.routes.summary.summarize_text", summarize)
    monkeypatch.setattr("app.routes.summary.summarize_long_text", summarize)
    r = client.post(
        "/api/summary", json={"url": "https://example.com/v"}, headers=_auth_headers(),
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error_type"] == "summary_unsupported_length"
    assert "超过当前总结长度上限" in r.json()["detail"]["error"]
    assert calls == []


@pytest.mark.parametrize("source_chars", [20_001, 35_000, 60_000])
def test_long_route_preserves_markdown_and_metadata_and_skips_old_pipeline(monkeypatch, source_chars):
    monkeypatch.setattr("app.config.settings.summary_max_source_chars", 60_000)
    monkeypatch.setattr("app.config.settings.summary_long_threshold_chars", 20_000)
    monkeypatch.setattr("app.config.settings.llm_long_summary_max_input_chars", 60_000)
    doc = SubtitleDocument("真实标题", "en", False, ["en"], "字" * source_chars)
    monkeypatch.setattr("app.routes.insight_common.fetch_subtitle_document", lambda url, language: doc)
    calls = []
    markdown = "\n# 概览\n\n- **完整主题**\n"
    def long_summary(text, title, output_language):
        calls.append((text, title, output_language))
        return LLMSummaryResult(markdown, [], "openai-compatible", "deepseek-v4-pro")
    monkeypatch.setattr("app.routes.summary.summarize_long_text", long_summary)
    monkeypatch.setattr("app.routes.summary.summarize_text", lambda *args, **kwargs: pytest.fail("old pipeline"))
    r = client.post("/api/summary", json={"url": "https://example.com/v", "output_language": "en"}, headers=_auth_headers())
    assert r.status_code == 200
    assert r.json() == {"title": doc.title, "source_language": "en", "summary": markdown,
        "key_points": [], "provider": "openai-compatible", "model": "deepseek-v4-pro", "format": "markdown", "conclusion": ""}
    assert calls == [(doc.text, doc.title, "en")]


@pytest.mark.parametrize("public_cap,service_cap,source_chars", [(60_000, 60_000, 60_001), (60_000, 30_000, 30_001)])
def test_long_limits_reject_without_either_model_call(monkeypatch, public_cap, service_cap, source_chars):
    monkeypatch.setattr("app.config.settings.summary_max_source_chars", public_cap)
    monkeypatch.setattr("app.config.settings.llm_long_summary_max_input_chars", service_cap)
    doc = SubtitleDocument("title", "en", False, ["en"], "x" * source_chars)
    monkeypatch.setattr("app.routes.insight_common.fetch_subtitle_document", lambda url, language: doc)
    monkeypatch.setattr("app.routes.summary.summarize_long_text", lambda *args, **kwargs: pytest.fail("unexpected long call"))
    monkeypatch.setattr("app.routes.summary.summarize_text", lambda *args, **kwargs: pytest.fail("unexpected short call"))
    r = client.post("/api/summary", json={"url": "https://example.com/v"}, headers=_auth_headers())
    assert r.status_code == 422
    assert r.json()["detail"]["error_type"] == "summary_unsupported_length"


@pytest.mark.parametrize("kind,status", [("llm_busy", 503), ("llm_unconfigured", 503),
    ("llm_error", 502), ("llm_incomplete_response", 502), ("llm_invalid_response", 502)])
def test_long_failure_status_and_no_short_fallback(monkeypatch, kind, status):
    monkeypatch.setattr("app.config.settings.summary_max_source_chars", 60_000)
    doc = SubtitleDocument("title", "en", False, ["en"], "x" * 21_000)
    monkeypatch.setattr("app.routes.insight_common.fetch_subtitle_document", lambda url, language: doc)
    monkeypatch.setattr("app.routes.summary.summarize_text", lambda *args, **kwargs: pytest.fail("unexpected fallback"))
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise LLMServiceError(kind, "safe failure")
    monkeypatch.setattr("app.routes.summary.summarize_long_text", fail)
    r = client.post("/api/summary", json={"url": "https://example.com/v"}, headers=_auth_headers())
    assert r.status_code == status
    assert r.json()["detail"] == {"error_type": kind, "error": "safe failure"}
    assert calls == [1]


def test_long_threshold_is_independent_of_public_limit(monkeypatch):
    monkeypatch.setattr("app.config.settings.summary_max_source_chars", 60_000)
    monkeypatch.setattr("app.config.settings.summary_long_threshold_chars", 10)
    monkeypatch.setattr("app.routes.insight_common.fetch_subtitle_document", lambda url, language: _doc())
    monkeypatch.setattr("app.routes.summary.summarize_long_text", lambda *args, **kwargs: LLMSummaryResult("markdown", [], "mock", "pro"))
    monkeypatch.setattr("app.routes.summary.summarize_text", lambda *args, **kwargs: pytest.fail("old pipeline"))
    r = client.post("/api/summary", json={"url": "https://example.com/v"}, headers=_auth_headers())
    assert r.status_code == 200
    assert r.json()["format"] == "markdown"


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
