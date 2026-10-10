"""One-shot transcript-path evaluation, at most three POSTs within existing 26.

Engineering: skills first, configurable narrow services, UI three-layer tokens,
yt-dlp/HTTP sole service layers, scene read-only. MIT corpus/output CC BY-NC-SA4.
Default/check modes read no credentials and make no network requests.
"""
import argparse
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
RESULTS = REPORT / "results"
GROUP = PROJECT / ".planning/2026-10-08-summary-quality-finish/budget-group.json"
TRACKER = PROJECT / ".planning/2026-10-08-summary-quality-finish/budget-continuation.json"
CORPUS = REPORT.parent / "2026-10-04-natural-subtitle-quality/corpus"
HELPER = REPORT.parent / "2026-10-05-grounded-summary-evidence/scripts/evaluate.py"
LOCK = REPORT.parent / "2026-10-05-grounded-summary/results/.http-session-lock"
WORK_ID, PHASE = "summary-quality-finish-20261008", "adaptive-transcript-long"
CONFIG = {"llm_summary_strategy": "legacy", "llm_summary_length_mode": "adaptive",
          "llm_summary_response_format": "json_object", "llm_summary_thinking_mode": "disabled",
          "llm_summary_chunk_chars": 20000, "llm_max_input_chars": 60000,
          "llm_summary_max_chunks": 16, "llm_summary_max_output_tokens": 4096,
          "llm_summary_output_token_ceiling": 8192, "llm_summary_point_ceiling": 14,
          "llm_summary_source_context_chars": 1200}
spec = importlib.util.spec_from_file_location("adaptive_evidence_io", HELPER)
io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(io)  # Pure existing durable I/O; no runtime or dotenv load.


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def assets():
    paths = [Path(__file__), HELPER, GROUP, CORPUS / "manifest.json", CORPUS / "en-long.txt",
             PROJECT / "backend/app/config.py", PROJECT / "backend/app/services/llm_service.py"]
    paths += list((PROJECT / "backend/app/services").glob("summary_*.py"))
    for phase in ("2026-10-08-summary-quality-final", "2026-10-09-summary-quality-repaired"):
        paths += [p for p in (REPORT.parent / phase / "results").rglob("*") if p.is_file()]
    return {str(path.relative_to(PROJECT)): io.digest(path.read_bytes()) for path in sorted(set(paths))}


def prior_count():
    group = read(GROUP)
    if (group.get("work_id") != WORK_ID or type(group.get("hard_ceiling")) is not int
            or group["hard_ceiling"] != 26 or group.get("status") != "closed"
            or [p["phase"] for p in group["phases"]] != ["quality-final", "quality-repaired"]):
        raise RuntimeError("Unexpected prior work group; refuse POST")
    counts = [len(read(Path(p["ledger"]))["requests"]) for p in group["phases"]]
    if counts != [3, 14] or type(group.get("reserved_posts")) is not int or group["reserved_posts"] != 17:
        raise RuntimeError("Prior reservations differ from seventeen")
    return sum(counts)


def check():
    frozen = read(RESULTS / "provenance.json")
    if frozen["assets"] != assets() or frozen["config"] != CONFIG or prior_count() != 17:
        raise RuntimeError("Frozen inputs changed")
    ledger = read(RESULTS / "request-ledger.json")
    if ledger["work_id"] != WORK_ID or ledger["phase"] != PHASE or not 0 <= len(ledger["requests"]) <= 3:
        raise RuntimeError("Wrong continuation ledger")
    for ordinal, row in enumerate(ledger["requests"], 1):
        if row["ordinal"] != ordinal or type(row["ordinal"]) is not int:
            raise RuntimeError("Invalid ordinal")
        for name in ("payload", "response"):
            if name == "response" and row["status"] != "response":
                continue
            path = RESULTS / f"{name}-{ordinal:02d}.json"
            if io.digest(path.read_bytes()) != row[f"{name}_sha256"]:
                raise RuntimeError("Raw evidence hash mismatch")
    return frozen, ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group()
    flags.add_argument("--run", action="store_true")
    flags.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        _, ledger = check()
        print(json.dumps({"evidence_hashes_verified": True, "posts": len(ledger["requests"]),
                          "work_posts": 17 + len(ledger["requests"]), "semantic_quality_verified": False}))
        return
    if not args.run:
        print(json.dumps({"phase": PHASE, "network": False, "prior_posts": prior_count(),
                          "maximum_posts": 3, "maximum_work_posts": 20, "hard_ceiling": 26, "config": CONFIG}))
        return
    with io.directory_guard(LOCK):
        if RESULTS.exists() or TRACKER.exists():
            raise RuntimeError("One-shot evaluation already allocated; never reopen")
        prior_count()
        sys.path.insert(0, str(PROJECT / "backend"))
        io.load_dotenv(PROJECT / "backend/.env", override=False)
        from app.config import settings
        from app.services import llm_service as service
        import httpx
        for key, value in CONFIG.items():
            setattr(settings, key, value)
        endpoint = service._endpoint()
        parsed = urlsplit(endpoint)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise RuntimeError("Endpoint contains credential/query metadata")
        manifest = read(CORPUS / "manifest.json")
        sample = next(s for s in manifest["samples"] if s["id"] == "en-long")
        source = (CORPUS / sample["file"]).read_text(encoding="utf-8")
        if io.digest((CORPUS / sample["file"]).read_bytes()) != sample["sha256"]:
            raise RuntimeError("Source differs from original corpus")
        chunks = service._summary_chunks(service._summary_input(source), 20000)
        if len(chunks) != 2:
            raise RuntimeError("Unexpected request count")
        frozen = {"work_id": WORK_ID, "phase": PHASE, "frozen_utc": io.now(), "assets": assets(),
                  "config": CONFIG, "endpoint": endpoint, "model": settings.llm_model,
                  "provider": settings.llm_provider, "maximum_posts": 3, "prior_posts": 17,
                  "source_sha256": sample["sha256"], "sample": "en-long", "attribution": sample["attribution"],
                  "license": sample["license"], "output_language": "zh-CN"}
        io.exclusive(RESULTS / "provenance.json", frozen)
        ledger = {"work_id": WORK_ID, "phase": PHASE, "maximum_posts": 3, "prior_posts": 17, "requests": []}
        io.exclusive(RESULTS / "request-ledger.json", ledger)
        tracker = {"work_id": WORK_ID, "hard_ceiling": 26, "parent_snapshot": str(GROUP),
                   "parent_posts": 17, "ledger": str(RESULTS / "request-ledger.json"),
                   "maximum_posts": 3, "maximum_work_posts": 20, "reserved_posts": 17,
                   "reason": "User replaces fixed-length fact-contract goal with finite adaptive transcript summarization",
                   "status": "frozen"}
        io.exclusive(TRACKER, tracker)
        class Client:
            def post(self, url, *, headers, json):
                check()
                if (url != endpoint or settings.llm_model != frozen["model"]
                        or any(getattr(settings, k) != v for k, v in CONFIG.items())
                        or len(ledger["requests"]) >= 3 or 17 + len(ledger["requests"]) >= 26):
                    raise RuntimeError("Finite frozen request budget exceeded")
                ordinal = len(ledger["requests"]) + 1
                path = RESULTS / f"payload-{ordinal:02d}.json"
                io.exclusive(path, json)
                row = {"ordinal": ordinal, "status": "reserved", "reserved_utc": io.now(),
                       "payload_sha256": io.digest(path.read_bytes())}
                ledger["requests"].append(row)
                io.durable(RESULTS / "request-ledger.json", ledger)
                tracker["reserved_posts"] = 17 + len(ledger["requests"])
                io.durable(TRACKER, tracker)  # Both reservations persist BEFORE transport.
                response = http.post(url, headers=headers, json=json)
                body = response.json()
                safe = {k: body[k] for k in ("id", "model", "usage") if k in body}
                safe["choices"] = [{"finish_reason": c.get("finish_reason"),
                    "message": {"content": c.get("message", {}).get("content")}}
                    for c in body.get("choices", [])]
                safe["http_status"] = response.status_code
                safe["received_utc"] = io.now()
                path = RESULTS / f"response-{ordinal:02d}.json"
                io.exclusive(path, safe)
                row.update(status="response", http_status=response.status_code,
                           response_sha256=io.digest(path.read_bytes()))
                io.durable(RESULTS / "request-ledger.json", ledger)
                return response
        try:
            with httpx.Client(timeout=float(settings.llm_timeout_seconds)) as http:
                result = service.summarize_text(source, title=sample["title"], output_language="zh-CN", client=Client())
            public = {"result": asdict(result), "success": True}
        except Exception as exc:
            public = {"success": False, "error_type": getattr(exc, "error_type", type(exc).__name__)}
        finally:
            tracker["status"] = "closed"
            io.durable(TRACKER, tracker)
        io.exclusive(RESULTS / "result.json", public)
        print(json.dumps({"success": public["success"], "posts": len(ledger["requests"]),
                          "work_posts": 17 + len(ledger["requests"]), "hard_ceiling": 26}))


if __name__ == "__main__":
    main()
