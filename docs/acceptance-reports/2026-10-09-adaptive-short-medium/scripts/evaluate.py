"""One-shot adaptive short/medium transcript verification; maximum two POSTs.

Plan/check are offline and do not read dotenv files. Freeze and run are
separate; any reservation or result prevents reopening this phase.
Engineering: configurable narrow services, LLM only in llm_service, yt-dlp
only in ytdlp_service, scene read-only. MIT-derived source/output: CC BY-NC-SA4.
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
GROUP = PROJECT / ".planning/2026-10-08-summary-quality-finish/budget-group.json"
LONG_TRACKER = PROJECT / ".planning/2026-10-08-summary-quality-finish/budget-continuation.json"
TRACKER = PROJECT / ".planning/2026-10-08-summary-quality-finish/budget-continuation-short-medium.json"
WORK_ID = "summary-quality-finish-20261008"
PHASE = "adaptive-transcript-short-medium"
MAX_POSTS = 2
PRIOR_POSTS = 20
HARD_CEILING = 26
SAMPLES = ("zh-short", "en-medium")
CONFIG = {
    "llm_summary_strategy": "legacy", "llm_summary_length_mode": "adaptive",
    "llm_summary_response_format": "json_object", "llm_summary_thinking_mode": "disabled",
    "llm_summary_chunk_chars": 20000, "llm_max_input_chars": 60000,
    "llm_summary_max_chunks": 16, "llm_summary_max_output_tokens": 4096,
    "llm_summary_output_token_ceiling": 8192, "llm_summary_point_ceiling": 14,
    "llm_summary_source_context_chars": 1200,
}
spec = importlib.util.spec_from_file_location("adaptive_validation_io", HELPER)
io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(io)


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def expected_sample_plan() -> list[dict]:
    manifest = read(CORPUS / "manifest.json")
    expected = []
    for sample_id in SAMPLES:
        sample = next(row for row in manifest["samples"] if row.get("id") == sample_id)
        path = (CORPUS / sample["file"]).resolve()
        if not path.is_relative_to(CORPUS.resolve()):
            raise RuntimeError("Manifest source escaped the frozen corpus")
        raw = path.read_bytes()
        if io.digest(raw) != sample.get("sha256"):
            raise RuntimeError("Original sample differs from manifest")
        clean_lines, seen = [], set()
        for line in raw.decode("utf-8").splitlines():
            normalized = re.sub(r"\s+", " ", line).strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                clean_lines.append(normalized)
        expected.append({"id": sample_id, "file": sample["file"], "title": sample["title"],
            "sha256": sample["sha256"], "cleaned_chars": len("\n".join(clean_lines)),
            "expected_posts": 1, "attribution": sample["attribution"], "license": sample["license"]})
    return expected


def add_tree(paths: list[Path], root: Path) -> None:
    if root.exists():
        paths.extend(path for path in root.rglob("*") if path.is_file())


def assets() -> dict[str, str]:
    paths = [
        Path(__file__), HELPER, GROUP, LONG_TRACKER,
        PROJECT / "AGENTS.md", PROJECT / "docs/handoff-2026-10-09-adaptive.md",
        CORPUS / "manifest.json", CORPUS / "zh-short.txt", CORPUS / "en-medium.txt",
        OLD_REPAIRED / "rubric.json",
        OLD_REPAIRED / "short-medium-semantic-review.md",
        REPORT / "review-criteria.md",
        PROJECT / "backend/app/config.py", PROJECT / "backend/app/services/llm_service.py",
    ]
    paths += list((PROJECT / "backend/app/services").glob("summary_*.py"))
    for root in (OLD_FINAL / "results", OLD_REPAIRED / "results", LONG_REPORT):
        add_tree(paths, root)
    return {str(path.relative_to(PROJECT)): io.digest(path.read_bytes())
            for path in sorted(set(paths))}


def prior_count() -> int:
    group = read(GROUP)
    expected_phases = ["quality-final", "quality-repaired"]
    if (group.get("work_id") != WORK_ID or group.get("status") != "closed"
            or type(group.get("hard_ceiling")) is not int or group["hard_ceiling"] != HARD_CEILING
            or [row.get("phase") for row in group.get("phases", [])] != expected_phases
            or type(group.get("reserved_posts")) is not int or group["reserved_posts"] != 17):
        raise RuntimeError("Historical work group changed; refuse new phase")
    expected_paths = [OLD_FINAL / "results/request-ledger.json",
                      OLD_REPAIRED / "results/request-ledger.json"]
    old_counts = []
    for phase, row, expected_path in zip(expected_phases, group["phases"], expected_paths):
        if Path(row.get("ledger", "")).resolve() != expected_path.resolve():
            raise RuntimeError("Historical ledger path differs from frozen phase identity")
        old_ledger = read(expected_path)
        requests = old_ledger.get("requests", [])
        if (old_ledger.get("phase") != phase or old_ledger.get("ceiling") != 19
                or any(item.get("phase") != phase or item.get("ordinal") != ordinal
                       for ordinal, item in enumerate(requests, 1))):
            raise RuntimeError("Historical ledger identity or ordinals differ")
        old_counts.append(len(requests))
    if old_counts != [3, 14]:
        raise RuntimeError("Historical phase ledgers differ from 3+14")

    continuation = read(LONG_TRACKER)
    long_results = LONG_REPORT / "results"
    long_ledger = read(long_results / "request-ledger.json")
    if (continuation.get("work_id") != WORK_ID or continuation.get("status") != "closed"
            or continuation.get("hard_ceiling") != HARD_CEILING
            or continuation.get("parent_posts") != 17
            or continuation.get("parent_snapshot") != str(GROUP)
            or continuation.get("ledger") != str(long_results / "request-ledger.json")
            or continuation.get("maximum_posts") != 3
            or continuation.get("maximum_work_posts") != 20
            or continuation.get("reserved_posts") != 20
            or long_ledger.get("phase") != "adaptive-transcript-long"
            or long_ledger.get("work_id") != WORK_ID
            or long_ledger.get("prior_posts") != 17
            or long_ledger.get("maximum_posts") != 3
            or len(long_ledger.get("requests", [])) != 3
            or any(row.get("ordinal") != ordinal or row.get("status") != "response"
                   or row.get("http_status") != 200
                   for ordinal, row in enumerate(long_ledger["requests"], 1))
            or read(long_results / "result.json").get("success") is not True):
        raise RuntimeError("Completed adaptive-long phase evidence differs")
    for ordinal, row in enumerate(long_ledger["requests"], 1):
        for name in ("payload", "response"):
            path = long_results / f"{name}-{ordinal:02d}.json"
            if io.digest(path.read_bytes()) != row.get(f"{name}_sha256"):
                raise RuntimeError("Adaptive-long evidence hash mismatch")
    if not 0 <= PRIOR_POSTS + MAX_POSTS <= HARD_CEILING:
        raise RuntimeError("New phase exceeds the fixed work-group ceiling")
    return 17 + len(long_ledger["requests"])


def frozen_state():
    provenance = read(RESULTS / "provenance.json")
    ledger = read(RESULTS / "request-ledger.json")
    tracker = read(TRACKER)
    if (provenance.get("assets") != assets() or provenance.get("config") != CONFIG
            or provenance.get("phase") != PHASE or provenance.get("work_id") != WORK_ID
            or provenance.get("samples") != list(SAMPLES)
            or provenance.get("sample_plan") != expected_sample_plan()
            or provenance.get("prior_posts") != PRIOR_POSTS
            or provenance.get("maximum_posts") != MAX_POSTS
            or provenance.get("maximum_work_posts") != PRIOR_POSTS + MAX_POSTS
            or provenance.get("hard_ceiling") != HARD_CEILING
            or provenance.get("output_language") != "zh-CN"
            or not provenance.get("endpoint") or not provenance.get("provider")
            or not provenance.get("model") or prior_count() != PRIOR_POSTS):
        raise RuntimeError("Frozen inputs, sample order, or prior budget changed")
    if (ledger.get("work_id") != WORK_ID or ledger.get("phase") != PHASE
            or ledger.get("prior_posts") != PRIOR_POSTS or ledger.get("maximum_posts") != MAX_POSTS
            or len(ledger.get("requests", [])) > MAX_POSTS):
        raise RuntimeError("New phase ledger invalid")
    if (tracker.get("work_id") != WORK_ID or tracker.get("phase") != PHASE
            or tracker.get("hard_ceiling") != HARD_CEILING or tracker.get("parent_posts") != PRIOR_POSTS
            or tracker.get("maximum_posts") != MAX_POSTS
            or tracker.get("maximum_work_posts") != PRIOR_POSTS + MAX_POSTS
            or tracker.get("ledger") != str(RESULTS / "request-ledger.json")):
        raise RuntimeError("New phase continuation tracker invalid")
    if tracker.get("reserved_posts") != PRIOR_POSTS + len(ledger.get("requests", [])):
        raise RuntimeError("Phase reservation total does not match its durable ledger")
    return provenance, ledger, tracker


def verify_results() -> dict:
    provenance, ledger, tracker = frozen_state()
    requests = ledger["requests"]
    if tracker.get("status") != "closed" or len(requests) != MAX_POSTS:
        raise RuntimeError("Phase is not closed or did not complete both planned requests")
    index = read(RESULTS / "result-index.json")
    if (index.get("phase") != PHASE or index.get("posts") != MAX_POSTS
            or index.get("stopped_on_error") is not False):
        raise RuntimeError("Phase result index does not confirm both samples completed")
    indexed_samples = index.get("samples", [])
    if [item.get("sample") for item in indexed_samples] != list(SAMPLES):
        raise RuntimeError("Result index does not contain both samples in frozen order")
    for ordinal, row in enumerate(requests, 1):
        if (row.get("ordinal") != ordinal or row.get("sample") != SAMPLES[ordinal - 1]
                or row.get("status") != "response" or row.get("http_status") != 200):
            raise RuntimeError("Request sequence or sample identity changed")
        for name in ("payload", "response"):
            path = RESULTS / f"{name}-{ordinal:02d}.json"
            if not path.exists() or io.digest(path.read_bytes()) != row.get(f"{name}_sha256"):
                raise RuntimeError(f"{name} evidence hash mismatch")
        response = read(RESULTS / f"response-{ordinal:02d}.json")
        if response.get("http_status") != 200 or response.get("choices", [{}])[0].get("finish_reason") != "stop":
            raise RuntimeError("A model request did not finish normally")
        result_path = RESULTS / f"{row['sample']}.json"
        result = read(result_path)
        if (io.digest(result_path.read_bytes()) != row.get("result_sha256")
                or result.get("success") is not True or result.get("sample") != row["sample"]
                or result.get("source_sha256") != provenance["sample_plan"][ordinal - 1]["sha256"]):
            raise RuntimeError("Public result hash mismatch")
        indexed = indexed_samples[ordinal - 1]
        if (indexed.get("success") is not True
                or indexed.get("result_sha256") != io.digest(result_path.read_bytes())):
            raise RuntimeError("Result index hash or success state mismatch")
    if tracker.get("reserved_posts") != PRIOR_POSTS + MAX_POSTS:
        raise RuntimeError("Closed tracker does not reflect both durable reservations")
    return {"evidence_hashes_verified": True, "posts": len(requests),
            "work_posts": PRIOR_POSTS + len(requests), "phase_closed": True,
            "semantic_quality_verified": False, "provider": provenance.get("provider"),
            "model": provenance.get("model")}


def runtime():
    sys.path.insert(0, str(PROJECT / "backend"))
    io.load_dotenv(PROJECT / "backend/.env", override=False)
    from app.config import settings
    from app.services import llm_service as service
    for key, value in CONFIG.items():
        setattr(settings, key, value)
    endpoint = service._endpoint()
    parsed = urlsplit(endpoint)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError("Endpoint contains credential/query metadata")
    return settings, service, endpoint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group()
    flags.add_argument("--freeze", action="store_true")
    flags.add_argument("--check", action="store_true")
    flags.add_argument("--run", action="store_true")
    flags.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    if args.verify:
        print(json.dumps(verify_results(), ensure_ascii=False))
        return
    if args.check:
        provenance, ledger, tracker = frozen_state()
        if tracker.get("status") != "frozen" or ledger.get("requests"):
            raise RuntimeError("Pre-run check requires a fresh frozen phase")
        print(json.dumps({"freeze_valid": True, "network": False, "dotenv_read": False,
                          "prior_posts": PRIOR_POSTS, "maximum_posts": MAX_POSTS,
                          "maximum_work_posts": PRIOR_POSTS + MAX_POSTS,
                          "samples": provenance["sample_plan"]}, ensure_ascii=False))
        return
    if args.run:
        if not RESULTS.exists() or not TRACKER.exists():
            raise RuntimeError("Freeze and check must complete before --run")
        with io.directory_guard(SHARED_LOCK):
            provenance, ledger, tracker = frozen_state()
            if tracker.get("status") != "frozen" or ledger.get("requests") or RESULTS.joinpath("result-index.json").exists():
                raise RuntimeError("One-shot phase already started; never reopen")
            settings, service, endpoint = runtime()
            if (endpoint != provenance.get("endpoint") or settings.llm_provider != provenance.get("provider")
                    or settings.llm_model != provenance.get("model")
                    or any(getattr(settings, key) != value for key, value in CONFIG.items())):
                raise RuntimeError("Runtime does not match frozen phase")
            tracker["status"] = "running"
            io.durable(TRACKER, tracker)
            failed = False
            with __import__("httpx").Client(timeout=float(settings.llm_timeout_seconds)) as http:
                for sample in provenance["sample_plan"]:
                    if len(ledger["requests"]) >= MAX_POSTS:
                        raise RuntimeError("Frozen phase request cap reached")
                    source = (CORPUS / sample["file"]).read_text(encoding="utf-8")

                    class Client:
                        def post(self, url, *, headers, json):
                            current, current_ledger, current_tracker = frozen_state()
                            ordinal = len(current_ledger["requests"]) + 1
                            if (ordinal > MAX_POSTS or sample["id"] != SAMPLES[ordinal - 1]
                                    or url != endpoint or settings.llm_model != current["model"]
                                    or settings.llm_provider != current["provider"]
                                    or any(getattr(settings, key) != value for key, value in CONFIG.items())
                                    or current_tracker.get("status") != "running"):
                                raise RuntimeError("Frozen request budget or runtime changed")
                            payload = RESULTS / f"payload-{ordinal:02d}.json"
                            io.exclusive(payload, json)
                            row = {"ordinal": ordinal, "sample": sample["id"], "status": "reserved",
                                   "reserved_utc": io.now(), "payload_sha256": io.digest(payload.read_bytes())}
                            current_ledger["requests"].append(row)
                            io.durable(RESULTS / "request-ledger.json", current_ledger)
                            current_tracker["reserved_posts"] = PRIOR_POSTS + ordinal
                            io.durable(TRACKER, current_tracker)
                            response = http.post(url, headers=headers, json=json)
                            body = response.json()
                            safe = {key: body[key] for key in ("id", "model", "usage") if key in body}
                            safe["choices"] = [{"finish_reason": choice.get("finish_reason"),
                                "message": {"content": choice.get("message", {}).get("content")}}
                                for choice in body.get("choices", [])]
                            safe["http_status"] = response.status_code
                            safe["received_utc"] = io.now()
                            response_path = RESULTS / f"response-{ordinal:02d}.json"
                            io.exclusive(response_path, safe)
                            row.update(status="response", http_status=response.status_code,
                                       response_sha256=io.digest(response_path.read_bytes()))
                            io.durable(RESULTS / "request-ledger.json", current_ledger)
                            return response

                    before = len(read(RESULTS / "request-ledger.json")["requests"])
                    try:
                        summary = service.summarize_text(source, title=sample["title"],
                            output_language="zh-CN", client=Client())
                        current_ledger = read(RESULTS / "request-ledger.json")
                        if len(current_ledger["requests"]) != before + 1:
                            raise RuntimeError("Sample did not use exactly one POST")
                        result = {"sample": sample["id"], "source_sha256": sample["sha256"],
                                  "result": asdict(summary), "success": True}
                    except Exception as exc:
                        failed = True
                        result = {"sample": sample["id"], "source_sha256": sample["sha256"],
                                  "success": False,
                                  "error_type": getattr(exc, "error_type", type(exc).__name__)}
                    result_path = RESULTS / f"{sample['id']}.json"
                    io.exclusive(result_path, result)
                    current_ledger = read(RESULTS / "request-ledger.json")
                    if current_ledger["requests"] and current_ledger["requests"][-1]["sample"] == sample["id"]:
                        current_ledger["requests"][-1]["result_sha256"] = io.digest(result_path.read_bytes())
                        io.durable(RESULTS / "request-ledger.json", current_ledger)
                    print(json.dumps({"sample": sample["id"], "success": result["success"],
                                      "posts": len(current_ledger["requests"]) - before,
                                      "work_posts": PRIOR_POSTS + len(current_ledger["requests"])}), flush=True)
                    if failed:
                        break
            tracker = read(TRACKER)
            tracker["status"] = "closed"
            tracker["reserved_posts"] = PRIOR_POSTS + len(read(RESULTS / "request-ledger.json")["requests"])
            io.durable(TRACKER, tracker)
            final_ledger = read(RESULTS / "request-ledger.json")
            index_samples = []
            for sample in provenance["sample_plan"]:
                result_path = RESULTS / f"{sample['id']}.json"
                if result_path.exists():
                    sample_result = read(result_path)
                    index_samples.append({"sample": sample["id"], "success": sample_result["success"],
                                          "result_sha256": io.digest(result_path.read_bytes())})
            io.exclusive(RESULTS / "result-index.json", {
                "phase": PHASE, "ended_utc": io.now(), "posts": len(final_ledger["requests"]),
                "stopped_on_error": failed, "samples": index_samples,
            })
        return

    if not args.freeze:
        manifest = read(CORPUS / "manifest.json")
        plans = []
        for sample_id in SAMPLES:
            sample = next(row for row in manifest["samples"] if row["id"] == sample_id)
            source = CORPUS / sample["file"]
            plans.append({"id": sample_id, "source_chars": len(source.read_text(encoding="utf-8")),
                          "source_sha256": io.digest(source.read_bytes()), "expected_posts": 1,
                          "attribution": sample["attribution"], "license": sample["license"]})
        print(json.dumps({"phase": PHASE, "network": False, "dotenv_read": False,
                          "prior_posts": prior_count(), "maximum_posts": MAX_POSTS,
                          "maximum_work_posts": PRIOR_POSTS + MAX_POSTS,
                          "hard_ceiling": HARD_CEILING, "config": CONFIG, "samples": plans}, ensure_ascii=False))
        return

    if RESULTS.exists() or TRACKER.exists():
        raise RuntimeError("New phase already allocated; never reopen")
    with io.directory_guard(SHARED_LOCK):
        if prior_count() != PRIOR_POSTS:
            raise RuntimeError("Unexpected prior work-group total")
        settings, service, endpoint = runtime()
        manifest = read(CORPUS / "manifest.json")
        sample_plan = []
        for sample_id in SAMPLES:
            sample = next(row for row in manifest["samples"] if row["id"] == sample_id)
            source = (CORPUS / sample["file"]).read_text(encoding="utf-8")
            if io.digest((CORPUS / sample["file"]).read_bytes()) != sample["sha256"]:
                raise RuntimeError("Original source differs from manifest")
            chunks = service._summary_chunks(service._summary_input(source), CONFIG["llm_summary_chunk_chars"])
            if len(chunks) != 1:
                raise RuntimeError("Selected sample is not a one-request default-path case")
            sample_plan.append({"id": sample_id, "file": sample["file"], "title": sample["title"],
                "sha256": sample["sha256"], "cleaned_chars": len(service._summary_input(source)),
                "expected_posts": 1, "attribution": sample["attribution"], "license": sample["license"]})
        frozen = {"work_id": WORK_ID, "phase": PHASE, "frozen_utc": io.now(), "assets": assets(),
                  "config": CONFIG, "endpoint": endpoint, "provider": settings.llm_provider,
                  "model": settings.llm_model, "samples": list(SAMPLES), "sample_plan": sample_plan,
                  "prior_posts": PRIOR_POSTS, "maximum_posts": MAX_POSTS,
                  "maximum_work_posts": PRIOR_POSTS + MAX_POSTS, "hard_ceiling": HARD_CEILING,
                  "semantic_basis": [str(OLD_REPAIRED / "rubric.json"),
                                     str(OLD_REPAIRED / "short-medium-semantic-review.md")],
                  "output_language": "zh-CN"}
        RESULTS.mkdir(parents=True)
        io.exclusive(RESULTS / "provenance.json", frozen)
        io.exclusive(RESULTS / "request-ledger.json", {"work_id": WORK_ID, "phase": PHASE,
            "prior_posts": PRIOR_POSTS, "maximum_posts": MAX_POSTS, "requests": []})
        io.exclusive(TRACKER, {"work_id": WORK_ID, "phase": PHASE, "status": "frozen",
            "hard_ceiling": HARD_CEILING, "parent_snapshot": str(GROUP), "parent_posts": PRIOR_POSTS,
            "ledger": str(RESULTS / "request-ledger.json"), "maximum_posts": MAX_POSTS,
            "maximum_work_posts": PRIOR_POSTS + MAX_POSTS, "reserved_posts": PRIOR_POSTS,
            "reason": "User-requested adaptive short/medium regression verification; two prior samples, one POST each"})
        print(json.dumps({"phase": PHASE, "frozen": True, "network": False,
                          "maximum_posts": MAX_POSTS, "maximum_work_posts": PRIOR_POSTS + MAX_POSTS,
                          "samples": sample_plan}, ensure_ascii=False))


if __name__ == "__main__":
    main()
