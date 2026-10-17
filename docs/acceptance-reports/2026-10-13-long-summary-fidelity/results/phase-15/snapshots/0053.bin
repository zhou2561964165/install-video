"""Bound staged continuation: prior 5 + normal 6 + at most one format POST <=12.

Plan/check/verify are offline and never read dotenv/product runtime. Root alone
freezes/runs. Prior phase remains immutable; saved leaf notes are structural
inputs, not proof of semantic quality. No retry/fallback/paid capability probes.
Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only ytdlp_service; scene read-only; source/outputs retain CC BY-NC-SA 4.0.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import re
import sys
from types import ModuleType

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
RESULTS = REPORT / "results"
CORPUS = REPORT.parent / "2026-10-04-natural-subtitle-quality/corpus"
PARENT_REPORT = REPORT.parent / "2026-10-10-source-first-summary-live"
PARENT_RESULTS = PARENT_REPORT / "results"
PARENT_RUNNER = PARENT_REPORT / "scripts/evaluate.py"
PARENT_GROUP = PROJECT / ".planning/2026-10-10-source-first-summary-acceptance/budget-group.json"
PARENT_TRACKER = PARENT_GROUP.with_name("phase-1.json")
GROUP = PARENT_GROUP.with_name("budget-continuation-staged.json")
TRACKER = PARENT_GROUP.with_name("phase-2.json")
SHARED_LOCK = REPORT.parent / "2026-10-05-grounded-summary/results/.http-session-lock"
WORK_ID, PHASE = "source-first-summary-20261010", "source-first-summary-staged-2"
PARENT_PHASE = "source-first-summary-live-1"
PARENT_POSTS, MAX_POSTS, HARD_CEILING = 5, 7, 12
SAMPLES = ("zh-short", "en-medium", "en-long")
spec = importlib.util.spec_from_file_location("staged_prior_io", PARENT_RUNNER)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
io = base.io
BASE_CONFIG = dict(base.CONFIG)
CONFIG = BASE_CONFIG | {"llm_summary_generation_mode": "staged", "llm_summary_format_retries": 1,
    "llm_summary_semantic_retries": 0, "llm_summary_max_extra_calls": 1}
base_versions = base.versions
FORMAT_REASONS = ("invalid_json", "duplicate_json_field", "invalid_fields", "invalid_count")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def base_context():
    # Reuse audited helpers in memory; never execute the historical phase.
    for name in ("PROJECT", "RESULTS", "GROUP", "TRACKER", "WORK_ID", "PHASE", "MAX_POSTS", "HARD_CEILING"):
        setattr(base, name, globals()[name])


def durable(path, value):
    base_context()
    return base.durable(path, value)


def versions():
    from importlib.metadata import version
    return base_versions() | {"langchain-core": version("langchain-core"), "langsmith": version("langsmith")}


def codec_from_bytes(raw, name):
    codec = ModuleType(name)
    # Historical bytes must use their own compiler flags; inheriting this
    # runner's postponed annotations changes Pydantic's frozen field types.
    exec(compile(raw, name, "exec", dont_inherit=True), codec.__dict__)
    return codec


def parent_state(*, reader=None):
    """Prove parent counts, immutable receipts, exact source and the two saved leaves."""
    get = reader or (lambda path: path.read_bytes())
    data = lambda path: json.loads(get(path).decode("utf-8"))
    parent = data(PARENT_GROUP)
    if (parent.get("work_id") != WORK_ID or parent.get("status") != "closed"
            or parent.get("hard_ceiling") != 10 or parent.get("reserved_posts") != PARENT_POSTS
            or len(parent.get("phases", [])) != 1):
        raise RuntimeError("Parent closed 5/10 work group differs")
    phase, tracker = parent["phases"][0], data(PARENT_TRACKER)
    receipt, frozen, ledger, index = [data(PARENT_RESULTS / name) for name in (
        "closed-receipt.json", "provenance.json", "request-ledger.json", "result-index.json")]
    identities = {"work_id": WORK_ID, "phase": PARENT_PHASE}
    if any(any(obj.get(k) != v for k, v in identities.items()) for obj in (receipt, frozen, ledger, tracker, index)):
        raise RuntimeError("Parent phase identity differs")
    expected_phase = {"phase": PARENT_PHASE, "status": "closed", "maximum_posts": 5,
        "reserved_posts": 5, "ledger": str(PARENT_RESULTS / "request-ledger.json"), "tracker": str(PARENT_TRACKER),
        "provenance_sha256": io.digest(get(PARENT_RESULTS / "provenance.json")),
        "closed_receipt_sha256": io.digest(get(PARENT_RESULTS / "closed-receipt.json"))}
    if (any(phase.get(k) != v for k, v in expected_phase.items())
            or tracker.get("status") != "closed" or tracker.get("reserved_posts") != 5
            or tracker.get("ledger") != expected_phase["ledger"]
            or tracker.get("provenance_sha256") != expected_phase["provenance_sha256"]
            or tracker.get("closed_receipt_sha256") != expected_phase["closed_receipt_sha256"]
            or receipt.get("status") != "closed" or receipt.get("posts") != 5 or receipt.get("work_posts") != 5
            or receipt.get("hard_ceiling") != 10 or frozen.get("config") != BASE_CONFIG
            or receipt.get("provenance_sha256") != expected_phase["provenance_sha256"]
            or receipt.get("ledger_sha256") != io.digest(get(PARENT_RESULTS / "request-ledger.json"))
            or receipt.get("index_sha256") != io.digest(get(PARENT_RESULTS / "result-index.json"))
            or index.get("posts") != 5 or len(ledger.get("requests", [])) != 5):
        raise RuntimeError("Parent closed receipt/ledger/provenance differs")
    for name, record in frozen["snapshots"].items():
        path = (PARENT_RESULTS / record["file"]).resolve()
        if (not path.is_relative_to((PARENT_RESULTS / "snapshots").resolve())
                or not (PROJECT / name).resolve().is_relative_to(PROJECT.resolve())
                or io.digest(get(path)) != record["sha256"]):
            raise RuntimeError("Parent frozen snapshot differs")
    runner_name = PARENT_RUNNER.relative_to(PROJECT).as_posix()
    if frozen["snapshots"].get(runner_name, {}).get("sha256") != io.digest(get(PARENT_RUNNER)):
        raise RuntimeError("Parent immutable runner differs")
    samples, source_parts = [], {}
    manifest = data(CORPUS / "manifest.json")
    manifest_name = (CORPUS / "manifest.json").relative_to(PROJECT).as_posix()
    if frozen["snapshots"].get(manifest_name, {}).get("sha256") != io.digest(get(CORPUS / "manifest.json")):
        raise RuntimeError("Parent source manifest differs")
    for sid, expected in zip(SAMPLES, (1, 1, 3)):
        rows = [s for s in manifest["samples"] if s.get("id") == sid]
        old_rows = [s for s in frozen["sample_plan"] if s.get("id") == sid]
        if len(rows) != 1 or len(old_rows) != 1:
            raise RuntimeError("Parent sample identity ambiguous")
        sample, old = rows[0], old_rows[0]
        for file_key, hash_key in (("file", "sha256"), ("raw_path", "raw_sha256")):
            path = (CORPUS / sample[file_key]).resolve()
            name = path.relative_to(PROJECT).as_posix()
            if (not path.is_relative_to(CORPUS.resolve()) or io.digest(get(path)) != sample[hash_key]
                    or old.get(hash_key) != sample[hash_key]
                    or frozen["snapshots"].get(name, {}).get("sha256") != sample[hash_key]):
                raise RuntimeError("Parent exact subtitle source binding differs")
        text = base.cleaned(get(CORPUS / sample["file"]).decode("utf-8"))
        parts = base.chunks(text, min(CONFIG["llm_summary_chunk_chars"], CONFIG["llm_max_input_chars"]))
        if (old.get("cleaned_sha256") != io.digest(text) or old.get("chunks") != [io.digest(p) for p in parts]
                or old.get("expected_posts") != expected):
            raise RuntimeError("Parent source segmentation differs")
        samples.append({key: sample[key] for key in ("id", "file", "raw_path", "sha256", "raw_sha256", "title", "license", "attribution")}
            | {"expected_posts": 2, "cleaned_sha256": io.digest(text), "chunks": [io.digest(p) for p in parts]})
        source_parts[sid] = parts
    expected = [("zh-short", 1, "extract"), ("en-medium", 1, "extract"),
        ("en-long", 1, "extract"), ("en-long", 2, "extract"), ("en-long", 3, "merge")]
    for i, row in enumerate(ledger["requests"], 1):
        if (row.get("ordinal") != i or (row.get("sample"), row.get("sample_post"), row.get("stage")) != expected[i - 1]
                or row.get("status") != "response" or row.get("http_status") != 200):
            raise RuntimeError("Parent request/leaf identity differs")
        for kind in ("payload", "response"):
            if io.digest(get(PARENT_RESULTS / f"{kind}-{i:02d}.json")) != row.get(f"{kind}_sha256"):
                raise RuntimeError("Parent payload/raw evidence differs")
    record = frozen["snapshots"]["backend/app/services/summary_output.py"]
    codec = codec_from_bytes(get(PARENT_RESULTS / record["file"]), "prior_summary_codec")
    reused = []
    for ordinal, part in zip((3, 4), source_parts["en-long"]):
        raw, payload = data(PARENT_RESULTS / f"response-{ordinal:02d}.json"), data(PARENT_RESULTS / f"payload-{ordinal:02d}.json")
        stage = frozen["stages"]["en-long"][ordinal - 3]
        if (stage["stage"] != "extract" or payload != stage["payload"]
                or raw.get("http_status") != 200 or raw.get("finish_reason") != "stop"
                or raw.get("model") != frozen["model"] or not isinstance(raw.get("content"), str)
                or not payload["messages"][-1]["content"].endswith("Transcript:\n" + part)):
            raise RuntimeError("Parent saved leaf StagePayload/model/source differs")
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw["content"].strip(), flags=re.IGNORECASE)
        try:
            value = codec.decode_payload(json.loads(content), strict=False)
            summary, points = value.summary.strip(), [p.strip() for p in value.key_points if p.strip()]
        except Exception:
            raise RuntimeError("Parent saved leaf structure invalid") from None
        if not summary or not points or len(points) > stage["max_points"]:
            raise RuntimeError("Parent saved leaf finite budget differs")
        reused.append({"parent_ordinal": ordinal, "part_index": ordinal - 3, "part_sha256": io.digest(part),
            "summary": summary, "key_points": points, "provider": frozen["provider"], "model": frozen["model"]})
    return {"parent_sha256": io.digest(get(PARENT_GROUP)), "parent_phase": phase, "samples": samples,
        "reused_sections": reused, "source_parts": source_parts, "parent_semantic_quality_verified": False}


def group_state(parent=None):
    base_context()
    group = base.group_state()
    if (group.get("parent_snapshot") != str(PARENT_GROUP) or group.get("parent_posts") != 5
            or group.get("budget_adjustment") != {"from": 10, "to": 12}
            or (parent is not None and (group.get("parent_sha256") != parent["parent_sha256"]
                or not group["phases"] or group["phases"][0] != parent["parent_phase"]))):
        raise RuntimeError("Continuation parent/budget adjustment differs")
    return group


def plan():
    parent = parent_state()
    group = group_state(parent)
    return {"work_id": WORK_ID, "phase": PHASE, "network": False, "dotenv_read": False,
        "parent_posts": 5, "maximum_posts": 7, "normal_posts": 6, "format_posts_ceiling": 1,
        "hard_ceiling": 12, "work_reserved_posts": group["reserved_posts"], "config": CONFIG,
        "samples": parent["samples"], "parent_semantic_quality_verified": False}


def asset_paths():
    paths = [Path(__file__), PARENT_RUNNER, base.HELPER, PARENT_GROUP, PARENT_TRACKER,
        PROJECT / "pyproject.toml", PROJECT / "uv.lock", PROJECT / "backend/app/config.py",
        PROJECT / "backend/app/services/llm_service.py", REPORT / "review-criteria.md",
        PROJECT / "docs/superpowers/specs/2026-10-10-staged-summary-design.md",
        PARENT_REPORT / "report.md", PARENT_REPORT / "review-criteria.md"]
    paths.extend((PROJECT / "backend/app/services").glob("summary_*.py"))
    for directory in (CORPUS, PARENT_RESULTS):
        paths.extend(p for p in directory.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    return sorted(set(paths))


def runtime():
    sys.path.insert(0, str(PROJECT / "backend"))
    io.load_dotenv(PROJECT / "backend/.env", override=False)
    from app.config import settings
    from app.services import llm_service as service
    from urllib.parse import urlsplit
    for key, value in CONFIG.items():
        setattr(settings, key, value)
    endpoint = service._endpoint()
    parts = urlsplit(endpoint)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise RuntimeError("Endpoint must be HTTPS without credential/query metadata")
    return settings, service, endpoint


def match_runtime(settings, service, endpoint, frozen):
    if (endpoint != frozen["endpoint"] or service._endpoint() != frozen["endpoint"]
            or settings.llm_model != frozen["model"] or settings.llm_provider != frozen["provider"]
            or base.runtime_config(settings) != frozen["runtime_config"] or versions() != frozen["library_versions"]):
        raise RuntimeError("Runtime endpoint/provider/model/config/library drift")


def notes_for(reused):
    return json.dumps([{"section": i + 1, "summary": s["summary"], "key_points": s["key_points"]}
        for i, s in enumerate(reused)], ensure_ascii=False)


def freeze():
    with io.directory_guard(SHARED_LOCK):
        if RESULTS.exists() or TRACKER.exists():
            raise RuntimeError("Staged phase already allocated; never reopen")
        parent = parent_state()
        group = group_state(parent)
        if group["status"] != "active" or group["reserved_posts"] != 5 or len(group["phases"]) != 1:
            raise RuntimeError("Continuation must start from closed parent 5")
        settings, service, endpoint = runtime()
        templates = {}
        for sample in parent["samples"]:
            source = (CORPUS / sample["file"]).read_text(encoding="utf-8")
            prepared = service._summary_chunks(service._summary_input(source), min(
                CONFIG["llm_summary_chunk_chars"], CONFIG["llm_max_input_chars"]))
            if prepared != parent["source_parts"][sample["id"]]:
                raise RuntimeError("Production source parts differ from bound parent")
            budget = service._summary_budget(len(source))
            reused = parent["reused_sections"] if sample["id"] == "en-long" else []
            notes = notes_for(reused) if reused else ""
            if reused:
                objects = [service.LLMSummaryResult(s["summary"], s["key_points"], s["provider"], s["model"]) for s in reused]
                if service._section_notes(objects) != notes:
                    raise RuntimeError("Production section notes differ from bound parent raw")
            roles = {}
            for role in ("points", "overview"):
                messages = service._staged_messages(role, transcript=source, notes=notes, key_points=[],
                    title=sample["title"], output_language="zh-CN", budget=budget)
                if role == "overview" and not messages[-1]["content"].endswith("[]"):
                    raise RuntimeError("Overview must expose completed points at its frozen boundary")
                if len(messages[-1]["content"]) > CONFIG["llm_max_input_chars"]:
                    raise RuntimeError("Staged source/notes exceed frozen capacity")
                options = service._summary_options(budget)
                payload = {"model": settings.llm_model, "temperature": 0.2,
                    "messages": messages, "max_tokens": budget.max_tokens, **options}
                formats = {}
                # Freeze the actual format helper's fixed text separately from
                # its bound base message and raw. No fixture answer is generated.
                for reason in FORMAT_REASONS:
                    markers = [{"role": "system", "content": messages[0]["content"]},
                        {"role": "user", "content": "ACCEPTANCE_BASE_MESSAGE_SLOT"}]
                    repair = service._staged_format_messages(markers, raw="ACCEPTANCE_RAW_SLOT", reason=reason, budget=budget)
                    user = repair[-1]["content"]
                    if user.count("ACCEPTANCE_BASE_MESSAGE_SLOT") != 1 or user.count("ACCEPTANCE_RAW_SLOT") != 1:
                        raise RuntimeError("Format helper does not expose unique bound input slots")
                    prefix, rest = user.split("ACCEPTANCE_BASE_MESSAGE_SLOT")
                    middle, suffix = rest.split("ACCEPTANCE_RAW_SLOT")
                    if suffix or repair[0] != messages[0]:
                        raise RuntimeError("Format helper fixed role/boundary differs")
                    formats[reason] = {"prefix": prefix, "middle": middle}
                roles[role] = {"payload": payload, "max_points": budget.max_points,
                    "point_char_limit": budget.point_char_limit, "formats": formats}
            templates[sample["id"]] = roles
        assets = []
        for path in asset_paths():
            if (not path.resolve().is_relative_to(PROJECT.resolve()) or path.name.lower().startswith(".env")
                    or "credential" in path.name.lower() or path.suffix.lower() in {".db", ".sqlite", ".sqlite3", ".key", ".pem", ".p12"}):
                raise RuntimeError("Unsafe frozen asset")
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
                base.os.fsync(stream.fileno())
        frozen = {"work_id": WORK_ID, "phase": PHASE, "frozen_utc": io.now(), "parent_posts": 5,
            "maximum_posts": 7, "hard_ceiling": 12, "config": CONFIG, "runtime_config": base.runtime_config(settings),
            "library_versions": versions(), "snapshots": snapshots, "sample_plan": parent["samples"],
            "templates": templates, "reused_sections": parent["reused_sections"],
            "parent_sha256": parent["parent_sha256"], "parent_phase": parent["parent_phase"],
            "model": settings.llm_model, "provider": settings.llm_provider, "endpoint": endpoint,
            "output_language": "zh-CN", "parent_semantic_quality_verified": False}
        io.exclusive(RESULTS / "provenance.json", frozen)
        io.exclusive(RESULTS / "request-ledger.json", {"work_id": WORK_ID, "phase": PHASE, "maximum_posts": 7, "requests": []})
        tracker = {"work_id": WORK_ID, "phase": PHASE, "status": "frozen", "maximum_posts": 7,
            "hard_ceiling": 12, "parent_posts": 5, "reserved_posts": 0,
            "ledger": str(RESULTS / "request-ledger.json"), "provenance_sha256": io.digest((RESULTS / "provenance.json").read_bytes())}
        io.exclusive(TRACKER, tracker)
        group["phases"].append({"phase": PHASE, "status": "frozen", "maximum_posts": 7,
            "reserved_posts": 0, "ledger": tracker["ledger"], "tracker": str(TRACKER), "provenance_sha256": tracker["provenance_sha256"]})
        durable(GROUP, group)
        return {"frozen": True, "network": False, "phase": PHASE, "normal_posts": 6, "maximum_posts": 7}


def snapshot_bytes(frozen, path):
    name = path.resolve().relative_to(PROJECT.resolve()).as_posix()
    return (RESULTS / frozen["snapshots"][name]["file"]).read_bytes()


def frozen_state(*, live):
    frozen, ledger, tracker = read(RESULTS / "provenance.json"), read(RESULTS / "request-ledger.json"), read(TRACKER)
    for obj in (frozen, ledger, tracker):
        if obj.get("work_id") != WORK_ID or obj.get("phase") != PHASE or obj.get("maximum_posts") != 7:
            raise RuntimeError("Staged frozen identity differs")
    if (frozen.get("config") != CONFIG or frozen.get("hard_ceiling") != 12 or frozen.get("parent_posts") != 5
            or frozen.get("output_language") != "zh-CN" or frozen.get("library_versions") != versions()
            or tracker.get("provenance_sha256") != io.digest((RESULTS / "provenance.json").read_bytes())
            or tracker.get("ledger") != str(RESULTS / "request-ledger.json")
            or tracker.get("hard_ceiling") != 12 or tracker.get("parent_posts") != 5):
        raise RuntimeError("Staged provenance/config/library differs")
    if not frozen.get("snapshots") or "backend/app/services/summary_output.py" not in frozen["snapshots"]:
        raise RuntimeError("Staged codec snapshot missing")
    for name, record in frozen["snapshots"].items():
        original, snapshot = (PROJECT / name).resolve(), (RESULTS / record["file"]).resolve()
        if (not original.is_relative_to(PROJECT.resolve()) or not snapshot.is_relative_to((RESULTS / "snapshots").resolve())
                or io.digest(snapshot.read_bytes()) != record["sha256"]):
            raise RuntimeError("Staged frozen snapshot differs")
        if live and io.digest(original.read_bytes()) != record["sha256"]:
            raise RuntimeError("Live asset/parent differs from freeze")
    parent = parent_state(reader=lambda path: snapshot_bytes(frozen, path))
    if (parent["parent_sha256"] != frozen["parent_sha256"] or parent["parent_phase"] != frozen["parent_phase"]
            or parent["samples"] != frozen["sample_plan"] or parent["reused_sections"] != frozen["reused_sections"]):
        raise RuntimeError("Frozen parent notes/source differs")
    if live and set(frozen["snapshots"]) != {p.relative_to(PROJECT).as_posix() for p in asset_paths()}:
        raise RuntimeError("Staged live asset inventory differs")
    rows = ledger.get("requests", [])
    group = group_state(parent)
    phase = [p for p in group["phases"] if p.get("phase") == PHASE]
    if (len(rows) > 7 or tracker.get("reserved_posts") != len(rows) or len(phase) != 1
            or phase[0].get("ledger") != tracker["ledger"] or phase[0].get("tracker") != str(TRACKER)
            or phase[0].get("maximum_posts") != 7 or phase[0].get("reserved_posts") != len(rows)
            or phase[0].get("provenance_sha256") != tracker["provenance_sha256"]
            or group["reserved_posts"] != 5 + len(rows)):
        raise RuntimeError("Staged continuation reservations differ")
    if any(r.get("ordinal") != i for i, r in enumerate(rows, 1)):
        raise RuntimeError("Staged request ordinals differ")
    return frozen, ledger, tracker


def check():
    with io.directory_guard(SHARED_LOCK):
        frozen, ledger, tracker = frozen_state(live=True)
        if tracker["status"] != "frozen" or ledger["requests"] or group_state()["status"] != "active":
            raise RuntimeError("Check requires fresh frozen continuation")
        receipt = {"phase": PHASE, "provenance_sha256": tracker["provenance_sha256"], "network": False, "dotenv_read": False}
        path = RESULTS / "offline-check.json"
        if path.exists():
            if read(path) != receipt:
                raise RuntimeError("Offline check receipt differs")
        else:
            io.exclusive(path, receipt)
        return receipt | {"freeze_valid": True}


class FormatFailure(ValueError):
    pass


def decoded_stage(frozen, row, codec):
    raw = read(RESULTS / f"response-{row['ordinal']:02d}.json")
    if (row.get("status") != "response" or raw.get("http_status") != 200 or raw.get("model") != frozen["model"]
            or raw.get("finish_reason") != "stop" or not isinstance(raw.get("content"), str)):
        raise RuntimeError("Staged raw model/status/completion differs")
    role = row["stage"].removesuffix("_format")
    record = frozen["templates"][row["sample"]][role]
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise FormatFailure("duplicate_json_field")
            result[key] = value
        return result
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw["content"].strip(), flags=re.IGNORECASE)
    try:
        payload = json.loads(content, object_pairs_hook=pairs)
    except json.JSONDecodeError:
        raise FormatFailure("invalid_json") from None
    if isinstance(payload, dict):
        payload = dict(payload)
        if isinstance(payload.get("summary"), str):
            payload["summary"] = payload["summary"].strip()
        if isinstance(payload.get("key_points"), list):
            payload["key_points"] = [p.strip() if isinstance(p, str) else p for p in payload["key_points"]
                if not isinstance(p, str) or p.strip()]
    from pydantic import ValidationError
    try:
        return codec.stage_model(role, record["max_points"], record["point_char_limit"]).model_validate(payload).model_dump()
    except ValidationError as exc:
        reason = "invalid_count" if any(e["type"] in {"too_long", "too_short"} and e["loc"] == ("key_points",)
            for e in exc.errors(include_input=False)) else "invalid_fields"
        raise FormatFailure(reason) from None


def next_stage(frozen, sample, rows, codec):
    matching = [r for r in rows if r["sample"] == sample]
    if not matching:
        return "points", None
    last = matching[-1]
    role = last["stage"].removesuffix("_format")
    try:
        decoded_stage(frozen, last, codec)
    except FormatFailure as exc:
        if last["stage"].endswith("_format"):
            raise RuntimeError("Format repair failed; stop") from None
        return role + "_format", str(exc)
    return ("overview", None) if role == "points" else (None, None)


def expected_payload(frozen, sample, stage, rows, codec):
    role = stage.removesuffix("_format")
    record = frozen["templates"][sample][role]
    payload = json.loads(json.dumps(record["payload"]))
    if role == "overview":
        points = [r for r in rows if r["sample"] == sample and r["stage"].startswith("points")]
        if not points:
            raise RuntimeError("Overview lacks accepted points")
        accepted = decoded_stage(frozen, points[-1], codec)
        payload["messages"][-1]["content"] = payload["messages"][-1]["content"][:-2] + json.dumps(accepted["key_points"], ensure_ascii=False)
    if stage.endswith("_format"):
        latest = [r for r in rows if r["sample"] == sample][-1]
        _, reason = next_stage(frozen, sample, rows, codec)
        if reason not in record["formats"]:
            raise RuntimeError("Unclassified/non-structure repair refused")
        raw = read(RESULTS / f"response-{latest['ordinal']:02d}.json")["content"].strip()
        template = record["formats"][reason]
        payload["messages"][-1]["content"] = template["prefix"] + payload["messages"][-1]["content"] + template["middle"] + raw
    if len(payload["messages"][-1]["content"]) > CONFIG["llm_max_input_chars"]:
        raise RuntimeError("Staged actual request exceeds frozen capacity")
    return payload


def final_result(frozen, sample, rows, codec):
    matching = [r for r in rows if r["sample"] == sample]
    points = [r for r in matching if r["stage"].startswith("points")]
    overview = [r for r in matching if r["stage"].startswith("overview")]
    if not points or not overview or next_stage(frozen, sample, rows, codec)[0] is not None:
        raise RuntimeError("Final result lacks completed independent roles")
    return decoded_stage(frozen, points[-1], codec) | decoded_stage(frozen, overview[-1], codec) | {
        "provider": frozen["provider"], "model": frozen["model"]}


def run(*, transport=None):
    with io.directory_guard(SHARED_LOCK):
        tracker = read(TRACKER)
        if tracker.get("status") != "frozen" or (RESULTS / "result-index.json").exists():
            raise RuntimeError("One-shot staged phase already started; never reopen")
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
            codec = codec_from_bytes(snapshot_bytes(frozen, PROJECT / "backend/app/services/summary_output.py"), "staged_frozen_codec")
            import httpx
            manager = nullcontext(transport) if transport is not None else httpx.Client(
                timeout=float(settings.llm_timeout_seconds), transport=httpx.HTTPTransport(retries=0))
            with manager as http:
                for sample in frozen["sample_plan"]:
                    before = len(read(RESULTS / "request-ledger.json")["requests"])
                    trace_path = RESULTS / f"trace-{sample['id']}.json"
                    trace = []
                    io.exclusive(trace_path, trace)
                    started = None

                    def diagnostic(event):
                        nonlocal started
                        allowed = {"strategy", "generation_mode", "stage", "attempt", "request_count", "status", "format_used",
                            "error_type", "category", "reason"}
                        safe = {k: v for k, v in event.items() if k in allowed}
                        if (safe.get("strategy") != "legacy" or safe.get("generation_mode") != "staged"
                                or safe.get("stage") not in {"points", "overview", "points_format", "overview_format"}
                                or safe.get("status") not in {"started", "passed", "failed"}):
                            raise RuntimeError("Unplanned staged diagnostic/leaf request")
                        trace.append(safe)
                        durable(trace_path, trace)
                        if safe["status"] == "started":
                            started = safe

                    class Client:
                        def post(self, url, *, headers, json):
                            nonlocal pending, started
                            current, current_ledger, current_tracker = frozen_state(live=True)
                            match_runtime(settings, service, endpoint, current)
                            group = group_state()
                            rows = current_ledger["requests"]
                            stage, reason = next_stage(current, sample["id"], rows, codec)
                            matching = [r for r in rows if r["sample"] == sample["id"]]
                            format_count = sum(r["stage"].endswith("_format") for r in rows)
                            sample_formats = sum(r["stage"].endswith("_format") for r in matching)
                            if (stage is None or started is None or stage != started.get("stage")
                                    or started.get("request_count") != len(matching) + 1 or started.get("attempt") != 1
                                    or started.get("format_used") != sample_formats + int(stage.endswith("_format"))
                                    or current_tracker["status"] != "running" or group["status"] != "active"
                                    or len(rows) >= MAX_POSTS or group["reserved_posts"] >= HARD_CEILING
                                    or (stage.endswith("_format") and (format_count >= 1 or sample_formats >= 1))
                                    or url != endpoint):
                                raise RuntimeError("Unplanned staged route or 7/12/one-format budget exceeded")
                            if stage.endswith("_format") and not any(e.get("status") == "failed" and e.get("stage") == stage.removesuffix("_format")
                                    and e.get("category") == "format" and e.get("reason") == reason for e in trace):
                                raise RuntimeError("Format attempt lacks classified structure failure")
                            expected = expected_payload(current, sample["id"], stage, rows, codec)
                            if json != expected:
                                raise RuntimeError("Staged actual payload/options/notes/points differ from freeze")
                            ordinal = len(rows) + 1
                            payload_path = RESULTS / f"payload-{ordinal:02d}.json"
                            io.exclusive(payload_path, expected)
                            row = {"ordinal": ordinal, "sample": sample["id"], "sample_post": len(matching) + 1,
                                "stage": stage, "status": "reserved", "reserved_utc": io.now(), "diagnostic_started": started,
                                "payload_sha256": io.digest(payload_path.read_bytes())}
                            started = None
                            pending = row
                            rows.append(row)
                            group["reserved_posts"] += 1
                            phase = next(p for p in group["phases"] if p["phase"] == PHASE)
                            phase.update(status="running", reserved_posts=ordinal)
                            current_tracker["reserved_posts"] = ordinal
                            try:
                                durable(GROUP, group)
                                durable(RESULTS / "request-ledger.json", current_ledger)
                                durable(TRACKER, current_tracker)
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
                                row.update(status="response", http_status=response.status_code,
                                    response_sha256=io.digest(raw_path.read_bytes()))
                                durable(RESULTS / "request-ledger.json", current_ledger)
                                pending = None
                                if safe["model"] != current["model"]:
                                    raise RuntimeError("Raw provider model drift")
                                return response
                            except BaseException as exc:
                                row.update(status="error", error_type=type(exc).__name__)
                                durable(GROUP, group)
                                durable(RESULTS / "request-ledger.json", current_ledger)
                                durable(TRACKER, current_tracker)
                                pending = None
                                raise

                    try:
                        source = (CORPUS / sample["file"]).read_text(encoding="utf-8")
                        kwargs = {"title": sample["title"], "output_language": "zh-CN", "client": Client(), "diagnostic": diagnostic}
                        if sample["id"] == "en-long":
                            parent = parent_state()
                            notes = [service.LLMSummaryResult(s["summary"], s["key_points"], s["provider"], s["model"]) for s in frozen["reused_sections"]]
                            summary = service.summarize_sections(source, notes, source_parts=parent["source_parts"]["en-long"], **kwargs)
                        else:
                            summary = service.summarize_text(source, **kwargs)
                        match_runtime(settings, service, endpoint, frozen)
                        frozen_state(live=True)
                        ledger = read(RESULTS / "request-ledger.json")
                        public = asdict(summary)
                        if public != final_result(frozen, sample["id"], ledger["requests"], codec):
                            raise RuntimeError("Final points/overview differ from accepted independent raw roles")
                        result = {"sample": sample["id"], "source_sha256": sample["sha256"], "success": True, "result": public}
                    except Exception as exc:
                        index["stopped_on_error"] = True
                        result = {"sample": sample["id"], "source_sha256": sample["sha256"], "success": False,
                            "error_type": getattr(exc, "error_type", type(exc).__name__)}
                    result_path = RESULTS / f"{sample['id']}.json"
                    io.exclusive(result_path, result)
                    checksum = io.digest(result_path.read_bytes())
                    ledger = read(RESULTS / "request-ledger.json")
                    for row in ledger["requests"][before:]:
                        row["result_sha256"] = checksum
                    durable(RESULTS / "request-ledger.json", ledger)
                    index["samples"].append({"sample": sample["id"], "success": result["success"], "result_sha256": checksum,
                        "posts": len(ledger["requests"]) - before, "trace_sha256": io.digest(trace_path.read_bytes())})
                    if index["stopped_on_error"]:
                        break
        except BaseException as exc:
            index.update(stopped_on_error=True, phase_error_type=type(exc).__name__)
            raise
        finally:
            base_context()
            base.close_phase(index, pending)
        return index


def verify_results():
    frozen, ledger, tracker = frozen_state(live=False)
    index, receipt = read(RESULTS / "result-index.json"), read(RESULTS / "closed-receipt.json")
    group = group_state()
    phase = next(p for p in group["phases"] if p["phase"] == PHASE)
    checksum = io.digest((RESULTS / "closed-receipt.json").read_bytes())
    rows, samples = ledger["requests"], index.get("samples", [])
    if (tracker["status"] != "closed" or phase["status"] != "closed" or receipt.get("status") != "closed"
            or receipt.get("work_id") != WORK_ID or receipt.get("phase") != PHASE
            or tracker.get("closed_receipt_sha256") != checksum or phase.get("closed_receipt_sha256") != checksum
            or receipt.get("ledger_sha256") != io.digest((RESULTS / "request-ledger.json").read_bytes())
            or receipt.get("index_sha256") != io.digest((RESULTS / "result-index.json").read_bytes())
            or receipt.get("provenance_sha256") != tracker["provenance_sha256"]
            or receipt.get("posts") != len(rows) or receipt.get("work_posts") != 5 + len(rows) or receipt.get("hard_ceiling") != 12
            or index.get("work_id") != WORK_ID or index.get("phase") != PHASE or index.get("posts") != len(rows)
            or type(index.get("stopped_on_error")) is not bool
            or [s.get("sample") for s in samples] != list(SAMPLES[:len(samples)])):
        raise RuntimeError("Staged closed receipt/index/group differs")
    codec = codec_from_bytes(snapshot_bytes(frozen, PROJECT / "backend/app/services/summary_output.py"), "verify_staged_codec")
    formats = 0
    for i, row in enumerate(rows):
        if row.get("status") not in {"response", "error"}:
            raise RuntimeError("Staged attempt not closed")
        stage, reason = next_stage(frozen, row["sample"], rows[:i], codec)
        if row.get("stage") != stage or stage is None:
            raise RuntimeError("Saved staged attempt route differs")
        formats += int(stage.endswith("_format"))
        matching = [r for r in rows[:i] if r["sample"] == row["sample"]]
        started = row.get("diagnostic_started", {})
        if (formats > 1 or row.get("sample_post") != len(matching) + 1 or started.get("stage") != stage
                or started.get("request_count") != len(matching) + 1 or started.get("attempt") != 1
                or started.get("format_used") != sum(r["stage"].endswith("_format") for r in matching) + int(stage.endswith("_format"))):
            raise RuntimeError("Saved staged diagnostic/format budget differs")
        trace = read(RESULTS / f"trace-{row['sample']}.json")
        if started not in trace:
            raise RuntimeError("Attempt not bound to persisted diagnostic")
        if stage.endswith("_format") and not any(e.get("status") == "failed" and e.get("category") == "format"
                and e.get("reason") == reason and e.get("stage") == stage.removesuffix("_format") for e in trace):
            raise RuntimeError("Saved repair lacks classified structural failure")
        payload_path = RESULTS / f"payload-{row['ordinal']:02d}.json"
        if (io.digest(payload_path.read_bytes()) != row.get("payload_sha256")
                or read(payload_path) != expected_payload(frozen, row["sample"], stage, rows[:i], codec)):
            raise RuntimeError("Saved payload/source/notes/accepted points differs")
        if row.get("response_sha256"):
            if io.digest((RESULTS / f"response-{row['ordinal']:02d}.json").read_bytes()) != row["response_sha256"]:
                raise RuntimeError("Saved raw response differs")
    stopped = index["stopped_on_error"]
    if (not stopped and (len(samples) != 3 or len(rows) not in {6, 7} or any(s.get("success") is not True for s in samples))
            or stopped and not (index.get("phase_error_type") or any(s.get("success") is False for s in samples))):
        raise RuntimeError("Staged phase completion/error disposition differs")
    for item in samples:
        path = RESULTS / f"{item['sample']}.json"
        result = read(path)
        sample = next(s for s in frozen["sample_plan"] if s["id"] == item["sample"])
        matching = [r for r in rows if r["sample"] == item["sample"]]
        if (io.digest(path.read_bytes()) != item.get("result_sha256") or result.get("sample") != item["sample"]
                or result.get("source_sha256") != sample["sha256"] or result.get("success") != item["success"]
                or item.get("posts") != len(matching) or any(r.get("result_sha256") != item["result_sha256"] for r in matching)
                or item.get("trace_sha256") != io.digest((RESULTS / f"trace-{item['sample']}.json").read_bytes())):
            raise RuntimeError("Staged result/trace/attempt ownership differs")
        if item["success"] and result.get("result") != final_result(frozen, item["sample"], rows, codec):
            raise RuntimeError("Final points/overview do not correspond to independent accepted raw roles")
    return {"evidence_hashes_verified": True, "phase_closed": True, "posts": len(rows), "work_posts": 5 + len(rows),
        "format_posts": formats, "stopped_on_error": stopped, "semantic_quality_verified": False,
        "reused_parent_posts": [3, 4], "provider": frozen["provider"], "model": frozen["model"]}


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
