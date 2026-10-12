"""Finite capacity continuation: 3 POSTs, cumulative 10 -> at most 13.

Two accepted paid leaves are reused verbatim through the production merge
request. Private adapters preserve shared locking, preallocation and closing;
there is no retry, SDK, telemetry, paid fallback or reasoning persistence.
Plan/check/verify are offline; only root may run. Historical 51 POSTs and the
closed 10 POST parent remain immutable and are never fresh budget capacity.
Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only through ytdlp_service; scene remains read-only. Corpus and derived
outputs retain their existing MIT authors and CC BY-NC-SA 4.0 attribution.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
RESULTS = REPORT / "results"
PARENT_REPORT = REPORT.parent / "2026-10-11-summary-content-local-repair"
ADAPTER = PARENT_REPORT / "scripts/evaluate.py"
spec = importlib.util.spec_from_file_location("capacity_local_repair_engine", ADAPTER)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
engine = prior.prior.base
PARENT_GROUP = prior.GROUP
PARENT_TRACKER = prior.TRACKER
PARENT_PHASE = prior.PHASE
HELPER, CORPUS, SHARED_LOCK = prior.HELPER, prior.CORPUS, prior.SHARED_LOCK
GROUP = PARENT_GROUP.with_name("budget-continuation-capacity.json")
TRACKER = GROUP.with_name("phase-3.json")
WORK_ID, PHASE = prior.WORK_ID, "summary-thinking-capacity-3"
MAX_POSTS, HARD_CEILING, SAMPLES = 3, 13, prior.SAMPLES
CONFIG = prior.CONFIG | {"llm_summary_max_output_tokens": 16384,
    "llm_summary_output_token_ceiling": 24576}
PARENT_CONFIG = dict(prior.CONFIG)
io, os = prior.io, prior.os
read, versions, runtime_config = prior.read, prior.versions, prior.runtime_config
_original = {name: getattr(prior, name) for name in (
    "base_context", "inventory_paths", "group_state", "runtime", "check", "run",
    "verify_results", "durable", "close_phase")}
_base_samples, _base_expected = engine.sample_plan, engine.expected_payload
_closing = False


def base_context():
    for name in ("PROJECT", "REPORT", "RESULTS", "CORPUS", "GROUP", "TRACKER",
                 "SHARED_LOCK", "WORK_ID", "PHASE", "MAX_POSTS", "HARD_CEILING",
                 "SAMPLES", "CONFIG", "HELPER", "runtime", "versions", "asset_paths",
                 "group_state", "durable", "close_phase"):
        setattr(prior, name, globals()[name])
    prior.base_context = base_context
    _original["base_context"]()
    engine.sample_plan = sample_plan
    engine.expected_payload = expected_payload


def _snapshot_module(frozen, filename, name, get):
    record = frozen["snapshots"][filename]
    path = (PARENT_REPORT / "results" / record["file"]).resolve()
    if (not path.is_relative_to((PARENT_REPORT / "results/snapshots").resolve())
            or io.digest(get(path)) != record["sha256"]):
        raise RuntimeError("Parent frozen codec snapshot differs")
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    # Use exactly the bytes whose hash was checked, not a second mutable read.
    exec(compile(get(path), str(path), "exec", dont_inherit=True), module.__dict__)
    return module


def parent_state(group=None):
    """Adapt the established saved-leaf receipt/source/typed-codec checks."""
    cache = {}
    def get(path):
        path = Path(path).resolve()
        if not path.is_relative_to(PROJECT.resolve()):
            raise RuntimeError("Parent evidence path is outside project")
        if path not in cache:
            cache[path] = path.read_bytes()
        return cache[path]
    def data(path):
        return json.loads(get(path))
    try:
        group = read(GROUP) if group is None else group
        binding = group.get("continuation_parent", {})
        parent_bytes = get(PARENT_GROUP)
        parent = json.loads(parent_bytes)
        if (binding.get("path") != str(PARENT_GROUP) or binding.get("parent_posts") != 10
                or binding.get("sha256") != io.digest(parent_bytes)
                or group.get("parent_posts") != 10
                or group.get("budget_adjustment") != {"from": 10, "to": 13}
                or group.get("reserved_posts", -1) < 10
                or parent.get("work_id") != WORK_ID or parent.get("status") != "closed"
                or parent.get("hard_ceiling") != 10 or parent.get("reserved_posts") != 10
                or len(parent.get("phases", [])) != 2
                or group.get("phases", [])[:2] != parent["phases"]
                or [p.get("phase") for p in parent["phases"]] != ["summary-thinking-single-1", PARENT_PHASE]
                or any(p.get("status") != "closed" or p.get("reserved_posts") != 5 for p in parent["phases"])
                or group.get("historical_parents") != parent.get("historical_parents")):
            raise RuntimeError("Continuation parent/count/phase prefix differs")
        phase = parent["phases"][-1]
        paths = {name: PARENT_REPORT / "results" / name for name in (
            "closed-receipt.json", "provenance.json", "request-ledger.json", "result-index.json")}
        receipt, frozen, ledger, index = [data(paths[name]) for name in paths]
        tracker = data(PARENT_TRACKER)
        for obj in (receipt, frozen, ledger, index, tracker):
            if obj.get("work_id") != WORK_ID or obj.get("phase") != PARENT_PHASE:
                raise RuntimeError("Parent phase identity differs")
        receipt_hash, provenance_hash = io.digest(get(paths["closed-receipt.json"])), io.digest(get(paths["provenance.json"]))
        if (phase.get("tracker") != str(PARENT_TRACKER) or phase.get("ledger") != str(paths["request-ledger.json"])
                or phase.get("maximum_posts") != 5 or tracker.get("maximum_posts") != 5
                or tracker.get("status") != "closed" or tracker.get("reserved_posts") != 5
                or tracker.get("hard_ceiling") != 10 or tracker.get("parent_posts") != 5
                or tracker.get("ledger") != str(paths["request-ledger.json"])
                or any(obj.get("closed_receipt_sha256") != receipt_hash for obj in (phase, tracker))
                or any(obj.get("provenance_sha256") != provenance_hash for obj in (phase, tracker, receipt))
                or receipt.get("status") != "closed" or receipt.get("posts") != 5
                or receipt.get("work_posts") != 10 or receipt.get("hard_ceiling") != 10
                or receipt.get("ledger_sha256") != io.digest(get(paths["request-ledger.json"]))
                or receipt.get("index_sha256") != io.digest(get(paths["result-index.json"]))
                or frozen.get("config") != PARENT_CONFIG or frozen.get("parent_posts") != 5
                or frozen.get("hard_ceiling") != 10 or frozen.get("maximum_posts") != 5
                or index.get("posts") != 5 or len(ledger.get("requests", [])) != 5):
            raise RuntimeError("Parent closed receipt/ledger/provenance differs")
        expected = [("zh-short", 1, "extract"), ("en-medium", 1, "extract"),
            ("en-long", 1, "extract"), ("en-long", 2, "extract"), ("en-long", 3, "merge")]
        for i, row in enumerate(ledger["requests"], 1):
            if (row.get("ordinal") != i or (row.get("sample"), row.get("sample_post"), row.get("stage")) != expected[i - 1]
                    or row.get("status") != "response" or row.get("http_status") != 200):
                raise RuntimeError("Parent accepted request ordering differs")
        # Current exact corpus preparation must agree with the paid freeze.
        samples = _base_samples()
        if frozen.get("sample_plan") != samples:
            raise RuntimeError("Parent exact source/chunk binding differs")
        for sample in samples:
            for key, checksum in (("file", "sha256"), ("raw_path", "raw_sha256")):
                path = (CORPUS / sample[key]).resolve()
                if frozen["snapshots"].get(path.relative_to(PROJECT).as_posix(), {}).get("sha256") != sample[checksum]:
                    raise RuntimeError("Parent frozen source/raw hash differs")
        schema = _snapshot_module(frozen, "backend/app/services/summary_output.py", "paid_leaf_schema", get)
        norm = _snapshot_module(frozen, "backend/app/services/summary_json.py", "paid_leaf_json", get)
        source_text = engine.cleaned(get(CORPUS / samples[-1]["file"]).decode("utf-8"))
        source_parts = engine.chunks(source_text, min(CONFIG["llm_summary_chunk_chars"], CONFIG["llm_max_input_chars"]))
        stages = frozen["stages"]["en-long"]
        if (len(source_parts) != 2 or len(stages) != 3
                or [s.get("stage") for s in stages] != ["extract", "extract", "merge"]):
            raise RuntimeError("Parent long stage shape differs")
        notes = []
        for section, ordinal in enumerate((3, 4), 1):
            row = ledger["requests"][ordinal - 1]
            raw_path, payload_path = (PARENT_REPORT / "results" / f"{kind}-{ordinal:02d}.json" for kind in ("response", "payload"))
            raw, payload = data(raw_path), data(payload_path)
            if (io.digest(get(raw_path)) != row.get("response_sha256")
                    or io.digest(get(payload_path)) != row.get("payload_sha256")
                    or payload != stages[section - 1]["payload"]
                    or not payload["messages"][1]["content"].endswith("Transcript:\n" + source_parts[section - 1])
                    or raw.get("model") != frozen["model"] or raw.get("http_status") != 200
                    or raw.get("finish_reason") != "stop" or not isinstance(raw.get("content"), str)):
                raise RuntimeError("Parent saved leaf model/raw/payload differs")
            value = schema.decode_payload(norm.decode_summary_json(raw["content"]), strict=False)
            summary, points = value.summary.strip(), [p.strip() for p in value.key_points if p.strip()]
            if not summary or not points or len(points) > stages[section - 1]["max_points"]:
                raise RuntimeError("Parent saved leaf finite structure differs")
            note = {"section": section, "summary": summary, "key_points": points}
            context = stages[-1]["source_contexts"][section - 1]
            if context:
                note["source_context"] = context
            notes.append(note)
        wire_path = PARENT_REPORT / "results/payload-05.json"
        wire = data(wire_path)
        if io.digest(get(wire_path)) != ledger["requests"][-1].get("payload_sha256"):
            raise RuntimeError("Parent merge wire hash differs")
        template = stages[-1]["payload"]
        prefix, content = template["messages"][1]["content"], wire["messages"][1]["content"]
        rebound = json.loads(json.dumps(wire))
        rebound["messages"][1]["content"] = prefix
        if not content.startswith(prefix) or rebound != template:
            raise RuntimeError("Parent merge payload prefix/options differs")
        exact_notes = content[len(prefix):]
        if json.loads(exact_notes) != notes or exact_notes != json.dumps(notes, ensure_ascii=False):
            raise RuntimeError("Parent paid notes/raw/context differs")
        if len(exact_notes) > CONFIG["llm_max_input_chars"]:
            raise RuntimeError("Parent notes exceed finite merge capacity")
        return {"parent_sha256": io.digest(parent_bytes), "parent_phases": parent["phases"],
            "samples": samples, "notes": exact_notes, "source_chars": samples[-1]["cleaned_chars"],
            "reused_parent_posts": [3, 4]}
    except (KeyError, IndexError, TypeError, ValueError, OSError) as exc:
        raise RuntimeError("Parent evidence is unreadable or invalid") from exc


def group_state():
    base_context()
    group = _original["group_state"]()
    if not _closing:
        parent = parent_state(group)
        frozen_path = RESULTS / "provenance.json"
        if frozen_path.exists():
            frozen = read(frozen_path)
            if (frozen.get("continuation_parent") != group.get("continuation_parent")
                    or frozen.get("reused_notes") != parent["notes"]):
                raise RuntimeError("Continuation parent/notes differ from freeze")
    return group


def sample_plan():
    return [sample | {"expected_posts": 1,
        "source_input_mode": "reused_leaf_notes" if sample["id"] == "en-long" else "transcript"}
        for sample in _base_samples()]


def plan():
    base_context()
    group = group_state()
    return {"work_id": WORK_ID, "phase": PHASE, "network": False, "dotenv_read": False,
        "maximum_posts": MAX_POSTS, "normal_posts": MAX_POSTS, "hard_ceiling": HARD_CEILING,
        "work_reserved_posts": group["reserved_posts"], "config": CONFIG, "samples": sample_plan(),
        "format_posts_ceiling": 0, "semantic_posts_ceiling": 0, "reused_parent_posts": [3, 4],
        "historical_semantic_quality_verified": False} | prior.prior.historical_state(group)


class ServiceProxy:
    """Delegate short/medium; invoke the sole production merge for the exact long source."""
    def __init__(self, service):
        self._service = service

    def __getattr__(self, name):
        return getattr(self._service, name)

    def summarize_text(self, transcript, *, title, output_language, client):
        frozen = read(RESULTS / "provenance.json")
        long = frozen["sample_plan"][-1]
        if title == long["title"]:
            if io.digest(self._service._summary_input(transcript)) != long["cleaned_sha256"]:
                raise RuntimeError("Reused merge original source differs")
            return self._service._summary_request(frozen["reused_notes"], title=title,
                output_language=output_language, merge=True, source_chars=long["cleaned_chars"], client=client)
        return self._service.summarize_text(transcript, title=title, output_language=output_language, client=client)


def runtime():
    base_context()
    settings, service, endpoint = _original["runtime"]()
    return settings, ServiceProxy(service), endpoint


def expected_payload(frozen, sample, sample_post, ledger, codec):
    record = frozen["stages"][sample][sample_post - 1]
    if record["stage"] == "merge_reused":
        if sample != "en-long" or sample_post != 1:
            raise RuntimeError("Unplanned reused merge stage")
        return json.loads(json.dumps(record["payload"]))
    return _base_expected(frozen, sample, sample_post, ledger, codec)


def parent_asset_paths():
    paths = [PARENT_GROUP, PARENT_TRACKER,
        *(PARENT_REPORT / "results" / name for name in (
            "provenance.json", "request-ledger.json", "closed-receipt.json", "result-index.json",
            "response-03.json", "response-04.json", "payload-03.json", "payload-04.json", "payload-05.json"))]
    frozen = read(PARENT_REPORT / "results/provenance.json")
    paths.extend(PARENT_REPORT / "results" / frozen["snapshots"][name]["file"] for name in (
        "backend/app/services/summary_output.py", "backend/app/services/summary_json.py"))
    return paths


def inventory_paths():
    base_context()
    return sorted(set(_original["inventory_paths"]() + parent_asset_paths() + [
        Path(__file__), ADAPTER, PROJECT / "backend/tests/test_summary_capacity_evaluation.py",
        PARENT_REPORT / "review-criteria.md",
        PROJECT / "backend/tests/test_summary_json.py",
        PROJECT / "backend/tests/test_summary_json_integration.py",
        PROJECT / "backend/tests/test_llm_service.py",
    ]))


asset_paths = inventory_paths


def durable(path, value):
    base_context()
    return _original["durable"](path, value)


def close_phase(index, pending):
    global _closing
    base_context()
    _closing = True
    try:
        return _original["close_phase"](index, pending)
    finally:
        _closing = False


def freeze():
    """Reuse source-first freeze publication; only the three-stage capture differs."""
    base_context()
    with io.directory_guard(SHARED_LOCK):
        if RESULTS.exists() or TRACKER.exists():
            raise RuntimeError("Phase already allocated; never reopen")
        group = group_state()
        if group["status"] != "active" or any(p["phase"] == PHASE for p in group["phases"]):
            raise RuntimeError("Work group closed or phase already allocated")
        if group["reserved_posts"] + MAX_POSTS > HARD_CEILING:
            raise RuntimeError("Insufficient work group headroom; refuse freeze")
        planned, parent = plan(), parent_state(group)
        settings, service, endpoint = runtime()
        stages = {}
        for sample in planned["samples"]:
            text = service._summary_input((CORPUS / sample["file"]).read_text(encoding="utf-8"))
            parts = service._summary_chunks(text, CONFIG["llm_summary_chunk_chars"])
            if io.digest(text) != sample["cleaned_sha256"] or [io.digest(p) for p in parts] != sample["chunks"]:
                raise RuntimeError("Product caption preparation differs from offline plan")
            merge = sample["id"] == "en-long"
            payload = engine.capture_request(service, parent["notes"] if merge else parts[0], sample,
                merge=merge, source_chars=sample["cleaned_chars"] if merge else None)
            stages[sample["id"]] = [{"stage": "merge_reused" if merge else "extract", "payload": payload,
                "max_points": service._summary_budget(sample["cleaned_chars"]).max_points}]
        assets = []
        for path in asset_paths():
            if (not path.resolve().is_relative_to(PROJECT.resolve()) or path.name.lower().startswith(".env")
                    or "credential" in path.name.lower()
                    or path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".key", ".pem", ".p12"}):
                raise RuntimeError("Unsafe frozen asset path")
            assets.append((path.relative_to(PROJECT).as_posix(), path.read_bytes()))
        snapshots = {name: {"file": f"snapshots/{i:04d}.bin", "sha256": io.digest(raw)}
            for i, (name, raw) in enumerate(assets, 1)}
        RESULTS.mkdir(parents=True)
        for name, raw in assets:
            path = RESULTS / snapshots[name]["file"]
            path.parent.mkdir(exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        frozen = {"work_id": WORK_ID, "phase": PHASE, "frozen_utc": io.now(),
            "config": CONFIG, "runtime_config": runtime_config(settings), "library_versions": versions(),
            "snapshots": snapshots, "sample_plan": planned["samples"], "stages": stages,
            "model": settings.llm_model, "provider": settings.llm_provider, "endpoint": endpoint,
            "output_language": "zh-CN", "maximum_posts": MAX_POSTS, "hard_ceiling": HARD_CEILING,
            "parent_posts": group["reserved_posts"], "group_at_freeze": group,
            "continuation_parent": group["continuation_parent"], "reused_notes": parent["notes"],
            "reused_parent_posts": [3, 4], "parent_semantic_quality_verified": False}
        io.exclusive(RESULTS / "provenance.json", frozen)
        io.exclusive(RESULTS / "request-ledger.json", {"work_id": WORK_ID, "phase": PHASE,
            "maximum_posts": MAX_POSTS, "requests": []})
        tracker = {"work_id": WORK_ID, "phase": PHASE, "status": "frozen", "reserved_posts": 0,
            "maximum_posts": MAX_POSTS, "hard_ceiling": HARD_CEILING, "parent_posts": group["reserved_posts"],
            "ledger": str(RESULTS / "request-ledger.json"),
            "provenance_sha256": io.digest((RESULTS / "provenance.json").read_bytes())}
        io.exclusive(TRACKER, tracker)
        group["phases"].append({"phase": PHASE, "status": "frozen", "maximum_posts": MAX_POSTS,
            "reserved_posts": 0, "tracker": str(TRACKER), "ledger": tracker["ledger"],
            "provenance_sha256": tracker["provenance_sha256"]})
        durable(GROUP, group)
        return {"frozen": True, "network": False, "phase": PHASE, "maximum_posts": MAX_POSTS}


def check():
    base_context()
    return _original["check"]()


def run(*, transport=None):
    base_context()
    return _original["run"](transport=transport)


def verify_results():
    base_context()
    return _original["verify_results"]()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group()
    for name in ("freeze", "check", "run", "verify"):
        flags.add_argument(f"--{name}", action="store_true")
    args = parser.parse_args(argv)
    action = freeze if args.freeze else check if args.check else run if args.run else verify_results if args.verify else plan
    print(json.dumps(action(), ensure_ascii=False))


if __name__ == "__main__":
    main()
