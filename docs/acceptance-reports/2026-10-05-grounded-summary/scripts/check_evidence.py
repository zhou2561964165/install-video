"""Offline lexical/hash/ledger evidence check; does not grade semantic truth.

Engineering: skill priority, UI skills + token layers, configuration, narrow
interfaces, yt-dlp only ytdlp_service, LLM only llm_service, scene read-only.
MIT-derived content/review: original authors and CC BY-NC-SA 4.0 retained.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
OLD = REPORT.parent / "2026-10-04-natural-subtitle-quality"
BASE = REPORT.parent / "2026-10-04-schema-summary-quality"
sys.path.insert(0, str(PROJECT / "backend"))
from app.services.llm_service import _summary_input


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text):
    return " ".join(text.split())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["initial", "initial-contract", "refined"], required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    results = REPORT / "results"
    provenance = json.loads((results / f"{args.phase}-provenance.json").read_text(encoding="utf-8"))
    assert digest(REPORT / "rubric.json") == provenance["rubric_sha256"]
    for key, value in provenance["module_sha256"].items():
        assert digest(results / f"{args.phase}-{key}.py") == value
    for row in provenance["baseline"]["sample_results"]:
        assert digest(BASE / "results" / row["file"]) == row["sha256"]
    manifest = json.loads((OLD / "corpus/manifest.json").read_text(encoding="utf-8"))
    ledger = json.loads((results / "request-ledger.json").read_text(encoding="utf-8"))
    assert ledger["ceiling"] == 24 and len(ledger["requests"]) <= 24
    for ordinal, row in enumerate(ledger["requests"], 1):
        assert ordinal == row["ordinal"]
        assert digest(results / "payloads" / f"{ordinal:02d}.json") == row["payload_sha256"]
        if "response_sha256" in row:
            assert digest(results / "responses" / f"{ordinal:02d}.json") == row["response_sha256"]
        if row["phase"] == args.phase:
            assert row["module_sha256"] == provenance["module_sha256"]
            payload = json.loads((results / "payloads" / f"{ordinal:02d}.json").read_text(encoding="utf-8"))
            assert payload["messages"][0]["content"] == provenance["stage_prompts"][row["stage"]]
    index = json.loads((results / f"{args.phase}-index.json").read_text(encoding="utf-8"))
    checked = []
    for row in index["sample_results"]:
        assert digest(results / row["file"]) == row["sha256"]
        result = json.loads((results / row["file"]).read_text(encoding="utf-8"))
        trace_path = results / f"{args.phase}-{row['id']}-trace.json"
        assert digest(trace_path) == result["trace_sha256"]
        sample = next(item for item in manifest["samples"] if item["id"] == row["id"])
        source = OLD / "corpus" / sample["file"]
        assert digest(source) == sample["sha256"]
        clean = _summary_input(source.read_text(encoding="utf-8"))
        events = json.loads(trace_path.read_text(encoding="utf-8"))["events"]
        last = events[-1] if events else {}
        sources = {part["id"]: part for part in last.get("sources", [])}
        for part in sources.values():
            start = part["global_start"]
            assert clean[start:start + len(part["text"])] == part["text"]
            assert hashlib.sha256(part["text"].encode("utf-8")).hexdigest() == part["sha256"]
        facts = last.get("audit", {}).get("facts", last.get("facts", []))
        seen = set()
        for fact in facts:
            assert fact["id"] not in seen; seen.add(fact["id"])
            part = sources[fact["source_id"]]
            assert fact["source_sha256"] == part["sha256"]
            start, end = fact["start"], fact["end"]
            assert part["global_start"] <= start < end <= part["global_start"] + len(part["text"])
            assert clean[start:end] == fact["quote"]  # caller canonicalizes to original bytes
            assert len(fact["quote"]) <= provenance["fact_limits"]["max_quote_chars"]
            assert all(norm(value) in norm(fact["quote"]) for value in fact["qualifiers"])
            if args.phase != "refined":
                assert fact["attribution"] == "source" or norm(fact["attribution"]) in norm(fact["quote"])
            elif fact["attribution"] == "source":
                assert fact["attribution_start"] is None and fact["attribution_end"] is None
            else:
                begin, finish = fact["attribution_start"], fact["attribution_end"]
                assert type(begin) is int and type(finish) is int
                assert part["global_start"] <= begin < finish <= part["global_start"] + len(part["text"])
                assert norm(clean[begin:finish]) == norm(fact["attribution"])
        output = last.get("audit", {}).get("output")
        if output:
            assert all(item["fact_ids"] and set(item["fact_ids"]) <= seen
                       for item in output["summary"] + output["key_points"])
            assert 1 <= len(output["key_points"]) <= 7
            assert all(0 < len(item["text"]) <= 240 for item in output["key_points"])
            assert result["result"]["summary"] == " ".join(item["text"] for item in output["summary"])
            assert result["result"]["key_points"] == [item["text"] for item in output["key_points"]]
        checked.append({"id": row["id"], "quote_spans_checked": len(facts),
                        "named_attribution_spans_checked": sum(item["attribution"] != "source" for item in facts),
                        "audit_added_facts": sum(item["id"].startswith("A") for item in facts),
                        "pipeline_status": last.get("status"), "error_type": result.get("error_type"),
                        "semantic_entailment_proven": False})
    evidence = {"phase": args.phase, "offline_only": True, "samples": checked,
                "reserved_all_phases": len(ledger["requests"]), "ceiling": 24,
                "trace_lexically_valid": True,
                "semantic_accuracy_not_proven_by_this_check": True}
    if args.write:
        with (results / f"{args.phase}-offline-check.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(evidence, stream, ensure_ascii=False, indent=2); stream.write("\n")
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    main()
