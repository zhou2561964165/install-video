"""Phase-12 single-request point-ceiling contrast; no default/product change.

Reuse the direct-source adapter and mature freeze/HTTP/accounting engine.
Skills first, narrow interfaces; UI design skills/three-tier tokens, yt-dlp in
its service and scene read-only. Protect env/accounts/UI/models/old evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# The sibling loader needs no runtime imports, dotenv or network.
import importlib.util
_spec = importlib.util.spec_from_file_location("capacity_direct_primitives", Path(__file__).with_name("direct_source_evaluate.py"))
direct = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(direct)
native, engine, parent = direct.base, direct.engine, direct.parent
PROJECT, REPORT, CORPUS = direct.PROJECT, direct.REPORT, direct.CORPUS
GROUP, SHARED_LOCK, WORK_ID = direct.GROUP, direct.SHARED_LOCK, direct.WORK_ID
CONFIG = direct.CONFIG | {"llm_summary_point_ceiling": 15}
SAMPLES, PHASE_POST_CAP = ("en-long",), 1
read, io, ServiceAdapter = direct.read, direct.io, direct.ServiceAdapter
_live_runtime, _source_plan, _closed = direct._live_runtime, direct.sample_plan, direct._closed
_verifying = False


def select_phase(phase):
    global PHASE, RESULTS, TRACKER
    if phase != "phase-12":
        raise ValueError("This capacity contrast only allocates fresh phase-12")
    PHASE, RESULTS, TRACKER = phase, REPORT / "results" / phase, GROUP.with_name(phase + ".json")


select_phase("phase-12")


def bind():
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "WORK_ID",
                 "PHASE", "RESULTS", "TRACKER", "CONFIG", "SAMPLES"):
        setattr(direct, name, globals()[name])
    for name in ("sample_plan", "runtime", "asset_paths", "frozen_sources", "closed_binding",
                 "prior_closed_guard", "parent_evidence"):
        setattr(direct, name, globals()[name])
    direct.bind()


def prior_closed_guard():
    group = engine.group_state()
    found = {}
    for phase in ("phase-10", "phase-11"):
        rows = [r for r in group["phases"] if r.get("phase") == phase]
        if len(rows) != 1 or rows[0].get("status") != "closed" or rows[0].get("reserved_posts") != 1:
            raise RuntimeError("Expected closed phase-10 and phase-11")
        found[phase] = rows[0]
    own = [r for r in group["phases"] if r.get("phase") == PHASE]
    if group["reserved_posts"] != 17 + sum(r["reserved_posts"] for r in own):
        raise RuntimeError("Expected existing cumulative count 17")
    return group, found["phase-10"]


def evidence(row):
    paths = _closed(row, WORK_ID)
    directory = Path(row["ledger"]).parent
    paths += [directory / name for name in ("en-long.json", "payload-01.json", "response-01.json")]
    binding = {"paths": {}, "sha256": {}}
    for key, path in zip(("tracker", "ledger", "receipt", "index", "provenance", "product", "payload", "raw"), paths):
        path = path.resolve()
        if not path.is_relative_to(PROJECT.resolve()):
            raise RuntimeError("Closed evidence escapes project")
        binding["paths"][key] = path.relative_to(PROJECT.resolve()).as_posix()
        binding["sha256"][key] = io.digest(path.read_bytes())
    attempt = read(paths[1])["requests"][0]
    if (any(attempt.get(field + "_sha256") != binding["sha256"][name]
            for field, name in (("result", "product"), ("payload", "payload"), ("response", "raw")))
            or read(paths[3])["samples"][0].get("result_sha256") != binding["sha256"]["product"]
            or read(paths[5]).get("success") is not True
            or read(paths[6]) != read(paths[4])["stages"]["en-long"][0]["payload"]):
        raise RuntimeError("Closed product/payload/raw binding differs before allocation")
    return binding


def parent_evidence():
    group, row = prior_closed_guard()
    return evidence(row), row


def sample_plan():
    sample = _source_plan()[0]
    group, ignored = prior_closed_guard()
    row = next(r for r in group["phases"] if r["phase"] == "phase-11")
    return [sample | {"comparison_evidence": evidence(row), "comparison_group_row": row}]


def candidate_assets():
    return sorted(set([*direct.candidate_assets(), Path(__file__),
        PROJECT / "backend/tests/test_direct_source_capacity_evaluation.py",
        PROJECT / "docs/superpowers/plans/2026-10-15-direct-source-capacity-check.md",
        REPORT / "reviews/phase-12-capacity-tool.md"]))


def asset_paths():
    sample = sample_plan()[0]
    return sorted(set([*candidate_assets(), *(PROJECT / path for key in ("parent_evidence", "comparison_evidence")
        for path in sample[key]["paths"].values())]))


def runtime():
    settings, service, ignored = _live_runtime()
    sample = sample_plan()[0]
    budget = service._summary_budget(sample["cleaned_chars"])
    if (budget.max_points, budget.max_tokens, budget.point_char_limit) != (15, 8192, None):
        raise RuntimeError("Production adaptive source budget must be 15 points/8192 tokens")
    adapter = ServiceAdapter(service, sample)
    return settings, adapter, adapter._endpoint()


def plan():
    bind()
    group, ignored = prior_closed_guard()
    return {"work_id": WORK_ID, "phase": PHASE, "planned_posts": 1, "phase_post_cap": 1,
        "budget_mode": "uncapped", "hard_ceiling": None, "work_reserved_posts": group["reserved_posts"],
        "network": False, "dotenv_read": False, "samples": sample_plan(), "config": CONFIG,
        "format_posts": 0, "semantic_posts": 0, "historical_semantic_quality_verified": False}


def freeze():
    bind()
    prior_closed_guard()
    # Native freeze labels this single final stage "merge" and initializes its
    # metadata to 14. Only during construction, replace that metadata from the
    # actual production-captured schema (already checked by runtime()). All
    # persisted/live/replay validation remains non-mutating.
    def prepare(frozen):
        stage = frozen["stages"]["en-long"][0]
        stage["max_points"] = stage["payload"]["text"]["format"]["schema"]["properties"]["key_points"]["maxItems"]
        frozen_sources(frozen)
    native.frozen_sources = prepare
    try:
        return native.freeze()
    finally:
        bind()


def frozen_evidence(frozen, key, rowkey, phase, cumulative):
    sample = frozen["sample_plan"][0]
    binding, row = sample[key], sample[rowkey]
    paths = {k: engine.snapshot_path(frozen, name) for k, name in binding["paths"].items()}
    if any(io.digest(p.read_bytes()) != binding["sha256"][k] for k, p in paths.items()):
        raise RuntimeError("Frozen closed evidence hash differs")
    values = {k: read(p) for k, p in paths.items()}
    tracker, ledger, receipt, index, old, product = [values[k] for k in ("tracker", "ledger", "receipt", "index", "provenance", "product")]
    if (any(obj.get("work_id") != WORK_ID or obj.get("phase") != phase for obj in (tracker, ledger, receipt, index, old))
            or row.get("phase") != phase or row.get("status") != "closed" or row.get("reserved_posts") != 1
            or tracker.get("status") != "closed" or tracker.get("reserved_posts") != 1 or receipt.get("status") != "closed"
            or receipt.get("posts") != 1 or receipt.get("work_posts") != cumulative or index.get("posts") != 1
            or len(ledger.get("requests", [])) != 1 or len(index.get("samples", [])) != 1
            or any(obj.get("closed_receipt_sha256") != binding["sha256"]["receipt"] for obj in (row, tracker))
            or receipt.get("ledger_sha256") != binding["sha256"]["ledger"] or receipt.get("index_sha256") != binding["sha256"]["index"]
            or any(obj.get("provenance_sha256") != binding["sha256"]["provenance"] for obj in (row, tracker, receipt))
            or any(ledger["requests"][0].get(field + "_sha256") != binding["sha256"][name]
                   for field, name in (("result", "product"), ("payload", "payload"), ("response", "raw")))
            or index["samples"][0].get("result_sha256") != binding["sha256"]["product"]
            or product.get("sample") != "en-long" or product.get("success") is not True
            or values["payload"] != old["stages"]["en-long"][0]["payload"]):
        raise RuntimeError("Frozen closed historical binding differs")
    direct.source_identity_guard(sample, sample["manifest_sha256"], old)
    return values


def assert_capacity_payload(payload, previous):
    expected = json.loads(json.dumps(previous))
    expected["text"]["format"]["schema"]["properties"]["key_points"]["maxItems"] = 15
    expected["instructions"] = expected["instructions"].replace("array of 1-14 strings", "array of 1-15 strings")
    prefix, separator, source = expected["input"][-1]["content"].partition("Transcript:\n")
    expected["input"][-1]["content"] = prefix.replace("one to 14 thematic key points", "one to 15 thematic key points") + separator + source
    if not separator or payload != expected:
        raise RuntimeError("Only adaptive capacity numerical guidance/schema may differ from phase-11")


def frozen_sources(frozen):
    sample = frozen["sample_plan"][0]
    parent_values = frozen_evidence(frozen, "parent_evidence", "parent_group_row", "phase-10", 16)
    comparison = frozen_evidence(frozen, "comparison_evidence", "comparison_group_row", "phase-11", 17)
    old = comparison["provenance"]
    if (old["config"] | {"llm_summary_point_ceiling": 15} != frozen["config"]
            or old["config"].get("llm_summary_point_ceiling") != 14
            or old["runtime_config"] | {"llm_summary_point_ceiling": 15} != frozen["runtime_config"]
            or any(old[key] != frozen[key] for key in ("provider", "model", "endpoint", "library_versions", "output_language"))):
        raise RuntimeError("Only point ceiling configuration may differ from phase-11")
    manifest_path = engine.snapshot_path(frozen, (CORPUS / "manifest.json").relative_to(PROJECT).as_posix())
    direct.source_identity_guard(sample, io.digest(manifest_path.read_bytes()), parent_values["provenance"])
    manifest = read(manifest_path)
    matches = [r for r in manifest["samples"] if r.get("id") == "en-long"]
    source = engine.snapshot_path(frozen, (CORPUS / sample["file"]).relative_to(PROJECT).as_posix())
    captions = engine.snapshot_path(frozen, (CORPUS / sample["raw_path"]).relative_to(PROJECT).as_posix())
    text = engine.merge_helpers(frozen)._summary_input(source.read_text(encoding="utf-8"))
    stages, codec = frozen["stages"]["en-long"], engine.load_codec(frozen)
    payload = stages[0]["payload"]
    if (len(matches) != 1 or any(matches[0].get(k) != sample.get(k) for k in ("file", "raw_path", "sha256", "raw_sha256", "title", "license", "attribution"))
            or frozen["config"] != CONFIG or io.digest(source.read_bytes()) != sample["sha256"]
            or io.digest(captions.read_bytes()) != sample["raw_sha256"] or io.digest(text) != sample["cleaned_sha256"]
            or len(text) != sample["cleaned_chars"] or not 32000 < len(text) <= CONFIG["llm_max_input_chars"]
            or "notes" in sample or "leaf_evidence" in sample or frozen["parent_posts"] != 17
            or frozen["planned_posts"] != 1 or frozen["phase_post_cap"] != 1 or sample["expected_posts"] != 1
            or len(stages) != 1 or stages[0]["stage"] != "merge" or sample.get("request_path") != "direct_source" or stages[0]["max_points"] != 15
            or payload.get("model") != "deepseek-v4-pro" or payload.get("max_output_tokens") != 8192
            or payload.get("reasoning") != {"effort": "none"}
            or payload.get("text") != {"format": {"type": "json_schema", "name": "video_summary", "schema": codec.output_schema(15, None)}}
            or not payload["input"][-1]["content"].endswith("Transcript:\n" + text)
            or sum(len(m["content"]) for m in payload["input"]) + len(payload["instructions"]) > CONFIG["llm_max_input_chars"]):
        raise RuntimeError("Frozen full-source capacity payload differs")
    assert_capacity_payload(payload, comparison["payload"])


def closed_binding(row, work_id):
    if (engine._closing or _verifying) and row.get("phase") in ("phase-10", "phase-11"):
        frozen = read(RESULTS / "provenance.json")
        frozen_sources(frozen)
        key, rowkey = ("parent_evidence", "parent_group_row") if row["phase"] == "phase-10" else ("comparison_evidence", "comparison_group_row")
        sample = frozen["sample_plan"][0]
        if work_id != WORK_ID or row != sample[rowkey]:
            raise RuntimeError("Closed history group row differs")
        return [engine.snapshot_path(frozen, sample[key]["paths"][k]) for k in ("tracker", "ledger", "receipt", "index", "provenance")]
    return _closed(row, work_id)


def check():
    bind()
    return engine.check()


def run(*, transport=None, caller=None):
    bind()
    return direct.run(transport=transport, caller=caller)


def verify_results():
    global _verifying
    bind()
    _verifying = True
    try:
        return engine.verify_results()
    finally:
        _verifying = False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--caller", choices=("root",))
    flags = parser.add_mutually_exclusive_group(required=True)
    for name in ("plan", "freeze", "check", "run", "verify"):
        flags.add_argument(f"--{name}", action="store_true")
    args = parser.parse_args(argv)
    select_phase(args.phase)
    action = plan if args.plan else freeze if args.freeze else check if args.check else verify_results
    print(json.dumps(run(caller=args.caller) if args.run else action(), ensure_ascii=False))


if __name__ == "__main__":
    main()
