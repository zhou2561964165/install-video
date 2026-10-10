"""Offline replay of verified normalization/reference/repair evidence.

Engineering: skills first, configurable narrow modules, HTTP and downloads stay
in their service layers, scene read-only, UI three-layer tokens. MIT-derived
source/rubric/outputs retain CC BY-NC-SA 4.0 attribution. No semantic-score claim.
Frozen config and HTTP functions are never executed; orchestration is replayed
with a local completion callback that checks the exact recorded messages.
"""
import argparse
import ast
from dataclasses import asdict, dataclass
import importlib.util
import json
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit
import uuid

import httpx

ENTRY = Path(__file__).with_name("evaluate.py")
spec = importlib.util.spec_from_file_location("normalized_checker_entry", ENTRY)
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return entry.base.digest(path.read_bytes())


def verify_assets():
    results, phase = entry.RESULTS, entry.PHASE
    frozen = entry.read(results / f"{phase}-provenance.json")
    require(frozen.get("phase") == phase and type(frozen.get("ceiling")) is int
            and frozen["ceiling"] == 19 and frozen.get("work_id") == entry.WORK_ID,
            "Frozen phase identity mismatch")
    require(entry.same_json(frozen.get("config"), entry.CONFIG), "Frozen configuration mismatch")
    require(entry.same_json(frozen.get("runner_chain_sha256"), {
        "entry": digest(ENTRY), "checker": digest(Path(__file__)), "helper": digest(entry.HELPER)}),
        "Runner/checker/helper hash mismatch")
    modules = frozen.get("module_sha256")
    require(isinstance(modules, dict) and set(modules) == set(entry.MODULES), "Missing frozen module")
    for key, value in modules.items():
        require(digest(results / f"{phase}-{key}.py") == value, "Frozen module hash mismatch")
    require(digest(entry.REPORT / "rubric.json") == frozen["rubric_sha256"], "Rubric hash mismatch")
    manifest_path = entry.base.OLD / "corpus/manifest.json"
    require(digest(manifest_path) == frozen["manifest_sha256"], "Manifest hash mismatch")
    manifest = entry.read(manifest_path)
    require([s["id"] for s in manifest["samples"]] == [s["id"] for s in frozen["samples"]],
            "Frozen samples mismatch")
    require(type(frozen.get("expected_posts")) is int and frozen["expected_posts"] == 13,
            "Normal POST count mismatch")
    for sample, plan in zip(manifest["samples"], frozen["samples"]):
        path = (entry.base.OLD / "corpus" / sample["file"]).resolve()
        require(path.is_relative_to((entry.base.OLD / "corpus").resolve())
                and digest(path) == sample["sha256"] == plan["sha256"], "Source bytes mismatch")
        require(type(plan.get("sections")) is int and plan["sections"] >= 1
                and type(plan.get("expected_posts")) is int and plan["expected_posts"] == plan["sections"] + 2
                and type(plan.get("maximum_posts")) is int and plan["maximum_posts"] == plan["sections"] + 4,
                "Frozen sample budget mismatch")
    require(sum(s["maximum_posts"] for s in frozen["samples"]) == 19, "Maximum POST count mismatch")
    for row in frozen["baseline"]["sample_results"]:
        require(digest(entry.base.BASE / "results" / row["file"]) == row["sha256"], "Baseline hash mismatch")
    return frozen, manifest


def frozen_runtime(frozen):
    """Load verified pure modules and function definitions in an isolated namespace."""
    package = "normalized_frozen_" + uuid.uuid4().hex
    added = []
    for name in (package, package + ".services"):
        module = ModuleType(name)
        module.__path__ = []
        sys.modules[name] = module
        added.append(name)
    try:
        modules = {}
        for key in ("facts", "normalization", "references", "retry"):
            name = package + ".services.summary_" + key
            path = entry.RESULTS / f"{entry.PHASE}-{key}.py"
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            added.append(name)
            spec.loader.exec_module(module)
            modules[key] = module
        name = package + ".services.llm_service"
        runtime = ModuleType(name)
        runtime.__package__ = package + ".services"
        sys.modules[name] = runtime
        added.append(name)
        runtime.__dict__.update(json=json, re=re, httpx=httpx, dataclass=dataclass, asdict=asdict,
            Any=Any, Callable=Callable, urlsplit=urlsplit, urlunsplit=urlunsplit,
            settings=SimpleNamespace(**{**frozen["config"], "llm_provider": frozen["provider"],
                "llm_model": frozen["model"]}))
        for key in ("facts", "retry"):
            runtime.__dict__.update({n: getattr(modules[key], n) for n in dir(modules[key]) if not n.startswith("_")})
        source = entry.RESULTS / f"{entry.PHASE}-service.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        # Only definitions and two literal protocol constants are executed.
        # The HTTP function is excluded; settings come solely from the freeze.
        body = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
        body += [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                 and node.name not in {"_complete", "translate_text", "summarize_text"}]
        body += [node for node in tree.body if isinstance(node, ast.Assign)
                 and all(isinstance(target, ast.Name) and target.id in {
                     "_SUMMARY_PROVIDER_DEFAULTS", "_FACT_FIELDS_GUIDANCE"} for target in node.targets)]
        selected = ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))
        exec(compile(selected, str(source), "exec"), runtime.__dict__)
        return runtime, added
    except Exception:
        for name in reversed(added):
            sys.modules.pop(name, None)
        raise


def replay_sample(runtime, frozen, sample, public, trace, calls):
    source = (entry.base.OLD / "corpus" / sample["file"]).read_text(encoding="utf-8")
    text = runtime._summary_input(source)
    plan = next(p for p in frozen["samples"] if p["id"] == sample["id"])
    require(entry.base.digest(text) == plan["cleaned_sha256"] and len(text) == plan["cleaned_chars"],
            "Cleaned source mismatch")
    chunks = runtime._summary_chunks(text, min(frozen["config"]["llm_summary_facts_chunk_chars"],
        frozen["config"]["llm_summary_chunk_chars"], frozen["config"]["llm_max_input_chars"]))
    require(len(chunks) == plan["sections"], "Section count mismatch")
    parts = runtime._source_parts(text, chunks)
    limits = runtime.FactLimits(**frozen["fact_limits"])
    events, position = [], 0

    def complete(messages, *, client=None, max_tokens=None, summary_options=None):
        nonlocal position
        require(position < len(calls), "Replay required an unrecorded POST")
        row = calls[position]
        position += 1
        payload = entry.read(entry.RESULTS / "payloads" / f"{row['ordinal']:02d}.json")
        expected = {"model": frozen["model"], "temperature": 0.2, "messages": messages,
                    "max_tokens": max_tokens, **(summary_options or {})}
        require(entry.same_json(payload, expected), "Recorded POST differs from frozen replay")
        paid = events[-1]["stages"][-1]
        require(entry.same_json(row.get("stage"), paid["stage"])
                and entry.same_json(row.get("attempt"), paid["attempt"])
                and entry.same_json(row.get("recovery"), paid["recovery"]), "Request attempt identity mismatch")
        if row.get("status") == "transport_error":
            try:
                raise httpx.ConnectError("Offline replay of recorded transport error")
            except httpx.RequestError as exc:
                raise runtime.LLMServiceError("llm_error", "Recorded transport error") from exc
        response = entry.read(entry.RESULTS / "responses" / f"{row['ordinal']:02d}.json")
        if not 200 <= response["http_status"] < 300 or response.get("error_type") == "invalid_json":
            raise runtime.LLMServiceError("llm_error", "Recorded provider error")
        # This pure decoder mirrors accepted text/finish semantics without HTTP.
        return runtime._content_from_payload({"choices": [{"finish_reason": response["finish_reason"],
            "message": {"content": response["content"]}}]})

    runtime._complete = complete
    context = {"title": sample["title"], "output_language": frozen["output_language"],
               "facts_per_part_limit": limits.max_facts_per_chunk}
    result, error = None, None
    try:
        result = asdict(runtime._summarize_facts(parts, limits, context, frozen["options"],
            client=None, diagnostic=events.append))
    except runtime.LLMServiceError as exc:
        error = exc.error_type
    require(position == len(calls), "Recorded POST was not reached by frozen replay")
    require(entry.same_json(trace.get("events"), events), "Diagnostic trace differs from frozen replay")
    require(entry.same_json(public.get("result"), result) and public.get("error_type") == error,
            "Public result differs from frozen replay")
    require(len(calls) <= plan["maximum_posts"], "Sample exceeds POST ceiling")
    return {"id": sample["id"], "posts": len(calls), "status": "completed" if result else "failed",
            "retry_budget": events[-1].get("retry_budget") if events else None,
            "semantic_quality": "NOT_EVALUATED"}


def check_phase():
    frozen, manifest = verify_assets()  # All hashes before executing frozen definitions.
    ledger = entry.validate_ledger()
    require(len(ledger["requests"]) <= 19, "Phase budget overflow")
    for row in ledger["requests"]:
        ordinal = row["ordinal"]
        payload_path = entry.RESULTS / "payloads" / f"{ordinal:02d}.json"
        require(digest(payload_path) == row.get("payload_sha256"), "Payload hash mismatch")
        payload = entry.read(payload_path)
        entry.read_user(payload)
        if row.get("status") != "transport_error":
            path = entry.RESULTS / "responses" / f"{ordinal:02d}.json"
            require(digest(path) == row.get("response_sha256"), "Response hash mismatch")
            response = entry.read(path)
            require(response.get("phase") == entry.PHASE and response.get("sample") == row["sample"]
                and entry.same_json(response.get("ordinal"), ordinal)
                and response.get("stage") == row["stage"], "Response identity mismatch")
    index = entry.read(entry.RESULTS / f"{entry.PHASE}-index.json")
    rows = index.get("sample_results")
    require(isinstance(rows, list) and len(rows) <= 3, "Invalid result index")
    require([row["id"] for row in rows] == [s["id"] for s in manifest["samples"][:len(rows)]],
            "Result sample ordering mismatch")
    public_rows = []
    for row in rows:
        path = (entry.RESULTS / row["file"]).resolve()
        require(path.is_relative_to(entry.RESULTS.resolve()) and digest(path) == row["sha256"],
                "Result hash/path mismatch")
        public = entry.read(path)
        trace_path = entry.RESULTS / f"{entry.PHASE}-{row['id']}-trace.json"
        require(digest(trace_path) == public.get("trace_sha256"), "Trace hash mismatch")
        require(public.get("source_sha256") == next(s["sha256"] for s in manifest["samples"] if s["id"] == row["id"]),
                "Public source hash mismatch")
        public_rows.append((public, entry.read(trace_path)))
    require(set(r["sample"] for r in ledger["requests"]) <= {r["id"] for r in rows},
            "Ledger contains unindexed requests")
    runtime, added = frozen_runtime(frozen)
    try:
        samples = []
        for sample, (public, trace) in zip(manifest["samples"], public_rows):
            calls = [r for r in ledger["requests"] if r["sample"] == sample["id"]]
            samples.append(replay_sample(runtime, frozen, sample, public, trace, calls))
            require(samples[-1]["status"] == "completed" or len(samples) == len(rows),
                    "Phase continued after final sample failure")
        return {"phase": entry.PHASE, "posts": len(ledger["requests"]), "ceiling": 19,
                "evidence_verified": True, "samples": samples, "semantic_quality": "NOT_EVALUATED"}
    finally:
        for name in reversed(added):
            sys.modules.pop(name, None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    result = check_phase()
    if args.write:
        entry.base.exclusive(entry.RESULTS / f"{entry.PHASE}-offline-check.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
