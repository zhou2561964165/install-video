"""Fresh long-source fidelity acceptance, uncapped cumulative actual attempts.

Root is the sole caller under the existing shared lock. A frozen stage plan
audits production arity; it is not a total POST or cost budget. Errors stop the
phase, reservations never refund, and closed phases never reopen. No retries,
paid fallback, reasoning persistence or telemetry. Engineering: skills first;
UI three-layer tokens; narrow interfaces; yt-dlp only ytdlp_service; read-only
scene. Corpus and outputs retain the existing MIT/CC BY-NC-SA attribution.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import nullcontext
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
CORPUS = REPORT.parent / "2026-10-04-natural-subtitle-quality/corpus"
GROUP = PROJECT / ".planning/2026-10-13-long-summary-fidelity/call-group.json"
BASE = REPORT.parent / "2026-10-10-source-first-summary-live/scripts/evaluate.py"
HISTORY_HELPER = REPORT.parent / "2026-10-11-summary-content-resume/scripts/evaluate.py"
spec = importlib.util.spec_from_file_location("fidelity_source_primitives", BASE)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
spec = importlib.util.spec_from_file_location("fidelity_history_primitives", HISTORY_HELPER)
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)
io, os = base.io, base.os
SHARED_LOCK = base.SHARED_LOCK
WORK_ID = "long-summary-fidelity-20261013"
SAMPLES = ("en-long",)
CONFIG = base.CONFIG | {
    "llm_summary_generation_mode": "single", "llm_summary_thinking_mode": "enabled",
    "llm_summary_max_output_tokens": 16384, "llm_summary_output_token_ceiling": 24576,
    "llm_summary_format_retries": 0, "llm_summary_semantic_retries": 0,
    "llm_summary_max_extra_calls": 0, "llm_summary_notes_language": "source",
    "llm_summary_source_context_mode": "auto",
}
read, versions, runtime_config = base.read, history.versions, base.runtime_config
_closing = False


def select_phase(phase):
    global PHASE, RESULTS, TRACKER
    if not isinstance(phase, str) or not re.fullmatch(r"phase-[1-9][0-9]*", phase):
        raise ValueError("Phase must be a positive phase-N identifier")
    PHASE = phase
    RESULTS = REPORT / "results" / PHASE
    TRACKER = GROUP.with_name(PHASE + ".json")


select_phase("phase-1")


def durable(path, value):
    # Reuse the mature atomic writer with our strictly owned current paths.
    for name in ("PROJECT", "GROUP", "TRACKER", "RESULTS"):
        setattr(base, name, globals()[name])
    return base.durable(path, value)


def cleaned(text):
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    return "\n".join(lines)


def sample_plan():
    manifest = read(CORPUS / "manifest.json")
    samples = []
    for sid in SAMPLES:
        matches = [row for row in manifest["samples"] if row.get("id") == sid]
        if len(matches) != 1:
            raise RuntimeError("Source identity is ambiguous")
        row = matches[0]
        for name, checksum in (("file", "sha256"), ("raw_path", "raw_sha256")):
            path = (CORPUS / row[name]).resolve()
            if not path.is_relative_to(CORPUS.resolve()) or io.digest(path.read_bytes()) != row[checksum]:
                raise RuntimeError("Source path/hash differs")
        text = cleaned((CORPUS / row["file"]).read_text(encoding="utf-8"))
        parts = base.chunks(text, min(CONFIG["llm_summary_chunk_chars"], CONFIG["llm_max_input_chars"]))
        if len(parts) != 2:
            raise RuntimeError("Current long production plan requires two full-source leaves")
        samples.append({key: row[key] for key in (
            "id", "file", "raw_path", "sha256", "raw_sha256", "title", "license", "attribution")}
            | {"cleaned_chars": len(text), "cleaned_sha256": io.digest(text),
               "chunks": [io.digest(part) for part in parts], "expected_posts": len(parts) + 1})
    return samples


def history_paths():
    return [PROJECT / ".planning/2026-10-11-summary-content-resume/budget-continuation-long-final.json"]


def closed_binding(phase, work_id):
    """Read bounded closed metadata only; never load old runners or raw outputs."""
    tracker_path, ledger_path = Path(phase["tracker"]).resolve(), Path(phase["ledger"]).resolve()
    paths = [tracker_path, ledger_path, *(ledger_path.parent / name for name in (
        "closed-receipt.json", "result-index.json", "provenance.json"))]
    if any(not path.is_relative_to(PROJECT.resolve()) or path.name.lower().startswith(".env") for path in paths):
        raise RuntimeError("Closed phase metadata path is unsafe")
    tracker, ledger, receipt, index, provenance = [read(path) for path in paths]
    checksum = io.digest(paths[2].read_bytes())
    count = phase["reserved_posts"]
    if (any(obj.get("work_id") != work_id or obj.get("phase") != phase["phase"]
            for obj in (tracker, ledger, receipt, index, provenance))
            or phase.get("status") != "closed" or tracker.get("status") != "closed" or receipt.get("status") != "closed"
            or type(count) is not int or count < 0 or tracker.get("reserved_posts") != count
            or len(ledger.get("requests", [])) != count or receipt.get("posts") != count or index.get("posts") != count
            or any(obj.get("closed_receipt_sha256") != checksum for obj in (phase, tracker))
            or receipt.get("ledger_sha256") != io.digest(ledger_path.read_bytes())
            or receipt.get("index_sha256") != io.digest(paths[3].read_bytes())
            or any(obj.get("provenance_sha256") != io.digest(paths[4].read_bytes()) for obj in (phase, tracker, receipt))):
        raise RuntimeError("Closed phase receipt/accounting binding differs")
    return paths


def historical_records():
    records = []
    for path in history_paths():
        path = Path(path).resolve()
        if not path.is_relative_to(PROJECT.resolve()):
            raise RuntimeError("Historical group is outside project")
        state = read(path)
        if (state.get("status") != "closed" or type(state.get("reserved_posts")) is not int
                or any(row.get("status") != "closed" for row in state.get("phases", []))):
            raise RuntimeError("Historical group is not closed")
        for phase in state.get("phases", []):
            closed_binding(phase, state["work_id"])
        records.extend(state.get("historical_parents", []))
        records.append({"path": str(path), "sha256": io.digest(path.read_bytes()),
            "posts": state["reserved_posts"], "status": "closed"})
    return records


def historical_state(group):
    for name in ("PROJECT", "GROUP", "TRACKER", "RESULTS"):
        setattr(history, name, globals()[name])
    return history.historical_state(group)


def new_group():
    return {"work_id": WORK_ID, "budget_mode": "uncapped", "hard_ceiling": None,
        "status": "active", "reserved_posts": 0, "phases": [],
        "authorization": "User 2026-10-13 removed this task's total call/cost budget; root serial durable accounting remains",
        "historical_parents": historical_records()}


def group_state(*, validate_history=True):
    group = read(GROUP)
    if (group.get("work_id") != WORK_ID or group.get("budget_mode") != "uncapped"
            or "hard_ceiling" not in group or group["hard_ceiling"] is not None
            or type(group.get("reserved_posts")) is not int or group["reserved_posts"] < 0
            or group.get("status") not in {"active", "closed"} or not isinstance(group.get("phases"), list)):
        raise RuntimeError("Uncapped group identity/accounting differs")
    rows = group["phases"]
    if (len({row.get("phase") for row in rows}) != len(rows)
            or any(type(row.get("reserved_posts")) is not int or row["reserved_posts"] < 0 for row in rows)
            or sum(row["reserved_posts"] for row in rows) > group["reserved_posts"]):
        raise RuntimeError("Group phase identity/accounting differs")
    for row in rows:
        if row.get("status") == "closed":
            closed_binding(row, WORK_ID)
    if validate_history and not _closing:
        historical_state(group)
    return group


def plan():
    group = group_state() if GROUP.exists() else new_group()
    samples = sample_plan()
    return {"work_id": WORK_ID, "phase": PHASE, "network": False, "dotenv_read": False,
        "budget_mode": "uncapped", "hard_ceiling": None,
        "work_reserved_posts": group["reserved_posts"], "planned_posts": sum(s["expected_posts"] for s in samples),
        "stage_count_purpose": "production_arity_audit_not_total_budget", "samples": samples, "config": CONFIG,
        "format_posts": 0, "semantic_posts": 0, "historical_semantic_quality_verified": False} | historical_state(group)


def allocation_guard(group):
    """An owned directory or tracker is an allocation even before group registration.

    Keep partial files intact and stop, rather than bypassing them with a new
    phase name. This is deliberately not an automatic recovery/cleanup path.
    """
    allocations = set()
    results_root = REPORT / "results"
    if results_root.exists():
        allocations.update(path.name for path in results_root.iterdir()
            if re.fullmatch(r"phase-[1-9][0-9]*", path.name))
    if GROUP.parent.exists():
        for path in GROUP.parent.iterdir():
            matched = re.fullmatch(r"(phase-[1-9][0-9]*)\.json(\.writing)?", path.name)
            if matched:
                if matched.group(2):
                    raise RuntimeError("Unclosed owned tracker allocation write; stop without cleanup")
                allocations.add(matched.group(1))
    registered = {row["phase"]: row for row in group["phases"]}
    for phase in allocations:
        if phase not in registered or registered[phase].get("status") != "closed":
            raise RuntimeError("Unclosed or unregistered owned phase allocation; stop without cleanup")


def asset_paths():
    paths = [Path(__file__), BASE, HISTORY_HELPER, base.HELPER,
        PROJECT / "backend/tests/test_long_fidelity_evaluation.py",
        PROJECT / "backend/tests/test_long_summary_fidelity.py", PROJECT / "pyproject.toml", PROJECT / "uv.lock",
        PROJECT / "backend/app/config.py", PROJECT / "backend/app/services/llm_service.py",
        PROJECT / "backend/app/services/subtitle_service.py", REPORT / "review-criteria.md",
        REPORT / "review-final.md",
        PROJECT / "docs/superpowers/specs/2026-10-13-long-summary-fidelity-design.md"]
    paths.extend((PROJECT / "backend/app/services").glob("summary_*.py"))
    paths.extend(path for path in CORPUS.rglob("*") if path.is_file())
    paths.extend(Path(row["path"]) if Path(row["path"]).is_absolute() else PROJECT / row["path"]
                 for row in historical_records())
    # Bind the last closed phase's receipt/ledger/source freeze, without historical raw.
    prior_report = REPORT.parent / "2026-10-12-summary-long-final-check"
    paths.extend(prior_report / "results" / name for name in (
        "provenance.json", "request-ledger.json", "closed-receipt.json", "result-index.json"))
    paths.append(PROJECT / ".planning/2026-10-11-summary-content-resume/phase-4.json")
    return sorted(set(paths))


def runtime():
    sys.path.insert(0, str(PROJECT / "backend"))
    io.load_dotenv(PROJECT / "backend/.env", override=False)
    from app.config import Settings
    from app.services import llm_service as service
    # Build after explicit dotenv loading even if config was imported previously.
    settings = Settings.from_env()
    for key, value in CONFIG.items():
        setattr(settings, key, value)
    service.settings = settings
    from urllib.parse import urlsplit
    endpoint = service._endpoint()
    parts = urlsplit(endpoint)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise RuntimeError("Endpoint must be HTTPS without credentials or query metadata")
    return settings, service, endpoint


def capture_request(service, text, sample, **options):
    class Captured(BaseException):
        pass
    class Capture:
        payload = None
        def post(self, url, *, headers, json):
            self.payload = json
            raise Captured
    client = Capture()
    try:
        service._summary_request(text, title=sample["title"], output_language="zh-CN", client=client, **options)
    except Captured:
        pass
    if client.payload is None:
        raise RuntimeError("Production payload capture failed")
    return client.payload


def match_runtime(settings, service, endpoint, frozen):
    if (endpoint != frozen["endpoint"] or service._endpoint() != frozen["endpoint"]
            or settings.llm_model != frozen["model"] or settings.llm_provider != frozen["provider"]
            or runtime_config(settings) != frozen["runtime_config"] or versions() != frozen["library_versions"]):
        raise RuntimeError("Runtime model/provider/endpoint/configuration drift")


def freeze():
    with io.directory_guard(SHARED_LOCK):
        if RESULTS.exists() or TRACKER.exists():
            raise RuntimeError("Phase already allocated; never reopen")
        group = group_state() if GROUP.exists() else new_group()
        historical_state(group)
        allocation_guard(group)
        if (group["status"] != "active" or any(row["phase"] == PHASE or row["status"] != "closed" for row in group["phases"])):
            raise RuntimeError("Group is closed or has an allocated/running phase")
        planned = plan()
        settings, service, endpoint = runtime()
        if any(getattr(settings, key, None) != value for key, value in CONFIG.items()):
            raise RuntimeError("Runtime candidate profile/configuration differs")
        stages = {}
        for sample in planned["samples"]:
            text = service._summary_input((CORPUS / sample["file"]).read_text(encoding="utf-8"))
            parts = service._summary_chunks(text, min(CONFIG["llm_summary_chunk_chars"], CONFIG["llm_max_input_chars"]))
            if io.digest(text) != sample["cleaned_sha256"] or [io.digest(part) for part in parts] != sample["chunks"]:
                raise RuntimeError("Production source preparation differs from offline plan")
            records = [{"stage": "extract", "payload": capture_request(service, part, sample, intermediate_notes=True),
                "max_points": service._summary_budget(len(part)).max_points} for part in parts]
            records.append({"stage": "merge", "payload": capture_request(service, "", sample,
                merge=True, source_chars=sum(map(len, parts))), "source_parts": parts,
                "max_points": service._summary_budget(sum(map(len, parts))).max_points})
            stages[sample["id"]] = records
        assets = []
        for path in asset_paths():
            path = Path(path).resolve()
            if (not path.is_relative_to(PROJECT.resolve()) or path.name.lower().startswith(".env")
                    or "credential" in path.name.lower() or path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".key", ".pem", ".p12"}):
                raise RuntimeError("Unsafe snapshot path")
            assets.append((path.relative_to(PROJECT).as_posix(), path.read_bytes()))
        snapshots = {name: {"file": f"snapshots/{index:04d}.bin", "sha256": io.digest(raw)}
            for index, (name, raw) in enumerate(assets, 1)}
        for required in ("summary_output.py", "summary_json.py", "llm_service.py"):
            if f"backend/app/services/{required}" not in snapshots:
                raise RuntimeError("Required frozen codec/merge source missing")
        RESULTS.mkdir(parents=True)
        io.exclusive(RESULTS / "allocation.json", {"work_id": WORK_ID, "phase": PHASE,
            "allocated_utc": io.now(), "kind": "owned_phase_allocation",
            "disposition": "group_tracker_receipt_or_unregistered_stop"})
        for name, raw in assets:
            path = RESULTS / snapshots[name]["file"]
            path.parent.mkdir(exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        frozen = {"work_id": WORK_ID, "phase": PHASE, "frozen_utc": io.now(), "config": CONFIG,
            "runtime_config": runtime_config(settings), "library_versions": versions(), "snapshots": snapshots,
            "sample_plan": planned["samples"], "stages": stages, "planned_posts": planned["planned_posts"],
            "stage_count_purpose": planned["stage_count_purpose"], "provider": settings.llm_provider,
            "model": settings.llm_model, "endpoint": endpoint, "output_language": "zh-CN",
            "budget_mode": "uncapped", "hard_ceiling": None, "parent_posts": group["reserved_posts"],
            "group_at_freeze": group}
        load_codec(frozen)
        merge_helpers(frozen)
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
        if GROUP.exists():
            durable(GROUP, group)
        else:
            io.exclusive(GROUP, group)
        return {"frozen": True, "network": False, "phase": PHASE, "planned_posts": planned["planned_posts"]}


def snapshot_path(frozen, name):
    record = frozen["snapshots"][name]
    path = (RESULTS / record["file"]).resolve()
    if not path.is_relative_to((RESULTS / "snapshots").resolve()) or io.digest(path.read_bytes()) != record["sha256"]:
        raise RuntimeError("Frozen snapshot path/hash differs")
    return path


def load_codec(frozen):
    from importlib.machinery import SourceFileLoader
    modules = []
    for name in ("summary_output", "summary_json"):
        path = snapshot_path(frozen, f"backend/app/services/{name}.py")
        loader = SourceFileLoader(f"frozen_fidelity_{name}", str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        try:
            loader.exec_module(module)
        except (ImportError, AttributeError, TypeError, SyntaxError):
            raise RuntimeError("Frozen decoder cannot execute with installed Python/library APIs") from None
        modules.append(module)
    codec, normalizer = modules
    codec.decode_summary_json = normalizer.decode_summary_json
    return codec


def merge_helpers(frozen):
    """Execute five frozen pure preparation/merge helpers, no runtime imports."""
    path = snapshot_path(frozen, "backend/app/services/llm_service.py")
    source = ast.parse(path.read_text(encoding="utf-8"))
    names = {"_summary_input", "_summary_chunks", "_section_notes", "_source_context", "_summary_merge_contexts"}
    nodes = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if len(nodes) != len(names) or {node.name for node in nodes} != names or any(node.decorator_list for node in nodes):
        raise RuntimeError("Frozen pure merge helper inventory differs")
    tree = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    ast.fix_missing_locations(tree)
    namespace = {"json": json, "re": re, "settings": SimpleNamespace(**frozen["runtime_config"])}
    exec(compile(tree, str(path), "exec", dont_inherit=True), namespace)
    return SimpleNamespace(**{name: namespace[name] for name in names})


def decoded_response(frozen, ordinal, max_points, codec):
    raw = read(RESULTS / f"response-{ordinal:02d}.json")
    if raw.get("http_status") != 200 or raw.get("model") != frozen["model"] or raw.get("finish_reason") != "stop":
        raise RuntimeError("Raw response model/completion differs")
    value = codec.decode_payload(codec.decode_summary_json(raw.get("content")), strict=False)
    summary, points = value.summary.strip(), [point.strip() for point in value.key_points if point.strip()]
    if not summary or not points or len(points) > max_points:
        raise RuntimeError("Raw business structure differs")
    return {"summary": summary, "key_points": points, "provider": frozen["provider"], "model": frozen["model"]}


def expected_payload(frozen, sample, sample_post, ledger, codec):
    record = frozen["stages"][sample][sample_post - 1]
    payload = json.loads(json.dumps(record["payload"]))
    if record["stage"] == "merge":
        rows = [row for row in ledger["requests"] if row["sample"] == sample]
        if len(rows) != sample_post - 1:
            raise RuntimeError("Merge requires all fresh leaf responses")
        notes = [SimpleNamespace(**decoded_response(frozen, row["ordinal"],
            frozen["stages"][sample][index]["max_points"], codec)) for index, row in enumerate(rows)]
        helpers = merge_helpers(frozen)
        contexts = helpers._summary_merge_contexts(notes, record["source_parts"])
        content = helpers._section_notes(notes, contexts)
        if len(content) > frozen["config"]["llm_max_input_chars"]:
            raise RuntimeError("Frozen merge capacity exceeded; no hidden stages")
        payload["messages"][1]["content"] += content
    return payload


def frozen_sources(frozen):
    samples = frozen["sample_plan"]
    if [sample.get("id") for sample in samples] != list(SAMPLES):
        raise RuntimeError("Frozen source inventory differs")
    helpers = merge_helpers(frozen)
    for sample in samples:
        name = (CORPUS / sample["file"]).resolve().relative_to(PROJECT.resolve()).as_posix()
        raw = snapshot_path(frozen, name).read_bytes()
        text = helpers._summary_input(raw.decode("utf-8"))
        parts = helpers._summary_chunks(text, min(frozen["config"]["llm_summary_chunk_chars"], frozen["config"]["llm_max_input_chars"]))
        stages = frozen["stages"][sample["id"]]
        if (io.digest(raw) != sample["sha256"] or io.digest(text) != sample["cleaned_sha256"]
                or len(text) != sample["cleaned_chars"] or [io.digest(part) for part in parts] != sample["chunks"]
                or sample["expected_posts"] != len(parts) + 1 or len(stages) != len(parts) + 1
                or [stage["stage"] for stage in stages] != ["extract"] * len(parts) + ["merge"]
                or stages[-1]["source_parts"] != parts):
            raise RuntimeError("Frozen source preparation/merge evidence differs")


def frozen_state(*, live):
    frozen, ledger, tracker = (read(RESULTS / "provenance.json"), read(RESULTS / "request-ledger.json"), read(TRACKER))
    for obj in (frozen, ledger, tracker):
        if obj.get("work_id") != WORK_ID or obj.get("phase") != PHASE or obj.get("planned_posts") != frozen["planned_posts"]:
            raise RuntimeError("Frozen phase identity differs")
    if (frozen.get("budget_mode") != "uncapped" or frozen.get("hard_ceiling") is not None
            or tracker.get("budget_mode") != "uncapped" or tracker.get("hard_ceiling") is not None
            or frozen.get("output_language") != "zh-CN"
            or live and (frozen.get("config") != CONFIG or frozen.get("library_versions") != versions())
            or tracker.get("provenance_sha256") != io.digest((RESULTS / "provenance.json").read_bytes())
            or tracker.get("ledger") != str(RESULTS / "request-ledger.json")
            or tracker.get("parent_posts") != frozen.get("parent_posts")):
        raise RuntimeError("Frozen configuration/provenance differs")
    rows = ledger.get("requests")
    sequence = [(sample["id"], index, stage["stage"]) for sample in frozen["sample_plan"]
        for index, stage in enumerate(frozen["stages"][sample["id"]], 1)]
    if (not isinstance(rows, list) or len(sequence) != frozen["planned_posts"]
            or len(rows) > len(sequence) or tracker.get("reserved_posts") != len(rows)
            or any(row.get("ordinal") != index or (row.get("sample"), row.get("sample_post"), row.get("stage")) != sequence[index - 1]
                   for index, row in enumerate(rows, 1))):
        raise RuntimeError("Frozen stage arity/reservations differ")
    for name in frozen["snapshots"]:
        snapshot_path(frozen, name)
        original = (PROJECT / name).resolve()
        if not original.is_relative_to(PROJECT.resolve()) or live and io.digest(original.read_bytes()) != frozen["snapshots"][name]["sha256"]:
            raise RuntimeError("Live asset differs from freeze")
    frozen_sources(frozen)
    if live and (set(frozen["snapshots"]) != {p.resolve().relative_to(PROJECT.resolve()).as_posix() for p in asset_paths()}
                 or sample_plan() != frozen["sample_plan"]):
        raise RuntimeError("Live source/snapshot inventory differs")
    group = group_state(validate_history=live)
    matches = [row for row in group["phases"] if row["phase"] == PHASE]
    if (len(matches) != 1 or matches[0].get("reserved_posts") != len(rows)
            or matches[0].get("planned_posts") != frozen["planned_posts"]
            or matches[0].get("tracker") != str(TRACKER) or matches[0].get("ledger") != tracker["ledger"]
            or matches[0].get("provenance_sha256") != tracker["provenance_sha256"]
            or group["reserved_posts"] < frozen["parent_posts"] + len(rows)
            or group.get("historical_parents") != frozen["group_at_freeze"].get("historical_parents")):
        raise RuntimeError("Group phase ownership/accounting differs")
    return frozen, ledger, tracker


def check():
    with io.directory_guard(SHARED_LOCK):
        frozen, ledger, tracker = frozen_state(live=True)
        if tracker["status"] != "frozen" or ledger["requests"] or group_state()["status"] != "active":
            raise RuntimeError("Offline check requires fresh frozen phase")
        receipt = {"phase": PHASE, "provenance_sha256": tracker["provenance_sha256"], "network": False, "dotenv_read": False}
        path = RESULTS / "offline-check.json"
        if path.exists():
            if read(path) != receipt:
                raise RuntimeError("Offline check receipt differs")
        else:
            io.exclusive(path, receipt)
        return receipt | {"freeze_valid": True}


def run(*, transport=None):
    with io.directory_guard(SHARED_LOCK):
        tracker = read(TRACKER)
        if tracker.get("status") != "frozen" or (RESULTS / "result-index.json").exists():
            raise RuntimeError("One-shot phase already started; never reopen")
        receipt = {"phase": PHASE, "provenance_sha256": tracker["provenance_sha256"], "network": False, "dotenv_read": False}
        if not (RESULTS / "offline-check.json").exists() or read(RESULTS / "offline-check.json") != receipt:
            raise RuntimeError("Persisted offline check required")
        index = {"work_id": WORK_ID, "phase": PHASE, "posts": 0, "stopped_on_error": False, "samples": []}
        pending = None
        tracker["status"] = "running"
        try:
            durable(TRACKER, tracker)
            frozen, ledger, tracker = frozen_state(live=True)
            settings, service, endpoint = runtime()
            match_runtime(settings, service, endpoint, frozen)
            codec = load_codec(frozen)
            manager = nullcontext(transport) if transport is not None else __import__("httpx").Client(
                timeout=float(settings.llm_timeout_seconds), transport=__import__("httpx").HTTPTransport(retries=0))
            with manager as http:
                for sample in frozen["sample_plan"]:
                    before = len(read(RESULTS / "request-ledger.json")["requests"])
                    class Client:
                        def post(self, url, *, headers, json):
                            nonlocal pending
                            current, ledger, tracker = frozen_state(live=True)
                            match_runtime(settings, service, endpoint, current)
                            group = group_state()
                            ordinal, sample_post = len(ledger["requests"]) + 1, len(ledger["requests"]) + 1 - before
                            if (tracker["status"] != "running" or group["status"] != "active"
                                    or sample_post > sample["expected_posts"] or url != endpoint):
                                raise RuntimeError("Unplanned production stage; arity audit refused")
                            expected = expected_payload(current, sample["id"], sample_post, ledger, codec)
                            if json != expected:
                                raise RuntimeError("Actual payload/options/source differ from freeze")
                            path = RESULTS / f"payload-{ordinal:02d}.json"
                            io.exclusive(path, expected)
                            row = {"ordinal": ordinal, "sample": sample["id"], "sample_post": sample_post,
                                "stage": current["stages"][sample["id"]][sample_post - 1]["stage"],
                                "status": "reserved", "reserved_utc": io.now(), "payload_sha256": io.digest(path.read_bytes())}
                            pending = row
                            group["reserved_posts"] += 1
                            phase = next(row for row in group["phases"] if row["phase"] == PHASE)
                            phase.update(status="running", reserved_posts=ordinal)
                            ledger["requests"].append(row)
                            tracker["reserved_posts"] = ordinal
                            try:
                                durable(GROUP, group)
                                durable(RESULTS / "request-ledger.json", ledger)
                                durable(TRACKER, tracker)
                                response = http.post(url, headers=headers, json=json)
                                try:
                                    body = response.json()
                                except ValueError:
                                    body = None
                                safe = io.response_evidence(body)
                                safe.update(http_status=response.status_code, received_utc=io.now(),
                                    model=current["model"] if isinstance(body, dict) and body.get("model") == current["model"] else "mismatch")
                                raw_path = RESULTS / f"response-{ordinal:02d}.json"
                                io.exclusive(raw_path, safe)
                                row.update(status="response", http_status=response.status_code, response_sha256=io.digest(raw_path.read_bytes()))
                                durable(RESULTS / "request-ledger.json", ledger)
                                pending = None
                                if safe["model"] != current["model"]:
                                    raise RuntimeError("Raw provider model drift")
                                return response
                            except BaseException as exc:
                                row.update(status="error", error_type=type(exc).__name__)
                                durable(GROUP, group)
                                durable(RESULTS / "request-ledger.json", ledger)
                                durable(TRACKER, tracker)
                                pending = None
                                raise
                    try:
                        summary = service.summarize_text((CORPUS / sample["file"]).read_text(encoding="utf-8"),
                            title=sample["title"], output_language="zh-CN", client=Client())
                        match_runtime(settings, service, endpoint, frozen)
                        frozen_state(live=True)
                        after = read(RESULTS / "request-ledger.json")
                        if len(after["requests"]) != before + sample["expected_posts"]:
                            raise RuntimeError("Sample production arity differs")
                        public = asdict(summary)
                        if public != decoded_response(frozen, len(after["requests"]), frozen["stages"][sample["id"]][-1]["max_points"], codec):
                            raise RuntimeError("Public result differs from last raw")
                        result = {"sample": sample["id"], "source_sha256": sample["sha256"], "success": True, "result": public}
                    except Exception as exc:
                        index["stopped_on_error"] = True
                        result = {"sample": sample["id"], "source_sha256": sample["sha256"], "success": False,
                            "error_type": getattr(exc, "error_type", type(exc).__name__)}
                    path = RESULTS / f"{sample['id']}.json"
                    io.exclusive(path, result)
                    checksum = io.digest(path.read_bytes())
                    ledger = read(RESULTS / "request-ledger.json")
                    for row in ledger["requests"][before:]:
                        row["result_sha256"] = checksum
                    durable(RESULTS / "request-ledger.json", ledger)
                    index["samples"].append({"sample": sample["id"], "success": result["success"],
                        "result_sha256": checksum, "posts": len(ledger["requests"]) - before})
                    if index["stopped_on_error"]:
                        break
        except BaseException as exc:
            index.update(stopped_on_error=True, phase_error_type=type(exc).__name__)
            raise
        finally:
            close_phase(index, pending)
        return index


def close_phase(index, pending):
    global _closing
    _closing = True
    try:
        ledger, tracker, group = read(RESULTS / "request-ledger.json"), read(TRACKER), group_state()
        if pending is not None:
            if len(ledger["requests"]) < pending["ordinal"]:
                ledger["requests"].append(pending)
            ledger["requests"][pending["ordinal"] - 1].update(status="error", error_type="ReservationPersistenceFailure")
        for row in ledger["requests"]:
            if row["status"] == "reserved":
                row.update(status="error", error_type="InterruptedAttempt")
        count = len(ledger["requests"])
        index.update(posts=count, ended_utc=io.now())
        tracker.update(status="closed", reserved_posts=count)
        phase = next(row for row in group["phases"] if row["phase"] == PHASE)
        phase.update(status="closed", reserved_posts=count)
        group["reserved_posts"] = max(group["reserved_posts"], tracker["parent_posts"] + count)
        durable(RESULTS / "request-ledger.json", ledger)
        io.exclusive(RESULTS / "result-index.json", index)
        receipt = {"work_id": WORK_ID, "phase": PHASE, "status": "closed", "posts": count,
            "work_posts": group["reserved_posts"], "budget_mode": "uncapped", "hard_ceiling": None,
            "ledger_sha256": io.digest((RESULTS / "request-ledger.json").read_bytes()),
            "index_sha256": io.digest((RESULTS / "result-index.json").read_bytes()),
            "provenance_sha256": tracker["provenance_sha256"]}
        io.exclusive(RESULTS / "closed-receipt.json", receipt)
        tracker["closed_receipt_sha256"] = phase["closed_receipt_sha256"] = io.digest((RESULTS / "closed-receipt.json").read_bytes())
        durable(TRACKER, tracker)
        durable(GROUP, group)
    finally:
        _closing = False


def verify_results():
    frozen, ledger, tracker = frozen_state(live=False)
    index, receipt, group = read(RESULTS / "result-index.json"), read(RESULTS / "closed-receipt.json"), group_state(validate_history=False)
    rows, samples = ledger["requests"], index.get("samples", [])
    phase = next(row for row in group["phases"] if row["phase"] == PHASE)
    checksum = io.digest((RESULTS / "closed-receipt.json").read_bytes())
    if (tracker["status"] != "closed" or phase["status"] != "closed"
            or receipt.get("work_id") != WORK_ID or receipt.get("phase") != PHASE or receipt.get("status") != "closed"
            or receipt.get("budget_mode") != "uncapped" or receipt.get("hard_ceiling") is not None
            or receipt.get("posts") != len(rows) or receipt.get("work_posts") > group["reserved_posts"]
            or receipt.get("work_posts") < frozen["parent_posts"] + len(rows)
            or tracker.get("closed_receipt_sha256") != checksum or phase.get("closed_receipt_sha256") != checksum
            or receipt.get("ledger_sha256") != io.digest((RESULTS / "request-ledger.json").read_bytes())
            or receipt.get("index_sha256") != io.digest((RESULTS / "result-index.json").read_bytes())
            or receipt.get("provenance_sha256") != tracker["provenance_sha256"]
            or index.get("work_id") != WORK_ID or index.get("phase") != PHASE or index.get("posts") != len(rows)
            or type(index.get("stopped_on_error")) is not bool
            or [row.get("sample") for row in samples] != list(SAMPLES[:len(samples)])):
        raise RuntimeError("Closed phase receipt/index differs")
    stopped = index["stopped_on_error"]
    if not stopped and (len(rows) != frozen["planned_posts"] or len(samples) != len(SAMPLES) or any(row.get("success") is not True for row in samples)):
        raise RuntimeError("Successful phase requires complete frozen sources/stages")
    if stopped and not (index.get("phase_error_type") or any(row.get("success") is False for row in samples)):
        raise RuntimeError("Stopped phase lacks error disposition")
    codec = load_codec(frozen)
    for index, row in enumerate(rows):
        if row.get("status") not in {"response", "error"}:
            raise RuntimeError("Unclosed attempt")
        path = RESULTS / f"payload-{row['ordinal']:02d}.json"
        if io.digest(path.read_bytes()) != row.get("payload_sha256") or read(path) != expected_payload(frozen, row["sample"], row["sample_post"], {"requests": rows[:index]}, codec):
            raise RuntimeError("Payload hash/options/source differ")
        if row.get("response_sha256") and io.digest((RESULTS / f"response-{row['ordinal']:02d}.json").read_bytes()) != row["response_sha256"]:
            raise RuntimeError("Raw response hash differs")
    for item in samples:
        path = RESULTS / f"{item['sample']}.json"
        result = read(path)
        source = next(sample for sample in frozen["sample_plan"] if sample["id"] == item["sample"])
        matching = [row for row in rows if row["sample"] == item["sample"]]
        name = (CORPUS / source["file"]).relative_to(PROJECT).as_posix()
        if (io.digest(path.read_bytes()) != item.get("result_sha256") or result.get("sample") != item["sample"]
                or result.get("source_sha256") != source["sha256"] or frozen["snapshots"].get(name, {}).get("sha256") != source["sha256"]
                or result.get("success") != item.get("success") or item.get("posts") != len(matching)
                or any(row.get("result_sha256") != item["result_sha256"] for row in matching)):
            raise RuntimeError("Result source/hash/attempt ownership differs")
        if item["success"]:
            if len(matching) != source["expected_posts"] or any(row["status"] != "response" for row in matching):
                raise RuntimeError("Successful sample lacks stages")
            for row in matching:
                decoded_response(frozen, row["ordinal"], frozen["stages"][item["sample"]][row["sample_post"] - 1]["max_points"], codec)
            if result.get("result") != decoded_response(frozen, matching[-1]["ordinal"], frozen["stages"][item["sample"]][-1]["max_points"], codec):
                raise RuntimeError("Final public result differs from last raw")
    return {"evidence_hashes_verified": True, "phase_closed": True, "posts": len(rows), "work_posts": receipt["work_posts"],
        "budget_mode": "uncapped", "hard_ceiling": None, "stopped_on_error": stopped,
        "semantic_quality_verified": False, "provider": frozen["provider"], "model": frozen["model"]}


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
