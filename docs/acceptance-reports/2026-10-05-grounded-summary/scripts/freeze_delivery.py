"""Bind final opt-in implementation and immutable real-call evidence offline.

Engineering: skills first; UI skills/token/config requirements; narrow interfaces;
yt-dlp only ytdlp_service, LLM only llm_service, visual scene read-only.
MIT source and generated derivatives retain attribution/CC BY-NC-SA4.0.
"""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
RESULTS = REPORT / "results"
BASE = REPORT.parent / "2026-10-04-schema-summary-quality"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def functions(path):
    return {node.name: digest(ast.dump(node, include_attributes=False).encode("utf-8"))
            for node in ast.parse(path.read_text(encoding="utf-8")).body if isinstance(node, ast.FunctionDef)}


def main():
    final = json.loads((RESULTS / "refined-provenance.json").read_text(encoding="utf-8"))
    paths = {"service": PROJECT / "backend/app/services/llm_service.py",
             "config": PROJECT / "backend/app/config.py",
             "facts": PROJECT / "backend/app/services/summary_facts.py"}
    for key, path in paths.items():
        assert digest(path.read_bytes()) == final["module_sha256"][key]
    old = functions(BASE / "results/natural-refined-service.py")
    new = functions(paths["service"])
    legacy_names = ["_endpoint", "_complete", "_summary_options", "_summary_request",
                    "_parse_summary_json", "_summary_input", "_summary_chunks",
                    "_section_notes", "_source_context"]
    identical = {key: new[key] for key in legacy_names if old[key] == new[key]}
    assert len(identical) == len(legacy_names)
    ledger = json.loads((RESULTS / "request-ledger.json").read_text(encoding="utf-8"))
    assert len(ledger["requests"]) == 5 and ledger["ceiling"] == 24
    assert all(row["http_status"] == 200 for row in ledger["requests"])
    artifacts = ["rubric.json", "results/request-ledger.json", "results/budget-safety.json",
                 "results/initial-provenance.json", "results/initial-contract-provenance.json",
                 "results/refined-provenance.json", "results/initial-contract-index.json",
                 "results/refined-index.json", "results/initial-contract-review.json",
                 "results/refined-review.json", "results/initial-contract-failure-diagnosis.json",
                 "results/refined-failure-diagnosis.json", "results/initial-contract-offline-check.json",
                 "results/refined-offline-check.json"]
    evidence = {
        "bound_utc": datetime.now(timezone.utc).isoformat(), "module_sha256": final["module_sha256"],
        "default_strategy": "legacy", "measured_strategy": "facts",
        "default_promotion": False, "final_measured_profile": "refined",
        "final_profile_delivered_valid_output": False,
        "baseline": final["baseline"], "legacy_function_ast_sha256_unchanged_from_baseline": identical,
        "legacy_summarize_wrapper_changed": True,
        "legacy_preservation_scope": "Named original transport/summary/cleanup helpers AST-identical; wrapper adds preselected strategy routing and private callback. Full API tests are separate root verification, not proven by AST hash.",
        "reserved_attempts": 5, "http_200": 5,
        "reported_tokens": sum(row["usage"]["total_tokens"] for row in ledger["requests"]),
        "ceiling": 24, "remaining_not_used": 19, "calls_stopped": True,
        "more_calls_planned": False, "valid_delivered_samples": 1,
        "independently_verified_new_essential_facts": 4,
        "all14_coverage_measured": False, "long_organization_goal_met": False,
        "env_file_changed": False, "model_assets_or_ui_changed": False,
        "artifacts_sha256": {name: digest((REPORT / name).read_bytes()) for name in artifacts},
        "licensing": "MIT OCW authors/page/caption URLs retained in original manifest and rubric. Source excerpts and model-derived summaries/review CC BY-NC-SA4.0, noncommercial ShareAlike; product/scripts not relicensed."}
    with (RESULTS / "delivery-profile.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(evidence, stream, ensure_ascii=False, indent=2); stream.write("\n")
    print(json.dumps({"default": "legacy", "legacy_helpers_unchanged": len(identical),
                      "reserved": 5, "tokens": evidence["reported_tokens"], "calls_stopped": True}))


if __name__ == "__main__":
    main()
