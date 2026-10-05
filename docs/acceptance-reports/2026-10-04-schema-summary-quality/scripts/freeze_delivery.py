"""Bind selected measured default profile to final source, controls and evidence.

Offline only; no paid calls. Engineering: skills, tokens, narrow configurable
services, scene read-only, yt-dlp boundary. Derived MIT evidence remains NC/SA.
"""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("schema_evaluator", Path(__file__).with_name("evaluate.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    selected_name = "natural-refined"
    selected = json.loads((module.RESULTS / f"{selected_name}-provenance.json").read_text(encoding="utf-8"))
    assert module.digest(module.SERVICE.read_bytes()) == selected["service_sha256"]
    assert module.digest(module.CONFIG_SOURCE.read_bytes()) == selected["settings_source_sha256"]
    for key, value in module.BASE_CONFIG.items():
        setattr(module.settings, key, value)
    module.settings.llm_summary_response_format = "auto"
    module.settings.llm_summary_thinking_mode = "auto"
    module.settings.llm_summary_max_point_chars = 240
    module.settings.llm_summary_source_context_chars = 1200
    capture = module.request_capture()
    assert capture["request_options"] == selected["request_options"]
    assert capture["system_prompt_sha256"] == selected["system_prompt_sha256"]
    ledger_path = module.RESULTS / "request-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    indexes = [{"file": path.name, "sha256": module.digest(path.read_bytes())} for path in sorted(module.RESULTS.glob("*-index.json"))]
    reviews = [{"file": path.name, "sha256": module.digest(path.read_bytes())} for path in sorted(module.RESULTS.glob("*-review.json"))]
    value = {
        "bound_utc": module.now(), "selected_default_profile": selected_name,
        "service_sha256": selected["service_sha256"], "settings_source_sha256": selected["settings_source_sha256"],
        "selected_provenance_sha256": module.digest((module.RESULTS / f"{selected_name}-provenance.json").read_bytes()),
        "provider": selected["provider"], "model": selected["model"],
        "response_format": "auto", "thinking_mode": "auto", "max_point_chars": 240, "source_context_chars": 1200,
        "evaluation_process_config": module.BASE_CONFIG, "env_file_changed": False,
        "resolved_request_options": capture["request_options"],
        "actual_default_endpoint_metadata": {"host": capture["endpoint_host"], "path": capture["endpoint_path"]},
        "system_prompt_sha256": selected["system_prompt_sha256"],
        "manifest_and_facts_sha256": selected["manifest_and_facts_sha256"], "rubric_sha256": selected["rubric_sha256"],
        "baseline": selected["baseline"], "phase_indexes": indexes, "derived_reviews": reviews,
        "request_ledger_sha256": module.digest(ledger_path.read_bytes()),
        "reserved_attempts": len(ledger["requests"]),
        "confirmed_http_responses": sum(row.get("status") == "response" for row in ledger["requests"]),
        "reported_tokens": sum(row.get("usage", {}).get("total_tokens", 0) for row in ledger["requests"]),
        "ceiling": ledger["ceiling"], "calls_stopped": True, "more_calls_planned": False,
        "default_valid_sample_point_counts": [5, 5, 7],
        "essential_compound_facts_fully_retained": 12, "essential_compound_facts_partial": 2,
        "long_catch_all_chars": 365, "long_organization_goal_met": False,
        "legacy_point_length_limit_is_soft": True,
        "explicit_modes_promoted_to_default": False,
        "explicit_mode_results": {
            "json_schema": "Responses adversarial eight-point request returned eight points; local refusal.",
            "strict_tool": "Normal short/medium succeeded, long final point 294 exceeded pattern 240 and local refusal; empty adversarial first slot also failed."
        },
        "limitations": ["Joint section guidance/context change; no isolated mechanism causal estimate.",
                        "Cultural attribution and scope issues remain; not universal factual accuracy.",
                        "No upstream hard schema/pattern guarantee established.",
                        "One transport error has no received HTTP response; not 19 successful summaries."],
        "attribution_license": "MIT-derived source/results/review retain original authors, URLs and CC BY-NC-SA 4.0 noncommercial ShareAlike; product/scripts not relicensed."
    }
    module.exclusive(module.RESULTS / "delivery-profile.json", value)
    print(json.dumps({"offline_only": True, "selected": selected_name, "source_bound": True,
                      "reserved": value["reserved_attempts"], "http_responses": value["confirmed_http_responses"]}))


if __name__ == "__main__":
    main()
