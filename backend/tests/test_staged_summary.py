"""Offline contract tests for the opt-in serial summary pipeline."""
import json

import httpx
import pytest
from langsmith import get_tracing_context

from app.config import Settings, settings
from app.services import llm_service as service


@pytest.fixture
def staged(monkeypatch):
    for name, value in {
        'llm_base_url': 'https://llm.example/v1', 'llm_model': 'model',
        'llm_summary_generation_mode': 'staged', 'llm_summary_strategy': 'legacy',
        'llm_summary_length_mode': 'adaptive', 'llm_summary_response_format': 'json_object',
        'llm_summary_thinking_mode': 'disabled', 'llm_summary_chunk_chars': 20000,
        'llm_max_input_chars': 60000, 'llm_summary_max_chunks': 16,
        'llm_summary_max_output_tokens': 4096, 'llm_summary_output_token_ceiling': 8192,
        'llm_summary_point_ceiling': 14, 'llm_summary_format_retries': 1,
        'llm_summary_max_extra_calls': 2,
    }.items():
        monkeypatch.setattr(settings, name, value, raising=False)


def fake_client(outputs, captured):
    def respond(request):
        captured.append(json.loads(request.content))
        item = outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        raw = item if isinstance(item, str) else json.dumps(item)
        return httpx.Response(200, json={'choices': [{'message': {'content': raw}, 'finish_reason': 'stop'}]})
    return httpx.Client(transport=httpx.MockTransport(respond))


def test_serial_roles_preserve_points_and_full_raw_source(staged):
    captured, trace = [], []
    source = 'Original repeated detail.\nOriginal repeated detail.\nClosing condition.'
    with fake_client([{'key_points': ['Mechanism with condition.']}, {'summary': 'Central relationship.'}], captured) as client:
        result = service.summarize_text(source, title='Title', output_language='en', client=client, diagnostic=trace.append)
    assert result.summary == 'Central relationship.'
    assert result.key_points == ['Mechanism with condition.']
    assert len(captured) == 2
    assert source in captured[0]['messages'][1]['content']
    assert 'Mechanism with condition.' in captured[1]['messages'][1]['content']
    assert [item['stage'] for item in trace if item['status'] == 'started'] == ['points', 'overview']


def test_fenced_whitespace_is_repaired_locally(staged):
    captured = []
    with fake_client(['```json\n{"key_points":["  A complete claim.  "]}\n```', {'summary': ' Overall relationship. '}], captured) as client:
        result = service.summarize_text('Source.', title='', output_language='en', client=client)
    assert result.key_points == ['A complete claim.']
    assert result.summary == 'Overall relationship.'
    assert len(captured) == 2


def test_overflow_gets_one_format_merge_without_slicing(staged):
    captured, trace = [], []
    points = [f'Unique content {i}.' for i in range(8)]
    with fake_client([{'key_points': points}, {'key_points': [' '.join(points)]}, {'summary': 'Subject.'}], captured) as client:
        result = service.summarize_text('Source.', title='', output_language='en', client=client, diagnostic=trace.append)
    assert all(point in result.key_points[0] for point in points)
    assert all(point in captured[1]['messages'][1]['content'] for point in points)
    assert [item['stage'] for item in trace if item['status'] == 'started'] == ['points', 'points_format', 'overview']
    assert len(captured) == 3


def test_format_budget_is_shared_and_failures_stop(staged):
    captured = []
    with fake_client([{'key_points': [str(i) for i in range(8)]}, {'key_points': ['Merged.']}, {'summary': 42}], captured) as client:
        with pytest.raises(service.LLMServiceError):
            service.summarize_text('Source.', title='', output_language='en', client=client)
    assert len(captured) == 3


def test_network_error_never_repairs(staged):
    captured = []
    with fake_client([httpx.ConnectError('offline')], captured) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.summarize_text('Source.', title='', output_language='en', client=client)
    assert error.value.error_type == 'llm_error'
    assert len(captured) == 1


def test_tracing_env_is_disabled_during_entire_invoke(staged, monkeypatch):
    monkeypatch.setenv('LANGSMITH_TRACING', 'true')
    monkeypatch.setenv('LANGCHAIN_TRACING_V2', 'true')
    captured, enabled = [], []
    def respond(request):
        enabled.append(get_tracing_context()['enabled'])
        captured.append(json.loads(request.content))
        body = {'key_points': ['Point.']} if len(captured) == 1 else {'summary': 'Overview.'}
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(body)}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        service.summarize_text('Source.', title='', output_language='en', client=client)
    assert enabled == [False, False]


def test_two_leaves_then_global_points_then_overview(staged, monkeypatch):
    monkeypatch.setattr(settings, 'llm_summary_chunk_chars', 8000)
    source = 'Some source detail. ' * 600
    captured = []
    leaf = {'summary': 'Notes.', 'key_points': ['Condition.']}
    with fake_client([leaf, leaf, {'key_points': ['Global condition.']}, {'summary': 'Relationship.'}], captured) as client:
        result = service.summarize_text(source, title='', output_language='en', client=client)
    assert len(captured) == 4
    assert source in captured[2]['messages'][1]['content']
    assert captured[2]['max_tokens'] > captured[0]['max_tokens']
    assert result.key_points == ['Global condition.']


def test_reuse_sections_checks_original_parts_before_any_post(staged, monkeypatch):
    monkeypatch.setattr(settings, 'llm_summary_chunk_chars', 8)
    source = 'First.\nSecond.'
    parts = service._summary_chunks(service._summary_input(source), 8)
    results = [service.LLMSummaryResult('Notes.', ['Detail.'], 'p', 'm') for _ in parts]
    captured = []
    with fake_client([{'key_points': ['Global.']}, {'summary': 'Overview.'}], captured) as client:
        with pytest.raises(service.LLMServiceError):
            service.summarize_sections(source, results, source_parts=['Unrelated.'] * len(parts), title='', output_language='en', client=client)
        result = service.summarize_sections(source, results, source_parts=parts, title='', output_language='en', client=client)
    assert result.summary == 'Overview.'
    assert len(captured) == 2


def test_capacity_checks_raw_before_leaf_calls(staged, monkeypatch):
    monkeypatch.setattr(settings, 'llm_max_input_chars', 10)
    captured = []
    with fake_client([], captured) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.summarize_text('same\nsame\nsame\nsame', title='', output_language='en', client=client)
    assert error.value.error_type == 'llm_input_too_large'
    assert not captured


@pytest.mark.parametrize('name,value', [('llm_summary_length_mode', 'fixed'), ('llm_summary_response_format', 'strict_tool')])
def test_incompatible_staged_config_fails_before_post(staged, monkeypatch, name, value):
    monkeypatch.setattr(settings, name, value)
    captured = []
    with fake_client([], captured) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.summarize_text('Source.', title='', output_language='en', client=client)
    assert error.value.error_type == 'llm_unconfigured'
    assert not captured


def test_generation_mode_config_defaults_and_env(monkeypatch):
    assert Settings().llm_summary_generation_mode == 'single'
    monkeypatch.setenv('LLM_SUMMARY_GENERATION_MODE', 'staged')
    assert Settings.from_env().llm_summary_generation_mode == 'staged'
    with pytest.raises(ValueError):
        Settings(llm_summary_generation_mode='parallel')


def test_format_template_is_reconstructable_and_preserves_raw():
    budget = service._SummaryBudget(4096, 7, None)
    base = [{'role': 'system', 'content': 'Role.'}, {'role': 'user', 'content': 'Source.'}]
    messages = service._staged_format_messages(base, raw='Every original claim.', reason='invalid_count', budget=budget)
    assert messages[0] == base[0]
    assert 'Every original claim.' in messages[1]['content']
    assert 'Source.' in messages[1]['content']


def test_malformed_repair_stops_without_overview(staged):
    captured = []
    with fake_client([{'key_points': [str(i) for i in range(8)]}, {'key_points': [str(i) for i in range(9)]}], captured) as client:
        with pytest.raises(service.LLMServiceError):
            service.summarize_text('Source.', title='', output_language='en', client=client)
    assert len(captured) == 2


def test_format_can_be_disabled(staged, monkeypatch):
    monkeypatch.setattr(settings, 'llm_summary_format_retries', 0)
    captured = []
    with fake_client([{'key_points': [str(i) for i in range(8)]}], captured) as client:
        with pytest.raises(service.LLMServiceError):
            service.summarize_text('Source.', title='', output_language='en', client=client)
    assert len(captured) == 1


@pytest.mark.parametrize('raw', ['{"key_points":[1]}', '{"key_points":["a"],"summary":"b"}',
                                     '{"key_points":["a"],"key_points":["b"]}'])
def test_stage_codec_rejects_coercion_role_leakage_and_duplicate_fields(staged, raw):
    with pytest.raises(service.LLMServiceError):
        service._parse_stage_json(raw, role='points', budget=service._summary_budget(1))


def test_staged_schema_matches_each_role(staged, monkeypatch):
    monkeypatch.setattr(settings, 'llm_summary_response_format', 'json_schema')
    captured = []
    def respond(request):
        payload = json.loads(request.content)
        captured.append(payload)
        role = 'points' if len(captured) == 1 else 'overview'
        body = {'key_points': ['Condition.']} if role == 'points' else {'summary': 'Relationship.'}
        return httpx.Response(200, json={'object': 'response', 'status': 'completed', 'output': [{
            'type': 'message', 'role': 'assistant', 'status': 'completed',
            'content': [{'type': 'output_text', 'text': json.dumps(body)}]}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = service.summarize_text('Source.', title='', output_language='en', client=client)
    assert result.summary == 'Relationship.'
    schemas = [p['text']['format']['schema'] for p in captured]
    assert set(schemas[0]['properties']) == {'key_points'}
    assert set(schemas[1]['properties']) == {'summary'}
    assert all(schema['additionalProperties'] is False for schema in schemas)


def test_leaf_format_fences_are_local_even_with_schema(staged, monkeypatch):
    monkeypatch.setattr(settings, 'llm_summary_chunk_chars', 8)
    monkeypatch.setattr(settings, 'llm_summary_response_format', 'json_schema')
    outputs = ['```json\n{"summary":"Notes.","key_points":["Point."]}\n```'] * 2
    outputs += ['{"key_points":["Global."]}', '{"summary":"Overview."}']
    captured = []
    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={'object': 'response', 'status': 'completed', 'output': [{
            'type': 'message', 'role': 'assistant', 'status': 'completed',
            'content': [{'type': 'output_text', 'text': outputs.pop(0)}]}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = service.summarize_text('First.\nSecond.', title='', output_language='en', client=client)
    assert result.summary == 'Overview.'
    assert len(captured) == 4


def test_provider_incomplete_is_terminal_and_diagnosed(staged):
    captured, trace = [], []
    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"key_points":["p"]}'}, 'finish_reason': 'length'}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.summarize_text('Source.', title='', output_language='en', client=client, diagnostic=trace.append)
    assert error.value.error_type == 'llm_incomplete_response'
    assert len(captured) == 1
    assert trace[-1]['status'] == 'failed'
    assert trace[-1]['category'] == 'provider'


def test_tracing_env_never_sends_third_party_requests(staged, monkeypatch):
    import requests
    monkeypatch.setenv('LANGSMITH_TRACING', 'true')
    monkeypatch.setenv('LANGCHAIN_TRACING_V2', 'true')
    def forbidden(*args, **kwargs):
        pytest.fail('Unexpected third party network request')
    monkeypatch.setattr(requests.Session, 'request', forbidden)
    captured = []
    with fake_client([{'key_points': ['Point.']}, {'summary': 'Relationship.'}], captured) as client:
        service.summarize_text('Source.', title='', output_language='en', client=client)
    assert len(captured) == 2


def test_raw_size_not_deduplicated_size_controls_budget(staged):
    source = 'Repeated source.\n' * 600
    captured = []
    with fake_client([{'key_points': ['Point.']}, {'summary': 'Relationship.'}], captured) as client:
        service.summarize_text(source, title='', output_language='en', client=client)
    assert len(captured) == 2
    assert all(p['max_tokens'] == service._summary_budget(len(source)).max_tokens > 4096 for p in captured)


def test_oversized_reused_notes_fail_before_any_global_post(staged, monkeypatch):
    monkeypatch.setattr(settings, 'llm_summary_chunk_chars', 8)
    monkeypatch.setattr(settings, 'llm_max_input_chars', 1000)
    source = 'First.\nSecond.'
    parts = service._summary_chunks(service._summary_input(source), 8)
    results = [service.LLMSummaryResult('Notes.' * 200, ['Point.'], 'p', 'm') for _ in parts]
    captured = []
    with fake_client([], captured) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.summarize_sections(source, results, source_parts=parts, title='', output_language='en', client=client)
    assert error.value.error_type == 'llm_input_too_large'
    assert not captured


def test_staged_facts_still_selects_original_facts_flow(staged, monkeypatch):
    monkeypatch.setattr(settings, 'llm_summary_strategy', 'facts')
    sentinel = service.LLMSummaryResult('Original facts.', ['Fact.'], 'p', 'm')
    monkeypatch.setattr(service, '_summarize_facts', lambda *args, **kwargs: sentinel)
    result = service.summarize_text('A sufficiently simple statement.', title='', output_language='en')
    assert result is sentinel


def test_leaf_and_global_roles_share_one_format_retry(staged, monkeypatch):
    monkeypatch.setattr(settings, 'llm_summary_chunk_chars', 8)
    captured, trace = [], []
    bad_leaf = {'summary': 'Notes.', 'key_points': [str(i) for i in range(8)]}
    good_leaf = {'summary': 'Notes.', 'key_points': ['Merged conditions.']}
    with fake_client([bad_leaf, good_leaf, good_leaf, {'key_points': [str(i) for i in range(8)]}], captured) as client:
        with pytest.raises(service.LLMServiceError):
            service.summarize_text('First.\nSecond.', title='', output_language='en', client=client, diagnostic=trace.append)
    assert [item['stage'] for item in trace if item['status'] == 'started'] == ['leaf', 'leaf_format', 'leaf', 'points']
    assert len(captured) == 4


def test_duplicate_leaf_json_fields_cannot_silently_discard_claim(staged, monkeypatch):
    monkeypatch.setattr(settings, 'llm_summary_chunk_chars', 8)
    monkeypatch.setattr(settings, 'llm_summary_format_retries', 0)
    captured = []
    raw = '{"summary":"First important claim.","summary":"Second claim.","key_points":["Detail."]}'
    with fake_client([raw], captured) as client:
        with pytest.raises(service.LLMServiceError):
            service.summarize_text('First.\nSecond.', title='', output_language='en', client=client)
    assert len(captured) == 1


def test_missing_model_configuration_is_rejected_before_attempt_diagnostic(staged, monkeypatch):
    monkeypatch.setattr(settings, 'llm_model', '')
    trace, captured = [], []
    with fake_client([], captured) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.summarize_text('Source.', title='', output_language='en', client=client, diagnostic=trace.append)
    assert error.value.error_type == 'llm_unconfigured'
    assert not captured
    assert not trace


@pytest.mark.parametrize('raw', [
    '{"key_points":' + '[' * 10000 + '"Claim."' + ']' * 10000 + '}',
    '{"key_points":[' + '9' * 5000 + ']}',
], ids=['excessive_json_nesting', 'excessive_integer_digits'])
def test_parser_resource_limits_are_terminal_and_diagnosed(staged, raw):
    captured, trace = [], []
    with fake_client([raw], captured) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.summarize_text('Source.', title='', output_language='en', client=client, diagnostic=trace.append)
    assert error.value.error_type == 'llm_input_too_large'
    assert len(captured) == 1
    assert trace[-1]['status'] == 'failed'
    assert trace[-1]['category'] == 'capacity'
    assert trace[-1]['request_count'] == 1
    assert trace[-1]['format_used'] == 0
