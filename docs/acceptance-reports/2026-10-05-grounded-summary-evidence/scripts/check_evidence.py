"""Offline lexical/hash/ledger evidence check for the sentence-ID phase.

Verifies the caller resolved the model-selected sentence IDs to exact cleaned-input
spans and hash; does not grade semantic truth. Engineering: skill priority, narrow
interfaces, yt-dlp only ytdlp_service, LLM only llm_service, scene read-only.
MIT-derived content/review: original authors and CC BY-NC-SA 4.0 retained.
"""
import argparse
import ast
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
OLD = REPORT.parent / "2026-10-04-natural-subtitle-quality"      # frozen corpus
BASE = REPORT.parent / "2026-10-04-schema-summary-quality"       # frozen baseline
PRIOR = REPORT.parent / "2026-10-05-grounded-summary"            # prior round
RESULTS = REPORT / "results"
SHARED_LEDGER = PRIOR / "results/request-ledger.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text):
    return " ".join(text.split())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def frozen_helpers(phase):
    # These reviewed, hash-verified snapshots are trusted local project code.
    # Load only the pure codec and cleanup function, never the service's HTTP,
    # config or environment-loading module initialization.
    path = RESULTS / f"{phase}-facts.py"
    name = "_evidence_frozen_facts_" + digest(path)[:16]
    spec = importlib.util.spec_from_file_location(name, path)
    facts = importlib.util.module_from_spec(spec)
    sys.modules[name] = facts  # dataclasses resolves the defining module
    spec.loader.exec_module(facts)
    tree = ast.parse((RESULTS / f"{phase}-service.py").read_text(encoding="utf-8"))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_summary_input"]
    require(len(functions) == 1, "Frozen cleanup function missing")
    namespace = {"re": re}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(RESULTS / f"{phase}-service.py"), "exec"), namespace)
    return facts, namespace["_summary_input"]


def check_phase(phase):
    require(re.fullmatch(r"[a-z0-9-]+", phase) is not None, "Invalid phase")
    provenance = read(RESULTS / f"{phase}-provenance.json")
    require(digest(REPORT / "rubric.json") == provenance["rubric_sha256"], "Rubric hash mismatch")
    require(set(provenance["module_sha256"]) == {"service", "config", "facts"}, "Missing frozen module")
    for key, value in provenance["module_sha256"].items():
        require(digest(RESULTS / f"{phase}-{key}.py") == value, "Frozen module hash mismatch")
    for row in provenance["baseline"]["sample_results"]:
        require(digest(BASE / "results" / row["file"]) == row["sha256"], "Baseline hash mismatch")
    manifest_path = OLD / "corpus/manifest.json"
    require(digest(manifest_path) == provenance["manifest_sha256"], "Frozen manifest hash mismatch")
    manifest = read(manifest_path)
    codec, cleanup = frozen_helpers(phase)
    limits = codec.FactLimits(**provenance["fact_limits"])
    plans = provenance["samples"]
    require([item["id"] for item in plans] == [item["id"] for item in manifest["samples"]], "Frozen samples mismatch")
    for sample, plan in zip(manifest["samples"], plans):
        source = OLD / "corpus" / sample["file"]
        require(digest(source) == sample["sha256"] == plan["sha256"], "Frozen source hash mismatch")
        cleaned = cleanup(source.read_text(encoding="utf-8"))
        require(hashlib.sha256(cleaned.encode("utf-8")).hexdigest() == plan["cleaned_sha256"], "Frozen cleaned hash mismatch")
        require(len(cleaned) == plan["cleaned_chars"], "Frozen cleaned size mismatch")
        require(plan["expected_posts"] == plan["sections"] + 2, "Invalid frozen call plan")
    ledger = read(SHARED_LEDGER)
    require(type(ledger["ceiling"]) is int and len(ledger["requests"]) <= ledger["ceiling"], "Invalid budget ledger")
    require([row["ordinal"] for row in ledger["requests"]] == list(range(1, len(ledger["requests"]) + 1)), "Invalid ledger ordinals")
    own = [row for row in ledger["requests"] if row["phase"] == phase]
    for row in own:
        ordinal = row["ordinal"]
        require(digest(RESULTS / "payloads" / f"{ordinal:02d}.json") == row["payload_sha256"], "Payload hash mismatch")
        if "response_sha256" in row:
            require(digest(RESULTS / "responses" / f"{ordinal:02d}.json") == row["response_sha256"], "Response hash mismatch")
        require(row["module_sha256"] == provenance["module_sha256"], "Ledger module mismatch")
        payload = read(RESULTS / "payloads" / f"{ordinal:02d}.json")
        require(payload["messages"][0]["content"] == provenance["stage_prompts"][row["stage"]], "Stage prompt mismatch")
    index = read(RESULTS / f"{phase}-index.json")
    rows = index["sample_results"]
    # A phase stops on its first failure; only a nonempty prefix is legitimate.
    require(0 < len(rows) <= len(plans), "Missing sample index")
    require([row["id"] for row in rows] == [plan["id"] for plan in plans[:len(rows)]], "Sample index order mismatch")
    require(all(row["sample"] in {item["id"] for item in rows} for row in own), "Unindexed requests")
    checked = []
    for number, row in enumerate(rows):
        require(row["file"] == f"{phase}-{row['id']}.json", "Result file mismatch")
        require(digest(RESULTS / row["file"]) == row["sha256"], "Result hash mismatch")
        result = read(RESULTS / row["file"])
        require(result["phase"] == phase and result["id"] == row["id"], "Result identity mismatch")
        trace_path = RESULTS / f"{phase}-{row['id']}-trace.json"
        require(digest(trace_path) == result["trace_sha256"], "Trace hash mismatch")
        trace = read(trace_path)
        require(trace["phase"] == phase and trace["id"] == row["id"], "Trace identity mismatch")
        calls = [item for item in own if item["sample"] == row["id"]]
        plan = plans[number]
        require(type(row["posts"]) is int and row["posts"] == len(calls) <= plan["expected_posts"], "Sample call count mismatch")
        require([item["sample_post"] for item in calls] == list(range(1, len(calls) + 1)), "Sample call order mismatch")
        expected_stages = ["extract"] * plan["sections"] + ["compose", "audit"]
        require([item["stage"] for item in calls] == expected_stages[:len(calls)], "Sample stages mismatch")
        sample = next(item for item in manifest["samples"] if item["id"] == row["id"])
        source = OLD / "corpus" / sample["file"]
        require(result["source_sha256"] == plan["sha256"], "Result source hash mismatch")
        clean = cleanup(source.read_text(encoding="utf-8"))
        events = trace["events"]
        last = events[-1] if events else {}
        source_rows = last.get("sources", [])
        sources = {part["id"]: part for part in source_rows}
        require(len(sources) == len(source_rows), "Duplicate source IDs")
        if calls:
            require(len(sources) == plan["sections"], "Missing source parts")
            require(last["planned_calls"] == plan["expected_posts"], "Trace call plan mismatch")
        for part in source_rows:
            start = part["global_start"]
            require(type(start) is int and start >= 0 and bool(part["text"]), "Invalid source span")
            require(clean[start:start + len(part["text"])] == part["text"], "Source span mismatch")
            require(hashlib.sha256(part["text"].encode("utf-8")).hexdigest() == part["sha256"], "Source part hash mismatch")
        facts = last.get("audit", {}).get("facts", last.get("facts", []))
        seen = set()
        for fact in facts:
            require(fact["id"] not in seen, "Duplicate fact ID")
            seen.add(fact["id"])
            part = sources[fact["source_id"]]
            require(fact["source_sha256"] == part["sha256"], "Fact source hash mismatch")
            sentences = codec.split_sentences(codec.SourcePart(part["id"], part["text"], part["global_start"]))
            evidence = fact["evidence_indices"]
            require(isinstance(evidence, list) and bool(evidence), "Invalid evidence list")
            require(all(type(e) is int and 1 <= e <= len(sentences) for e in evidence), "Invalid evidence index")
            require(evidence == sorted(set(evidence)), "Noncanonical evidence order")
            selected = [sentences[i - 1] for i in evidence]
            require(fact["quote"] == "\n".join(s.text for s in selected), "Evidence quote mismatch")
            require(fact["start"] == part["global_start"] + selected[0].start, "Evidence start mismatch")
            require(fact["end"] == part["global_start"] + selected[-1].end, "Evidence end mismatch")
            for sentence in selected:
                require(clean[part["global_start"] + sentence.start:part["global_start"] + sentence.end] == sentence.text, "Evidence slice mismatch")
            require(len(evidence) <= limits.max_evidence_sentences, "Too many evidence lines")
            if fact["attribution"] == "source":
                require(fact["attribution_start"] is None and fact["attribution_end"] is None, "Generic attribution span")
            else:
                begin, finish = fact["attribution_start"], fact["attribution_end"]
                require(type(begin) is int and type(finish) is int, "Invalid attribution span")
                require(part["global_start"] <= begin < finish <= part["global_start"] + len(part["text"]), "Attribution outside source")
                # Historical codec allowed whitespace normalization; this check
                # follows its frozen contract, not today's stricter matcher.
                require(norm(clean[begin:finish]) == norm(fact["attribution"]), "Attribution mismatch")
        complete = "error_type" not in result
        if complete:
            require(len(calls) == plan["expected_posts"] and last.get("status") == "completed", "Incomplete successful pipeline")
            audit = last.get("audit")
            require(isinstance(audit, dict) and "checks" in audit and "output" in audit, "Missing final audit")
            originals = [codec.GroundedFact(**{**fact, "evidence_indices": tuple(fact["evidence_indices"])}) for fact in last["facts"]]
            additional = [{"source_id": fact["source_id"], "topic": fact["topic"], "claim": fact["claim"],
                           "evidence": fact["evidence_indices"], "attribution": fact["attribution"], "importance": fact["importance"]}
                          for fact in audit["facts"][len(originals):]]
            parsed = codec.parse_audit({"additional_facts": additional, "output": audit["output"], "checks": audit["checks"]},
                [codec.SourcePart(part["id"], part["text"], part["global_start"]) for part in source_rows], originals, limits)
            require(json.loads(json.dumps([asdict(fact) for fact in parsed.facts])) == audit["facts"], "Audit fact reconstruction mismatch")
            require(result["result"]["summary"] == parsed.candidate.public_summary, "Public summary mismatch")
            require(result["result"]["key_points"] == list(parsed.candidate.public_key_points), "Public points mismatch")
            require(result["result"]["provider"] == provenance["provider"] and result["result"]["model"] == provenance["model"], "Public model metadata mismatch")
        else:
            require(number == len(rows) - 1 and "result" not in result, "Phase continued after failure")
            if calls:
                require(last.get("status") == "failed" and last.get("error_type") == result["error_type"], "Failure trace mismatch")
        if number == len(rows) - 1 and len(rows) < len(plans):
            require(not complete, "Missing unfailed samples")
        checked.append({"id": row["id"], "evidence_spans_checked": len(facts),
                        "named_attribution_spans_checked": sum(item["attribution"] != "source" for item in facts),
                        "audit_added_facts": sum(item["id"].startswith("A") for item in facts),
                        "pipeline_status": last.get("status"), "error_type": result.get("error_type"),
                        "audit_contract_valid": complete,
                        "semantic_entailment_proven": False})
    return {"phase": phase, "offline_only": True, "samples": checked,
                "reserved_all_phases": len(ledger["requests"]), "ceiling": ledger["ceiling"],
                "trace_lexically_valid": True,
                "semantic_accuracy_not_proven_by_this_check": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["evidence-wide"], required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    evidence = check_phase(args.phase)
    if args.write:
        with (RESULTS / f"{args.phase}-offline-check.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(evidence, stream, ensure_ascii=False, indent=2); stream.write("\n")
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    main()
