"""Full normal-profile long/regression acceptance, using the audited IO engine.

Only root sends real POSTs, after independent content/tool review. Stage arity
is an audit, never a task-wide budget; uncapped accounting remains cumulative.
No paid retry/fallback, telemetry, reasoning persistence or env writes.
Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only ytdlp_service; scene read-only. Preserve all old evidence and attribution.
"""
from __future__ import annotations

import argparse
import ast
from collections import namedtuple
import importlib.util
import json
from pathlib import Path
import re
from types import SimpleNamespace

ENTRY = Path(__file__).with_name("evaluate.py")


def load_engine(name):
    spec = importlib.util.spec_from_file_location(name, ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


engine = load_engine("full_accounting_engine")
inventory = load_engine("full_inventory_engine")
PROJECT, REPORT, GROUP, SHARED_LOCK = engine.PROJECT, engine.REPORT, engine.GROUP, engine.SHARED_LOCK
OLD_CORPUS, NEW_CORPUS = engine.CORPUS, REPORT / "corpus"
CORPUS = PROJECT  # Engine IO uses project-relative source paths across both corpora.
WORK_ID = engine.WORK_ID
SUITES = {"long": ("en-long", "en-long-unseen"), "regression": ("zh-short", "en-medium")}
CONFIG = engine.CONFIG | {
    "llm_summary_max_output_tokens": 4096, "llm_summary_output_token_ceiling": 8192,
    "llm_summary_thinking_mode": "auto", "llm_summary_response_format": "auto",
    "llm_summary_fidelity_mode": "review", "llm_summary_review_max_output_tokens": 4096,
}
CRITERIA_SHA256 = "d59574c4b59ab69e2deff61ed3576a8eccd3ff869eeafb726dc6835f478b491d"
read, io, os = engine.read, engine.io, engine.os
_live_runtime = engine.runtime
_expected_payload = engine.expected_payload
_decoded_response = engine.decoded_response
_feedback_spec = importlib.util.spec_from_file_location("full_frozen_feedback_tools", Path(__file__).with_name("review_evaluate.py"))
feedback_tools = importlib.util.module_from_spec(_feedback_spec)
_feedback_spec.loader.exec_module(feedback_tools)


def select_phase(phase):
    global PHASE, RESULTS, TRACKER
    if not isinstance(phase, str) or not re.fullmatch(r"phase-[1-9][0-9]*", phase) or int(phase[6:]) < 3:
        raise ValueError("Full generation uses only fresh phase-N with N>=3")
    PHASE = phase
    RESULTS, TRACKER = REPORT / "results" / phase, GROUP.with_name(phase + ".json")


def select_suite(suite):
    global SUITE, SAMPLES
    if suite not in SUITES:
        raise ValueError("Suite must be long or regression")
    SUITE, SAMPLES = suite, SUITES[suite]


select_phase("phase-3")
select_suite("long")


def bind():
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "WORK_ID",
                 "PHASE", "RESULTS", "TRACKER", "CONFIG", "SAMPLES"):
        setattr(engine, name, globals()[name])
    engine.sample_plan, engine.frozen_sources, engine.expected_payload = sample_plan, frozen_sources, expected_payload
    engine.asset_paths, engine.runtime = asset_paths, runtime
    engine.decoded_response = decoded_response
    feedback_tools.RESULTS = RESULTS
    feedback_tools.engine.RESULTS = RESULTS


def safe_path(path, root):
    path = Path(path).resolve()
    if (not path.is_relative_to(Path(root).resolve()) or path.name.lower().startswith(".env")
            or "credential" in path.name.lower()
            or path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".key", ".pem", ".p12"}):
        raise RuntimeError("Unsafe source/snapshot path")
    return path


def criteria_path():
    path = safe_path(REPORT / "unseen-review-criteria.md", PROJECT)
    if io.digest(path.read_bytes()) != CRITERIA_SHA256:
        raise RuntimeError("Pre-generation unseen criteria hash differs")
    return path


def sample_plan():
    criteria_path()
    manifests = {OLD_CORPUS: read(safe_path(OLD_CORPUS / "manifest.json", PROJECT)),
                 NEW_CORPUS: read(safe_path(NEW_CORPUS / "manifest.json", PROJECT))}
    samples = []
    for sid in SAMPLES:
        corpus = NEW_CORPUS if sid == "en-long-unseen" else OLD_CORPUS
        rows = [row for row in manifests[corpus]["samples"] if row.get("id") == sid]
        if len(rows) != 1:
            raise RuntimeError("Source identity is missing or ambiguous")
        row = rows[0]
        if any(not isinstance(row.get(key), str) or not row[key].strip() for key in (
                "file", "raw_path", "title", "license", "attribution", "sha256", "raw_sha256")):
            raise RuntimeError("Source license/attribution/identity is incomplete")
        paths = {key: safe_path(corpus / row[key], corpus) for key in ("file", "raw_path")}
        for name, checksum in (("file", "sha256"), ("raw_path", "raw_sha256")):
            if not re.fullmatch(r"[0-9a-f]{64}", row[checksum]) or io.digest(paths[name].read_bytes()) != row[checksum]:
                raise RuntimeError("Source path/hash differs")
        text = engine.cleaned(paths["file"].read_text(encoding="utf-8"))
        chunks = engine.base.chunks(text, min(CONFIG["llm_summary_chunk_chars"], CONFIG["llm_max_input_chars"]))
        expected_chunks = 2 if SUITE == "long" else 1
        if not text or len(chunks) != expected_chunks:
            raise RuntimeError("Frozen suite requires two long leaves or one regression stage")
        sample = {key: row[key] for key in ("id", "sha256", "raw_sha256", "title", "license", "attribution")}
        sample.update(file=paths["file"].relative_to(PROJECT.resolve()).as_posix(),
            raw_path=paths["raw_path"].relative_to(PROJECT.resolve()).as_posix(),
            manifest=(corpus / "manifest.json").resolve().relative_to(PROJECT.resolve()).as_posix(),
            original_file=row["file"], original_raw_path=row["raw_path"],
            cleaned_chars=len(text), cleaned_sha256=io.digest(text), chunks=[io.digest(part) for part in chunks],
            expected_posts=5 if SUITE == "long" else 1)
        samples.append(sample)
    return samples


def plan():
    bind()
    group = engine.group_state()
    samples = sample_plan()
    return {"work_id": WORK_ID, "phase": PHASE, "suite": SUITE, "network": False, "dotenv_read": False,
        "budget_mode": "uncapped", "hard_ceiling": None, "work_reserved_posts": group["reserved_posts"],
        "planned_posts": sum(sample["expected_posts"] for sample in samples),
        "stage_count_purpose": "production_arity_audit_not_total_budget", "samples": samples, "config": CONFIG,
        "format_posts": 0, "semantic_posts": 0, "historical_semantic_quality_verified": False} | engine.historical_state(group)


def candidate_assets():
    return [*inventory.asset_paths(), Path(__file__),
        PROJECT / "backend/tests/test_long_full_evaluation.py",
        PROJECT / "backend/tests/test_summary_source_revision.py",
        PROJECT / "backend/tests/test_summary_source_review.py",
        Path(__file__).with_name("review_evaluate.py"),
        PROJECT / "docs/superpowers/specs/2026-10-14-source-review-summary-design.md",
        REPORT / "review-product-final.md", criteria_path(),
        *(path for path in NEW_CORPUS.rglob("*") if path.is_file())]


def asset_paths():
    return sorted(set([*candidate_assets(), *(PROJECT / sample[key] for sample in sample_plan()
        for key in ("file", "raw_path", "manifest"))]))


def runtime():
    return _live_runtime()


def capture_request(action):
    class Captured(BaseException):
        pass
    class Capture:
        payload = None
        def post(self, url, *, headers, json):
            self.payload = json
            raise Captured
    client = Capture()
    try:
        action(client)
    except Captured:
        pass
    if client.payload is None:
        raise RuntimeError("Production payload capture failed")
    return client.payload


def stage_records(service, sample, text, parts):
    records = [{"stage": "extract", "payload": capture_request(lambda client, part=part:
        service._summary_request(part, title=sample["title"], output_language="zh-CN", client=client,
            intermediate_notes=len(parts) > 1)), "source_chars": len(part),
        "max_points": service._summary_budget(len(part)).max_points} for part in parts]
    if len(parts) > 1:
        size = sum(map(len, parts))
        records.append({"stage": "merge", "payload": capture_request(lambda client:
            service._summary_request("", title=sample["title"], output_language="zh-CN", client=client,
                merge=True, source_chars=size)), "source_parts": parts, "source_chars": size,
            "max_points": service._summary_budget(size).max_points})
        draft = service.LLMSummaryResult("Frozen draft placeholder.", ["Frozen point placeholder."],
            service.settings.llm_provider, service.settings.llm_model)
        class Adapter:
            def summarize_text(self, transcript, *, title, output_language, client):
                return service.review_summary(transcript, draft, title=title, output_language=output_language, client=client)
        final_payloads = feedback_tools.capture_request(Adapter(), text, sample)
        records.extend({"stage": stage, "payload": payload, "source_text": text, "source_chars": len(text),
                        "max_points": service._summary_budget(len(text)).max_points}
                       for stage, payload in zip(("review", "refine"), final_payloads))
    return records


def freeze():
    bind()
    with io.directory_guard(SHARED_LOCK):
        if RESULTS.exists() or TRACKER.exists():
            raise RuntimeError("Phase already allocated; never reopen")
        group = engine.group_state()
        engine.allocation_guard(group)
        if group["status"] != "active" or any(row["status"] != "closed" for row in group["phases"]):
            raise RuntimeError("Prior phases must be closed")
        planned = plan()
        settings, service, endpoint = runtime()
        if any(getattr(settings, key, None) != value for key, value in CONFIG.items()):
            raise RuntimeError("Runtime candidate profile/configuration differs")
        last = group["phases"][-1]
        prior = read(safe_path(Path(last["ledger"]).parent / "provenance.json", PROJECT))
        if (settings.llm_model != prior["model"] or settings.llm_provider != prior["provider"] or endpoint != prior["endpoint"]):
            raise RuntimeError("Normal profile must retain the existing provider/model/endpoint")
        stages = {}
        for sample in planned["samples"]:
            text = service._summary_input((CORPUS / sample["file"]).read_text(encoding="utf-8"))
            parts = service._summary_chunks(text, min(CONFIG["llm_summary_chunk_chars"], CONFIG["llm_max_input_chars"]))
            if io.digest(text) != sample["cleaned_sha256"] or [io.digest(part) for part in parts] != sample["chunks"]:
                raise RuntimeError("Production source preparation differs from offline plan")
            stages[sample["id"]] = stage_records(service, sample, text, parts)
        assets = [(safe_path(path, PROJECT).relative_to(PROJECT.resolve()).as_posix(), safe_path(path, PROJECT).read_bytes())
            for path in asset_paths()]
        snapshots = {name: {"file": f"snapshots/{index:04d}.bin", "sha256": io.digest(raw)}
            for index, (name, raw) in enumerate(assets, 1)}
        frozen = {"work_id": WORK_ID, "phase": PHASE, "suite": SUITE, "frozen_utc": io.now(), "config": CONFIG,
            "runtime_config": engine.runtime_config(settings), "library_versions": engine.versions(), "snapshots": snapshots,
            "sample_plan": planned["samples"], "stages": stages, "planned_posts": planned["planned_posts"],
            "stage_count_purpose": planned["stage_count_purpose"], "provider": settings.llm_provider,
            "model": settings.llm_model, "endpoint": endpoint, "output_language": "zh-CN",
            "budget_mode": "uncapped", "hard_ceiling": None, "parent_posts": group["reserved_posts"],
            "criteria_sha256": CRITERIA_SHA256, "group_at_freeze": group}
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
            "planned_posts": planned["planned_posts"], "requests": []})
        tracker = {"work_id": WORK_ID, "phase": PHASE, "status": "frozen", "reserved_posts": 0,
            "parent_posts": group["reserved_posts"], "planned_posts": planned["planned_posts"],
            "budget_mode": "uncapped", "hard_ceiling": None, "ledger": str(RESULTS / "request-ledger.json"),
            "provenance_sha256": io.digest((RESULTS / "provenance.json").read_bytes())}
        io.exclusive(TRACKER, tracker)
        group["phases"].append({"phase": PHASE, "status": "frozen", "reserved_posts": 0,
            "tracker": str(TRACKER), "ledger": tracker["ledger"], "planned_posts": planned["planned_posts"],
            "provenance_sha256": tracker["provenance_sha256"]})
        engine.durable(GROUP, group)
        return {"frozen": True, "network": False, "phase": PHASE, "suite": SUITE, "planned_posts": planned["planned_posts"]}


def budget_helper(frozen):
    path = engine.snapshot_path(frozen, "backend/app/services/llm_service.py")
    source = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == "_summary_budget"]
    if len(nodes) != 1 or nodes[0].decorator_list:
        raise RuntimeError("Frozen pure budget helper inventory differs")
    tree = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    ast.fix_missing_locations(tree)
    namespace = {"settings": SimpleNamespace(**frozen["runtime_config"]), "LLMServiceError": RuntimeError,
        "_SummaryBudget": namedtuple("FrozenBudget", "max_tokens max_points point_char_limit")}
    exec(compile(tree, str(path), "exec", dont_inherit=True), namespace)
    return namespace["_summary_budget"]


def frozen_sources(frozen):
    if frozen.get("suite") != SUITE or [s.get("id") for s in frozen["sample_plan"]] != list(SUITES[SUITE]):
        raise RuntimeError("Frozen suite/source inventory differs")
    criteria = engine.snapshot_path(frozen, (REPORT / "unseen-review-criteria.md").relative_to(PROJECT).as_posix())
    if io.digest(criteria.read_bytes()) != frozen.get("criteria_sha256"):
        raise RuntimeError("Frozen pre-generation criteria differs")
    helpers, budget = engine.merge_helpers(frozen), budget_helper(frozen)
    total = 0
    for sample in frozen["sample_plan"]:
        manifest = read(engine.snapshot_path(frozen, sample["manifest"]))
        rows = [row for row in manifest["samples"] if row.get("id") == sample["id"]]
        if len(rows) != 1 or any(rows[0].get(key) != sample[key] for key in (
                "title", "license", "attribution", "sha256", "raw_sha256")) or (
                rows[0].get("file"), rows[0].get("raw_path")) != (sample["original_file"], sample["original_raw_path"]):
            raise RuntimeError("Frozen source manifest/attribution differs")
        raw, captions = engine.snapshot_path(frozen, sample["file"]), engine.snapshot_path(frozen, sample["raw_path"])
        text = helpers._summary_input(raw.read_text(encoding="utf-8"))
        parts = helpers._summary_chunks(text, min(frozen["config"]["llm_summary_chunk_chars"], frozen["config"]["llm_max_input_chars"]))
        records = frozen["stages"][sample["id"]]
        wanted = ["extract", "extract", "merge", "review", "refine"] if SUITE == "long" else ["extract"]
        sizes = [len(part) for part in parts] + ([sum(map(len, parts)), len(text), len(text)] if SUITE == "long" else [])
        if (io.digest(raw.read_bytes()) != sample["sha256"] or io.digest(captions.read_bytes()) != sample["raw_sha256"]
                or io.digest(text) != sample["cleaned_sha256"] or len(text) != sample["cleaned_chars"]
                or [io.digest(part) for part in parts] != sample["chunks"]
                or len(parts) != (2 if SUITE == "long" else 1) or [r["stage"] for r in records] != wanted
                or sample["expected_posts"] != len(wanted)
                or SUITE == "long" and (records[2]["source_parts"] != parts
                    or records[3]["source_text"] != text or records[4]["source_text"] != text)):
            raise RuntimeError("Frozen source preparation/stage evidence differs")
        for record, size in zip(records, sizes):
            derived = budget(size)
            if (record.get("source_chars") != size or record.get("max_points") != derived.max_points
                    or record["payload"].get("max_tokens") != (frozen["config"]["llm_summary_review_max_output_tokens"]
                        if record["stage"] == "review" else derived.max_tokens)
                    or record["payload"].get("model") != frozen["model"]):
                raise RuntimeError("Frozen stage/source/output budget differs")
        total += len(wanted)
    if frozen["planned_posts"] != total:
        raise RuntimeError("Frozen suite production arity differs")


def expected_payload(frozen, sample, sample_post, ledger, codec):
    # Any evidence drift stops all later payments, including independent leaves.
    # Consumption-only checks would postpone detection until the merge stage.
    for row in ledger["requests"]:
        path = RESULTS / f"payload-{row['ordinal']:02d}.json"
        if io.digest(path.read_bytes()) != row.get("payload_sha256"):
            raise RuntimeError("Persisted request packet drift before the next payment")
        if row.get("status") == "response":
            response_path = RESULTS / f"response-{row['ordinal']:02d}.json"
            if io.digest(response_path.read_bytes()) != row.get("response_sha256"):
                raise RuntimeError("Persisted response packet drift before the next payment")
    record = frozen["stages"][sample][sample_post - 1]
    if record["stage"] not in {"review", "refine"}:
        return _expected_payload(frozen, sample, sample_post, ledger, codec)
    rows = [row for row in ledger["requests"] if row["sample"] == sample]
    wanted = ["extract", "extract", "merge"] + (["review"] if record["stage"] == "refine" else [])
    if len(rows) != len(wanted) or [row["stage"] for row in rows] != wanted:
        raise RuntimeError("Final stages require the fresh successful merge and review")
    for index, row in enumerate(rows[:3]):
        if row["status"] != "response":
            raise RuntimeError("Revision cannot consume an unsuccessful attempt")
        draft = engine.decoded_response(frozen, row["ordinal"], frozen["stages"][sample][index]["max_points"], codec)
    payload = json.loads(json.dumps(record["payload"]))
    prefix, marker, serialized = payload["messages"][1]["content"].rpartition("Evidence and draft:\n")
    evidence = json.loads(serialized) if marker else None
    keys = {"original_transcript", "draft"} | ({"review_feedback"} if record["stage"] == "refine" else set())
    if (not isinstance(evidence, dict) or set(evidence) != keys
            or evidence["original_transcript"] != record["source_text"]):
        raise RuntimeError("Frozen full-source revision template differs")
    evidence["draft"] = {"key_points": draft["key_points"], "summary": draft["summary"]}
    if record["stage"] == "refine":
        if rows[-1]["status"] != "response":
            raise RuntimeError("Revision cannot consume an unsuccessful feedback attempt")
        evidence["review_feedback"] = feedback_tools.feedback_from_raw(frozen, rows[-1]["ordinal"])
    payload["messages"][1]["content"] = prefix + marker + json.dumps(evidence, ensure_ascii=False)
    if len("\n".join(message["content"] for message in payload["messages"])) > frozen["runtime_config"]["llm_max_input_chars"]:
        raise RuntimeError("Complete source/draft revision capacity exceeded; no truncation or extra stage")
    return payload


def decoded_response(frozen, ordinal, max_points, codec):
    row = read(RESULTS / "request-ledger.json")["requests"][ordinal - 1]
    if (row.get("ordinal") != ordinal or row.get("status") != "response"
            or io.digest((RESULTS / f"response-{ordinal:02d}.json").read_bytes()) != row.get("response_sha256")):
        raise RuntimeError("Persisted raw differs before consumption by a paid successor stage")
    if row["stage"] == "review":
        return {"feedback": feedback_tools.feedback_from_raw(frozen, ordinal)}
    return _decoded_response(frozen, ordinal, max_points, codec)


def check():
    bind()
    return engine.check()


def run(*, transport=None):
    bind()
    return engine.run(transport=transport)


def verify_results():
    bind()
    return engine.verify_results()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--suite", choices=tuple(SUITES), required=True)
    flags = parser.add_mutually_exclusive_group(required=True)
    for name in ("plan", "freeze", "check", "run", "verify"):
        flags.add_argument(f"--{name}", action="store_true")
    args = parser.parse_args(argv)
    select_phase(args.phase)
    select_suite(args.suite)
    action = plan if args.plan else freeze if args.freeze else check if args.check else run if args.run else verify_results
    print(json.dumps(action(), ensure_ascii=False))


if __name__ == "__main__":
    main()
