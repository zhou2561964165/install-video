import httpx
import pytest

from app.config import settings
from app.services.llm_service import LLMServiceError, _content_from_payload, summarize_text, translate_text


class _FakeClient:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def post(self, url, headers, json):
        self.calls.append((url, headers, json))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": self.content}}]},
            request=httpx.Request("POST", url),
        )


def _configure(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.example/v1")
    monkeypatch.setattr(settings, "llm_api_key", "secret")
    monkeypatch.setattr(settings, "llm_model", "model-x")
    monkeypatch.setattr(settings, "llm_provider", "compatible")


def test_unconfigured_llm_has_explicit_error(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "")
    monkeypatch.setattr(settings, "llm_model", "")
    with pytest.raises(LLMServiceError) as exc:
        translate_text("hello", "zh-CN", client=_FakeClient("你好"))
    assert exc.value.error_type == "llm_unconfigured"


def test_translate_uses_configured_endpoint(monkeypatch):
    _configure(monkeypatch)
    client = _FakeClient("你好")
    result = translate_text("hello", "zh-CN", source_language="en", client=client)
    assert result.text == "你好"
    assert result.model == "model-x"
    url, headers, payload = client.calls[0]
    assert url == "https://llm.example/v1/chat/completions"
    assert headers["Authorization"] == "Bearer secret"
    assert payload["model"] == "model-x"


def test_summary_parses_json_fence(monkeypatch):
    _configure(monkeypatch)
    client = _FakeClient('```json\n{"summary":"摘要","key_points":["一","二","三"]}\n```')
    result = summarize_text("字幕", title="标题", output_language="zh-CN", client=client)
    assert result.summary == "摘要"
    assert result.key_points == ["一", "二", "三"]


def test_long_transcript_is_rejected_instead_of_silently_translated_partially(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(settings, "llm_max_input_chars", 5)
    client = _FakeClient("partial translation")
    with pytest.raises(LLMServiceError) as exc:
        translate_text("complete transcript", "zh-CN", client=client)
    assert exc.value.error_type == "llm_input_too_large"
    assert client.calls == []


@pytest.mark.parametrize("content", ['[]', 'null', '{"summary":"x","key_points":[null,{}]}'])
def test_malformed_summary_is_reported_as_invalid_response(monkeypatch, content):
    _configure(monkeypatch)
    with pytest.raises(LLMServiceError) as exc:
        summarize_text("transcript", title="t", output_language="en", client=_FakeClient(content))
    assert exc.value.error_type == "llm_invalid_response"


def test_incomplete_provider_output_is_not_accepted_as_full_translation():
    with pytest.raises(LLMServiceError) as exc:
        _content_from_payload({"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]})
    assert exc.value.error_type == "llm_incomplete_response"


@pytest.mark.parametrize("choice", [
    {"finish_reason": [], "message": {"content": "result"}},
    {"finish_reason": {"reason": "stop"}, "message": {"content": "result"}},
    {"finish_reason": "stop", "message": {"content": [{"type": "text", "text": 7}]}},
    {"finish_reason": "stop", "message": {"content": [{"type": "text", "text": None}]}},
])
def test_malformed_provider_fields_return_classified_error(monkeypatch, choice):
    _configure(monkeypatch)
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={"choices": [choice]},
    ))) as client:
        with pytest.raises(LLMServiceError) as exc:
            summarize_text("A source fact.", title="video", output_language="en", client=client)
    assert exc.value.error_type == "llm_invalid_response"


def test_valid_provider_text_blocks_can_supply_summary(monkeypatch):
    _configure(monkeypatch)
    choice = {"finish_reason": "stop", "message": {"content": [
        {"type": "text", "text": '{"summary":"Source fact.",'},
        {"type": "text", "text": '"key_points":["Source fact."]}'},
    ]}}
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={"choices": [choice]},
    ))) as client:
        result = summarize_text("Source fact.", title="video", output_language="en", client=client)
    assert result.summary == "Source fact."
    assert result.key_points == ["Source fact."]


def test_summary_deduplicates_repeated_caption_lines(monkeypatch):
    _configure(monkeypatch)
    client = _FakeClient('{"summary":"摘要","key_points":["关键内容"]}')
    summarize_text('Important fact.\nImportant fact.\nFinal conclusion.', title='t', output_language='en', client=client)
    prompt = client.calls[0][2]['messages'][-1]['content']
    assert prompt.count('Important fact.') == 1
    assert 'Final conclusion.' in prompt


def test_long_summary_includes_last_section_and_merges_partial_results(monkeypatch):
    import json
    _configure(monkeypatch)
    monkeypatch.setattr(settings, 'llm_summary_chunk_chars', 30, raising=False)
    monkeypatch.setattr(settings, 'llm_max_input_chars', 1000)
    prompts = []

    def provider(request):
        payload = json.loads(request.content)
        prompt = payload['messages'][-1]['content']
        prompts.append(prompt)
        if 'Section summaries:' in prompt:
            body = {'summary': 'opening and final decision', 'key_points': ['FIRST', 'LAST']}
        else:
            marker = 'LAST' if 'FINAL_DECISION' in prompt else 'FIRST'
            body = {'summary': marker, 'key_points': [marker]}
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(body)}}]})

    transcript = 'OPENING_DISCUSSION about tools.\nANOTHER_TOPIC about testing.\nFINAL_DECISION choose automation.'
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        result = summarize_text(transcript, title='t', output_language='en', client=client)
    assert len(prompts) > 2
    assert any('FINAL_DECISION' in p for p in prompts[:-1])
    assert 'FIRST' in prompts[-1] and 'LAST' in prompts[-1]
    assert result.key_points == ['FIRST', 'LAST']


def test_summary_budget_rejects_excess_chunks_before_provider_call(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(settings, 'llm_summary_chunk_chars', 10)
    monkeypatch.setattr(settings, 'llm_summary_max_chunks', 2)
    client = _FakeClient('unused')
    with pytest.raises(LLMServiceError) as exc:
        summarize_text('012345678901234567890123456789', title='t', output_language='en', client=client)
    assert exc.value.error_type == 'llm_input_too_large'
    assert client.calls == []


def test_summary_above_whole_input_limit_preserves_facts_from_first_and_last_sections(monkeypatch):
    """Content routing regression; the local provider is not an LLM quality oracle."""
    import json

    _configure(monkeypatch)
    monkeypatch.setattr(settings, 'llm_max_input_chars', 60_000)
    monkeypatch.setattr(settings, 'llm_summary_chunk_chars', 20_000)
    monkeypatch.setattr(settings, 'llm_summary_max_chunks', 16)
    monkeypatch.setattr(settings, 'llm_summary_max_output_tokens', 4096)
    first = 'Budget ceiling is 48000 yuan for 1200 pilot records.'
    last = 'Final release is September 9 only after a clean audit; Noor may stop release.'
    lines = [first] + [f'Rehearsal observation {index}: ' + 'inspect the test copy and retain the original. ' * 5 for index in range(270)] + [last]
    transcript = '\n'.join(lines)
    assert len(transcript) > 60_000
    supplied_sources = []

    def provider(request):
        payload = json.loads(request.content)
        prompt = payload['messages'][-1]['content']
        if 'Section summaries:\n' in prompt:
            sections = json.loads(prompt.split('Section summaries:\n', 1)[1])
            facts = list(dict.fromkeys(point for section in sections for point in section['key_points']))
        else:
            source = prompt.split('Transcript:\n', 1)[1]
            supplied_sources.append(source)
            facts = [fact for fact in (first, last) if fact in source]
        body = {'summary': ' '.join(facts) or 'Intermediate rehearsal observations.', 'key_points': facts or ['Rehearsal observations.']}
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(body)}}]})

    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        result = summarize_text(transcript, title='Pilot decision', output_language='en', client=client)
    assert len(supplied_sources) >= 4
    assert all(len(section) <= 20_000 for section in supplied_sources)
    assert first in result.key_points
    assert last in result.key_points
    assert result.key_points.count(first) == 1
    assert result.key_points.count(last) == 1


def test_one_complete_summary_point_is_preserved_without_padding(monkeypatch):
    _configure(monkeypatch)
    fact = 'The community library is closed on Monday for maintenance.'
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={'choices': [{'message': {'content': '{"summary":"Library closure notice.","key_points":["' + fact + '"]}'}}]},
    ))) as client:
        result = summarize_text(fact, title='Library notice', output_language='en', client=client)
    assert result.key_points == [fact]


@pytest.mark.parametrize("provider,response_mode,thinking_mode,expected", [
    ("deepseek", "auto", "auto", {"response_format": {"type": "json_object"}, "thinking": {"type": "disabled"}}),
    (" DeepSeek ", "auto", "auto", {"response_format": {"type": "json_object"}, "thinking": {"type": "disabled"}}),
    ("compatible", "auto", "auto", {}),
    ("deepseek", "text", "enabled", {"thinking": {"type": "enabled"}}),
    ("compatible", "json_object", "disabled", {"response_format": {"type": "json_object"}, "thinking": {"type": "disabled"}}),
])
def test_summary_provider_output_controls(monkeypatch, provider, response_mode, thinking_mode, expected):
    """Breaks if summary defaults/overrides emit the wrong provider payload."""
    import json

    _configure(monkeypatch)
    monkeypatch.setattr(settings, "llm_provider", provider)
    monkeypatch.setattr(settings, "llm_summary_response_format", response_mode, raising=False)
    monkeypatch.setattr(settings, "llm_summary_thinking_mode", thinking_mode, raising=False)
    captured = []

    def provider_response(request):
        payload = json.loads(request.content)
        captured.append(payload)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": '{"summary":"Source fact.","key_points":["Source fact."]}'}}]})

    with httpx.Client(transport=httpx.MockTransport(provider_response)) as client:
        result = summarize_text("Source fact.", title="video", output_language="en", client=client)
    assert result.key_points == ["Source fact."]
    assert len(captured) == 1
    emitted = {key: captured[0][key] for key in ("response_format", "thinking") if key in captured[0]}
    assert emitted == expected
    assert captured[0]["max_tokens"] == settings.llm_summary_max_output_tokens


def test_translation_does_not_receive_summary_output_controls(monkeypatch):
    """Breaks if summary-specific compatibility options leak into translation."""
    _configure(monkeypatch)
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "llm_summary_response_format", "json_object", raising=False)
    monkeypatch.setattr(settings, "llm_summary_thinking_mode", "disabled", raising=False)
    client = _FakeClient("Translated fact.")
    result = translate_text("Source fact.", "en", client=client)
    assert result.text == "Translated fact."
    payload = client.calls[0][2]
    assert "response_format" not in payload
    assert "thinking" not in payload


@pytest.mark.parametrize("point_count,rejected", [(1, False), (7, False), (8, True), (12, True)])
def test_summary_enforces_point_count_contract_without_truncating_or_retrying(monkeypatch, point_count, rejected):
    """Breaks if an overlong model list is accepted/truncated or the POST repeats."""
    import json

    _configure(monkeypatch)
    points = [f"Distinct source fact {index}." for index in range(point_count)]
    client = _FakeClient(json.dumps({"summary": "Source facts.", "key_points": points}))
    if rejected:
        with pytest.raises(LLMServiceError) as error:
            summarize_text("\n".join(points), title="facts", output_language="en", client=client)
        assert error.value.error_type == "llm_invalid_response"
    else:
        result = summarize_text("\n".join(points), title="facts", output_language="en", client=client)
        assert result.key_points == points
    assert len(client.calls) == 1
