"""One explicit Pro/schema merge of phase-8's accepted leaves; phase cap 1.

Reuse production generation and mature Responses/accounting interfaces. No
default upgrade, retries, leaf regeneration or failed draft input. Engineering:
skills first, narrow interfaces; UI three-tier tokens/design skills; yt-dlp only
its service and scene read-only. Preserve accounts/env/models/history and UI.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


engine = load(Path(__file__).with_name("evaluate.py"), "native_merge_engine")
parent = load(Path(__file__).with_name("normal_evaluate.py"), "native_merge_parent")
PROJECT, REPORT, CORPUS = engine.PROJECT, engine.REPORT, engine.CORPUS
GROUP, SHARED_LOCK, WORK_ID = engine.GROUP, engine.SHARED_LOCK, engine.WORK_ID
SCHEMA_ENTRY = REPORT.parent / "2026-10-10-schema-pro-summary-live/scripts/evaluate.py"
native = load(SCHEMA_ENTRY, "native_merge_responses_primitives")
CONFIG = parent.CONFIG | {"llm_model": "deepseek-v4-pro", "llm_summary_response_format": "json_schema",
                         "llm_summary_thinking_mode": "disabled"}
SAMPLES, PHASE_POST_CAP = ("en-long",), 1
read, io = engine.read, engine.io
_live_runtime, _assets, _closed = engine.runtime, engine.asset_paths, engine.closed_binding
_verifying = False


def select_phase(phase):
    global PHASE, RESULTS, TRACKER
    if phase != "phase-9":
        raise ValueError("This finite contrast only allocates fresh phase-9")
    PHASE, RESULTS, TRACKER = phase, REPORT / "results" / phase, GROUP.with_name(phase + ".json")


select_phase("phase-9")


def bind():
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "WORK_ID",
                 "PHASE", "RESULTS", "TRACKER", "CONFIG", "SAMPLES"):
        setattr(engine, name, globals()[name])
    engine.runtime, engine.asset_paths = runtime, asset_paths
    engine.sample_plan, engine.frozen_sources = sample_plan, frozen_sources
    engine.expected_payload, engine.decoded_response = expected_payload, decoded_response
    engine.closed_binding, io.response_evidence = closed_binding, response_evidence
    native.PROJECT, native.RESULTS = PROJECT, RESULTS
    native.snapshot_bytes = lambda frozen, path: engine.snapshot_path(
        frozen, path.resolve().relative_to(PROJECT.resolve()).as_posix()).read_bytes()


def parent_evidence():
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK"):
        setattr(parent, name, globals()[name])
    parent.select_phase("phase-8")
    parent.bind()
    verified = parent.verify_results()
    if not verified["stopped_on_error"] or verified["posts"] != 3:
        raise RuntimeError("Parent must be closed phase-8 stopped on its third merge")
    old = read(parent.RESULTS / "provenance.json")
    source = old["sample_plan"][0]
    paths = {name: parent.RESULTS / filename for name, filename in (
        ("provenance", "provenance.json"), ("ledger", "request-ledger.json"),
        ("receipt", "closed-receipt.json"), ("index", "result-index.json"), ("failure", "en-long.json"),
        ("payload1", "payload-01.json"), ("payload2", "payload-02.json"),
        ("raw1", "response-01.json"), ("raw2", "response-02.json"))}
    paths["tracker"] = parent.TRACKER
    originals = {"manifest": (CORPUS / "manifest.json").relative_to(PROJECT).as_posix(),
        "source": (CORPUS / source["file"]).relative_to(PROJECT).as_posix(),
        "captions": (CORPUS / source["raw_path"]).relative_to(PROJECT).as_posix(),
        "preparation": "backend/app/services/llm_service.py", "codec": "backend/app/services/summary_output.py",
        "normalizer": "backend/app/services/summary_json.py"}
    paths.update({key: parent.engine.snapshot_path(old, original) for key, original in originals.items()})
    binding = {"paths": {}, "sha256": {}}
    for key, path in paths.items():
        path = path.resolve()
        if not path.is_relative_to(PROJECT.resolve()):
            raise RuntimeError("Parent evidence escapes project")
        binding["paths"][key], binding["sha256"][key] = path.relative_to(PROJECT).as_posix(), io.digest(path.read_bytes())
    codec = parent.engine.load_codec(old)
    notes = [parent.engine.decoded_response(old, n, old["stages"]["en-long"][n - 1]["max_points"], codec)
             for n in (1, 2)]
    row = next(row for row in read(GROUP)["phases"] if row["phase"] == "phase-8")
    return source | {"expected_posts": 1, "notes": notes, "leaf_evidence": binding,
        "parent_group_row": row, "parent_provider": old["provider"], "parent_endpoint": old["endpoint"]}


def sample_plan():
    sample = parent_evidence()
    for name, checksum in (("file", "sha256"), ("raw_path", "raw_sha256")):
        path = (CORPUS / sample[name]).resolve()
        if not path.is_relative_to(CORPUS.resolve()) or io.digest(path.read_bytes()) != sample[checksum]:
            raise RuntimeError("Current source differs from parent")
    return [sample]


def candidate_assets():
    return sorted(set([*_assets(), Path(__file__), SCHEMA_ENTRY, Path(parent.__file__),
        PROJECT / "backend/tests/test_native_merge_evaluation.py",
        PROJECT / "backend/tests/test_summary_scope_guidance.py",
        PROJECT / "docs/superpowers/plans/2026-10-15-native-merge-check.md",
        REPORT / "reviews/phase-9-native-merge-tool.md"]))


def asset_paths():
    return sorted(set([*candidate_assets(), *(PROJECT / name for name in sample_plan()[0]["leaf_evidence"]["paths"].values())]))


class ServiceAdapter:
    def __init__(self, service, sample):
        self.service, self.sample = service, sample

    def __getattr__(self, name):
        return getattr(self.service, name)

    def _endpoint(self):
        return self.service._endpoint(responses=True)

    def merge_content(self, transcript):
        text = self.service._summary_input(transcript)
        parts = self.service._summary_chunks(text, min(CONFIG["llm_summary_chunk_chars"], CONFIG["llm_max_input_chars"]))
        if io.digest(text) != self.sample["cleaned_sha256"] or [io.digest(p) for p in parts] != self.sample["chunks"]:
            raise RuntimeError("Merge source preparation differs from parent")
        notes = [self.service.LLMSummaryResult(**note) for note in self.sample["notes"]]
        contexts = self.service._summary_merge_contexts(notes, parts)
        if contexts != parts:
            raise RuntimeError("This contrast requires complete original source contexts")
        return self.service._section_notes(notes, contexts), len(text)

    def summarize_text(self, transcript, *, title, output_language, client=None):
        content, size = self.merge_content(transcript)
        return self.service._summary_request(content, title=title, output_language=output_language,
            client=client, merge=True, source_chars=size)


def runtime():
    settings, service, ignored = _live_runtime()
    adapter = ServiceAdapter(service, sample_plan()[0])
    return settings, adapter, adapter._endpoint()


def plan():
    bind()
    group = engine.group_state()
    return {"work_id": WORK_ID, "phase": PHASE, "planned_posts": 1, "phase_post_cap": 1,
        "budget_mode": "uncapped", "hard_ceiling": None, "work_reserved_posts": group["reserved_posts"],
        "network": False, "dotenv_read": False, "samples": sample_plan(), "config": CONFIG,
        "format_posts": 0, "semantic_posts": 0, "historical_semantic_quality_verified": False}


def freeze():
    bind()
    with io.directory_guard(SHARED_LOCK):
        if RESULTS.exists() or TRACKER.exists():
            raise RuntimeError("Phase already allocated; never reopen")
        group = engine.group_state()
        engine.allocation_guard(group)
        if group["status"] != "active" or any(r["status"] != "closed" for r in group["phases"]):
            raise RuntimeError("All prior phases must be closed")
        sample = sample_plan()[0]
        settings, service, endpoint = runtime()
        if (any(getattr(settings, k, None) != v for k, v in CONFIG.items())
                or settings.llm_provider != sample["parent_provider"]
                or endpoint != sample["parent_endpoint"].removesuffix("/chat/completions") + "/responses"):
            raise RuntimeError("Explicit native comparison profile/provider/endpoint differs")
        text = (CORPUS / sample["file"]).read_text(encoding="utf-8")
        content, size = service.merge_content(text)
        payload = engine.capture_request(service, content, sample, merge=True, source_chars=size)
        assets = [(p.resolve(), p.read_bytes()) for p in asset_paths()]
        snapshots = {}
        for index, (path, raw) in enumerate(assets, 1):
            if (not path.is_relative_to(PROJECT.resolve()) or path.name.lower().startswith(".env")
                    or "credential" in path.name.lower() or path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".key", ".pem", ".p12"}):
                raise RuntimeError("Unsafe snapshot path")
            snapshots[path.relative_to(PROJECT).as_posix()] = {"file": f"snapshots/{index:04d}.bin", "sha256": io.digest(raw)}
        frozen = {"work_id": WORK_ID, "phase": PHASE, "config": CONFIG,
            "runtime_config": engine.runtime_config(settings), "library_versions": engine.versions(),
            "snapshots": snapshots, "sample_plan": [sample], "stages": {"en-long": [{"stage": "merge",
                "payload": payload, "max_points": 14}]}, "planned_posts": 1, "phase_post_cap": 1,
            "provider": settings.llm_provider, "model": settings.llm_model, "endpoint": endpoint,
            "output_language": "zh-CN", "budget_mode": "uncapped", "hard_ceiling": None,
            "parent_posts": group["reserved_posts"], "group_at_freeze": group, "frozen_utc": io.now()}
        RESULTS.mkdir(parents=True)
        io.exclusive(RESULTS / "allocation.json", {"phase": PHASE, "kind": "owned_phase_allocation"})
        for (path, raw) in assets:
            target = RESULTS / snapshots[path.relative_to(PROJECT).as_posix()]["file"]
            target.parent.mkdir(exist_ok=True)
            with target.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                engine.os.fsync(stream.fileno())
        frozen_sources(frozen)
        io.exclusive(RESULTS / "provenance.json", frozen)
        io.exclusive(RESULTS / "request-ledger.json", {"work_id": WORK_ID, "phase": PHASE, "planned_posts": 1, "requests": []})
        tracker = {"work_id": WORK_ID, "phase": PHASE, "status": "frozen", "reserved_posts": 0,
            "parent_posts": group["reserved_posts"], "planned_posts": 1, "budget_mode": "uncapped",
            "hard_ceiling": None, "ledger": str(RESULTS / "request-ledger.json"),
            "provenance_sha256": io.digest((RESULTS / "provenance.json").read_bytes())}
        io.exclusive(TRACKER, tracker)
        group["phases"].append({"phase": PHASE, "status": "frozen", "reserved_posts": 0, "tracker": str(TRACKER),
            "ledger": tracker["ledger"], "planned_posts": 1, "provenance_sha256": tracker["provenance_sha256"]})
        engine.durable(GROUP, group)
        return {"frozen": True, "network": False, "phase_post_cap": 1}


def frozen_sources(frozen):
    sample = frozen["sample_plan"][0]
    binding = sample["leaf_evidence"]
    paths = {k: engine.snapshot_path(frozen, name) for k, name in binding["paths"].items()}
    if any(io.digest(p.read_bytes()) != binding["sha256"][k] for k, p in paths.items()):
        raise RuntimeError("Frozen parent evidence hash differs")
    old, ledger, receipt, index, tracker = [read(paths[k]) for k in ("provenance", "ledger", "receipt", "index", "tracker")]
    row = sample["parent_group_row"]
    failure, original = read(paths["failure"]), old["sample_plan"][0]
    manifest = [r for r in read(paths["manifest"])["samples"] if r["id"] == "en-long"]
    if (any(o.get("work_id") != WORK_ID or o.get("phase") != "phase-8" for o in (old, ledger, receipt, index, tracker))
            or tracker["status"] != "closed" or receipt["status"] != "closed" or index["stopped_on_error"] is not True
            or index["posts"] != 3 or receipt["posts"] != 3 or len(ledger["requests"]) != 3
            or [r["stage"] for r in ledger["requests"]] != ["extract", "extract", "merge"]
            or ledger["requests"][2]["status"] != "response" or row.get("status") != "closed"
            or failure.get("success") is not False or failure.get("error_type") != "llm_invalid_response"
            or any(r.get("result_sha256") != binding["sha256"]["failure"] for r in ledger["requests"])
            or index["samples"][0].get("success") is not False
            or row.get("closed_receipt_sha256") != binding["sha256"]["receipt"] or row.get("reserved_posts") != 3
            or tracker.get("closed_receipt_sha256") != binding["sha256"]["receipt"]
            or receipt["ledger_sha256"] != binding["sha256"]["ledger"] or receipt["index_sha256"] != binding["sha256"]["index"]
            or receipt["provenance_sha256"] != binding["sha256"]["provenance"] or tracker["provenance_sha256"] != binding["sha256"]["provenance"]):
        raise RuntimeError("Closed parent stage/receipt binding differs")
    mapping = {"codec": "summary_output.py", "normalizer": "summary_json.py", "preparation": "llm_service.py"}
    projection = old | {"snapshots": {f"backend/app/services/{name}": frozen["snapshots"][binding["paths"][key]] for key, name in mapping.items()}}
    codec, helpers = engine.load_codec(projection), engine.merge_helpers(projection)
    notes = []
    for n in (1, 2):
        attempt, raw = ledger["requests"][n - 1], read(paths[f"raw{n}"])
        payload = read(paths[f"payload{n}"])
        if (attempt["status"] != "response" or attempt["response_sha256"] != binding["sha256"][f"raw{n}"]
                or attempt["payload_sha256"] != binding["sha256"][f"payload{n}"]
                or payload != old["stages"]["en-long"][n - 1]["payload"]
                or raw.get("http_status") != 200 or raw.get("finish_reason") != "stop" or raw.get("model") != old["model"]):
            raise RuntimeError("Accepted parent leaf binding differs")
        decoded = codec.decode_payload(codec.decode_summary_json(raw["content"]), strict=True)
        if not decoded.summary.strip() or not 1 <= len(decoded.key_points) <= old["stages"]["en-long"][n - 1]["max_points"]:
            raise RuntimeError("Parent leaf structure was not accepted")
        notes.append({"summary": decoded.summary.strip(), "key_points": [p.strip() for p in decoded.key_points], "provider": old["provider"], "model": old["model"]})
    text = helpers._summary_input(paths["source"].read_text(encoding="utf-8"))
    parts = helpers._summary_chunks(text, min(CONFIG["llm_summary_chunk_chars"], CONFIG["llm_max_input_chars"]))
    supplied = helpers._section_notes([engine.SimpleNamespace(**n) for n in notes], parts)
    stage = frozen["stages"]["en-long"][0]
    payload = stage["payload"]
    current_codec = engine.load_codec(frozen)
    if (len(manifest) != 1 or any(manifest[0].get(k) != sample.get(k) or original.get(k) != sample.get(k)
            for k in ("file", "raw_path", "sha256", "raw_sha256", "title", "license", "attribution"))
            or frozen["config"] != CONFIG or len(text) != sample["cleaned_chars"]
            or io.digest(engine.snapshot_path(frozen, (CORPUS / sample["file"]).relative_to(PROJECT).as_posix()).read_bytes()) != sample["sha256"]
            or sample["notes"] != notes or io.digest(paths["source"].read_bytes()) != sample["sha256"]
            or io.digest(paths["captions"].read_bytes()) != sample["raw_sha256"] or io.digest(text) != sample["cleaned_sha256"]
            or [io.digest(p) for p in parts] != sample["chunks"] or len(parts) != 2
            or frozen["planned_posts"] != 1 or frozen["phase_post_cap"] != 1 or sample["expected_posts"] != 1
            or len(frozen["stages"]["en-long"]) != 1 or stage["stage"] != "merge" or stage["max_points"] != 14
            or payload.get("model") != "deepseek-v4-pro" or payload.get("max_output_tokens") != 8192
            or payload.get("reasoning") != {"effort": "none"}
            or payload.get("text") != {"format": {"type": "json_schema", "name": "video_summary", "schema": current_codec.output_schema(14, None)}}
            or not payload["input"][-1]["content"].endswith(supplied)
            or sum(len(m["content"]) for m in payload["input"]) + len(payload["instructions"]) > CONFIG["llm_max_input_chars"]):
        raise RuntimeError("Frozen source/notes/native merge payload differs")


def closed_binding(row, work_id):
    if (engine._closing or _verifying) and row.get("phase") == "phase-8":
        frozen = read(RESULTS / "provenance.json")
        frozen_sources(frozen)
        sample = frozen["sample_plan"][0]
        if work_id != WORK_ID or row != sample["parent_group_row"]:
            raise RuntimeError("Closed parent group row differs")
        return [engine.snapshot_path(frozen, sample["leaf_evidence"]["paths"][k]) for k in ("tracker", "ledger", "receipt", "index", "provenance")]
    return _closed(row, work_id)


def expected_payload(frozen, sample, sample_post, ledger, codec):
    if sample != "en-long" or sample_post != 1 or ledger["requests"]:
        raise RuntimeError("Only one frozen native merge is allowed")
    return frozen["stages"][sample][0]["payload"]


def response_evidence(body):
    return native.response_evidence(body)


def decoded_response(frozen, ordinal, max_points, codec):
    raw = read(RESULTS / f"response-{ordinal:02d}.json")
    if raw.get("http_status") != 200 or raw.get("model") != frozen["model"]:
        raise RuntimeError("Native response model/status differs")
    content = native.responses_content(raw, frozen)
    payload = codec.decode_payload(codec.decode_summary_json(content, allow_fences=False), strict=True)
    if not payload.summary.strip() or not 1 <= len(payload.key_points) <= max_points or any(not p.strip() for p in payload.key_points):
        raise RuntimeError("Native summary structure exceeds frozen budget")
    return {"summary": payload.summary.strip(), "key_points": [p.strip() for p in payload.key_points], "provider": frozen["provider"], "model": frozen["model"]}


def check():
    bind()
    return engine.check()


def run(*, transport=None, caller=None):
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "RESULTS", "TRACKER"):
        setattr(parent, name, globals()[name])
    parent.caller_guard(transport=transport, caller=caller)
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
