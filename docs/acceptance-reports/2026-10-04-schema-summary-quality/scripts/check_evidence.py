"""Offline immutable profile, baseline, response and ledger evidence checks.

Engineering: skills first; tokens; configurable narrow services; scene read-only.
MIT-derived content retains original attribution and CC BY-NC-SA 4.0.
"""
import hashlib
import json
from pathlib import Path
import subprocess

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
RESULTS = REPORT / "results"
OLD = REPORT.parent / "2026-10-04-natural-subtitle-quality"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ledger = json.loads((RESULTS / "request-ledger.json").read_text(encoding="utf-8"))
    assert ledger["ceiling"] == 20 and len(ledger["requests"]) <= 20
    profiles = {}
    for path in sorted(RESULTS.glob("*-provenance.json")):
        name = path.name.removesuffix("-provenance.json")
        frozen = json.loads(path.read_text(encoding="utf-8"))
        assert digest(RESULTS / f"{name}-service.py") == frozen["service_sha256"]
        assert digest(RESULTS / f"{name}-config.py") == frozen["settings_source_sha256"]
        assert digest(REPORT / "rubric.json") == frozen["rubric_sha256"]
        assert digest(OLD / "corpus/manifest.json") == frozen["manifest_and_facts_sha256"]
        baseline = frozen["baseline"]
        source = subprocess.check_output(["git", "show", f"{baseline['commit']}:backend/app/services/llm_service.py"], cwd=PROJECT)
        assert hashlib.sha256(source).hexdigest() == baseline["service_sha256"]
        for row in baseline["sample_results"]:
            assert digest(OLD / "results" / row["file"]) == row["sha256"]
        profiles[name] = frozen
    confirmed = 0
    for ordinal, row in enumerate(ledger["requests"], 1):
        assert row["ordinal"] == ordinal
        assert digest(RESULTS / "payloads" / f"{ordinal:02d}.json") == row["payload_sha256"]
        assert row["service_sha256"] == profiles[row["phase"]]["service_sha256"]
        if row.get("status") == "response":
            confirmed += 1
        if "response_sha256" in row:
            assert digest(RESULTS / "responses" / f"{ordinal:02d}.json") == row["response_sha256"]
    for index in RESULTS.glob("*-index.json"):
        for row in json.loads(index.read_text(encoding="utf-8"))["sample_results"]:
            assert digest(RESULTS / row["file"]) == row["sha256"]
    delivery_path = RESULTS / "delivery-profile.json"
    if delivery_path.exists():
        delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
        assert digest(PROJECT / "backend/app/services/llm_service.py") == delivery["service_sha256"]
        assert digest(PROJECT / "backend/app/config.py") == delivery["settings_source_sha256"]
        assert digest(RESULTS / "request-ledger.json") == delivery["request_ledger_sha256"]
        selected_name = delivery["selected_default_profile"]
        assert digest(RESULTS / f"{selected_name}-provenance.json") == delivery["selected_provenance_sha256"]
        assert delivery["reserved_attempts"] == len(ledger["requests"])
        assert delivery["confirmed_http_responses"] == confirmed
        for row in delivery["phase_indexes"] + delivery["derived_reviews"]:
            assert digest(RESULTS / row["file"]) == row["sha256"]
    print(json.dumps({"offline_only": True, "profiles": len(profiles), "reserved_post_attempts": len(ledger["requests"]),
                      "confirmed_http_responses": confirmed, "ceiling": 20,
                      "old_baseline_and_facts_intact": True, "profile_and_result_hashes_valid": True}))


if __name__ == "__main__":
    main()
