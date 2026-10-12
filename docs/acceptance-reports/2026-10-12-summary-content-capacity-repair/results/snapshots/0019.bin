"""Lossless format repairs reach existing production type and capacity validation."""
import json
import pytest
from app.services import llm_service as service


def test_missing_array_closure_preserves_the_last_point_in_production_parser():
    raw = '{"summary":"Overview","key_points":["First complete fact","Last complete fact"}'
    assert service._parse_summary_json(raw) == ('Overview', ['First complete fact','Last complete fact'])


def test_repaired_json_still_rejects_excess_points_without_trimming():
    raw = json.dumps({'summary':'Overview','key_points':[f'Fact {i}' for i in range(8)]})
    raw = raw[:-2] + '}'
    with pytest.raises(service.LLMServiceError) as error:
        service._parse_summary_json(raw)
    assert error.value.error_type == 'llm_invalid_response'
    assert '预算' in str(error.value)


def test_incomplete_last_point_is_rejected_instead_of_returning_a_shorter_summary():
    raw = '{"summary":"Overview","key_points":["First complete fact","Last unfinished fact'
    with pytest.raises(service.LLMServiceError) as error:
        service._parse_summary_json(raw)
    assert error.value.error_type == 'llm_invalid_response'
