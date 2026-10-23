"""Mind maps validate safe bounded trees; all source/model I/O is mocked."""
import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.services import llm_service, request_cache
from app.services.auth import get_current_user
from app.services.subtitle_service import SubtitleDocument


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    for key, value in {
        "llm_base_url": "https://llm.example/v1", "llm_model": "existing-model",
        "llm_api_key": "private-test-secret", "llm_provider": "openai-compatible",
        "mindmap_max_source_chars": 60000, "mindmap_max_output_tokens": 4096,
        "mindmap_max_nodes": 64, "mindmap_max_depth": 4,
    }.items():
        monkeypatch.setattr(settings, key, value, raising=False)
    request_cache._stores.clear()
    yield
    request_cache._stores.clear()


def node(label="主题", children=None):
    return {"label": label, "children": [] if children is None else children}


def transport_response(root=None, *, finish="stop", content=None):
    return httpx.Response(200, json={"choices": [{"finish_reason": finish,
        "message": {"role": "assistant", "content": content if content is not None
                    else json.dumps({"root": root or node(children=[node("细节")])}, ensure_ascii=False)}}]})


def generate(text="source", **kwargs):
    module = importlib.import_module("app.services.mindmap_service")
    return module.generate_mindmap(text, title="Video", output_language="zh-CN", **kwargs)


def test_public_transport_exists_before_service_implementation():
    assert callable(getattr(llm_service, "generate_mindmap_text", None))


def test_single_request_preserves_whole_source_uses_existing_model_and_finite_output():
    seen = []
    source = "first\n" + "x" * 23000 + "\nLAST"
    def provider(request):
        seen.append(request)
        return transport_response()
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        result = generate(source, client=client)
    assert result.root.model_dump() == node(children=[node("细节")])
    assert (result.provider, result.model) == ("openai-compatible", "existing-model")
    assert len(seen) == 1
    payload = json.loads(seen[0].content)
    assert payload["model"] == "existing-model"
    assert payload["max_tokens"] == 4096
    assert payload["response_format"] == {"type": "json_object"}
    assert str(seen[0].url) == "https://llm.example/v1/chat/completions"
    assert payload["messages"][-1]["content"].endswith(source)
    assert "zh-CN" in payload["messages"][-1]["content"]
    assert settings.llm_model == "existing-model"


@pytest.mark.parametrize("text,kind", [("x" * 60001, "llm_input_too_large"), (" \n", "llm_invalid_input")],
                         ids=["oversize", "blank"])
def test_source_rejected_before_model_without_truncation(text, kind):
    with httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("unexpected HTTP"))) as client:
        with pytest.raises(llm_service.LLMServiceError) as error:
            generate(text, client=client)
    assert error.value.error_type == kind


@pytest.mark.parametrize("finish", ["length", "content_filter"])
def test_incomplete_output_rejected_without_retry(finish):
    seen = []
    def provider(request):
        seen.append(request)
        return transport_response(finish=finish)
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        with pytest.raises(llm_service.LLMServiceError) as error:
            generate(client=client)
    assert error.value.error_type == "llm_incomplete_response"
    assert len(seen) == 1


@pytest.mark.parametrize("content", [
    "{}", '{"root":{"label":"topic"}}', '{"root":{"label":"topic","children":null}}',
    '{"root":{"label":1,"children":[]}}', '{"root":{"label":" ","children":[]}}',
    '{"root":{"label":"topic","children":[],"script":"alert(1)"}}',
    '{"root":{"label":"a","children":[]},"extra":true}',
    '{"root":{"label":"one","label":"two","children":[]}}',
    '```json\n{"root":{"label":"topic","children":[]}}\n```',
    '{"root":', '[]',
])
def test_malformed_or_non_contract_output_rejected(content):
    with httpx.Client(transport=httpx.MockTransport(lambda r: transport_response(content=content))) as client:
        with pytest.raises(llm_service.LLMServiceError) as error:
            generate(client=client)
    assert error.value.error_type == "llm_invalid_response"


@pytest.mark.parametrize("label", ["<script>alert(1)</script>", "![x](javascript:alert(1))", "```mermaid", "a\x00b", "x" * 121])
def test_unsafe_or_oversize_labels_are_rejected_not_edited(label):
    with httpx.Client(transport=httpx.MockTransport(lambda r: transport_response(node(label)))) as client:
        with pytest.raises(llm_service.LLMServiceError) as error:
            generate(client=client)
    assert error.value.error_type == "llm_invalid_response"


@pytest.mark.parametrize("root", [node(children=[node(str(i)) for i in range(9)]),
    node(children=[node(children=[node(children=[node(children=[node()])])])]),
    node(children=[node(children=[node(str(j)) for j in range(8)]) for i in range(8)]),
])
def test_node_children_depth_and_global_count_limits(root):
    with httpx.Client(transport=httpx.MockTransport(lambda r: transport_response(root))) as client:
        with pytest.raises(llm_service.LLMServiceError) as error:
            generate(client=client)
    assert error.value.error_type == "llm_invalid_response"


def test_exact_depth_node_and_label_limits_are_valid():
    # 1 root + 7 branches + 56 leaves = 64 nodes.
    tree = node("x" * 120, [node(children=[node(str(j)) for j in range(8)]) for i in range(7)])
    with httpx.Client(transport=httpx.MockTransport(lambda r: transport_response(tree))) as client:
        assert generate(client=client).root.model_dump() == tree
    tree = node(children=[node(children=[node(children=[node()])])])
    with httpx.Client(transport=httpx.MockTransport(lambda r: transport_response(tree))) as client:
        assert generate(client=client).root.model_dump() == tree


@pytest.mark.parametrize("code", [401, 429, 500])
def test_http_failures_hide_provider_credentials_and_never_retry(code):
    seen = []
    def provider(request):
        seen.append(request)
        return httpx.Response(code, text="private-test-secret provider-body")
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        with pytest.raises(llm_service.LLMServiceError) as error:
            generate(client=client)
    assert error.value.error_type == "llm_error"
    assert "private-test-secret" not in str(error.value)
    assert "llm.example" not in str(error.value)
    assert len(seen) == 1


def route_client(user="account-a"):
    module = importlib.import_module("app.routes.mindmap")
    app = FastAPI()
    app.include_router(module.router)
    if user:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user)
    return TestClient(app), app, module


def test_route_requires_login():
    client, _, _ = route_client(None)
    response = client.post("/api/mindmap", json={"url": "https://example.com/video"})
    assert response.status_code == 401


@pytest.mark.parametrize("missing", ["llm_base_url", "llm_model"])
def test_unconfigured_route_rejects_before_source_io(monkeypatch, missing):
    client, _, module = route_client()
    monkeypatch.setattr(settings, missing, "")
    monkeypatch.setattr(module, "load_cached_subtitle", lambda *args: pytest.fail("source I/O before configuration check"))
    response = client.post("/api/mindmap", json={"url": "https://example.com/video"})
    assert response.status_code == 503
    assert response.json()["detail"]["error_type"] == "llm_unconfigured"


def test_route_exposes_contract_and_reuses_by_account_parameters_document_config(monkeypatch):
    client, app, module = route_client()
    doc = [SubtitleDocument("Video", "en", False, ["en"], "source")]
    seen = []
    monkeypatch.setattr(module, "load_cached_subtitle", lambda *args: doc[0])
    def provider(request):
        seen.append(request)
        return transport_response()
    original = llm_service.generate_mindmap_text
    with httpx.Client(transport=httpx.MockTransport(provider)) as model_client:
        monkeypatch.setattr("app.services.mindmap_service.generate_mindmap_text", lambda *a, **kw: original(*a, **kw, client=model_client))
        body = {"url": "https://example.com/video"}
        first = client.post("/api/mindmap", json=body)
        assert first.status_code == 200, first.text
        assert first.json() == {"title": "Video", "source_language": "en", "root": node(children=[node("细节")]), "provider": "openai-compatible", "model": "existing-model"}
        assert client.post("/api/mindmap", json=body).json() == first.json()
        assert len(seen) == 1
        assert client.post("/api/mindmap", json={**body, "output_language": "en"}).status_code == 200
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="account-b")
        assert client.post("/api/mindmap", json=body).status_code == 200
        doc[0] = SubtitleDocument("Different title", "en", False, ["en"], "source")
        assert client.post("/api/mindmap", json=body).status_code == 200
        monkeypatch.setattr(settings, "mindmap_max_nodes", 63)
        assert client.post("/api/mindmap", json=body).status_code == 200
        monkeypatch.setattr(settings, "llm_api_key", "rotated-secret")
        assert client.post("/api/mindmap", json=body).status_code == 200
    assert len(seen) == 6


def test_route_source_limit_is_422_before_model(monkeypatch):
    client, _, module = route_client()
    monkeypatch.setattr(module, "load_cached_subtitle", lambda *args: SubtitleDocument("Video", "en", False, ["en"], "x" * 60001))
    monkeypatch.setattr(module, "generate_mindmap", lambda *a, **kw: pytest.fail("unexpected model call"))
    response = client.post("/api/mindmap", json={"url": "https://example.com/video"})
    assert response.status_code == 422
    assert response.json()["detail"]["error_type"] == "mindmap_unsupported_length"


def test_concurrent_duplicate_routes_share_single_model_call(monkeypatch):
    client, _, module = route_client()
    monkeypatch.setattr(module, "load_cached_subtitle", lambda *args: SubtitleDocument("Video", "en", False, ["en"], "source"))
    entered, joined, release = Event(), Event(), Event()
    from concurrent.futures import Future
    class ObservedFuture(Future):
        def result(self, timeout=None):
            joined.set()
            return super().result(timeout)
    monkeypatch.setattr(request_cache, "Future", ObservedFuture)
    calls = []
    def provider(request):
        calls.append(request)
        entered.set()
        assert release.wait(5)
        return transport_response()
    original = llm_service.generate_mindmap_text
    with httpx.Client(transport=httpx.MockTransport(provider)) as model_client, ThreadPoolExecutor(2) as pool:
        monkeypatch.setattr("app.services.mindmap_service.generate_mindmap_text", lambda *a, **kw: original(*a, **kw, client=model_client))
        first = pool.submit(client.post, "/api/mindmap", json={"url": "https://example.com/video"})
        assert entered.wait(3)
        second = pool.submit(client.post, "/api/mindmap", json={"url": "https://example.com/video"})
        try:
            assert joined.wait(3)
        finally:
            release.set()
        assert first.result(5).json() == second.result(5).json()
    assert len(calls) == 1


def test_deepseek_uses_json_and_disables_thinking_without_switching_models(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    requests = []
    def provider(request):
        requests.append(json.loads(request.content))
        return transport_response()
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        assert generate(client=client).model == "existing-model"
    assert len(requests) == 1
    assert requests[0]["thinking"] == {"type": "disabled"}
    assert requests[0]["response_format"] == {"type": "json_object"}


def test_network_failure_is_safe_and_not_retried():
    calls = []
    def provider(request):
        calls.append(request)
        raise httpx.ReadTimeout("private-test-secret llm.example", request=request)
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        with pytest.raises(llm_service.LLMServiceError) as error:
            generate(client=client)
    assert error.value.error_type == "llm_error"
    assert "private-test-secret" not in str(error.value)
    assert "llm.example" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize("setting,value", [
    ("mindmap_max_source_chars", 59999), ("mindmap_max_output_tokens", 4095),
    ("mindmap_max_nodes", 63), ("mindmap_max_depth", 3),
])
def test_each_mindmap_limit_invalidates_cached_result(monkeypatch, setting, value):
    client, _, module = route_client()
    monkeypatch.setattr(module, "load_cached_subtitle", lambda *args: SubtitleDocument("Video", "en", False, ["en"], "source"))
    calls = []
    original = llm_service.generate_mindmap_text
    def provider(request):
        calls.append(request)
        return transport_response()
    with httpx.Client(transport=httpx.MockTransport(provider)) as model_client:
        monkeypatch.setattr("app.services.mindmap_service.generate_mindmap_text", lambda *a, **kw: original(*a, **kw, client=model_client))
        body = {"url": "https://example.com/video"}
        assert client.post("/api/mindmap", json=body).status_code == 200
        monkeypatch.setattr(settings, setting, value)
        assert client.post("/api/mindmap", json=body).status_code == 200
    assert len(calls) == 2


@pytest.mark.parametrize("setting,value", [
    ("mindmap_max_source_chars", 60001), ("mindmap_max_output_tokens", 4097),
    ("mindmap_max_nodes", 65), ("mindmap_max_depth", 5),
    ("mindmap_max_nodes", True), ("mindmap_max_depth", 0),
])
def test_invalid_profile_is_503_before_subtitle_io(monkeypatch, setting, value):
    client, _, module = route_client()
    monkeypatch.setattr(settings, setting, value)
    monkeypatch.setattr(module, "load_cached_subtitle", lambda *a: pytest.fail("unexpected source I/O"))
    response = client.post("/api/mindmap", json={"url": "https://example.com/video"})
    assert response.status_code == 503
    assert response.json()["detail"]["error_type"] == "llm_unconfigured"


def test_route_model_errors_are_502_and_failures_are_not_cached(monkeypatch):
    client, _, module = route_client()
    monkeypatch.setattr(module, "load_cached_subtitle", lambda *args: SubtitleDocument("Video", "en", False, ["en"], "source"))
    calls = []
    original = llm_service.generate_mindmap_text
    def provider(request):
        calls.append(request)
        return transport_response(content="{}") if len(calls) == 1 else transport_response()
    with httpx.Client(transport=httpx.MockTransport(provider)) as model_client:
        monkeypatch.setattr("app.services.mindmap_service.generate_mindmap_text", lambda *a, **kw: original(*a, **kw, client=model_client))
        body = {"url": "https://example.com/video"}
        response = client.post("/api/mindmap", json=body)
        assert response.status_code == 502
        assert response.json()["detail"]["error_type"] == "llm_invalid_response"
        assert len(calls) == 1
        assert client.post("/api/mindmap", json=body).status_code == 200
    assert len(calls) == 2
