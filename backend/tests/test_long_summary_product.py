"""Product long summaries use one bounded request; every HTTP response is mocked."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import httpx
import pytest

from app.config import Settings, settings
from app.services import llm_service


@pytest.fixture(autouse=True)
def configure(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.example/v1/chat/completions")
    monkeypatch.setattr(settings, "llm_api_key", "test-secret")
    monkeypatch.setattr(settings, "llm_model", "short-model")
    monkeypatch.setattr(settings, "llm_provider", "openai-compatible")
    monkeypatch.setattr(settings, "llm_long_summary_model", "deepseek-v4-pro", raising=False)
    monkeypatch.setattr(settings, "llm_long_summary_max_input_chars", 60000, raising=False)
    monkeypatch.setattr(settings, "llm_long_summary_max_output_tokens", 16384, raising=False)
    monkeypatch.setattr(settings, "llm_long_summary_timeout_seconds", 300, raising=False)
    monkeypatch.setattr(settings, "llm_long_summary_max_concurrent", 1, raising=False)


def response(text="\n# Overview\n\nDetailed **themes**.\n", *, status="completed"):
    return httpx.Response(200, json={"object": "response", "status": status,
        "output": [{"type": "reasoning", "content": "private"},
                   {"type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": text}]}]})


def summarize(text="source", **kwargs):
    return llm_service.summarize_long_text(text, title="Video", output_language="en", **kwargs)


def test_full_source_goes_once_to_independent_pro_text_high_without_editing():
    seen = []
    source = "first\nfirst\n" + "x" * 22000 + "\nLAST"
    markdown = "\n# Overview\n\n- **Exact** result.\n"

    def provider(request):
        seen.append(request)
        return response(markdown)

    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        result = summarize(source, client=client)
    assert len(seen) == 1
    request = seen[0]
    payload = json.loads(request.content)
    assert str(request.url) == "https://llm.example/v1/responses"
    assert payload["model"] == "deepseek-v4-pro"
    assert payload["reasoning"] == {"effort": "high"}
    assert payload["text"] == {"format": {"type": "text"}}
    assert payload["max_output_tokens"] == 16384
    assert payload["input"][0]["content"].endswith(source)
    assert "en" in payload["instructions"] + payload["input"][0]["content"]
    assert result.summary == markdown
    assert result.key_points == []
    assert result.model == "deepseek-v4-pro"
    assert settings.llm_model == "short-model"
    assert result.provider == "openai-compatible"


@pytest.mark.parametrize("status,kind", [("incomplete", "llm_incomplete_response"), ("failed", "llm_error")])
def test_incomplete_or_failed_output_is_not_accepted_or_retried(status, kind):
    calls = []
    def provider(request):
        calls.append(request)
        return response(status=status)
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        with pytest.raises(llm_service.LLMServiceError) as exc:
            summarize(client=client)
    assert exc.value.error_type == kind
    assert len(calls) == 1


@pytest.mark.parametrize("text,kind", [("x" * 60001, "llm_input_too_large"), ("  ", "llm_invalid_input")], ids=["over-limit", "empty"])
def test_invalid_source_rejected_without_http(text, kind):
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("unexpected HTTP"))) as client:
        with pytest.raises(llm_service.LLMServiceError) as exc:
            summarize(text, client=client)
    assert exc.value.error_type == kind


@pytest.mark.parametrize("model", ["gpt-4.1", "deepseek-chat", "", "deepseek-v4-pro\nother"])
def test_incompatible_model_is_rejected_without_http(monkeypatch, model):
    monkeypatch.setattr(settings, "llm_long_summary_model", model)
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("unexpected HTTP"))) as client:
        with pytest.raises(llm_service.LLMServiceError) as exc:
            summarize(client=client)
    assert exc.value.error_type == "llm_unconfigured"


def test_busy_is_immediate_and_failed_slot_is_released():
    entered, finish = Event(), Event()
    def provider(request):
        entered.set()
        assert finish.wait(5)
        raise httpx.ReadTimeout("https://private.example/?token=test-secret", request=request)
    with httpx.Client(transport=httpx.MockTransport(provider)) as client, ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(summarize, client=client)
        try:
            assert entered.wait(5)
            with pytest.raises(llm_service.LLMServiceError) as busy:
                summarize(client=client)
            assert busy.value.error_type == "llm_busy"
        finally:
            finish.set()
        with pytest.raises(llm_service.LLMServiceError) as failed:
            pending.result(5)
    assert "test-secret" not in str(failed.value)
    assert "private.example" not in str(failed.value)
    with httpx.Client(transport=httpx.MockTransport(lambda request: response("success"))) as client:
        assert summarize(client=client).summary == "success"


def test_owned_client_has_independent_timeout_and_closes(monkeypatch):
    seen = []
    class FakeClient:
        def __init__(self, *, timeout):
            seen.append(timeout)
        def post(self, url, headers, json):
            return httpx.Response(200, json=response("done").json(), request=httpx.Request("POST", url))
        def close(self):
            seen.append("closed")
    monkeypatch.setattr(llm_service.httpx, "Client", FakeClient)
    assert summarize().summary == "done"
    assert seen == [300.0, "closed"]


@pytest.mark.parametrize("code", [401, 429, 500])
def test_http_errors_have_safe_messages_one_attempt_and_release_slot(code):
    calls = []
    def provider(request):
        calls.append(request)
        return httpx.Response(code, text="private provider body test-secret")
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        with pytest.raises(llm_service.LLMServiceError) as exc:
            summarize(client=client)
    assert exc.value.error_type == "llm_error"
    assert "test-secret" not in str(exc.value)
    assert "llm.example" not in str(exc.value)
    assert len(calls) == 1
    with httpx.Client(transport=httpx.MockTransport(lambda request: response("after error"))) as client:
        assert summarize(client=client).summary == "after error"


def test_two_configured_slots_allow_two_requests_then_reject_third(monkeypatch):
    monkeypatch.setattr(settings, "llm_long_summary_max_concurrent", 2)
    entered_one, entered_two, finish = Event(), Event(), Event()
    from threading import Lock
    counter_lock = Lock()
    count = 0
    def provider(request):
        nonlocal count
        with counter_lock:
            count += 1
            (entered_one if count == 1 else entered_two).set()
        assert finish.wait(5)
        return response("done")
    with httpx.Client(transport=httpx.MockTransport(provider)) as client, ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(summarize, client=client)
        second = None
        try:
            assert entered_one.wait(5)
            second = pool.submit(summarize, client=client)
            assert entered_two.wait(5)
            with pytest.raises(llm_service.LLMServiceError) as exc:
                summarize(client=client)
            assert exc.value.error_type == "llm_busy"
        finally:
            finish.set()
        assert first.result(5).summary == "done"
        assert second is not None and second.result(5).summary == "done"
    assert count == 2


def test_product_defaults_are_finite_and_short_default_unchanged():
    cfg = Settings()
    assert cfg.summary_max_source_chars == 60000
    assert cfg.summary_long_threshold_chars == 20000
    assert cfg.llm_long_summary_model == "deepseek-v4-pro"
    assert cfg.llm_long_summary_max_input_chars == 60000
    assert cfg.llm_long_summary_max_output_tokens == 16384
    assert cfg.llm_long_summary_timeout_seconds == 300
    assert cfg.llm_long_summary_max_concurrent == 1
    assert cfg.llm_summary_strategy == "legacy"
    assert cfg.llm_summary_generation_mode == "single"


@pytest.mark.parametrize("name,bad", [
    ("summary_long_threshold_chars", 0), ("summary_long_threshold_chars", True),
    ("llm_long_summary_max_input_chars", 60001), ("llm_long_summary_max_input_chars", -1),
    ("llm_long_summary_max_output_tokens", 65537), ("llm_long_summary_max_output_tokens", True),
    ("llm_long_summary_timeout_seconds", 0), ("llm_long_summary_timeout_seconds", 901),
    ("llm_long_summary_max_concurrent", 0), ("llm_long_summary_max_concurrent", 33),
    ("llm_long_summary_model", "gpt-test"),
])
def test_invalid_long_configuration_fails_at_startup(name, bad):
    with pytest.raises(ValueError, match=name):
        Settings(**{name: bad})


def test_long_configuration_uses_explicit_environment_controls(monkeypatch):
    values = {"SUMMARY_LONG_THRESHOLD_CHARS": "15000", "LLM_LONG_SUMMARY_MAX_INPUT_CHARS": "45000",
        "LLM_LONG_SUMMARY_MAX_OUTPUT_TOKENS": "10000", "LLM_LONG_SUMMARY_TIMEOUT_SECONDS": "180",
        "LLM_LONG_SUMMARY_MAX_CONCURRENT": "2", "LLM_LONG_SUMMARY_MODEL": "deepseek-v4-pro",
        "SUMMARY_MAX_SOURCE_CHARS": "10000"}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    cfg = Settings.from_env()
    for key, value in values.items():
        assert getattr(cfg, key.lower()) == (value if key.endswith("MODEL") else int(value))
