import json

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


def _response_payload(content):
    return {"id": "resp-test", "object": "response", "status": "completed", "error": None,
            "output": [{"id": "msg-test", "type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": content}]}]}


def _schema_config(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "llm_summary_response_format", "json_schema")
    monkeypatch.setattr(settings, "llm_summary_max_point_chars", 240, raising=False)


@pytest.mark.parametrize("base,expected", [
    ("https://llm.example/v1", "https://llm.example/v1/responses"),
    ("https://llm.example/v1/chat/completions/", "https://llm.example/v1/responses"),
    ("https://llm.example/v1/responses", "https://llm.example/v1/responses"),
])
def test_schema_summary_uses_responses_endpoint_and_enforced_contract(monkeypatch, base, expected):
    _schema_config(monkeypatch)
    monkeypatch.setattr(settings, "llm_base_url", base)
    captured = []

    def respond(request):
        captured.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json=_response_payload('{"summary":"A fact.","key_points":["A fact."]}'))

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = summarize_text("A fact.", title="t", output_language="en", client=client)
    assert result.key_points == ["A fact."]
    assert len(captured) == 1
    url, payload = captured[0]
    assert url == expected
    assert payload["max_output_tokens"] == 4096
    assert payload["reasoning"] == {"effort": "none"}
    assert "thinking" not in payload and "messages" not in payload and "max_tokens" not in payload
    assert payload["input"][0]["role"] == "user"
    assert "Transcript:\nA fact." in payload["input"][0]["content"]
    schema = payload["text"]["format"]["schema"]
    assert payload["text"]["format"]["type"] == "json_schema"
    assert schema["required"] == ["summary", "key_points"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["summary"]["minLength"] == 1
    assert schema["properties"]["key_points"]["minItems"] == 1
    assert schema["properties"]["key_points"]["maxItems"] == 7
    assert schema["properties"]["key_points"]["items"]["maxLength"] == 240


@pytest.mark.parametrize("body", [
    {"summary": "fact", "key_points": []},
    {"summary": "fact", "key_points": ["fact"] * 8},
    {"summary": "fact", "key_points": ["fact", " "]},
    {"summary": "fact", "key_points": ["x" * 241]},
    {"summary": "fact", "key_points": ["fact"], "extra": "ignored?"},
    {"summary": " ", "key_points": ["fact"]},
])
def test_schema_summary_rejects_contract_violations_without_billed_fallback(monkeypatch, body):
    _schema_config(monkeypatch)
    calls = []

    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=_response_payload(json.dumps(body)))

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(LLMServiceError) as error:
            summarize_text("fact", title="t", output_language="en", client=client)
    assert error.value.error_type == "llm_invalid_response"
    assert len(calls) == 1


@pytest.mark.parametrize("change,error_type", [
    ({"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}, "llm_incomplete_response"),
    ({"status": "in_progress"}, "llm_incomplete_response"),
    ({"status": "failed", "error": {"code": "server_error", "message": "failed"}}, "llm_error"),
    ({"status": "unknown"}, "llm_invalid_response"),
    ({"status": []}, "llm_invalid_response"),
    ({"output": [{"type": "message", "role": "assistant", "status": {}, "content": []}]}, "llm_invalid_response"),
    ({"output": []}, "llm_invalid_response"),
    ({"output": [{"type": "message", "role": "assistant", "status": "incomplete", "content": []}]}, "llm_incomplete_response"),
    ({"output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "refusal", "refusal": "No"}]}]}, "llm_invalid_response"),
    ({"output": [{"type": "function_call", "name": "anything", "arguments": "{}"}]}, "llm_invalid_response"),
    ({"output": [{"type": "message", "role": "user", "status": "completed", "content": [{"type": "output_text", "text": "{}"}]}]}, "llm_invalid_response"),
    ({"output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": 7}]}]}, "llm_invalid_response"),
])
def test_schema_summary_classifies_response_failure_and_never_retries(monkeypatch, change, error_type):
    _schema_config(monkeypatch)
    payload = _response_payload('{"summary":"fact","key_points":["fact"]}')
    payload.update(change)
    calls = []

    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(LLMServiceError) as error:
            summarize_text("fact", title="t", output_language="en", client=client)
    assert error.value.error_type == error_type
    assert len(calls) == 1


def test_translation_normalizes_full_responses_url_but_remains_generic_chat(monkeypatch):
    _schema_config(monkeypatch)
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.example/v1/responses/")
    client = _FakeClient("Translated fact.")
    assert translate_text("fact", "en", client=client).text == "Translated fact."
    url, _, payload = client.calls[0]
    assert url == "https://llm.example/v1/chat/completions"
    assert "text" not in payload and "reasoning" not in payload


def test_schema_point_length_uses_configuration_and_accepts_inclusive_limit(monkeypatch):
    _schema_config(monkeypatch)
    monkeypatch.setattr(settings, "llm_summary_max_point_chars", 4)
    replies = iter(["fact", "facts"])
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=_response_payload(json.dumps({"summary": "source", "key_points": [next(replies)]})))

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert summarize_text("fact", title="t", output_language="en", client=client).key_points == ["fact"]
        with pytest.raises(LLMServiceError) as error:
            summarize_text("facts", title="t", output_language="en", client=client)
    assert error.value.error_type == "llm_invalid_response"
    assert len(calls) == 2
    assert calls[0]["text"]["format"]["schema"]["properties"]["key_points"]["items"]["maxLength"] == 4


def test_explicit_legacy_json_mode_keeps_chat_and_has_no_schema_length_limit(monkeypatch):
    _schema_config(monkeypatch)
    monkeypatch.setattr(settings, "llm_summary_response_format", "json_object")
    monkeypatch.setattr(settings, "llm_summary_max_point_chars", 4)
    client = _FakeClient('{"summary":"source","key_points":["long source fact"]}')
    result = summarize_text("long source fact", title="t", output_language="en", client=client)
    assert result.key_points == ["long source fact"]
    assert client.calls[0][0] == "https://llm.example/v1/chat/completions"
    assert client.calls[0][2]["response_format"] == {"type": "json_object"}


def test_schema_provider_rejection_is_single_post_without_legacy_fallback(monkeypatch):
    _schema_config(monkeypatch)
    calls = []

    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(400, json={"error": {"message": "unsupported schema"}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(LLMServiceError) as error:
            summarize_text("fact", title="t", output_language="en", client=client)
    assert error.value.error_type == "llm_error"
    assert calls == ["https://llm.example/v1/responses"]


def _tool_payload(**changes):
    arguments = {"summary": "Source fact.", **{f"point_{i}": "Source fact." if i == 1 else "" for i in range(1, 8)}}
    arguments.update(changes)
    return {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
        "tool_calls": [{"type": "function", "function": {"name": "emit_video_summary", "arguments": json.dumps(arguments)}}]}}]}


def test_strict_tool_summary_uses_fixed_slots_and_beta_without_executing_tools(monkeypatch):
    _schema_config(monkeypatch)
    monkeypatch.setattr(settings, "llm_base_url", "https://api.deepseek.com/v1/chat/completions")
    monkeypatch.setattr(settings, "llm_summary_response_format", "strict_tool")
    captured = []
    def respond(request):
        captured.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json=_tool_payload())
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = summarize_text("Source fact.", title="t", output_language="en", client=client)
    assert result.key_points == ["Source fact."]
    assert len(captured) == 1
    url, body = captured[0]
    assert url == "https://api.deepseek.com/beta/chat/completions"
    function = body["tools"][0]["function"]
    assert function["strict"] is True
    assert body["tool_choice"]["function"]["name"] == "emit_video_summary"
    assert set(function["parameters"]["properties"]) == {"summary", *(f"point_{i}" for i in range(1, 8))}
    assert function["parameters"]["additionalProperties"] is False
    assert body["thinking"] == {"type": "disabled"}


@pytest.mark.parametrize("changes", [{"point_8": "extra"}, {"point_1": ""}, {"point_2": " "}, {"point_1": "x" * 241},
    {"point_1": " Source fact."}, {"point_3": "gap after empty slot"}, {"summary": " Source fact."}])
def test_strict_tool_rejects_invalid_slots_without_truncation_or_retry(monkeypatch, changes):
    _schema_config(monkeypatch)
    monkeypatch.setattr(settings, "llm_summary_response_format", "strict_tool")
    calls = []
    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=_tool_payload(**changes))
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(LLMServiceError) as error:
            summarize_text("Source fact.", title="t", output_language="en", client=client)
    assert error.value.error_type == "llm_invalid_response"
    assert len(calls) == 1


def test_deepseek_forced_summary_rejects_enabled_thinking_before_post(monkeypatch):
    _schema_config(monkeypatch)
    monkeypatch.setattr(settings, "llm_summary_response_format", "strict_tool")
    monkeypatch.setattr(settings, "llm_summary_thinking_mode", "enabled")
    client = _FakeClient("unused")
    with pytest.raises(LLMServiceError) as error:
        summarize_text("Source fact.", title="t", output_language="en", client=client)
    assert error.value.error_type == "llm_unconfigured"
    assert client.calls == []


@pytest.mark.parametrize("alteration,error_type", [
    ("wrong_function", "llm_invalid_response"),
    ("extra_call", "llm_invalid_response"),
    ("no_call", "llm_invalid_response"),
    ("arguments_object", "llm_invalid_response"),
    ("malformed_json", "llm_invalid_response"),
    ("refusal", "llm_invalid_response"),
    ("wrong_role", "llm_invalid_response"),
    ("length", "llm_incomplete_response"),
])
def test_strict_tool_completion_envelope_is_validated(monkeypatch, alteration, error_type):
    _schema_config(monkeypatch)
    monkeypatch.setattr(settings, "llm_summary_response_format", "strict_tool")
    body = _tool_payload()
    choice = body["choices"][0]
    message = choice["message"]
    call = message["tool_calls"][0]
    if alteration == "wrong_function":
        call["function"]["name"] = "execute_shell"
    elif alteration == "extra_call":
        message["tool_calls"].append(call.copy())
    elif alteration == "no_call":
        message["tool_calls"] = []
    elif alteration == "arguments_object":
        call["function"]["arguments"] = {"summary": "fact"}
    elif alteration == "malformed_json":
        call["function"]["arguments"] = "{"
    elif alteration == "refusal":
        message["refusal"] = "Cannot provide this."
    elif alteration == "wrong_role":
        message["role"] = "user"
    elif alteration == "length":
        choice["finish_reason"] = "length"
    calls = []
    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=body)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(LLMServiceError) as error:
            summarize_text("Source fact.", title="t", output_language="en", client=client)
    assert error.value.error_type == error_type
    assert len(calls) == 1


def test_summary_merge_receives_raw_boundary_evidence_when_section_notes_omit_it(monkeypatch):
    """Regression for lossy section notes, not a model quality oracle."""
    _configure(monkeypatch)
    monkeypatch.setattr(settings, "llm_summary_chunk_chars", 180)
    monkeypatch.setattr(settings, "llm_max_input_chars", 4000)
    monkeypatch.setattr(settings, "llm_summary_source_context_chars", 80, raising=False)
    final_fact = "Final decision: Lina pauses the launch if the reserve valve remains blocked."
    transcript = "Opening: inspect the reserve valve before launch. " + "background " * 40 + final_fact
    sources = []
    merges = []

    def respond(request):
        prompt = json.loads(request.content)["messages"][-1]["content"]
        if "Section summaries:\n" in prompt:
            sections = json.loads(prompt.split("Section summaries:\n", 1)[1])
            merges.append(sections)
            evidence = " ".join("\n".join(section.get("source_context", "") for section in sections).split())
            facts = [final_fact] if final_fact in evidence else ["Only generic inspection notes survived."]
        else:
            sources.append(prompt.split("Transcript:\n", 1)[1])
            facts = ["Inspect the machinery."]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"summary": "Inspection.", "key_points": facts})}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = summarize_text(transcript, title="Launch", output_language="en", client=client)
    assert result.key_points == [final_fact]
    assert len(sources) >= 2 and len(merges) == 1
    for section in merges[0]:
        assert len(section["source_context"]) <= 2 * 80 + len("\n[... omitted middle ...]\n")


def test_disabled_source_context_preserves_legacy_section_notes_shape(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(settings, "llm_summary_chunk_chars", 40)
    monkeypatch.setattr(settings, "llm_max_input_chars", 4000)
    monkeypatch.setattr(settings, "llm_summary_source_context_chars", 0, raising=False)
    merged_sections = []
    def respond(request):
        prompt = json.loads(request.content)["messages"][-1]["content"]
        if "Section summaries:\n" in prompt:
            merged_sections.extend(json.loads(prompt.split("Section summaries:\n", 1)[1]))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"summary":"Source.","key_points":["Source fact."]}'}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        summarize_text("First topic with a source fact. Second topic with a final decision.", title="t", output_language="en", client=client)
    assert merged_sections
    assert all(set(section) == {"section", "summary", "key_points"} for section in merged_sections)


def test_raw_context_capacity_failure_is_explicit_before_merge_post(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(settings, "llm_summary_chunk_chars", 100)
    monkeypatch.setattr(settings, "llm_max_input_chars", 160)
    monkeypatch.setattr(settings, "llm_summary_source_context_chars", 100, raising=False)
    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"summary":"x","key_points":["x"]}'}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(LLMServiceError) as error:
            summarize_text("A" * 180, title="t", output_language="en", client=client)
    assert error.value.error_type == "llm_input_too_large"
    assert len(calls) == 2
    assert all("Section summaries:\n" not in call["messages"][-1]["content"] for call in calls)


def test_hierarchical_merge_keeps_original_context_through_intermediate_notes(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(settings, "llm_summary_chunk_chars", 100)
    monkeypatch.setattr(settings, "llm_max_input_chars", 1000)
    monkeypatch.setattr(settings, "llm_summary_source_context_chars", 40, raising=False)
    transcript = "FIRST: release needs a clean audit. " + "x" * 335 + " LAST: Maia may halt the release."
    merge_sources = []
    requests = []
    def respond(request):
        prompt = json.loads(request.content)["messages"][-1]["content"]
        requests.append(prompt)
        if "Section summaries:\n" in prompt:
            assert len(prompt.split("Section summaries:\n", 1)[1]) <= 1000
            sections = json.loads(prompt.split("Section summaries:\n", 1)[1])
            evidence = " ".join("\n".join(section.get("source_context", "") for section in sections).split())
            merge_sources.append(evidence)
            summary = "Intermediate notes."  # Deliberately omit all raw facts.
            points = [fact for fact in ("FIRST: release needs a clean audit.", "LAST: Maia may halt the release.") if fact in evidence]
        else:
            summary = "Unimportant background. " * 12
            points = ["Generic notes."]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"summary": summary, "key_points": points or ["Generic notes."]})}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = summarize_text(transcript, title="Release", output_language="en", client=client)
    assert len(merge_sources) > 1
    assert "FIRST: release needs a clean audit." in merge_sources[-1]
    assert "LAST: Maia may halt the release." in merge_sources[-1]
    assert result.key_points == ["FIRST: release needs a clean audit.", "LAST: Maia may halt the release."]
