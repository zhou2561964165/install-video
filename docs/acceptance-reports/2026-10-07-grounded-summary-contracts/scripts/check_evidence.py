"""Offline contracts evidence verification using the hash-validated frozen codec.

Engineering: skills first; UI ui-ux-pro-max/design-system, three-layer tokens;
configurable narrow interfaces; llm_service/ytdlp_service boundaries; scene
read-only. Lexical contracts do not prove semantic quality; retain MIT authors
and CC BY-NC-SA 4.0 attribution. Historical code and evidence remain intact.
"""
import argparse
from contextlib import contextmanager
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
RESULTS = REPORT / "results"
LEDGER = RESULTS / "request-ledger.json"
PHASE = "organization-contracts"
CEILING = 13
CHECKER = REPORT.parent / "2026-10-05-grounded-summary-evidence/scripts/check_evidence.py"
CHAIN_PATHS = {
    "contracts": Path(__file__).with_name("evaluate.py"),
    "final": REPORT.parent / "2026-10-07-grounded-summary-final/scripts/evaluate.py",
    "organization": REPORT.parent / "2026-10-07-grounded-summary-organization/scripts/evaluate.py",
    "runner": REPORT.parent / "2026-10-05-grounded-summary-evidence/scripts/evaluate.py",
    "final-checker": REPORT.parent / "2026-10-07-grounded-summary-final/scripts/check_evidence.py",
}
_spec = importlib.util.spec_from_file_location("contracts_historical_checker", CHECKER)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)


@contextmanager
def configured_checker():
    overrides = {"REPORT": REPORT, "RESULTS": RESULTS, "SHARED_LEDGER": LEDGER, "read": read}
    previous = {key: getattr(checker, key) for key in overrides}
    try:
        for key, value in overrides.items():
            setattr(checker, key, value)
        yield
    finally:
        for key, value in previous.items():
            setattr(checker, key, value)


def canonical(value):
    return json.loads(json.dumps(value))


def same_json(left, right):
    """Compare JSON values with strict scalar types and ordered arrays.

    Object key order is immaterial. Python tuples serialize as JSON arrays,
    preserving the caller's existing dataclass-to-JSON contract.
    """
    options = {"sort_keys": True, "ensure_ascii": False, "allow_nan": False,
               "separators": (",", ":")}
    return json.dumps(left, **options) == json.dumps(right, **options)


def candidate_record(candidate):
    return {"summary": [{"text": item.text, "fact_ids": list(item.fact_ids)} for item in candidate.summary],
            "key_points": [{"topic": item.topic, "text": item.text, "fact_ids": list(item.fact_ids)}
                           for item in candidate.key_points]}


def numbered_source(codec, source):
    lines = codec.split_sentences(source)
    return {"id": source.id, "line_count": len(lines),
            "text": "\n".join(f"[{index}] {line.text}" for index, line in enumerate(lines, 1))}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        checker.require(key not in result, "Duplicate JSON field")
        result[key] = value
    return result


def read(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def require_count(value, expected, reason):
    checker.require(type(value) is int and value == expected, reason)


def require_source_counts(sources):
    checker.require(isinstance(sources, list)
                    and all(isinstance(source, dict) and type(source.get("line_count")) is int
                            and source["line_count"] >= 1 for source in sources), "Source line count must be an integer")


def user_payload(row):
    payload = checker.read(RESULTS / "payloads" / f"{row['ordinal']:02d}.json")
    messages = payload.get("messages")
    checker.require(isinstance(messages, list) and len(messages) == 2
                    and messages[1].get("role") == "user"
                    and isinstance(messages[1].get("content"), str), "Invalid stage user payload")
    try:
        user = json.loads(messages[1]["content"], object_pairs_hook=unique_object)
    except (TypeError, json.JSONDecodeError):
        raise ValueError("Invalid stage user JSON") from None
    checker.require(isinstance(user, dict), "Invalid stage user object")
    return user


def bind_sample(codec, limits, frozen, result, calls, last):
    require = checker.require
    parts = [codec.SourcePart(p["id"], p["text"], p["global_start"]) for p in last.get("sources", [])]
    stages = last.get("stages", [])
    require(isinstance(stages, list) and all(isinstance(s, dict) for s in stages), "Invalid trace stages")
    if calls:
        require_count(last.get("planned_calls"), len(parts) + 2, "Trace call count must be an integer and match")
    complete = "error_type" not in result
    # A guard can stop a requesting stage before durable reservation. It may
    # appear in a failed trace but can never contribute validated artifacts.
    require(len(calls) <= len(stages) <= len(calls) + (not complete), "Trace stage count mismatch")
    expected = ["extract"] * len(parts) + ["compose", "audit"]
    require(same_json([s.get("stage") for s in stages], expected[:len(stages)]), "Trace stage order mismatch")
    require(all(s.get("status") == "validated" for s in stages[:-1]), "Nonterminal unvalidated stage")
    require(all(s.get("status") in {"requesting", "received", "validated"} for s in stages), "Invalid trace stage status")
    if complete:
        require(len(stages) == len(expected) and all(s["status"] == "validated" for s in stages),
                "Completed pipeline contains unvalidated stage")
    elif stages and len(stages) > len(calls):
        require(stages[-1]["status"] == "requesting", "Unreserved stage claims validation")
    facts, planned, validated, unvalidated = [], None, 0, []
    for index, row in enumerate(calls):
        stage = stages[index]
        require_count(stage.get("max_output_tokens"), frozen["stage_max_output_tokens"][row["stage"]],
                      "Trace stage budget mismatch")
        user = user_payload(row)
        if row["stage"] == "extract":
            require_source_counts([user.get("source")])
            require(same_json(user.get("source"), numbered_source(codec, parts[index])), "Extract request source mismatch")
        elif row["stage"] == "compose":
            expected_facts = [{"id": f.id, "topic": f.topic, "claim": f.claim, "evidence": f.quote,
                               "attribution": f.attribution, "importance": f.importance} for f in facts]
            require(same_json(user.get("facts"), expected_facts), "Compose request facts mismatch")
        else:
            require(planned is not None, "Audit without validated composition")
            themes = canonical([asdict(t) for t in planned.themes])
            candidate = candidate_record(planned.candidate)
            require(same_json(user.get("theme_plan"), themes) and same_json(themes, last.get("theme_plan")), "Audit theme plan mismatch")
            require(same_json(user.get("candidate"), candidate) and same_json(candidate, last.get("candidate")), "Audit candidate mismatch")
            require_source_counts(user.get("sources"))
            require(same_json(user.get("sources"), [numbered_source(codec, part) for part in parts]), "Audit request sources mismatch")
            expected_facts = [{"id": f.id, "source_id": f.source_id, "topic": f.topic, "claim": f.claim,
                               "evidence": list(f.evidence_indices), "attribution": f.attribution,
                               "importance": f.importance} for f in facts]
            require(same_json(user.get("facts"), expected_facts), "Audit request facts mismatch")
            referenced = {ref for item in (*planned.candidate.summary, *planned.candidate.key_points) for ref in item.fact_ids}
            require(same_json(user.get("missing_core_fact_ids"), [f.id for f in facts if f.importance == "core" and f.id not in referenced]),
                    "Audit missing core IDs mismatch")
        response = checker.read(RESULTS / "responses" / f"{row['ordinal']:02d}.json") if "response_sha256" in row else None
        if response is not None:
            require(type(response.get("ordinal")) is int and response["ordinal"] == row["ordinal"] and response.get("phase") == PHASE
                    and response.get("sample") == row["sample"] and response.get("stage") == row["stage"],
                    "Response stage identity mismatch")
        content = response.get("content") if response else None
        def parse():
            if row["stage"] == "extract":
                return codec.parse_extraction(content, parts[index], limits, f"F{index + 1}_")
            if row["stage"] == "compose":
                return codec.parse_planned_composition(content, facts, limits)
            return codec.parse_audit(content, parts, facts, limits)
        if stage["status"] != "validated":
            require(not complete and index == len(calls) - 1, "Unvalidated nonterminal contract stage")
            reason = "not_validated_by_caller"
            if content is not None:
                try:
                    parse()
                except codec.FactValidationError as exc:
                    reason = str(exc)
            unvalidated.append({"stage": row["stage"], "trace_status": stage["status"], "reason": reason})
            continue
        require(row.get("status") == "response" and response is not None
                and type(response.get("http_status")) is int and 200 <= response["http_status"] < 300
                and isinstance(content, str) and response.get("finish_reason") not in {"length", "content_filter"},
                "Validated stage lacks successful raw response")
        try:
            parsed = parse()
        except codec.FactValidationError:
            raise ValueError("Validated raw contract rejected by frozen codec") from None
        validated += 1
        if row["stage"] == "extract":
            facts.extend(parsed)
        elif row["stage"] == "compose":
            planned = parsed
            require(same_json(candidate_record(planned.candidate), last.get("candidate")), "Raw compose candidate mismatch")
            require(same_json(canonical([asdict(t) for t in planned.themes]), last.get("theme_plan")), "Raw compose theme plan mismatch")
        else:
            audit = {"facts": canonical([asdict(f) for f in parsed.facts]),
                     "output": candidate_record(parsed.candidate), "checks": canonical([asdict(c) for c in parsed.checks])}
            require(same_json(audit, last.get("audit")), "Raw audit trace mismatch")
    require(same_json(canonical([asdict(f) for f in facts]), last.get("facts", [])), "Raw extraction trace facts mismatch")
    if planned is None:
        require(not last.get("candidate") and not last.get("theme_plan"), "Unvalidated compose artifacts in trace")
    if not any(s.get("stage") == "audit" and s.get("status") == "validated" for s in stages):
        require(not last.get("audit"), "Unvalidated audit artifacts in trace")
    return {"raw_contracts_bound": True, "validated_contract_stages": validated,
            "unvalidated_contract_stages": unvalidated}


def check_phase():
    with configured_checker():
        frozen = checker.read(RESULTS / f"{PHASE}-provenance.json")
        require = checker.require
        require(frozen.get("phase") == PHASE and type(frozen.get("ceiling")) is int
                and frozen["ceiling"] == CEILING and frozen.get("ledger") == str(LEDGER), "Frozen phase ledger identity mismatch")
        require_count(frozen.get("expected_posts"), CEILING, "Frozen POST count must be an integer and match")
        plans = frozen.get("samples")
        require(isinstance(plans, list) and len(plans) == 3, "Frozen sample count mismatch")
        for plan in plans:
            require(isinstance(plan, dict) and type(plan.get("sections")) is int and plan["sections"] >= 1,
                    "Frozen section count must be an integer")
            require_count(plan.get("expected_posts"), plan["sections"] + 2, "Frozen sample POST count must be an integer and match")
            require(type(plan.get("cleaned_chars")) is int and plan["cleaned_chars"] >= 1, "Frozen source count must be an integer")
        require(sum(plan["expected_posts"] for plan in plans) == CEILING, "Frozen total POST count mismatch")
        require(isinstance(frozen.get("stage_max_output_tokens"), dict)
                and all(type(frozen["stage_max_output_tokens"].get(stage)) is int
                        and frozen["stage_max_output_tokens"][stage] > 0 for stage in ("extract", "compose", "audit")),
                "Frozen stage budget must be an integer")
        paths = {**CHAIN_PATHS, "checker": Path(__file__), "checker-runner": CHECKER}
        require(same_json(frozen.get("runner_chain_sha256"), {key: checker.digest(path) for key, path in paths.items()}),
                "Runner/checker chain hash mismatch")
        require(checker.digest(Path(__file__)) == frozen.get("evidence_checker_sha256")
                and checker.digest(CHECKER) == frozen.get("evidence_checker_runner_sha256"), "Checker hash mismatch")
        ledger = checker.read(LEDGER)
        require(type(ledger.get("ceiling")) is int and ledger["ceiling"] == CEILING
                and isinstance(ledger.get("requests"), list), "Contracts ledger ceiling mismatch")
        sample_posts = {}
        for ordinal, row in enumerate(ledger["requests"], 1):
            require(isinstance(row, dict) and row.get("phase") == PHASE, "Foreign phase in contracts ledger")
            require_count(row.get("ordinal"), ordinal, "Contracts ledger ordinal identity mismatch")
            sample = row.get("sample")
            require(isinstance(sample, str), "Contracts ledger sample identity mismatch")
            sample_posts[sample] = sample_posts.get(sample, 0) + 1
            require_count(row.get("sample_post"), sample_posts[sample], "Contracts ledger sample_post identity mismatch")
        # Historical helper verifies frozen module/cleanup hashes before loading
        # any code and verifies lexical sources, ledger, output and original audit.
        result = checker.check_phase(PHASE)
        codec, _ = checker.frozen_helpers(PHASE)
        require(callable(getattr(codec, "parse_extraction", None))
                and callable(getattr(codec, "parse_planned_composition", None)), "Frozen contracts codec missing")
        limits = codec.FactLimits(**frozen["fact_limits"])
        index = checker.read(RESULTS / f"{PHASE}-index.json")
        for sample, row in zip(result["samples"], index["sample_results"]):
            public = checker.read(RESULTS / row["file"])
            trace = checker.read(RESULTS / f"{PHASE}-{row['id']}-trace.json")
            last = trace["events"][-1] if trace["events"] else {}
            calls = [r for r in ledger["requests"] if r["sample"] == row["id"]]
            sample.update(bind_sample(codec, limits, frozen, public, calls, last))
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    result = check_phase()
    if args.write:
        with (RESULTS / f"{PHASE}-offline-check.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
