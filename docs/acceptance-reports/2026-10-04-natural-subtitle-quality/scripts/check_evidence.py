"""Offline hash/count/chronology verification; no model-quality scoring or HTTP.

Engineering: skills outrank plans; UI skills and three-layer tokens; configurable
abilities; narrow interfaces; yt-dlp only in ytdlp_service.py; visuals read-only.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


def digest(value):
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    manifest_path = ROOT / "corpus/manifest.json"
    manifest = read(manifest_path)
    manifest_hash = digest(manifest_path.read_bytes())
    ledger = read(RESULTS / "request-ledger.json")
    assert ledger["ceiling"] == 24 and len(ledger["requests"]) <= 24
    assert [row["ordinal"] for row in ledger["requests"]] == list(range(1, len(ledger["requests"]) + 1))
    for sample in manifest["samples"]:
        source = (ROOT / "corpus" / sample["file"]).read_bytes()
        assert digest(source) == sample["sha256"]
        text = source.decode("utf-8")
        for fact in sample["expectations"]:
            for evidence in fact["evidence"]:
                assert text[evidence["char_start"]:evidence["char_end"]] == evidence["excerpt"]
    summary = {}
    phases = [phase for phase in ("before", "after", "validation-long", "compatible", "bounded", "concise-long")
              if (RESULTS / f"{phase}-index.json").exists()]
    for phase in phases:
        provenance = read(RESULTS / f"{phase}-provenance.json")
        assert provenance["manifest_sha256"] == manifest_hash
        assert digest(provenance["system_prompt"]) == provenance["system_prompt_sha256"]
        assert digest((RESULTS / f"{phase}-service.py").read_bytes()) == provenance["service_sha256"]
        if "settings_source_sha256" in provenance:
            assert digest((RESULTS / f"{phase}-config.py").read_bytes()) == provenance["settings_source_sha256"]
        assert datetime.fromisoformat(manifest["frozen_utc"]) <= datetime.fromisoformat(provenance["captured_at_utc"])
        rows = [row for row in ledger["requests"] if row["phase"] == phase]
        index = read(RESULTS / f"{phase}-index.json")
        assert index["phase_requests_sha256"] == digest(json.dumps(rows, ensure_ascii=False, sort_keys=True))
        assert index["manifest_and_facts_sha256"] == manifest_hash
        for row in rows:
            assert datetime.fromisoformat(provenance["captured_at_utc"]) <= datetime.fromisoformat(row["started_at_utc"])
            assert row["service_sha256"] == provenance["service_sha256"]
            assert row["system_prompt_sha256"] == provenance["system_prompt_sha256"]
            if "resolved_summary_options" in provenance:
                assert row["summary_options"] == provenance["resolved_summary_options"]
            assert digest((RESULTS / "responses" / f"{row['ordinal']:02d}.json").read_bytes()) == row["response_sha256"]
        for result in index["sample_results"]:
            assert digest((RESULTS / result["file"]).read_bytes()) == result["sha256"]
        summary[phase] = {"reserved": len(rows), "confirmed_responses": sum(row.get("status") == "response" for row in rows)}
    before = read(RESULTS / "before-provenance.json")
    after = read(RESULTS / "after-provenance.json")
    validation = read(RESULTS / "validation-long-provenance.json")
    for key in ("manifest_sha256", "samples", "config", "provider", "model", "output_language"):
        assert before[key] == after[key] == validation[key]
    for key in ("service_sha256", "system_prompt", "system_prompt_sha256"):
        assert after[key] == validation[key]
    assert validation["selected_sample_ids"] == ["en-long"]
    delivery = read(RESULTS / "delivery-profile.json")
    assert delivery["chosen_phase"] == "bounded"
    assert delivery["service_sha256"] == digest((ROOT.parents[2] / "backend/app/services/llm_service.py").read_bytes())
    assert delivery["settings_source_sha256"] == digest((ROOT.parents[2] / "backend/app/config.py").read_bytes())
    assert delivery["bounded_index_sha256"] == digest((RESULTS / "bounded-index.json").read_bytes())
    assert delivery["sample_results"] == read(RESULTS / "bounded-index.json")["sample_results"]
    assert delivery["reserved_attempts_total"] == len(ledger["requests"]) == 24
    assert delivery["confirmed_http_responses_total"] == sum(row.get("status") == "response" for row in ledger["requests"])
    print(json.dumps({"provider_http_posts_in_this_check": 0, "hashes_and_chronology_valid": True,
                      "phases": summary, "tokens_reported": sum(row.get("token_usage", {}).get("total_tokens", 0) for row in ledger["requests"])}))


if __name__ == "__main__":
    main()
