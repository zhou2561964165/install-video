"""Finite Responses/schema Pro contrast: immutable parent 11 + exactly <=6 POST.

Root alone freezes/runs. Plan/check/verify never load dotenv. No repair, retry,
fallback, capability probe or semantic claim. Engineering: skills first; narrow
interfaces; UI three-layer tokens and read-only scene; yt-dlp only its service.
Source and derivative artifacts retain their CC BY-NC-SA 4.0 attribution.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from urllib.parse import urlsplit

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
RESULTS = REPORT / "results"
PARENT2_REPORT = REPORT.parent / "2026-10-10-staged-summary-live"
PARENT2_RUNNER = PARENT2_REPORT / "scripts/evaluate.py"
PARENT2_RESULTS = PARENT2_REPORT / "results"
PARENT2_GROUP = PROJECT / ".planning/2026-10-10-source-first-summary-acceptance/budget-continuation-staged.json"
PARENT2_TRACKER = PARENT2_GROUP.with_name("phase-2.json")
GROUP = PARENT2_GROUP.with_name("budget-continuation-schema-pro.json")
TRACKER = PARENT2_GROUP.with_name("phase-3.json")
SHARED_LOCK = REPORT.parent / "2026-10-05-grounded-summary/results/.http-session-lock"
WORK_ID, PHASE = "source-first-summary-20261010", "source-first-summary-schema-pro-3"
PARENT_POSTS, MAX_POSTS, HARD_CEILING = 11, 6, 17
SAMPLES = ("zh-short", "en-medium", "en-long")


def load_stage(name):
    spec = importlib.util.spec_from_file_location(name, PARENT2_RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Separate instances keep the parent's 5/7/12 and original config intact.
prior, stage = load_stage("schema_pro_parent"), load_stage("schema_pro_caller")
io = prior.io
CORPUS = prior.CORPUS
CONFIG = dict(prior.CONFIG) | {"llm_model": "deepseek-v4-pro", "llm_summary_response_format": "json_schema",
    "llm_summary_thinking_mode": "disabled", "llm_summary_format_retries": 0,
    "llm_summary_semantic_retries": 0, "llm_summary_max_extra_calls": 0}
codec_from_bytes, versions = prior.codec_from_bytes, prior.versions


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def base_context():
    for name in ("PROJECT", "RESULTS", "GROUP", "TRACKER", "WORK_ID", "PHASE", "MAX_POSTS", "HARD_CEILING"):
        setattr(stage.base, name, globals()[name])


def durable(path, value):
    base_context()
    return stage.base.durable(path, value)


def parent_assets():
    paths = [PARENT2_RUNNER, PARENT2_GROUP, PARENT2_TRACKER, prior.PARENT_RUNNER,
             prior.PARENT_GROUP, prior.PARENT_TRACKER]
    for directory in (PARENT2_RESULTS, prior.PARENT_RESULTS, CORPUS):
        paths.extend(p for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    return sorted(set(paths))


def parent_state(*, reader=None):
    get = reader or (lambda path: path.read_bytes())
    data = lambda path: json.loads(get(path).decode("utf-8"))
    first = prior.parent_state(reader=get)
    group, tracker = data(PARENT2_GROUP), data(PARENT2_TRACKER)
    receipt, frozen, ledger, index = [data(PARENT2_RESULTS / name) for name in (
        "closed-receipt.json", "provenance.json", "request-ledger.json", "result-index.json")]
    if (group.get("work_id") != WORK_ID or group.get("status") != "closed" or group.get("hard_ceiling") != 12
            or group.get("reserved_posts") != 11 or len(group.get("phases", [])) != 2
            or group.get("parent_snapshot") != str(prior.PARENT_GROUP) or group.get("parent_posts") != 5
            or group.get("parent_sha256") != first["parent_sha256"] or group.get("budget_adjustment") != {"from": 10, "to": 12}
            or group["phases"][0] != first["parent_phase"]):
        raise RuntimeError("Parent two closed phases / 11 of 12 budget differs")
    phase = group["phases"][1]
    if any(obj.get("work_id") != WORK_ID or obj.get("phase") != prior.PHASE for obj in (tracker, receipt, frozen, ledger, index)):
        raise RuntimeError("Parent staged identity differs")
    provenance_sha, receipt_sha = io.digest(get(PARENT2_RESULTS / "provenance.json")), io.digest(get(PARENT2_RESULTS / "closed-receipt.json"))
    if (phase.get("status") != "closed" or phase.get("reserved_posts") != 6 or phase.get("maximum_posts") != 7
            or phase.get("ledger") != str(PARENT2_RESULTS / "request-ledger.json") or phase.get("tracker") != str(PARENT2_TRACKER)
            or tracker.get("status") != "closed" or tracker.get("reserved_posts") != 6 or tracker.get("maximum_posts") != 7
            or tracker.get("ledger") != phase["ledger"] or tracker.get("hard_ceiling") != 12 or tracker.get("parent_posts") != 5
            or receipt.get("status") != "closed" or receipt.get("posts") != 6 or receipt.get("work_posts") != 11
            or receipt.get("hard_ceiling") != 12 or frozen.get("config") != prior.CONFIG
            or frozen.get("maximum_posts") != 7 or frozen.get("parent_posts") != 5 or frozen.get("hard_ceiling") != 12
            or any(obj.get("provenance_sha256") != provenance_sha for obj in (phase, tracker, receipt))
            or any(obj.get("closed_receipt_sha256") != receipt_sha for obj in (phase, tracker))
            or receipt.get("ledger_sha256") != io.digest(get(PARENT2_RESULTS / "request-ledger.json"))
            or receipt.get("index_sha256") != io.digest(get(PARENT2_RESULTS / "result-index.json"))
            or frozen.get("parent_sha256") != first["parent_sha256"] or frozen.get("parent_phase") != first["parent_phase"]
            or frozen.get("sample_plan") != first["samples"] or frozen.get("reused_sections") != first["reused_sections"]
            or index.get("posts") != 6 or len(ledger.get("requests", [])) != 6):
        raise RuntimeError("Parent staged closed receipt/provenance/ledger differs")
    for name, record in frozen["snapshots"].items():
        path = (PARENT2_RESULTS / record["file"]).resolve()
        if (not path.is_relative_to((PARENT2_RESULTS / "snapshots").resolve())
                or not (PROJECT / name).resolve().is_relative_to(PROJECT.resolve())
                or io.digest(get(path)) != record["sha256"]):
            raise RuntimeError("Parent staged snapshot differs")
    runner_name = PARENT2_RUNNER.relative_to(PROJECT).as_posix()
    if frozen["snapshots"].get(runner_name, {}).get("sha256") != io.digest(get(PARENT2_RUNNER)):
        raise RuntimeError("Parent immutable staged runner differs")
    expected = [("zh-short", "points"), ("zh-short", "overview"), ("en-medium", "points"),
                ("en-medium", "overview"), ("en-long", "points"), ("en-long", "points_format")]
    for ordinal, row in enumerate(ledger["requests"], 1):
        if (row.get("ordinal") != ordinal or (row.get("sample"), row.get("stage")) != expected[ordinal - 1]
                or row.get("status") != "response" or row.get("http_status") != 200):
            raise RuntimeError("Parent staged historical attempts differ")
        for kind in ("payload", "response"):
            if io.digest(get(PARENT2_RESULTS / f"{kind}-{ordinal:02d}.json")) != row.get(f"{kind}_sha256"):
                raise RuntimeError("Parent staged raw/payload binding differs")
    for item in index.get("samples", []):
        if (io.digest(get(PARENT2_RESULTS / f"{item['sample']}.json")) != item.get("result_sha256")
                or io.digest(get(PARENT2_RESULTS / f"trace-{item['sample']}.json")) != item.get("trace_sha256")):
            raise RuntimeError("Parent staged result/trace binding differs")
    return first | {"parent_sha256": io.digest(get(PARENT2_GROUP)), "parent_phases": group["phases"]}


def group_state(parent=None):
    base_context()
    group = stage.base.group_state()
    if (group.get("parent_snapshot") != str(PARENT2_GROUP) or group.get("parent_posts") != 11
            or group.get("budget_adjustment") != {"from": 12, "to": 17}
            or parent is not None and (group.get("parent_sha256") != parent["parent_sha256"]
                or group["phases"][:2] != parent["parent_phases"])):
        raise RuntimeError("Schema Pro continuation parent/budget differs")
    return group


def plan():
    parent = parent_state()
    group = group_state(parent)
    return {"work_id": WORK_ID, "phase": PHASE, "network": False, "dotenv_read": False,
        "parent_posts": 11, "maximum_posts": 6, "normal_posts": 6, "format_posts_ceiling": 0,
        "hard_ceiling": 17, "work_reserved_posts": group["reserved_posts"], "config": CONFIG,
        "samples": parent["samples"], "parent_semantic_quality_verified": False}


def asset_paths():
    paths = parent_assets() + [Path(__file__), prior.base.HELPER, PROJECT / "pyproject.toml", PROJECT / "uv.lock",
        PROJECT / "backend/app/config.py", PROJECT / "backend/app/services/llm_service.py",
        REPORT / "review-criteria.md", PROJECT / "docs/superpowers/specs/2026-10-10-schema-pro-summary-design.md"]
    paths.extend((PROJECT / "backend/app/services").glob("summary_*.py"))
    return sorted(set(paths))


def runtime():
    sys.path.insert(0, str(PROJECT / "backend"))
    io.load_dotenv(PROJECT / "backend/.env", override=False)
    from app.config import settings
    from app.services import llm_service as service
    for key, value in CONFIG.items():
        setattr(settings, key, value)
    endpoint = service._endpoint(responses=True)
    parts = urlsplit(endpoint)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or not parts.path.endswith("/responses")):
        raise RuntimeError("Responses endpoint must be HTTPS without credentials/query metadata")
    return settings, service, endpoint


def match_runtime(settings, service, endpoint, frozen):
    if (endpoint != frozen["endpoint"] or service._endpoint(responses=True) != frozen["endpoint"]
            or settings.llm_model != frozen["model"] or settings.llm_provider != frozen["provider"]
            or any(getattr(settings, key) != value for key, value in CONFIG.items())
            or prior.base.runtime_config(settings) != frozen["runtime_config"] or versions() != frozen["library_versions"]):
        raise RuntimeError("Responses runtime endpoint/provider/model/config/library drift")


def capture_payload(service, messages, budget, role, endpoint):
    options = service._summary_options(budget)
    options["text"]["format"].update(name="video_summary_" + role,
        schema=service.stage_schema(role, budget.max_points, budget.point_char_limit))
    captured = {}
    class Captured(Exception):
        pass
    class Client:
        def post(self, url, *, headers, json):
            captured.update(url=url, payload=json)
            raise Captured
    try:
        service._complete(messages, client=Client(), max_tokens=budget.max_tokens, summary_options=options, summary_budget=budget)
    except Captured:
        pass
    if captured.get("url") != endpoint or "input" not in captured.get("payload", {}) or "messages" in captured["payload"]:
        raise RuntimeError("Product Responses construction differs")
    return captured["payload"]


def freeze():
    with io.directory_guard(SHARED_LOCK):
        if RESULTS.exists() or TRACKER.exists():
            raise RuntimeError("Schema Pro phase already allocated; never reopen")
        parent = parent_state()
        group = group_state(parent)
        if group["status"] != "active" or group["reserved_posts"] != 11 or len(group["phases"]) != 2:
            raise RuntimeError("Continuation must start from closed parent 11")
        settings, service, endpoint = runtime()
        if any(getattr(settings, k) != v for k, v in CONFIG.items()):
            raise RuntimeError("Runtime does not apply explicit Schema Pro config")
        templates = {}
        for sample in parent["samples"]:
            source = (CORPUS / sample["file"]).read_text(encoding="utf-8")
            prepared = service._summary_chunks(service._summary_input(source), min(CONFIG["llm_summary_chunk_chars"], CONFIG["llm_max_input_chars"]))
            if prepared != parent["source_parts"][sample["id"]]:
                raise RuntimeError("Production source parts differ from bound original")
            budget = service._summary_budget(len(source))
            reused = parent["reused_sections"] if sample["id"] == "en-long" else []
            notes = prior.notes_for(reused) if reused else ""
            if reused and service._section_notes([service.LLMSummaryResult(s["summary"], s["key_points"], s["provider"], s["model"]) for s in reused]) != notes:
                raise RuntimeError("Production notes differ from paid leaf raw")
            roles = {}
            for role in ("points", "overview"):
                messages = service._staged_messages(role, transcript=source, notes=notes, key_points=[], title=sample["title"], output_language="zh-CN", budget=budget)
                if len(messages[-1]["content"]) > CONFIG["llm_max_input_chars"] or role == "overview" and not messages[-1]["content"].endswith("[]"):
                    raise RuntimeError("Role input capacity/points slot differs")
                roles[role] = {"payload": capture_payload(service, messages, budget, role, endpoint),
                    "max_points": budget.max_points, "point_char_limit": budget.point_char_limit}
            templates[sample["id"]] = roles
        assets = []
        for path in asset_paths():
            if (not path.resolve().is_relative_to(PROJECT.resolve()) or path.name.lower().startswith(".env")
                    or "credential" in path.name.lower() or path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".key", ".pem", ".p12"}):
                raise RuntimeError("Unsafe frozen asset")
            assets.append((path.relative_to(PROJECT).as_posix(), path.read_bytes()))
        snapshots = {name: {"file": f"snapshots/{i:04d}.bin", "sha256": io.digest(raw)} for i, (name, raw) in enumerate(assets, 1)}
        RESULTS.mkdir(parents=True)
        for name, raw in assets:
            path = RESULTS / snapshots[name]["file"]
            path.parent.mkdir(exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                prior.base.os.fsync(stream.fileno())
        frozen = {"work_id": WORK_ID, "phase": PHASE, "frozen_utc": io.now(), "parent_posts": 11,
            "maximum_posts": 6, "hard_ceiling": 17, "config": CONFIG, "runtime_config": prior.base.runtime_config(settings),
            "library_versions": versions(), "snapshots": snapshots, "sample_plan": parent["samples"], "templates": templates,
            "reused_sections": parent["reused_sections"], "parent_sha256": parent["parent_sha256"], "parent_phases": parent["parent_phases"],
            "model": settings.llm_model, "provider": settings.llm_provider, "endpoint": endpoint, "output_language": "zh-CN", "parent_semantic_quality_verified": False}
        io.exclusive(RESULTS / "provenance.json", frozen)
        io.exclusive(RESULTS / "request-ledger.json", {"work_id": WORK_ID, "phase": PHASE, "maximum_posts": 6, "requests": []})
        tracker = {"work_id": WORK_ID, "phase": PHASE, "status": "frozen", "maximum_posts": 6,
            "hard_ceiling": 17, "parent_posts": 11, "reserved_posts": 0, "ledger": str(RESULTS / "request-ledger.json"),
            "provenance_sha256": io.digest((RESULTS / "provenance.json").read_bytes())}
        io.exclusive(TRACKER, tracker)
        group["phases"].append({"phase": PHASE, "status": "frozen", "maximum_posts": 6, "reserved_posts": 0,
            "ledger": tracker["ledger"], "tracker": str(TRACKER), "provenance_sha256": tracker["provenance_sha256"]})
        durable(GROUP, group)
        return {"frozen": True, "network": False, "phase": PHASE, "normal_posts": 6, "maximum_posts": 6}


def snapshot_bytes(frozen, path):
    name = path.resolve().relative_to(PROJECT.resolve()).as_posix()
    return (RESULTS / frozen["snapshots"][name]["file"]).read_bytes()


def frozen_state(*, live):
    frozen, ledger, tracker = [read(p) for p in (RESULTS / "provenance.json", RESULTS / "request-ledger.json", TRACKER)]
    if any(obj.get("work_id") != WORK_ID or obj.get("phase") != PHASE or obj.get("maximum_posts") != 6 for obj in (frozen, ledger, tracker)):
        raise RuntimeError("Schema Pro frozen identity differs")
    if (frozen.get("config") != CONFIG or frozen.get("hard_ceiling") != 17 or frozen.get("parent_posts") != 11
            or frozen.get("output_language") != "zh-CN" or frozen.get("library_versions") != versions()
            or tracker.get("provenance_sha256") != io.digest((RESULTS / "provenance.json").read_bytes())
            or tracker.get("ledger") != str(RESULTS / "request-ledger.json") or tracker.get("hard_ceiling") != 17 or tracker.get("parent_posts") != 11):
        raise RuntimeError("Schema Pro provenance/config differs")
    if "backend/app/services/summary_output.py" not in frozen.get("snapshots", {}):
        raise RuntimeError("Schema Pro codec snapshot missing")
    for name, record in frozen["snapshots"].items():
        original, snapshot = (PROJECT / name).resolve(), (RESULTS / record["file"]).resolve()
        if (not original.is_relative_to(PROJECT.resolve()) or not snapshot.is_relative_to((RESULTS / "snapshots").resolve())
                or io.digest(snapshot.read_bytes()) != record["sha256"] or live and io.digest(original.read_bytes()) != record["sha256"]):
            raise RuntimeError("Schema Pro live/frozen asset differs")
    parent = parent_state(reader=lambda path: snapshot_bytes(frozen, path))
    if (parent["parent_sha256"] != frozen["parent_sha256"] or parent["parent_phases"] != frozen["parent_phases"]
            or parent["samples"] != frozen["sample_plan"] or parent["reused_sections"] != frozen["reused_sections"]):
        raise RuntimeError("Frozen parent/source/notes differs")
    if live and set(frozen["snapshots"]) != {p.relative_to(PROJECT).as_posix() for p in asset_paths()}:
        raise RuntimeError("Live asset inventory differs")
    rows, group = ledger.get("requests", []), group_state(parent)
    phases = [p for p in group["phases"] if p.get("phase") == PHASE]
    if (len(rows) > 6 or tracker.get("reserved_posts") != len(rows) or len(phases) != 1
            or phases[0].get("ledger") != tracker["ledger"] or phases[0].get("tracker") != str(TRACKER)
            or phases[0].get("maximum_posts") != 6 or phases[0].get("reserved_posts") != len(rows)
            or phases[0].get("provenance_sha256") != tracker["provenance_sha256"] or group["reserved_posts"] != 11 + len(rows)
            or any(r.get("ordinal") != i for i, r in enumerate(rows, 1))):
        raise RuntimeError("Schema Pro reservations differ")
    return frozen, ledger, tracker


def bind():
    # Reuse audited caller, one-shot check, durable reservation and close handling
    # through its existing function globals, without altering historical bytes.
    for name in ("PROJECT", "REPORT", "RESULTS", "CORPUS", "GROUP", "TRACKER", "SHARED_LOCK", "WORK_ID", "PHASE", "MAX_POSTS", "HARD_CEILING", "CONFIG"):
        setattr(stage, name, globals()[name])
    for name in ("base_context", "durable", "parent_state", "group_state", "runtime", "match_runtime", "frozen_state", "snapshot_bytes", "decoded_stage", "next_stage", "expected_payload"):
        setattr(stage, name, globals()[name])
    stage.io = SimpleNamespace(**{name: getattr(io, name) for name in dir(io) if not name.startswith("__")})
    stage.io.response_evidence = response_evidence


def check():
    bind()
    return stage.check()


def response_evidence(body):
    """Whitelist genuine Responses fields; never manufacture chat completion flags."""
    if not isinstance(body, dict):
        return {"object": None, "status": None, "output": [], "content": None}
    safe = {key: body.get(key) if isinstance(body.get(key), str) else None for key in ("object", "status")}
    safe["error_present"] = body.get("error") is not None
    safe["incomplete_present"] = body.get("incomplete_details") is not None
    output = body.get("output")
    safe["output"] = None if not isinstance(output, list) else []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                safe["output"].append(None)
            elif item.get("type") != "reasoning":
                clean = {k: item.get(k) if isinstance(item.get(k), str) else None for k in ("type", "role", "status")}
                parts = item.get("content")
                clean["content"] = None if not isinstance(parts, list) else [
                    {"type": p.get("type") if isinstance(p.get("type"), str) else None,
                     "text": p.get("text") if p.get("type") == "output_text" and isinstance(p.get("text"), str) else None}
                    if isinstance(p, dict) else None for p in parts]
                safe["output"].append(clean)
    # Extract text with the frozen product parser. The live parser independently
    # validates the original response in _complete before returning to LCEL.
    try:
        safe["content"] = responses_content(safe, read(RESULTS / "provenance.json"))
    except Exception as exc:
        safe["content"] = None
        safe["parse_error_type"] = getattr(exc, "error_type", type(exc).__name__)
    usage = body.get("usage")
    if isinstance(usage, dict):
        safe["usage"] = {k: usage[k] for k in ("input_tokens", "output_tokens", "total_tokens") if type(usage.get(k)) is int and usage[k] >= 0}
        details = usage.get("input_tokens_details")
        if isinstance(details, dict) and type(details.get("cached_tokens")) is int and details["cached_tokens"] >= 0:
            safe["usage"]["input_tokens_details"] = {"cached_tokens": details["cached_tokens"]}
    return safe


def responses_content(raw, frozen):
    # Reuse the exact frozen parser without importing config or product runtime.
    import ast
    source = snapshot_bytes(frozen, PROJECT / "backend/app/services/llm_service.py")
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_responses_content")
    class InvalidResponse(ValueError):
        def __init__(self, error_type, message):
            self.error_type = error_type
            super().__init__(error_type)
    namespace = {"Any": object, "LLMServiceError": InvalidResponse}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "frozen_responses_parser", "exec", dont_inherit=True), namespace)
    payload = {k: raw.get(k) for k in ("object", "status", "output")}
    payload.update(error={} if raw.get("error_present") else None,
                   incomplete_details={} if raw.get("incomplete_present") else None)
    return namespace["_responses_content"](payload)


def decoded_stage(frozen, row, codec):
    raw = read(RESULTS / f"response-{row['ordinal']:02d}.json")
    if row.get("status") != "response" or raw.get("http_status") != 200 or raw.get("model") != frozen["model"]:
        raise RuntimeError("Responses raw model/status differs")
    content = responses_content(raw, frozen)
    role = row["stage"]
    record = frozen["templates"][row["sample"]][role]
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise RuntimeError("Duplicate Responses JSON field; no repair allowed")
            value[key] = item
        return value
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    payload = json.loads(content, object_pairs_hook=pairs)
    if isinstance(payload, dict):
        if isinstance(payload.get("summary"), str):
            payload["summary"] = payload["summary"].strip()
        if isinstance(payload.get("key_points"), list):
            payload["key_points"] = [p.strip() if isinstance(p, str) else p for p in payload["key_points"] if not isinstance(p, str) or p.strip()]
    return codec.stage_model(role, record["max_points"], record["point_char_limit"]).model_validate(payload).model_dump()


def next_stage(frozen, sample, rows, codec):
    matching = [r for r in rows if r["sample"] == sample]
    if not matching:
        return "points", None
    last = matching[-1]
    if last["stage"] not in {"points", "overview"}:
        raise RuntimeError("Format/semantic stage prohibited")
    decoded_stage(frozen, last, codec)
    return ("overview", None) if last["stage"] == "points" else (None, None)


def expected_payload(frozen, sample, role, rows, codec):
    if role not in {"points", "overview"}:
        raise RuntimeError("Format/semantic POST prohibited")
    payload = json.loads(json.dumps(frozen["templates"][sample][role]["payload"]))
    if role == "overview":
        matching = [r for r in rows if r["sample"] == sample and r["stage"] == "points"]
        if len(matching) != 1:
            raise RuntimeError("Overview lacks one accepted points role")
        points = decoded_stage(frozen, matching[0], codec)["key_points"]
        payload["input"][-1]["content"] = payload["input"][-1]["content"][:-2] + json.dumps(points, ensure_ascii=False)
    if len(payload["input"][-1]["content"]) > CONFIG["llm_max_input_chars"]:
        raise RuntimeError("Actual Responses input exceeds frozen capacity")
    return payload


def run(*, transport=None):
    bind()
    return stage.run(transport=transport)


def verify_results():
    bind()
    frozen, ledger, tracker = frozen_state(live=False)
    index, receipt = read(RESULTS / "result-index.json"), read(RESULTS / "closed-receipt.json")
    group = group_state()
    phase = next(p for p in group["phases"] if p["phase"] == PHASE)
    receipt_sha = io.digest((RESULTS / "closed-receipt.json").read_bytes())
    rows, samples = ledger["requests"], index.get("samples", [])
    if (tracker["status"] != "closed" or phase["status"] != "closed" or receipt.get("status") != "closed"
            or receipt.get("work_id") != WORK_ID or receipt.get("phase") != PHASE
            or any(obj.get("closed_receipt_sha256") != receipt_sha for obj in (tracker, phase))
            or receipt.get("ledger_sha256") != io.digest((RESULTS / "request-ledger.json").read_bytes())
            or receipt.get("index_sha256") != io.digest((RESULTS / "result-index.json").read_bytes())
            or receipt.get("provenance_sha256") != tracker["provenance_sha256"] or receipt.get("posts") != len(rows)
            or receipt.get("work_posts") != 11 + len(rows) or receipt.get("hard_ceiling") != 17
            or index.get("work_id") != WORK_ID or index.get("phase") != PHASE or index.get("posts") != len(rows)
            or type(index.get("stopped_on_error")) is not bool or [s.get("sample") for s in samples] != list(SAMPLES[:len(samples)])):
        raise RuntimeError("Schema Pro closed receipt differs")
    codec = codec_from_bytes(snapshot_bytes(frozen, PROJECT / "backend/app/services/summary_output.py"), "schema_pro_verify_codec")
    for i, row in enumerate(rows):
        role, _ = next_stage(frozen, row["sample"], rows[:i], codec)
        matching = [r for r in rows[:i] if r["sample"] == row["sample"]]
        started, trace = row.get("diagnostic_started", {}), read(RESULTS / f"trace-{row['sample']}.json")
        if (row.get("status") not in {"response", "error"} or row.get("stage") != role or role is None
                or row.get("sample_post") != len(matching) + 1 or started not in trace or started.get("stage") != role
                or started.get("request_count") != len(matching) + 1 or started.get("attempt") != 1 or started.get("format_used") != 0):
            raise RuntimeError("Responses role/diagnostic/zero-repair route differs")
        path = RESULTS / f"payload-{row['ordinal']:02d}.json"
        if io.digest(path.read_bytes()) != row.get("payload_sha256") or read(path) != expected_payload(frozen, row["sample"], role, rows[:i], codec):
            raise RuntimeError("Saved Responses source/notes/points/payload differs")
        if row.get("response_sha256") and io.digest((RESULTS / f"response-{row['ordinal']:02d}.json").read_bytes()) != row["response_sha256"]:
            raise RuntimeError("Responses raw hash differs")
    stopped = index["stopped_on_error"]
    if (not stopped and (len(rows) != 6 or len(samples) != 3 or any(s.get("success") is not True for s in samples))
            or stopped and not (index.get("phase_error_type") or any(s.get("success") is False for s in samples))):
        raise RuntimeError("Schema Pro error/completion disposition differs")
    for item in samples:
        path, sid = RESULTS / f"{item['sample']}.json", item["sample"]
        result = read(path)
        sample = next(s for s in frozen["sample_plan"] if s["id"] == sid)
        matching = [r for r in rows if r["sample"] == sid]
        if (io.digest(path.read_bytes()) != item.get("result_sha256") or result.get("sample") != sid
                or result.get("source_sha256") != sample["sha256"] or result.get("success") != item["success"]
                or item.get("posts") != len(matching) or any(r.get("result_sha256") != item["result_sha256"] for r in matching)
                or item.get("trace_sha256") != io.digest((RESULTS / f"trace-{sid}.json").read_bytes())):
            raise RuntimeError("Schema Pro result/trace ownership differs")
        if item["success"] and result.get("result") != stage.final_result(frozen, sid, rows, codec):
            raise RuntimeError("Final points/overview differ from independently accepted Responses raw")
    return {"evidence_hashes_verified": True, "phase_closed": True, "posts": len(rows), "work_posts": 11 + len(rows),
        "format_posts": 0, "stopped_on_error": stopped, "semantic_quality_verified": False, "reused_parent_posts": [3, 4],
        "provider": frozen["provider"], "model": frozen["model"]}


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
