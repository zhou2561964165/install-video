"""Final one-shot repair verification: the last 2 POSTs of the 26-POST work group.

Plan/check/verify never import product configuration or read dotenv. Freeze reads
runtime explicitly and sends no HTTP. Root alone runs this phase after offline
review. Engineering: skills first, UI three-layer tokens, narrow interfaces,
yt-dlp only ytdlp_service, scene read-only; source/output retain CC BY-NC-SA4.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib.util
import json
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
OLD_FINAL = REPORT.parent / "2026-10-08-summary-quality-final"
OLD_REPAIRED = REPORT.parent / "2026-10-09-summary-quality-repaired"
LONG_REPORT = REPORT.parent / "2026-10-09-adaptive-summary"
SHORT_REPORT = REPORT.parent / "2026-10-09-adaptive-short-medium"
REPAIR_REPORT = REPORT.parent / "2026-10-09-adaptive-summary-repair"
REPAIR_RUNNER = REPAIR_REPORT / "scripts/evaluate.py"
GROUP = PROJECT / ".planning/2026-10-08-summary-quality-finish/budget-group.json"
LONG_TRACKER = GROUP.with_name("budget-continuation.json")
SHORT_TRACKER = GROUP.with_name("budget-continuation-short-medium.json")
REPAIR_TRACKER = GROUP.with_name("budget-continuation-repair.json")
TRACKER = GROUP.with_name("budget-continuation-repair-final.json")
WORK_ID = "summary-quality-finish-20261008"
PHASE = "adaptive-transcript-repair-final"
MAX_POSTS, PRIOR_POSTS, HARD_CEILING = 2, 24, 26
SAMPLES = ("zh-short", "en-medium")
CONFIG = {
    "llm_summary_strategy": "legacy", "llm_summary_length_mode": "adaptive",
    "llm_summary_response_format": "json_object", "llm_summary_thinking_mode": "disabled",
    "llm_summary_chunk_chars": 20000, "llm_max_input_chars": 60000,
    "llm_summary_max_chunks": 16, "llm_summary_max_output_tokens": 4096,
    "llm_summary_output_token_ceiling": 8192, "llm_summary_point_ceiling": 14,
    "llm_summary_source_context_chars": 1200,
}
spec = importlib.util.spec_from_file_location("repair_validation_io", HELPER)
io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(io)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sample_plan():
    manifest = read(CORPUS / "manifest.json")
    samples = []
    for sid in SAMPLES:
        matches = [row for row in manifest["samples"] if row.get("id") == sid]
        if len(matches) != 1:
            raise RuntimeError("Source manifest sample identity is ambiguous")
        sample = matches[0]
        path = (CORPUS / sample["file"]).resolve()
        if not path.is_relative_to(CORPUS.resolve()) or io.digest(path.read_bytes()) != sample["sha256"]:
            raise RuntimeError("Source path/hash differs from original manifest")
        clean = list(dict.fromkeys(line for line in (
            re.sub(r"\s+", " ", line).strip() for line in path.read_text(encoding="utf-8").splitlines()) if line))
        if not clean or len("\n".join(clean)) > min(CONFIG["llm_summary_chunk_chars"], CONFIG["llm_max_input_chars"]):
            raise RuntimeError("Selected source is not exactly one summary POST")
        samples.append({key: sample[key] for key in ("id", "file", "title", "sha256", "license", "attribution")}
                       | {"cleaned_chars": len("\n".join(clean)), "expected_posts": 1})
    return samples


def prior_count():
    group = read(GROUP)
    phases = ("quality-final", "quality-repaired")
    ledgers = (OLD_FINAL / "results/request-ledger.json", OLD_REPAIRED / "results/request-ledger.json")
    if (group.get("work_id") != WORK_ID or group.get("status") != "closed"
            or type(group.get("hard_ceiling")) is not int or group["hard_ceiling"] != 26
            or type(group.get("reserved_posts")) is not int or group["reserved_posts"] != 17
            or [row.get("phase") for row in group.get("phases", [])] != list(phases)):
        raise RuntimeError("Historical closed work group differs")
    for phase, path, count, row in zip(phases, ledgers, (3, 14), group["phases"]):
        old = read(path)
        if (Path(row.get("ledger", "")).resolve() != path.resolve() or row.get("ceiling") != 19
                or old.get("phase") != phase or old.get("ceiling") != 19
                or len(old.get("requests", [])) != count
                or any(item.get("phase") != phase or item.get("ordinal") != i
                       for i, item in enumerate(old["requests"], 1))):
            raise RuntimeError("Historical 3+14 ledger identities or counts differ")
    for root, path, phase, parent, count in (
            (LONG_REPORT, LONG_TRACKER, "adaptive-transcript-long", 17, 3),
            (SHORT_REPORT, SHORT_TRACKER, "adaptive-transcript-short-medium", 20, 2)):
        tracker, ledger = read(path), read(root / "results/request-ledger.json")
        expected = {"work_id": WORK_ID, "status": "closed", "hard_ceiling": 26,
            "parent_snapshot": str(GROUP), "parent_posts": parent, "maximum_posts": count,
            "maximum_work_posts": parent + count, "reserved_posts": parent + count,
            "ledger": str(root / "results/request-ledger.json")}
        if (any(tracker.get(k) != v for k, v in expected.items())
                or (count == 2 and tracker.get("phase") != phase)
                or ledger.get("work_id") != WORK_ID or ledger.get("phase") != phase
                or ledger.get("prior_posts") != parent or ledger.get("maximum_posts") != count
                or len(ledger.get("requests", [])) != count):
            raise RuntimeError("Historical closed adaptive phase budget differs")
        for i, row in enumerate(ledger["requests"], 1):
            if row.get("ordinal") != i or row.get("status") != "response" or row.get("http_status") != 200:
                raise RuntimeError("Historical adaptive attempt state differs")
            for name in ("payload", "response"):
                if io.digest((root / f"results/{name}-{i:02d}.json").read_bytes()) != row.get(f"{name}_sha256"):
                    raise RuntimeError("Historical adaptive evidence hash differs")
        if count == 3:
            if read(root / "results/result.json").get("success") is not True:
                raise RuntimeError("Historical long result failed")
        else:
            index = read(root / "results/result-index.json")
            if (index.get("phase") != phase or index.get("posts") != 2 or index.get("stopped_on_error") is not False
                    or [row.get("sample") for row in index.get("samples", [])] != list(SAMPLES)
                    or any(row.get("success") is not True for row in index["samples"])):
                raise RuntimeError("Historical short-medium completion differs")
    prior_tracker = read(REPAIR_TRACKER)
    expected = {"work_id": WORK_ID, "phase": "adaptive-transcript-repair", "status": "closed",
        "parent_snapshot": str(GROUP), "parent_posts": 22, "hard_ceiling": 26,
        "maximum_posts": 2, "maximum_work_posts": 24, "reserved_posts": 24,
        "ledger": str(REPAIR_REPORT / "results/request-ledger.json")}
    provenance_path = REPAIR_REPORT / "results/provenance.json"
    if (any(prior_tracker.get(k) != v for k, v in expected.items())
            or prior_tracker.get("provenance_sha256") != io.digest(provenance_path.read_bytes())):
        raise RuntimeError("Historical closed repair budget or provenance differs")
    provenance = read(provenance_path)
    # Execute only the exact runner/helper already frozen in the closed phase.
    for path in (REPAIR_RUNNER, HELPER):
        frozen = provenance.get("snapshots", {}).get(str(path.relative_to(PROJECT)))
        if not frozen or io.digest(path.read_bytes()) != frozen.get("sha256"):
            raise RuntimeError("Historical repair runner/helper differs from frozen bytes")
    verified = load_repair_verifier().verify_results()
    if (verified.get("evidence_hashes_verified") is not True or verified.get("phase_closed") is not True
            or verified.get("posts") != 2 or verified.get("work_posts") != 24
            or verified.get("stopped_on_error") is not False):
        raise RuntimeError("Historical repair evidence does not close exactly 2 POSTs at total 24")
    return PRIOR_POSTS


def load_repair_verifier():
    spec = importlib.util.spec_from_file_location("closed_repair_verifier", REPAIR_RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Explicit identities also let temporary fixtures reuse the immutable verifier.
    for key in ("PROJECT", "CORPUS", "GROUP", "LONG_TRACKER", "SHORT_TRACKER"):
        setattr(module, key, globals()[key])
    module.REPORT, module.RESULTS, module.TRACKER = REPAIR_REPORT, REPAIR_REPORT / "results", REPAIR_TRACKER
    return module


def asset_paths():
    paths = [Path(__file__), HELPER, GROUP, LONG_TRACKER, SHORT_TRACKER, REPAIR_TRACKER,
        CORPUS / "manifest.json", CORPUS / "zh-short.txt", CORPUS / "en-medium.txt",
        OLD_REPAIRED / "rubric.json", OLD_REPAIRED / "short-medium-semantic-review.md",
        SHORT_REPORT / "review-criteria.md", REPAIR_REPORT / "review-criteria.md", REPORT / "review-criteria.md",
        PROJECT / "backend/app/config.py", PROJECT / "backend/app/services/llm_service.py"]
    paths.extend((PROJECT / "backend/app/services").glob("summary_*.py"))
    paths.extend(path for path in (REPAIR_REPORT / "scripts").rglob("*") if path.is_file()
                 and "__pycache__" not in path.parts)
    for root in (OLD_FINAL, OLD_REPAIRED, LONG_REPORT, SHORT_REPORT, REPAIR_REPORT):
        paths.extend(path for path in (root / "results").rglob("*") if path.is_file())
    return sorted(set(paths))


def runtime_config(settings):
    fields = settings.model_dump() if hasattr(settings, "model_dump") else vars(settings)
    return {key: value for key, value in fields.items() if key.startswith("llm_")
            and key not in {"llm_api_key", "llm_base_url"}}


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
        raise RuntimeError("Endpoint contains unsafe credential/query metadata or is not HTTPS")
    return settings, service, endpoint


def plan():
    return {"phase": PHASE, "network": False, "dotenv_read": False, "prior_posts": prior_count(),
        "maximum_posts": MAX_POSTS, "maximum_work_posts": PRIOR_POSTS + MAX_POSTS, "hard_ceiling": 26,
        "config": CONFIG, "samples": sample_plan()}


def freeze():
    if RESULTS.exists() or TRACKER.exists():
        raise RuntimeError("Repair phase already allocated; never reopen")
    with io.directory_guard(SHARED_LOCK):
        if RESULTS.exists() or TRACKER.exists():
            raise RuntimeError("Repair phase already allocated; never reopen")
        planned = plan()
        settings, service, endpoint = runtime()
        for sample in planned["samples"]:
            source = (CORPUS / sample["file"]).read_text(encoding="utf-8")
            if (len(service._summary_chunks(service._summary_input(source), min(
                    CONFIG["llm_summary_chunk_chars"], CONFIG["llm_max_input_chars"]))) != 1
                    or len(service._summary_input(source)) != sample["cleaned_chars"]):
                raise RuntimeError("Product source preparation differs from offline sample plan")
        raw_assets = [(str(path.relative_to(PROJECT)), path.read_bytes()) for path in asset_paths()]
        snapshots = {name: {"file": f"snapshots/{i:04d}.bin", "sha256": io.digest(raw)}
                     for i, (name, raw) in enumerate(raw_assets, 1)}
        RESULTS.mkdir(parents=True)
        for name, raw in raw_assets:
            path = RESULTS / snapshots[name]["file"]
            path.parent.mkdir(exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                __import__("os").fsync(stream.fileno())
        provenance = {"work_id": WORK_ID, "phase": PHASE, "frozen_utc": io.now(),
            "snapshots": snapshots, "config": CONFIG, "runtime_config": runtime_config(settings),
            "endpoint": endpoint, "provider": settings.llm_provider, "model": settings.llm_model,
            "sample_plan": planned["samples"], "samples": list(SAMPLES), "output_language": "zh-CN",
            "prior_posts": PRIOR_POSTS, "maximum_posts": 2, "maximum_work_posts": PRIOR_POSTS + MAX_POSTS, "hard_ceiling": 26}
        io.exclusive(RESULTS / "provenance.json", provenance)
        io.exclusive(RESULTS / "request-ledger.json", {"work_id": WORK_ID, "phase": PHASE,
            "prior_posts": PRIOR_POSTS, "maximum_posts": 2, "requests": []})
        io.exclusive(TRACKER, {"work_id": WORK_ID, "phase": PHASE, "status": "frozen",
            "parent_snapshot": str(GROUP), "parent_posts": PRIOR_POSTS, "hard_ceiling": 26,
            "maximum_posts": 2, "maximum_work_posts": PRIOR_POSTS + MAX_POSTS, "reserved_posts": PRIOR_POSTS,
            "ledger": str(RESULTS / "request-ledger.json"),
            "provenance_sha256": io.digest((RESULTS / "provenance.json").read_bytes()),
            "reason": "Final finite validation of overview/detail separation and claim qualifiers; stop at 26 work POSTs"})
        return {"phase": PHASE, "frozen": True, "network": False, "maximum_work_posts": PRIOR_POSTS + MAX_POSTS}


def frozen_state(*, live):
    provenance, ledger, tracker = (read(RESULTS / "provenance.json"),
        read(RESULTS / "request-ledger.json"), read(TRACKER))
    identity = {"work_id": WORK_ID, "phase": PHASE, "prior_posts": PRIOR_POSTS, "maximum_posts": 2}
    if (any(provenance.get(k) != v or ledger.get(k) != v for k, v in identity.items())
            or provenance.get("maximum_work_posts") != PRIOR_POSTS + MAX_POSTS or provenance.get("hard_ceiling") != 26
            or provenance.get("config") != CONFIG or provenance.get("samples") != list(SAMPLES)
            or provenance.get("output_language") != "zh-CN" or not provenance.get("model")
            or not provenance.get("provider") or not provenance.get("endpoint")):
        raise RuntimeError("Frozen phase identity or configuration differs")
    expected = {"work_id": WORK_ID, "phase": PHASE, "parent_posts": PRIOR_POSTS, "hard_ceiling": 26,
        "maximum_posts": 2, "maximum_work_posts": PRIOR_POSTS + MAX_POSTS, "parent_snapshot": str(GROUP),
        "ledger": str(RESULTS / "request-ledger.json"),
        "provenance_sha256": io.digest((RESULTS / "provenance.json").read_bytes())}
    requests = ledger.get("requests", [])
    if (any(tracker.get(k) != v for k, v in expected.items()) or len(requests) > 2
            or tracker.get("reserved_posts") != PRIOR_POSTS + len(requests)
            or any(row.get("ordinal") != i or row.get("sample") != SAMPLES[i - 1]
                   for i, row in enumerate(requests, 1))):
        raise RuntimeError("Phase durable reservations or identity differ")
    snapshots = provenance.get("snapshots", {})
    if not snapshots:
        raise RuntimeError("Frozen snapshot list is empty")
    for name, record in snapshots.items():
        snapshot = (RESULTS / record["file"]).resolve()
        original = (PROJECT / name).resolve()
        if (not snapshot.is_relative_to((RESULTS / "snapshots").resolve())
                or not original.is_relative_to(PROJECT.resolve())
                or io.digest(snapshot.read_bytes()) != record["sha256"]):
            raise RuntimeError("Frozen snapshot path/hash mismatch")
        if live and io.digest(original.read_bytes()) != record["sha256"]:
            raise RuntimeError("Current asset/input differs from frozen snapshot")
    if live and (set(snapshots) != {str(p.relative_to(PROJECT)) for p in asset_paths()}
                 or provenance["sample_plan"] != sample_plan() or prior_count() != PRIOR_POSTS):
        raise RuntimeError("Frozen source/assets or prior budget changed")
    return provenance, ledger, tracker


def check():
    provenance, ledger, tracker = frozen_state(live=True)
    if tracker.get("status") != "frozen" or ledger["requests"]:
        raise RuntimeError("Offline check requires a fresh frozen phase")
    path = RESULTS / "offline-check.json"
    receipt = {"phase": PHASE, "provenance_sha256": tracker["provenance_sha256"],
        "network": False, "dotenv_read": False}
    if path.exists():
        if read(path) != receipt:
            raise RuntimeError("Offline check receipt differs")
    else:
        io.exclusive(path, receipt)
    return receipt | {"freeze_valid": True, "prior_posts": PRIOR_POSTS, "maximum_work_posts": PRIOR_POSTS + MAX_POSTS}


def match_runtime(settings, endpoint, provenance):
    if (endpoint != provenance["endpoint"] or settings.llm_provider != provenance["provider"]
            or settings.llm_model != provenance["model"] or runtime_config(settings) != provenance["runtime_config"]):
        raise RuntimeError("Runtime endpoint/model/provider/config differs from freeze")


def run(*, transport=None):
    with io.directory_guard(SHARED_LOCK):
        provenance, ledger, tracker = frozen_state(live=True)
        if tracker.get("status") != "frozen" or ledger["requests"] or (RESULTS / "result-index.json").exists():
            raise RuntimeError("One-shot phase already started; never reopen")
        receipt = RESULTS / "offline-check.json"
        if not receipt.exists() or read(receipt) != {"phase": PHASE,
                "provenance_sha256": tracker["provenance_sha256"], "network": False, "dotenv_read": False}:
            raise RuntimeError("Persisted offline check must complete before run")
        settings, service, endpoint = runtime()
        match_runtime(settings, endpoint, provenance)
        tracker["status"] = "running"
        io.durable(TRACKER, tracker)
        from contextlib import nullcontext
        index = {"phase": PHASE, "posts": 0, "stopped_on_error": False, "samples": []}
        try:
            manager = nullcontext(transport) if transport is not None else __import__("httpx").Client(
                timeout=float(settings.llm_timeout_seconds))
            with manager as http:
                for sample in provenance["sample_plan"]:
                    source = (CORPUS / sample["file"]).read_text(encoding="utf-8")

                    class Client:
                        def post(self, url, *, headers, json):
                            current, current_ledger, current_tracker = frozen_state(live=True)
                            match_runtime(settings, endpoint, current)
                            ordinal = len(current_ledger["requests"]) + 1
                            if (ordinal > 2 or sample["id"] != SAMPLES[ordinal - 1]
                                    or current_tracker.get("status") != "running" or url != endpoint
                                    or json.get("model") != current["model"]):
                                raise RuntimeError("Frozen request sequence or budget differs")
                            payload = RESULTS / f"payload-{ordinal:02d}.json"
                            io.exclusive(payload, json)
                            row = {"ordinal": ordinal, "sample": sample["id"], "status": "reserved",
                                "reserved_utc": io.now(), "payload_sha256": io.digest(payload.read_bytes())}
                            current_ledger["requests"].append(row)
                            io.durable(RESULTS / "request-ledger.json", current_ledger)
                            current_tracker["reserved_posts"] = PRIOR_POSTS + ordinal
                            try:
                                io.durable(TRACKER, current_tracker)
                                response = http.post(url, headers=headers, json=json)
                                try:
                                    body = response.json()
                                except ValueError:
                                    body = None
                                safe = {"http_status": response.status_code, "received_utc": io.now(),
                                    "body_is_json": isinstance(body, dict)}
                                if isinstance(body, dict):
                                    safe.update({k: body[k] for k in ("id", "model", "usage") if k in body})
                                    choices = body.get("choices", [])
                                    safe["choices"] = [{"finish_reason": c.get("finish_reason"),
                                        "message": {"content": c.get("message", {}).get("content")}}
                                        for c in choices if isinstance(c, dict) and isinstance(c.get("message", {}), dict)] if isinstance(choices, list) else []
                                path = RESULTS / f"response-{ordinal:02d}.json"
                                io.exclusive(path, safe)
                                row.update(status="response", http_status=response.status_code,
                                    response_sha256=io.digest(path.read_bytes()))
                                io.durable(RESULTS / "request-ledger.json", current_ledger)
                                return response
                            except BaseException as exc:
                                row.update(status="error", error_type=type(exc).__name__)
                                io.durable(RESULTS / "request-ledger.json", current_ledger)
                                raise

                    before = len(read(RESULTS / "request-ledger.json")["requests"])
                    try:
                        summary = service.summarize_text(source, title=sample["title"],
                            output_language="zh-CN", client=Client())
                        match_runtime(settings, endpoint, provenance)
                        after = read(RESULTS / "request-ledger.json")
                        if len(after["requests"]) != before + 1:
                            raise RuntimeError("Sample must use exactly one POST")
                        result = {"sample": sample["id"], "source_sha256": sample["sha256"],
                            "success": True, "result": asdict(summary)}
                    except Exception as exc:
                        index["stopped_on_error"] = True
                        result = {"sample": sample["id"], "source_sha256": sample["sha256"],
                            "success": False, "error_type": getattr(exc, "error_type", type(exc).__name__)}
                    path = RESULTS / f"{sample['id']}.json"
                    io.exclusive(path, result)
                    current_ledger = read(RESULTS / "request-ledger.json")
                    result_hash = io.digest(path.read_bytes())
                    if len(current_ledger["requests"]) > before:
                        current_ledger["requests"][-1]["result_sha256"] = result_hash
                        io.durable(RESULTS / "request-ledger.json", current_ledger)
                    index["samples"].append({"sample": sample["id"], "success": result["success"],
                        "result_sha256": result_hash})
                    if index["stopped_on_error"]:
                        break
        except BaseException as exc:
            index["stopped_on_error"] = True
            index["phase_error_type"] = type(exc).__name__
            raise
        finally:
            index["posts"] = len(read(RESULTS / "request-ledger.json")["requests"])
            index["ended_utc"] = io.now()
            io.exclusive(RESULTS / "result-index.json", index)
            tracker = read(TRACKER)
            tracker.update(status="closed", reserved_posts=PRIOR_POSTS + index["posts"])
            io.durable(TRACKER, tracker)
        return index


def verify_results():
    provenance, ledger, tracker = frozen_state(live=False)
    index = read(RESULTS / "result-index.json")
    requests, samples = ledger["requests"], index.get("samples", [])
    if (tracker.get("status") != "closed" or index.get("phase") != PHASE
            or index.get("posts") != len(requests) or type(index.get("stopped_on_error")) is not bool
            or [item.get("sample") for item in samples] != list(SAMPLES[:len(samples)])
            or len(samples) > 2):
        raise RuntimeError("Closed phase index or sample order differs")
    stopped = index["stopped_on_error"]
    if stopped and not (index.get("phase_error_type") or any(s.get("success") is False for s in samples)):
        raise RuntimeError("Failure disposition has no failed result or phase error")
    if not stopped and (len(requests) != 2 or len(samples) != 2 or any(s.get("success") is not True for s in samples)):
        raise RuntimeError("Normal phase did not complete both samples")
    for item in samples:
        path = RESULTS / f"{item['sample']}.json"
        result = read(path)
        source = provenance["sample_plan"][SAMPLES.index(item["sample"])]
        if (io.digest(path.read_bytes()) != item.get("result_sha256")
                or result.get("success") != item.get("success") or result.get("sample") != item["sample"]
                or result.get("source_sha256") != source["sha256"]):
            raise RuntimeError("Public result source/hash or state differs")
        source_record = provenance["snapshots"].get(str((CORPUS / source["file"]).relative_to(PROJECT)))
        if not source_record or source_record["sha256"] != source["sha256"]:
            raise RuntimeError("Result source is not bound to frozen source snapshot")
        if item.get("success") is True:
            matches = [row for row in requests if row.get("sample") == item["sample"]]
            if len(matches) != 1 or matches[0].get("result_sha256") != item["result_sha256"]:
                raise RuntimeError("Successful sample requires one unique request with its result hash")
    for row in requests:
        ordinal = row["ordinal"]
        if row.get("status") not in {"response", "error"}:
            raise RuntimeError("Attempt left reserved without final response/error state")
        for name in ("payload", "response"):
            if name == "response" and row["status"] == "error" and not row.get("response_sha256"):
                continue
            path = RESULTS / f"{name}-{ordinal:02d}.json"
            if io.digest(path.read_bytes()) != row.get(f"{name}_sha256"):
                raise RuntimeError("Request/raw response evidence hash mismatch")
        payload = read(RESULTS / f"payload-{ordinal:02d}.json")
        if payload.get("model") != provenance["model"]:
            raise RuntimeError("Payload model differs")
        matches = [s for s in samples if s["sample"] == row["sample"]]
        if matches and row.get("result_sha256") != matches[0]["result_sha256"]:
            raise RuntimeError("Attempt result hash differs")
        if matches and matches[0]["success"]:
            response = read(RESULTS / f"response-{ordinal:02d}.json")
            choice = response.get("choices", [{}])[0]
            if (row["status"] != "response" or row.get("http_status") != 200
                    or response.get("http_status") != 200 or choice.get("finish_reason") != "stop"):
                raise RuntimeError("Successful result lacks a completed raw response")
            raw = choice.get("message", {}).get("content")
            if not isinstance(raw, str):
                raise RuntimeError("Raw response content missing")
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
            decoded = json.loads(raw)
            public = read(RESULTS / f"{row['sample']}.json")["result"]
            if (public.get("summary") != decoded["summary"].strip()
                    or public.get("key_points") != [p.strip() for p in decoded["key_points"] if p.strip()]
                    or public.get("provider") != provenance["provider"] or public.get("model") != provenance["model"]):
                raise RuntimeError("Public result does not correspond to raw response")
    return {"evidence_hashes_verified": True, "phase_closed": True, "posts": len(requests),
        "work_posts": PRIOR_POSTS + len(requests), "stopped_on_error": stopped, "semantic_quality_verified": False,
        "provider": provenance["provider"], "model": provenance["model"]}


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
