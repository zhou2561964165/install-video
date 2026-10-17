"""Source preservation and real request boundaries, never an LLM quality oracle."""
import json

import httpx
import pytest

from app.config import Settings, settings
from app.services import llm_service as service


@pytest.fixture
def configured(monkeypatch):
    values = {"llm_base_url": "https://llm.example/v1", "llm_model": "model", "llm_provider": "openai-compatible",
              "llm_summary_strategy": "legacy", "llm_summary_generation_mode": "single",
              "llm_summary_response_format": "json_object", "llm_summary_length_mode": "adaptive",
              "llm_summary_chunk_chars": 120, "llm_summary_max_chunks": 16, "llm_max_input_chars": 6000,
              "llm_summary_source_context_chars": 8, "llm_summary_notes_language": "source",
              "llm_summary_source_context_mode": "auto"}
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value, raising=False)


def summarize(text):
    captured = []
    def provider(request):
        captured.append(json.loads(request.content))
        content = json.dumps({"summary": "Overview.", "key_points": ["A source condition."]})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]})
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        service.summarize_text(text, title="Source", output_language="zh-CN", client=client)
    return captured


def sections(payload):
    return json.loads(payload["messages"][-1]["content"].split("Section summaries:\n", 1)[1])


def test_repeated_fragment_in_another_context_is_not_deleted(configured):
    text = "Earlier example.\nalpha, beta,\nA later list.\nalpha, beta,\ngamma and delta.\nFor the first three, retain the qualifier."
    prepared = service._summary_input(text)
    assert prepared.count("alpha, beta,") == 2
    assert "A later list.\nalpha, beta,\ngamma and delta.\nFor the first three" in prepared


def test_contiguous_caption_copy_is_still_collapsed(configured):
    assert service._summary_input("A repeated caption.\n A repeated caption. \nAnother context.\nA repeated caption.") == "A repeated caption.\nAnother context.\nA repeated caption."


def test_multisection_notes_keep_source_language_and_final_keeps_requested_language(configured):
    captured = summarize("Paragraph starts. " + "A supporting detail. " * 12)
    assert len(captured) >= 3
    assert all(p["messages"][-1]["content"].startswith("Output language: source\n") for p in captured[:-1])
    assert captured[-1]["messages"][-1]["content"].startswith("Output language: zh-CN\n")


def test_single_section_uses_requested_language_without_extra_generation(configured):
    captured = summarize("One brief source fact.")
    assert len(captured) == 1
    assert captured[0]["messages"][-1]["content"].startswith("Output language: zh-CN\n")


def test_full_source_merge_keeps_middle_evidence_not_in_leaf_notes(configured):
    text = "Opening. " + "x " * 20 + "MIDDLE CONDITION IS CONDITIONAL. " + "y " * 35 + "Closing."
    captured = summarize(text)
    supplied = sections(captured[-1])
    assert "MIDDLE CONDITION IS CONDITIONAL." in "\n".join(note["source_context"] for note in supplied)
    assert "[... omitted middle ...]" not in "\n".join(note["source_context"] for note in supplied)
    assert all(list(note).index("source_context") < list(note).index("summary") for note in supplied)
    # Derived from the source, not the production splitter: no original clause/section is lost.
    import re
    assert re.sub(r"\s+", " ", "\n".join(note["source_context"] for note in supplied)).strip() == re.sub(r"\s+", " ", text).strip()


def test_large_original_uses_explicit_bounded_context_without_discarding_sections(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_max_input_chars", 700)
    source = "\n".join(f"Section {i}: " + "detail " * 10 for i in range(5))
    captured = summarize(source)
    merges = [p for p in captured if "Section summaries:\n" in p["messages"][-1]["content"]]
    assert merges
    assert all(len(p["messages"][-1]["content"].split("Section summaries:\n", 1)[1]) <= 700 for p in merges)
    # Complete originals plus JSON/notes exceed this capacity; boundary evidence must state its omission.
    assert any("[... omitted middle ...]" in p["messages"][-1]["content"] for p in merges)


def test_explicit_compatibility_settings_use_requested_language_and_boundary(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_notes_language", "output")
    monkeypatch.setattr(settings, "llm_summary_source_context_mode", "boundary")
    captured = summarize("Opening. " + "x " * 70 + "Middle qualifier. " + "y " * 30 + "Closing.")
    assert all(p["messages"][-1]["content"].startswith("Output language: zh-CN\n") for p in captured)
    assert "[... omitted middle ...]" in captured[-1]["messages"][-1]["content"]


def test_zero_context_is_respected_in_auto_mode(configured, monkeypatch):
    monkeypatch.setattr(settings, "llm_summary_source_context_chars", 0)
    captured = summarize("Opening. " + "A detail. " * 25)
    assert all("source_context" not in note for note in sections(captured[-1]))


@pytest.mark.parametrize("key", ["llm_summary_notes_language", "llm_summary_source_context_mode"])
@pytest.mark.parametrize("value", ["invalid", None, [], True])
def test_invalid_new_policy_rejected_before_a_call(configured, monkeypatch, key, value):
    monkeypatch.setattr(settings, key, value)
    with pytest.raises(service.LLMServiceError) as error:
        summarize("Source fact.")
    assert error.value.error_type == "llm_unconfigured"


def test_new_policies_load_and_validate_as_real_settings(monkeypatch):
    monkeypatch.setenv("LLM_SUMMARY_NOTES_LANGUAGE", "output")
    monkeypatch.setenv("LLM_SUMMARY_SOURCE_CONTEXT_MODE", "boundary")
    configured = Settings.from_env()
    assert configured.llm_summary_notes_language == "output"
    assert configured.llm_summary_source_context_mode == "boundary"
    with pytest.raises(ValueError, match="llm_summary_notes_language"):
        Settings(llm_summary_notes_language="invalid")


@pytest.mark.parametrize("key", ["llm_summary_notes_language", "llm_summary_source_context_mode"])
def test_reused_staged_notes_reject_invalid_policy_without_post(configured, monkeypatch, key):
    monkeypatch.setattr(settings, "llm_summary_generation_mode", "staged")
    source = "A source condition. " * 15
    parts = service._summary_chunks(service._summary_input(source), 120)
    notes = [service.LLMSummaryResult("Overview.", ["A condition."], "offline", "model") for _ in parts]
    monkeypatch.setattr(settings, key, "invalid")
    requests = []
    def provider(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{}'}, "finish_reason": "stop"}]})
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        with pytest.raises(service.LLMServiceError) as error:
            service.summarize_sections(source, source_parts=parts, section_results=notes,
                                       title="Source", output_language="zh-CN", client=client)
    assert error.value.error_type == "llm_unconfigured"
    assert requests == []
