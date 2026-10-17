"""One-shot source-first acceptance: phase <=5 POST, separate work group <=10.

Plan/check/verify do not import product runtime or read dotenv. Freeze reads
runtime explicitly, with no HTTP. Root alone may run. Every failed attempt
keeps its reservation; no retry, fallback, budget extension or phase reopening.
Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only ytdlp_service; scene read-only. Corpus/outputs retain CC BY-NC-SA 4.0.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
RESULTS = REPORT / "results"
CORPUS = REPORT.parent / "2026-10-04-natural-subtitle-quality/corpus"
HELPER = REPORT.parent / "2026-10-05-grounded-summary-evidence/scripts/evaluate.py"
SHARED_LOCK = REPORT.parent / "2026-10-05-grounded-summary/results/.http-session-lock"
GROUP = PROJECT / ".planning/2026-10-10-source-first-summary-acceptance/budget-group.json"
TRACKER = GROUP.with_name("phase-1.json")
WORK_ID = "source-first-summary-20261010"
PHASE = "source-first-summary-live-1"
MAX_POSTS, HARD_CEILING = 5, 10
SAMPLES = ("zh-short", "en-medium", "en-long")
CONFIG = {
    "llm_summary_strategy": "legacy", "llm_summary_length_mode": "adaptive",
    "llm_summary_response_format": "json_object", "llm_summary_thinking_mode": "disabled",
    "llm_summary_chunk_chars": 20000, "llm_max_input_chars": 60000,
    "llm_summary_max_chunks": 16, "llm_summary_max_output_tokens": 4096,
    "llm_summary_output_token_ceiling": 8192, "llm_summary_point_ceiling": 14,
    "llm_summary_source_context_chars": 1200,
}
spec = importlib.util.spec_from_file_location("source_first_io", HELPER)
io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(io)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def durable(path, value):
    """Shared encoding/atomic replacement, with cleanup of our own failed write.

    Resolve Windows paths before mutation. An existing .writing file belongs to
    another operation and must remain intact, even if it is a stale lock.
    """
    path = Path(path).resolve()
    if (not path.is_relative_to(PROJECT.resolve())
            or not (path in {GROUP.resolve(), TRACKER.resolve()} or path.is_relative_to(RESULTS.resolve()))):
        raise RuntimeError("Durable path is outside owned phase files")
    temporary = path.with_name(path.name + ".writing")
    if temporary.resolve().parent != path.parent:
        raise RuntimeError("Durable temporary path is outside owned directory")
    encoded = io.encoded(value)
    owned_identity = None
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stat = os.fstat(stream.fileno())
            owned_identity = (stat.st_dev, stat.st_ino)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        if owned_identity is not None and temporary.exists():
            stat = temporary.stat()
            if (stat.st_dev, stat.st_ino) == owned_identity:
                temporary.unlink()
        raise


def versions():
    from importlib.metadata import version
    import platform
    import httpx
    import httpcore
    import pydantic
    import pydantic_core
    return {"python": platform.python_version(), "httpx": httpx.__version__,
        "httpcore": httpcore.__version__, "python-dotenv": version("python-dotenv"),
        "pydantic": pydantic.__version__, "pydantic_core": pydantic_core.__version__}


def group_state():
    group = read(GROUP)
    if (group.get("work_id") != WORK_ID or group.get("hard_ceiling") != HARD_CEILING
            or type(group.get("reserved_posts")) is not int
            or not 0 <= group["reserved_posts"] <= HARD_CEILING
            or group.get("status") not in {"active", "closed"}
            or not isinstance(group.get("phases"), list)):
        raise RuntimeError("Work group identity/budget differs")
    names = [row.get("phase") for row in group["phases"]]
    if len(set(names)) != len(names):
        raise RuntimeError("Work group phase identity is ambiguous")
    return group


def cleaned(text):
    return "\n".join(dict.fromkeys(line for line in (
        re.sub(r"\s+", " ", line).strip() for line in text.splitlines()) if line))


def chunks(text, limit):
    # Offline source accounting mirrors the established caption splitter, not a
    # new product engine. Freeze cross-checks these boundaries against runtime.
    parts = []
    while len(text) > limit:
        end = text.rfind("\n", limit // 2, limit + 1)
        if end < 0:
            end = text.rfind(" ", limit // 2, limit + 1)
        if end < 0:
            end = limit
        parts.append(text[:end])
        text = text[end:].lstrip()
    return parts + ([text] if text else [])


def sample_plan():
    manifest = read(CORPUS / "manifest.json")
    samples = []
    for sid, count in zip(SAMPLES, (1, 1, 3)):
        matches = [s for s in manifest["samples"] if s.get("id") == sid]
        if len(matches) != 1:
            raise RuntimeError("Corpus sample identity ambiguous")
        sample = matches[0]
        for filename, checksum in (("file", "sha256"), ("raw_path", "raw_sha256")):
            path = (CORPUS / sample[filename]).resolve()
            if not path.is_relative_to(CORPUS.resolve()) or io.digest(path.read_bytes()) != sample[checksum]:
                raise RuntimeError("Corpus path/hash differs")
        text = cleaned((CORPUS / sample["file"]).read_text(encoding="utf-8"))
        parts = chunks(text, min(CONFIG["llm_summary_chunk_chars"], CONFIG["llm_max_input_chars"]))
        expected = len(parts) + (1 if len(parts) > 1 else 0)
        if not parts or expected != count:
            raise RuntimeError("Source must retain planned 1/1/3 POST shape")
        samples.append({key: sample[key] for key in (
            "id", "file", "raw_path", "sha256", "raw_sha256", "title", "license", "attribution")}
            | {"cleaned_chars": len(text), "cleaned_sha256": io.digest(text),
                "chunks": [io.digest(p) for p in parts], "expected_posts": expected})
    return samples


def plan():
    group = group_state()
    return {"work_id": WORK_ID, "phase": PHASE, "network": False, "dotenv_read": False,
        "maximum_posts": MAX_POSTS, "hard_ceiling": HARD_CEILING,
        "work_reserved_posts": group["reserved_posts"], "config": CONFIG, "samples": sample_plan()}


def asset_paths():
    paths = [Path(__file__), HELPER, PROJECT / "pyproject.toml", PROJECT / "uv.lock",
        PROJECT / "backend/app/config.py", PROJECT / "backend/app/services/llm_service.py",
        PROJECT / "docs/superpowers/specs/2026-10-10-source-first-summary-design.md",
        PROJECT / "docs/acceptance-reports/2026-10-10-source-first-summary/report.md",
        REPORT / "review-criteria.md",
        REPORT.parent / "2026-10-09-adaptive-summary-final/report.md",
        REPORT.parent / "2026-10-09-adaptive-summary-final/review-criteria.md"]
    paths.extend((PROJECT / "backend/app/services").glob("summary_*.py"))
    paths.extend(path for path in CORPUS.rglob("*") if path.is_file())
    paths.extend(path for path in (REPORT.parent / "2026-10-10-source-first-summary/evidence").rglob("*")
                 if path.is_file())
    return sorted(set(paths))


def runtime_config(settings):
    fields = settings.model_dump() if hasattr(settings, "model_dump") else vars(settings)
    return {k: v for k, v in fields.items() if k.startswith("llm_") and k not in {"llm_api_key", "llm_base_url"}}


def runtime():
    sys.path.insert(0, str(PROJECT / "backend"))
    io.load_dotenv(PROJECT / "backend/.env", override=False)
    from app.config import settings
    from app.services import llm_service as service
    for key, value in CONFIG.items():
        setattr(settings, key, value)
    endpoint = service._endpoint()
    parts = urlsplit(endpoint)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise RuntimeError("Endpoint must be HTTPS without credentials/query metadata")
    return settings, service, endpoint


def capture_request(service, text, sample, *, merge=False, source_chars=None):
    """Capture production payload through its injected transport; never send HTTP."""
    class Captured(BaseException):
        pass

    class Capture:
        payload = None

        def post(self, url, *, headers, json):
            self.payload = json
            raise Captured

    client = Capture()
    try:
        service._summary_request(text, title=sample["title"], output_language="zh-CN",
            client=client, merge=merge, source_chars=source_chars)
    except Captured:
        pass
    if client.payload is None:
        raise RuntimeError("Product request planning failed to capture payload")
    return client.payload


def freeze():
    with io.directory_guard(SHARED_LOCK):
        if RESULTS.exists() or TRACKER.exists():
            raise RuntimeError("Phase already allocated; never reopen")
        group = group_state()
        if group["status"] != "active" or any(p["phase"] == PHASE for p in group["phases"]):
            raise RuntimeError("Work group closed or phase already allocated")
        if group["reserved_posts"] + MAX_POSTS > HARD_CEILING:
            raise RuntimeError("Insufficient work group headroom; refuse freeze")
        planned = plan()
        settings, service, endpoint = runtime()
        stages = {}
        for sample in planned["samples"]:
            text = service._summary_input((CORPUS / sample["file"]).read_text(encoding="utf-8"))
            parts = service._summary_chunks(text, CONFIG["llm_summary_chunk_chars"])
            if io.digest(text) != sample["cleaned_sha256"] or [io.digest(p) for p in parts] != sample["chunks"]:
                raise RuntimeError("Product caption preparation differs from offline plan")
            records = [{"stage": "extract", "payload": capture_request(service, p, sample),
                "max_points": service._summary_budget(len(p)).max_points} for p in parts]
            if len(parts) > 1:
                source_chars = sum(len(p) for p in parts)
                records.append({"stage": "merge", "payload": capture_request(service, "", sample,
                    merge=True, source_chars=source_chars), "max_points": service._summary_budget(source_chars).max_points,
                    "source_contexts": [service._source_context(p) for p in parts]})
            stages[sample["id"]] = records
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
        provenance = {"work_id": WORK_ID, "phase": PHASE, "frozen_utc": io.now(),
            "config": CONFIG, "runtime_config": runtime_config(settings), "library_versions": versions(),
            "snapshots": snapshots, "sample_plan": planned["samples"], "stages": stages,
            "model": settings.llm_model, "provider": settings.llm_provider, "endpoint": endpoint,
            "output_language": "zh-CN", "maximum_posts": MAX_POSTS, "hard_ceiling": HARD_CEILING,
            "parent_posts": group["reserved_posts"], "group_at_freeze": group}
        io.exclusive(RESULTS / "provenance.json", provenance)
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


def frozen_state(*, live):
    provenance, ledger, tracker = (read(RESULTS / "provenance.json"),
        read(RESULTS / "request-ledger.json"), read(TRACKER))
    for obj in (provenance, ledger, tracker):
        if obj.get("work_id") != WORK_ID or obj.get("phase") != PHASE or obj.get("maximum_posts") != MAX_POSTS:
            raise RuntimeError("Frozen phase identity differs")
    if (provenance.get("hard_ceiling") != HARD_CEILING or provenance.get("config") != CONFIG
            or provenance.get("output_language") != "zh-CN" or provenance.get("library_versions") != versions()
            or tracker.get("provenance_sha256") != io.digest((RESULTS / "provenance.json").read_bytes())
            or tracker.get("ledger") != str(RESULTS / "request-ledger.json")
            or tracker.get("parent_posts") != provenance.get("parent_posts")
            or tracker.get("hard_ceiling") != HARD_CEILING):
        raise RuntimeError("Frozen codec/configuration/provenance differs")
    rows = ledger.get("requests", [])
    if len(rows) > MAX_POSTS or tracker.get("reserved_posts") != len(rows):
        raise RuntimeError("Frozen reservations differ")
    sequence = [(sid, i, stage["stage"]) for sid in SAMPLES
        for i, stage in enumerate(provenance["stages"][sid], 1)]
    if any((r.get("sample"), r.get("sample_post"), r.get("stage")) != sequence[i - 1]
            or r.get("ordinal") != i for i, r in enumerate(rows, 1)):
        raise RuntimeError("Frozen sample/request order differs")
    snapshots = provenance.get("snapshots", {})
    if not snapshots or "backend/app/services/summary_output.py" not in snapshots:
        raise RuntimeError("Frozen codec snapshot missing")
    for name, record in snapshots.items():
        original, snapshot = (PROJECT / name).resolve(), (RESULTS / record["file"]).resolve()
        if (not original.is_relative_to(PROJECT.resolve())
                or not snapshot.is_relative_to((RESULTS / "snapshots").resolve())
                or io.digest(snapshot.read_bytes()) != record["sha256"]):
            raise RuntimeError("Frozen snapshot path/hash differs")
        if live and io.digest(original.read_bytes()) != record["sha256"]:
            raise RuntimeError("Live asset differs from freeze")
    if live and (set(snapshots) != {p.relative_to(PROJECT).as_posix() for p in asset_paths()}
                 or sample_plan() != provenance["sample_plan"]):
        raise RuntimeError("Live frozen assets/source inventory differs")
    group = group_state()
    matches = [p for p in group["phases"] if p.get("phase") == PHASE]
    if (len(matches) != 1 or matches[0].get("ledger") != tracker["ledger"]
            or matches[0].get("maximum_posts") != MAX_POSTS
            or matches[0].get("tracker") != str(TRACKER)
            or matches[0].get("provenance_sha256") != tracker["provenance_sha256"]
            or matches[0].get("reserved_posts") != len(rows)
            or group["reserved_posts"] < provenance["parent_posts"] + len(rows)):
        raise RuntimeError("Work group phase reservations/identity differs")
    return provenance, ledger, tracker


def check():
    with io.directory_guard(SHARED_LOCK):
        provenance, ledger, tracker = frozen_state(live=True)
        if tracker["status"] != "frozen" or ledger["requests"] or group_state()["status"] != "active":
            raise RuntimeError("Offline check requires a fresh frozen phase")
        receipt = {"phase": PHASE, "provenance_sha256": tracker["provenance_sha256"],
            "network": False, "dotenv_read": False}
        path = RESULTS / "offline-check.json"
        if path.exists():
            if read(path) != receipt:
                raise RuntimeError("Offline check receipt differs")
        else:
            io.exclusive(path, receipt)
        return receipt | {"freeze_valid": True}


def match_runtime(settings, service, endpoint, frozen):
    if (endpoint != frozen["endpoint"] or service._endpoint() != frozen["endpoint"]
            or settings.llm_model != frozen["model"] or settings.llm_provider != frozen["provider"]
            or runtime_config(settings) != frozen["runtime_config"] or versions() != frozen["library_versions"]):
        raise RuntimeError("Runtime model/provider/endpoint/config/codec drift")


def load_codec(frozen):
    record = frozen["snapshots"]["backend/app/services/summary_output.py"]
    path = RESULTS / record["file"]
    # .bin snapshots deliberately retain original bytes, so use a source loader.
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("frozen_summary_codec", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    codec = importlib.util.module_from_spec(spec)
    loader.exec_module(codec)
    return codec


def decoded_response(frozen, ordinal, max_points, codec):
    raw = read(RESULTS / f"response-{ordinal:02d}.json")
    if raw.get("http_status") != 200 or raw.get("model") != frozen["model"] or raw.get("finish_reason") != "stop":
        raise RuntimeError("Raw response model/completion differs")
    content = raw.get("content")
    if not isinstance(content, str):
        raise RuntimeError("Raw public content missing")
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    value = codec.decode_payload(json.loads(content), strict=False)
    summary, points = value.summary.strip(), [p.strip() for p in value.key_points if p.strip()]
    if not summary or not points or len(points) > max_points:
        raise RuntimeError("Raw summary business budget differs")
    return {"summary": summary, "key_points": points, "provider": frozen["provider"], "model": frozen["model"]}


def expected_payload(frozen, sample, sample_post, ledger, codec):
    record = frozen["stages"][sample][sample_post - 1]
    payload = json.loads(json.dumps(record["payload"]))
    if record["stage"] == "merge":
        previous = [r for r in ledger["requests"] if r["sample"] == sample]
        if len(previous) != sample_post - 1:
            raise RuntimeError("Merge requires every extract response")
        notes = []
        for i, row in enumerate(previous):
            value = decoded_response(frozen, row["ordinal"], frozen["stages"][sample][i]["max_points"], codec)
            note = {"section": i + 1, "summary": value["summary"], "key_points": value["key_points"]}
            if record["source_contexts"][i]:
                note["source_context"] = record["source_contexts"][i]
            notes.append(note)
        content = json.dumps(notes, ensure_ascii=False)
        if len(content) > CONFIG["llm_max_input_chars"]:
            raise RuntimeError("Final merge exceeds frozen capacity; refuse extra stages")
        payload["messages"][1]["content"] += content
    return payload


def run(*, transport=None):
    with io.directory_guard(SHARED_LOCK):
        tracker = read(TRACKER)
        if tracker.get("status") != "frozen" or (RESULTS / "result-index.json").exists():
            raise RuntimeError("One-shot phase already started; never reopen")
        receipt = {"phase": PHASE, "provenance_sha256": tracker["provenance_sha256"],
            "network": False, "dotenv_read": False}
        if not (RESULTS / "offline-check.json").exists() or read(RESULTS / "offline-check.json") != receipt:
            raise RuntimeError("Persisted offline check required before run")
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
                            current, current_ledger, current_tracker = frozen_state(live=True)
                            match_runtime(settings, service, endpoint, current)
                            group = group_state()
                            ordinal = len(current_ledger["requests"]) + 1
                            sample_post = ordinal - before
                            if (current_tracker["status"] != "running" or group["status"] != "active"
                                    or ordinal > MAX_POSTS or group["reserved_posts"] >= HARD_CEILING
                                    or sample_post > sample["expected_posts"] or url != endpoint):
                                raise RuntimeError("Unplanned attempt or 5/10 POST budget exceeded")
                            expected = expected_payload(current, sample["id"], sample_post, current_ledger, codec)
                            if json != expected:
                                raise RuntimeError("Actual payload/options/source differ from freeze")
                            path = RESULTS / f"payload-{ordinal:02d}.json"
                            io.exclusive(path, expected)
                            row = {"ordinal": ordinal, "sample": sample["id"], "sample_post": sample_post,
                                "stage": current["stages"][sample["id"]][sample_post - 1]["stage"],
                                "status": "reserved", "reserved_utc": io.now(), "payload_sha256": io.digest(path.read_bytes())}
                            pending = row
                            # Group goes first: crashes can overcount, never allow spent budget back.
                            group["reserved_posts"] += 1
                            phase = next(p for p in group["phases"] if p["phase"] == PHASE)
                            phase.update(status="running", reserved_posts=ordinal)
                            current_ledger["requests"].append(row)
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
                                # Keep attempted reservation even if an earlier durable write failed.
                                durable(GROUP, group)
                                durable(RESULTS / "request-ledger.json", current_ledger)
                                durable(TRACKER, current_tracker)
                                pending = None
                                raise

                    try:
                        summary = service.summarize_text((CORPUS / sample["file"]).read_text(encoding="utf-8"),
                            title=sample["title"], output_language="zh-CN", client=Client())
                        match_runtime(settings, service, endpoint, frozen)
                        frozen_state(live=True)
                        after = read(RESULTS / "request-ledger.json")
                        if len(after["requests"]) != before + sample["expected_posts"]:
                            raise RuntimeError("Sample POST count differs")
                        public = asdict(summary)
                        final = decoded_response(frozen, len(after["requests"]),
                            frozen["stages"][sample["id"]][-1]["max_points"], codec)
                        if public != final:
                            raise RuntimeError("Final result differs from final raw response")
                        result = {"sample": sample["id"], "source_sha256": sample["sha256"], "success": True, "result": public}
                    except Exception as exc:
                        index["stopped_on_error"] = True
                        result = {"sample": sample["id"], "source_sha256": sample["sha256"], "success": False,
                            "error_type": getattr(exc, "error_type", type(exc).__name__)}
                    path = RESULTS / f"{sample['id']}.json"
                    io.exclusive(path, result)
                    result_hash = io.digest(path.read_bytes())
                    ledger = read(RESULTS / "request-ledger.json")
                    for row in ledger["requests"][before:]:
                        row["result_sha256"] = result_hash
                    durable(RESULTS / "request-ledger.json", ledger)
                    index["samples"].append({"sample": sample["id"], "success": result["success"],
                        "result_sha256": result_hash, "posts": len(ledger["requests"]) - before})
                    if index["stopped_on_error"]:
                        break
        except BaseException as exc:
            index.update(stopped_on_error=True, phase_error_type=type(exc).__name__)
            raise
        finally:
            close_phase(index, pending)
        return index


def close_phase(index, pending):
    ledger, tracker, group = read(RESULTS / "request-ledger.json"), read(TRACKER), group_state()
    if pending is not None:
        if len(ledger["requests"]) < pending["ordinal"]:
            ledger["requests"].append(pending)
        for row in ledger["requests"]:
            if row["ordinal"] == pending["ordinal"]:
                row.update(status="error", error_type="ReservationPersistenceFailure")
    for row in ledger["requests"]:
        if row["status"] == "reserved":
            row.update(status="error", error_type="InterruptedAttempt")
    count = len(ledger["requests"])
    index.update(posts=count, ended_utc=io.now())
    tracker.update(status="closed", reserved_posts=count)
    phase = next(p for p in group["phases"] if p["phase"] == PHASE)
    phase.update(status="closed", reserved_posts=count)
    group["reserved_posts"] = max(group["reserved_posts"], tracker["parent_posts"] + count)
    if group["reserved_posts"] >= HARD_CEILING:
        group["status"] = "closed"
    durable(RESULTS / "request-ledger.json", ledger)
    io.exclusive(RESULTS / "result-index.json", index)
    receipt = {"work_id": WORK_ID, "phase": PHASE, "status": "closed", "posts": count,
        "work_posts": group["reserved_posts"], "hard_ceiling": HARD_CEILING,
        "ledger_sha256": io.digest((RESULTS / "request-ledger.json").read_bytes()),
        "index_sha256": io.digest((RESULTS / "result-index.json").read_bytes()),
        "provenance_sha256": tracker["provenance_sha256"]}
    io.exclusive(RESULTS / "closed-receipt.json", receipt)
    tracker["closed_receipt_sha256"] = phase["closed_receipt_sha256"] = io.digest((RESULTS / "closed-receipt.json").read_bytes())
    durable(TRACKER, tracker)
    durable(GROUP, group)


def verify_results():
    frozen, ledger, tracker = frozen_state(live=False)
    index, receipt, group = read(RESULTS / "result-index.json"), read(RESULTS / "closed-receipt.json"), group_state()
    rows, samples = ledger["requests"], index.get("samples", [])
    phase = next(p for p in group["phases"] if p["phase"] == PHASE)
    checksum = io.digest((RESULTS / "closed-receipt.json").read_bytes())
    if (tracker["status"] != "closed" or phase["status"] != "closed"
            or receipt.get("work_id") != WORK_ID or receipt.get("phase") != PHASE or receipt.get("status") != "closed"
            or tracker.get("closed_receipt_sha256") != checksum or phase.get("closed_receipt_sha256") != checksum
            or receipt.get("ledger_sha256") != io.digest((RESULTS / "request-ledger.json").read_bytes())
            or receipt.get("index_sha256") != io.digest((RESULTS / "result-index.json").read_bytes())
            or receipt.get("posts") != len(rows) or receipt.get("work_posts") > group["reserved_posts"]
            or receipt.get("work_posts") > HARD_CEILING or receipt.get("hard_ceiling") != HARD_CEILING
            or receipt.get("provenance_sha256") != tracker["provenance_sha256"]
            or index.get("work_id") != WORK_ID or index.get("posts") != len(rows) or index.get("phase") != PHASE
            or type(index.get("stopped_on_error")) is not bool
            or [s.get("sample") for s in samples] != list(SAMPLES[:len(samples)])):
        raise RuntimeError("Closed phase/group receipt/index differs")
    stopped = index["stopped_on_error"]
    if not stopped and (len(rows) != MAX_POSTS or len(samples) != 3 or any(s.get("success") is not True for s in samples)):
        raise RuntimeError("Successful phase requires all 1/1/3 POSTs")
    if stopped and not (index.get("phase_error_type") or any(s.get("success") is False for s in samples)):
        raise RuntimeError("Stopped phase lacks error disposition")
    codec = load_codec(frozen)
    for i, row in enumerate(rows):
        if row.get("status") not in {"response", "error"}:
            raise RuntimeError("Unclosed attempt")
        path = RESULTS / f"payload-{row['ordinal']:02d}.json"
        if io.digest(path.read_bytes()) != row.get("payload_sha256"):
            raise RuntimeError("Payload hash differs")
        prefix = {"requests": rows[:i]}
        if read(path) != expected_payload(frozen, row["sample"], row["sample_post"], prefix, codec):
            raise RuntimeError("Payload/options/source differs from frozen stage")
        if row.get("response_sha256"):
            path = RESULTS / f"response-{row['ordinal']:02d}.json"
            if io.digest(path.read_bytes()) != row["response_sha256"]:
                raise RuntimeError("Raw response hash differs")
    for item in samples:
        path = RESULTS / f"{item['sample']}.json"
        result = read(path)
        source = next(s for s in frozen["sample_plan"] if s["id"] == item["sample"])
        matching = [r for r in rows if r["sample"] == item["sample"]]
        source_name = (CORPUS / source["file"]).relative_to(PROJECT).as_posix()
        if (io.digest(path.read_bytes()) != item.get("result_sha256")
                or result.get("sample") != item["sample"] or result.get("source_sha256") != source["sha256"]
                or frozen["snapshots"].get(source_name, {}).get("sha256") != source["sha256"]
                or result.get("success") != item.get("success") or item.get("posts") != len(matching)
                or any(r.get("result_sha256") != item["result_sha256"] for r in matching)):
            raise RuntimeError("Result source/hash/attempt ownership differs")
        if item["success"]:
            if len(matching) != source["expected_posts"] or any(r["status"] != "response" for r in matching):
                raise RuntimeError("Sample missing successful stages")
            for row in matching:
                record = frozen["stages"][item["sample"]][row["sample_post"] - 1]
                decoded_response(frozen, row["ordinal"], record["max_points"], codec)
            last = matching[-1]
            final = decoded_response(frozen, last["ordinal"], frozen["stages"][item["sample"]][-1]["max_points"], codec)
            if result.get("result") != final:
                raise RuntimeError("Final public result does not correspond to last raw response")
    return {"evidence_hashes_verified": True, "phase_closed": True, "posts": len(rows),
        "work_posts": receipt["work_posts"], "stopped_on_error": stopped,
        "semantic_quality_verified": False, "provider": frozen["provider"], "model": frozen["model"]}


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
