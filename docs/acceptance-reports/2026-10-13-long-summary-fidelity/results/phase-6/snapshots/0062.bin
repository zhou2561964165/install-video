"""Phase-2: refine one successful closed draft against its complete original.

The existing uncapped engine owns lock/accounting/transport/close/verification.
Root alone calls the provider; one-stage arity is not a total call/cost budget.
No retry, fallback, env writes, reasoning persistence or telemetry. Engineering:
skills first; UI three-layer tokens; narrow interfaces; yt-dlp only through
ytdlp_service; scene is read-only. Preserve source attribution and old evidence.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ENTRY = Path(__file__).with_name("evaluate.py")


def load_engine(name):
    spec = importlib.util.spec_from_file_location(name, ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


engine = load_engine("refine_accounting_engine")
draft_engine = load_engine("refine_closed_draft_reader")
PROJECT, REPORT, CORPUS, GROUP, SHARED_LOCK = (
    engine.PROJECT, engine.REPORT, engine.CORPUS, engine.GROUP, engine.SHARED_LOCK)
WORK_ID, SAMPLES = engine.WORK_ID, engine.SAMPLES
CONFIG = engine.CONFIG | {"llm_summary_fidelity_mode": "long"}
read, io, os = engine.read, engine.io, engine.os
_live_runtime = engine.runtime
_closed_binding = engine.closed_binding
_verifying = False


def select_phase(phase):
    global PHASE, RESULTS, TRACKER
    if phase != "phase-2":
        raise ValueError("This entry only allocates phase-2; never reuse phase-1")
    PHASE = phase
    RESULTS = REPORT / "results" / PHASE
    TRACKER = GROUP.with_name(PHASE + ".json")


select_phase("phase-2")


def bind():
    # Only privately imported module globals are rebound; on-disk entry is intact.
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "WORK_ID",
                 "PHASE", "RESULTS", "TRACKER", "CONFIG", "SAMPLES"):
        setattr(engine, name, globals()[name])
    engine.sample_plan, engine.frozen_sources = sample_plan, frozen_sources
    engine.asset_paths, engine.runtime = asset_paths, runtime
    engine.closed_binding = closed_binding


def closed_binding(phase, work_id):
    # A stopped phase must be closable even when its parent's live files drifted.
    # Closed verification likewise uses the parent's immutable local snapshots.
    if (engine._closing or _verifying) and phase.get("phase") == "phase-1":
        frozen = read(RESULTS / "provenance.json")
        frozen_sources(frozen)
        previous = [row for row in frozen["group_at_freeze"]["phases"] if row["phase"] == "phase-1"]
        if work_id != WORK_ID or len(previous) != 1 or phase != previous[0]:
            raise RuntimeError("Closed parent group row differs from the frozen owner")
        binding = frozen["sample_plan"][0]["draft_evidence"]
        return [engine.snapshot_path(frozen, binding["paths"][name]) for name in (
            "tracker", "ledger", "receipt", "index", "provenance")]
    return _closed_binding(phase, work_id)


def prior_context():
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK"):
        setattr(draft_engine, name, globals()[name])
    draft_engine.select_phase("phase-1")


def parent_evidence():
    """Validate the existing closed phase with its own frozen verifier first."""
    prior_context()
    checked = draft_engine.verify_results()
    if checked["stopped_on_error"] or checked["posts"] != 3:
        raise RuntimeError("Phase-1 must be closed and successful with three source stages")
    frozen = read(draft_engine.RESULTS / "provenance.json")
    result = read(draft_engine.RESULTS / "en-long.json")
    if result.get("success") is not True:
        raise RuntimeError("Only a successful phase-1 product draft may be refined")
    source = frozen["sample_plan"][0]
    if source["id"] != "en-long" or source["expected_posts"] != 3:
        raise RuntimeError("Prior source/stage identity differs")
    paths = {name: draft_engine.RESULTS / file for name, file in (
        ("provenance", "provenance.json"), ("receipt", "closed-receipt.json"),
        ("ledger", "request-ledger.json"), ("index", "result-index.json"),
        ("product", "en-long.json"), ("raw", "response-03.json"))}
    paths["tracker"] = draft_engine.TRACKER
    source_names = {
        "source": (CORPUS / source["file"]).relative_to(PROJECT).as_posix(),
        "original_captions": (CORPUS / source["raw_path"]).relative_to(PROJECT).as_posix(),
        "codec": "backend/app/services/summary_output.py",
        "normalizer": "backend/app/services/summary_json.py",
        "preparation": "backend/app/services/llm_service.py",
    }
    for name, original in source_names.items():
        paths[name] = draft_engine.snapshot_path(frozen, original)
    binding = {"phase": "phase-1", "paths": {}, "sha256": {}}
    for name, path in paths.items():
        path = path.resolve()
        if not path.is_relative_to(PROJECT.resolve()):
            raise RuntimeError("Parent evidence escapes project")
        binding["paths"][name] = path.relative_to(PROJECT.resolve()).as_posix()
        binding["sha256"][name] = io.digest(path.read_bytes())
    helpers = draft_engine.merge_helpers(frozen)
    text = helpers._summary_input(paths["source"].read_text(encoding="utf-8"))
    return source, result["result"], binding, text, frozen


def sample_plan():
    source, draft, binding, text, frozen = parent_evidence()
    # Bind the current raw source bytes too, before explicit runtime or allocation.
    for name, checksum in (("file", "sha256"), ("raw_path", "raw_sha256")):
        path = (CORPUS / source[name]).resolve()
        if not path.is_relative_to(CORPUS.resolve()) or io.digest(path.read_bytes()) != source[checksum]:
            raise RuntimeError("Current source differs from the closed draft source")
    if len(text) != source["cleaned_chars"] or io.digest(text) != source["cleaned_sha256"]:
        raise RuntimeError("Prior prepared source binding differs")
    return [source | {"expected_posts": 1, "draft": draft, "draft_evidence": binding,
        "parent_model": frozen["model"], "parent_provider": frozen["provider"],
        "parent_endpoint": frozen["endpoint"]}]


def plan():
    bind()
    group = engine.group_state()
    samples = sample_plan()
    return {"work_id": WORK_ID, "phase": PHASE, "network": False, "dotenv_read": False,
        "budget_mode": "uncapped", "hard_ceiling": None, "work_reserved_posts": group["reserved_posts"],
        "planned_posts": 1, "stage_count_purpose": "production_arity_audit_not_total_budget",
        "samples": samples, "config": CONFIG, "format_posts": 0, "semantic_posts": 0,
        "historical_semantic_quality_verified": False} | engine.historical_state(group)


def candidate_assets():
    # Reuse the audited inventory, adding this entry/test and phase-specific review.
    return [*draft_engine.asset_paths(), Path(__file__),
        PROJECT / "backend/tests/test_long_refine_evaluation.py",
        PROJECT / "backend/tests/test_summary_source_revision.py",
        PROJECT / "docs/superpowers/specs/2026-10-14-long-summary-revision-design.md",
        REPORT / "review-revision-final.md"]


def asset_paths():
    sample = sample_plan()[0]
    return sorted(set([*candidate_assets(),
        *(PROJECT / name for name in sample["draft_evidence"]["paths"].values())]))


class ServiceAdapter:
    def __init__(self, service, draft):
        self.service, self.draft = service, draft

    def __getattr__(self, name):
        return getattr(self.service, name)

    def summarize_text(self, transcript, *, title, output_language, client=None):
        draft = self.service.LLMSummaryResult(**self.draft)
        return self.service.refine_summary(transcript, draft, title=title,
            output_language=output_language, client=client)


def runtime():
    settings, service, endpoint = _live_runtime()
    draft = sample_plan()[0]["draft"]
    return settings, ServiceAdapter(service, draft), endpoint


def capture_request(service, text, sample):
    class Captured(BaseException):
        pass
    class Capture:
        payload = None
        def post(self, url, *, headers, json):
            self.payload = json
            raise Captured
    client = Capture()
    try:
        service.summarize_text(text, title=sample["title"], output_language="zh-CN", client=client)
    except Captured:
        pass
    if client.payload is None:
        raise RuntimeError("Production refinement payload capture failed")
    return client.payload


def freeze():
    bind()
    with io.directory_guard(SHARED_LOCK):
        if RESULTS.exists() or TRACKER.exists():
            raise RuntimeError("Phase already allocated; never reopen")
        group = engine.group_state()
        engine.allocation_guard(group)
        if group["status"] != "active" or any(row["status"] != "closed" for row in group["phases"]):
            raise RuntimeError("All prior phases must be closed")
        planned = plan()
        sample = planned["samples"][0]
        settings, service, endpoint = runtime()
        if any(getattr(settings, key, None) != value for key, value in CONFIG.items()):
            raise RuntimeError("Runtime candidate profile/configuration differs")
        if (settings.llm_model != sample["parent_model"] or settings.llm_provider != sample["parent_provider"]
                or endpoint != sample["parent_endpoint"]):
            raise RuntimeError("Refinement must retain the closed draft provider/model/endpoint")
        text = service._summary_input((CORPUS / sample["file"]).read_text(encoding="utf-8"))
        if io.digest(text) != sample["cleaned_sha256"] or len(text) != sample["cleaned_chars"]:
            raise RuntimeError("Refinement source preparation differs from phase-1")
        stages = {sample["id"]: [{"stage": "refine", "payload": capture_request(service, text, sample),
            "max_points": service._summary_budget(len(text)).max_points}]}
        assets = []
        for path in asset_paths():
            path = Path(path).resolve()
            if (not path.is_relative_to(PROJECT.resolve()) or path.name.lower().startswith(".env")
                    or "credential" in path.name.lower()
                    or path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".key", ".pem", ".p12"}):
                raise RuntimeError("Unsafe snapshot path")
            assets.append((path.relative_to(PROJECT.resolve()).as_posix(), path.read_bytes()))
        snapshots = {name: {"file": f"snapshots/{index:04d}.bin", "sha256": io.digest(raw)}
            for index, (name, raw) in enumerate(assets, 1)}
        frozen = {"work_id": WORK_ID, "phase": PHASE, "frozen_utc": io.now(), "config": CONFIG,
            "runtime_config": engine.runtime_config(settings), "library_versions": engine.versions(),
            "snapshots": snapshots, "sample_plan": planned["samples"], "stages": stages,
            "planned_posts": 1, "stage_count_purpose": planned["stage_count_purpose"],
            "provider": settings.llm_provider, "model": settings.llm_model, "endpoint": endpoint,
            "output_language": "zh-CN", "budget_mode": "uncapped", "hard_ceiling": None,
            "parent_posts": group["reserved_posts"], "group_at_freeze": group}
        RESULTS.mkdir(parents=True)
        io.exclusive(RESULTS / "allocation.json", {"work_id": WORK_ID, "phase": PHASE,
            "allocated_utc": io.now(), "kind": "owned_phase_allocation", "disposition": "registered_or_stop"})
        for name, raw in assets:
            path = RESULTS / snapshots[name]["file"]
            path.parent.mkdir(exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        engine.load_codec(frozen)
        frozen_sources(frozen)
        io.exclusive(RESULTS / "provenance.json", frozen)
        io.exclusive(RESULTS / "request-ledger.json", {"work_id": WORK_ID, "phase": PHASE,
            "planned_posts": 1, "requests": []})
        tracker = {"work_id": WORK_ID, "phase": PHASE, "status": "frozen", "reserved_posts": 0,
            "parent_posts": group["reserved_posts"], "planned_posts": 1, "budget_mode": "uncapped",
            "hard_ceiling": None, "ledger": str(RESULTS / "request-ledger.json"),
            "provenance_sha256": io.digest((RESULTS / "provenance.json").read_bytes())}
        io.exclusive(TRACKER, tracker)
        group["phases"].append({"phase": PHASE, "status": "frozen", "reserved_posts": 0,
            "tracker": str(TRACKER), "ledger": tracker["ledger"], "planned_posts": 1,
            "provenance_sha256": tracker["provenance_sha256"]})
        engine.durable(GROUP, group)
        return {"frozen": True, "network": False, "phase": PHASE, "planned_posts": 1}


def frozen_sources(frozen):
    """Bind source and old raw/product using only this phase's snapshots."""
    samples = frozen["sample_plan"]
    if [sample.get("id") for sample in samples] != list(SAMPLES):
        raise RuntimeError("Frozen source inventory differs")
    sample = samples[0]
    binding = sample["draft_evidence"]
    if binding["phase"] != "phase-1":
        raise RuntimeError("Parent phase differs")
    paths = {name: engine.snapshot_path(frozen, original) for name, original in binding["paths"].items()}
    if any(io.digest(path.read_bytes()) != binding["sha256"][name] for name, path in paths.items()):
        raise RuntimeError("Frozen parent evidence hash differs")
    old, receipt, ledger, index, product, tracker = (read(paths[name]) for name in (
        "provenance", "receipt", "ledger", "index", "product", "tracker"))
    if (any(obj.get("work_id") != WORK_ID or obj.get("phase") != "phase-1"
            for obj in (old, receipt, ledger, index, tracker))
            or receipt.get("status") != "closed" or tracker.get("status") != "closed"
            or index.get("stopped_on_error") is not False or product.get("success") is not True
            or receipt.get("posts") != 3 or index.get("posts") != 3 or len(ledger.get("requests", [])) != 3
            or receipt.get("provenance_sha256") != binding["sha256"]["provenance"]
            or tracker.get("provenance_sha256") != binding["sha256"]["provenance"]
            or tracker.get("closed_receipt_sha256") != binding["sha256"]["receipt"]
            or receipt.get("ledger_sha256") != binding["sha256"]["ledger"]
            or receipt.get("index_sha256") != binding["sha256"]["index"]
            or ledger["requests"][-1].get("response_sha256") != binding["sha256"]["raw"]
            or any(row.get("result_sha256") != binding["sha256"]["product"] for row in ledger["requests"])
            or product.get("source_sha256") != sample["sha256"] or product.get("result") != sample["draft"]):
        raise RuntimeError("Frozen closed draft receipt/source/product ownership differs")
    projection = old | {"snapshots": {key: frozen["snapshots"][binding["paths"][name]] for name, key in (
        ("codec", "backend/app/services/summary_output.py"),
        ("normalizer", "backend/app/services/summary_json.py"),
        ("preparation", "backend/app/services/llm_service.py"))}}
    codec = engine.load_codec(projection)
    raw = read(paths["raw"])
    decoded = codec.decode_payload(codec.decode_summary_json(raw.get("content")), strict=False)
    public = {"summary": decoded.summary.strip(), "key_points": [p.strip() for p in decoded.key_points if p.strip()],
        "provider": old["provider"], "model": old["model"]}
    original = old["sample_plan"][0]
    helpers = engine.merge_helpers(projection)
    text = helpers._summary_input(paths["source"].read_text(encoding="utf-8"))
    chunks = helpers._summary_chunks(text, min(old["config"]["llm_summary_chunk_chars"], old["config"]["llm_max_input_chars"]))
    current_source = engine.snapshot_path(frozen, (CORPUS / sample["file"]).relative_to(PROJECT).as_posix())
    if (raw.get("http_status") != 200 or raw.get("model") != old["model"] or raw.get("finish_reason") != "stop"
            or not public["summary"] or not public["key_points"]
            or len(public["key_points"]) > old["stages"][sample["id"]][-1]["max_points"]
            or public != sample["draft"] or io.digest(paths["source"].read_bytes()) != sample["sha256"]
            or io.digest(current_source.read_bytes()) != sample["sha256"]
            or io.digest(paths["original_captions"].read_bytes()) != sample["raw_sha256"]
            or io.digest(text) != sample["cleaned_sha256"] or len(text) != sample["cleaned_chars"]
            or [io.digest(part) for part in chunks] != sample["chunks"]
            or any(sample[key] != original[key] for key in (
                "file", "raw_path", "sha256", "raw_sha256", "title", "cleaned_chars", "cleaned_sha256", "chunks"))
            or sample["expected_posts"] != 1 or frozen["planned_posts"] != 1
            or [stage["stage"] for stage in frozen["stages"][sample["id"]]] != ["refine"]):
        raise RuntimeError("Frozen raw/source/draft refinement binding differs")


def check():
    bind()
    return engine.check()


def run(*, transport=None):
    bind()
    return engine.run(transport=transport)


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
    flags = parser.add_mutually_exclusive_group(required=True)
    for name in ("plan", "freeze", "check", "run", "verify"):
        flags.add_argument(f"--{name}", action="store_true")
    args = parser.parse_args(argv)
    select_phase(args.phase)
    action = plan if args.plan else freeze if args.freeze else check if args.check else run if args.run else verify_results
    print(json.dumps(action(), ensure_ascii=False))


if __name__ == "__main__":
    main()
