"""Lossless closing repair only; no HTTP, runtime settings, or sample answers.

Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only through ytdlp_service; scene remains read-only.
"""
import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "app/services/summary_json.py"


@pytest.fixture
def decode():
    assert MODULE.exists(), "Independent summary JSON normalization layer is missing"
    spec = importlib.util.spec_from_file_location("summary_json_fixture", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.decode_summary_json


def test_normalization_layer_exists():
    assert MODULE.exists(), "Independent summary JSON normalization layer is missing"


@pytest.mark.parametrize("value", [None, True, 7, "plain", [], ["one"],
    {"summary": "overview", "key_points": ["condition"], "extra": {"nested": 4}},
    {"summary": "overview", "key_points": []}])
def test_valid_json_retains_any_shape_and_extra_fields(decode, value):
    assert decode(json.dumps(value, ensure_ascii=False)) == value


def test_valid_duplicate_fields_keep_standard_json_compatibility(decode):
    assert decode('{"summary":"first","summary":"last","key_points":["point"]}') == {
        "summary": "last", "key_points": ["point"]}


@pytest.mark.parametrize("ending,points_first", [("}", False), ("", False), ("]", False), ("", True)])
def test_missing_closings_preserve_every_complete_point_and_escape(decode, ending, points_first):
    value = {"summary": 'Topic "quoted" \n line', "key_points": [
        "条件：保留全部内容", 'Backslash \\ and quote " stay', "Final consequence"]}
    if points_first:
        # Points-first order only permits a missing object closing because the
        # array was already closed before the summary field was supplied.
        value = {"key_points": value["key_points"], "summary": value["summary"]}
        raw = json.dumps(value, ensure_ascii=True)[:-1]
    else:
        raw = json.dumps(value, ensure_ascii=True)[:-2] + ending
    assert decode(raw) == value


def test_missing_object_closing_preserves_empty_completed_array(decode):
    assert decode('{"summary":"overview","key_points":[]') == {"summary": "overview", "key_points": []}


def test_normalization_does_not_apply_downstream_point_or_length_limits(decode):
    value = {"summary": "Overview", "key_points": [
        f"Condition {index}: " + "完整说明。" * 500 for index in range(18)]}
    raw = json.dumps(value, ensure_ascii=False)[:-2] + "}"
    assert decode(raw) == value


def test_escaped_control_characters_and_braces_are_never_formatting(decode):
    value = {"summary": "Literal } ] , : text", "key_points": [
        "control\u0000 and tab\t and newline\n", 'quoted "]}" remains inside a string']}
    raw = json.dumps(value, ensure_ascii=True)[:-2]
    assert decode(raw) == value


@pytest.mark.parametrize("raw", [
    '{"summary":"overview","key_points":["complete","unfinished',
    '{"summary":"overview","key_points":["complete","unfinished\\',
    '{"summary":"overview","key_points":["complete","bad\\q"}',
    '{"summary":"overview","key_points":["complete","bad\\u12"}',
    '{"summary":"overview","key_points":["complete",}',
    '{"summary":"overview","key_points":["complete",',
    '{"summary":"overview","key_points":["complete"],}',
    '{"summary":"overview","key_points":["complete"] garbage',
    '{"summary":"overview",,"key_points":["complete"}',
    '{"summary":"overview","key_points":["first" "second"}',
    '{"summary":"overview","key_points":["complete",false',
    '{"summary":"overview","key_points":["complete",42',
    '{"summary":"overview","key_points":["complete",null',
    '{"summary":"overview","summary":"replaced","key_points":["complete"}',
    '{"summary":"overview","key_points":["old"],"key_points":["new"}',
    '{"summary":"overview","key_points":["complete"],"extra":"value"',
    '{"summary":"overview","key_points":["complete"],"extra":',
    '{"summary":"overview","key_points":',
    '{"summary":"overview","key_points":[',
    '{"summary":"overview"',
    '["complete"',
    '{"summary":null,"key_points":["complete"',
    '{"summary":"overview","key_points":[["nested"]',
])
def test_unfinished_or_malformed_content_is_never_discarded(decode, raw):
    with pytest.raises((json.JSONDecodeError, ValueError)) as error:
        decode(raw)
    assert raw not in str(error.value)


@pytest.mark.parametrize("prefix", ["```json\n", "```JSON ", "```\n"])
def test_paired_fences_are_optional_and_lossless(decode, prefix):
    content = prefix + '{"summary":"literal ``` text","key_points":["point"]}' + "\n```"
    assert decode(content)["summary"] == "literal ``` text"
    with pytest.raises((json.JSONDecodeError, ValueError)):
        decode(content, allow_fences=False)


@pytest.mark.parametrize("raw", [
    '```json\n{"summary":"overview","key_points":["point"]}',
    '{"summary":"overview","key_points":["point"]}\n```',
    '```python\n{"summary":"overview","key_points":["point"]}\n```',
    '```json\n{"summary":"overview","key_points":["point"]}\n``',
])
def test_malformed_fences_are_rejected(decode, raw):
    with pytest.raises((json.JSONDecodeError, ValueError)):
        decode(raw)


def test_strict_fence_setting_still_allows_lossless_json_closing_repair(decode):
    assert decode('{"summary":"overview","key_points":["point"}', allow_fences=False) == {
        "summary": "overview", "key_points": ["point"]}


@pytest.mark.parametrize("fields", [
    {"title": "A source-grounded topic"},
    {"conclusion": "A conditional result"},
    {"title": "Topic", "conclusion": "Result"},
])
def test_editorial_fields_are_retained_during_lossless_closing_repair(decode, fields):
    body = {"key_points": ["## Topic\n\nA supported detail"], "summary": "Overview", **fields}
    assert decode(json.dumps(body, ensure_ascii=False)[:-1]) == body


@pytest.mark.parametrize("raw", [
    '{"summary":"overview","key_points":["point"],"title":"unfinished',
    '{"summary":"overview","key_points":["point"],"conclusion":',
    '{"summary":"overview","key_points":["point"],"title":"old","title":"new"',
])
def test_incomplete_or_duplicate_editorial_values_are_not_silently_repaired(decode, raw):
    with pytest.raises(ValueError):
        decode(raw)
