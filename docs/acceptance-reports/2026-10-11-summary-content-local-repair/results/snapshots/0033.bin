"""One-shot local JSON repair acceptance: same 10 POST group, phase <=5.

The closed first phase and historical 51 POSTs retain their original bytes.
Private adapters reuse the shared lock, durable preallocation and one-shot
closing engine. Plan/check/verify do not read dotenv or send HTTP; root alone
may run. No retry, paid fallback, reasoning persistence or telemetry.
Engineering: skills first; UI primitive/semantic/component tokens; narrow
interfaces; yt-dlp only through ytdlp_service; scene remains read-only.
MIT corpus and derived outputs retain existing CC BY-NC-SA 4.0 attribution.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
RESULTS = REPORT / "results"
PARENT_REPORT = REPORT.parent / "2026-10-11-summary-content-resume"
ADAPTER = PARENT_REPORT / "scripts/evaluate.py"
spec = importlib.util.spec_from_file_location("local_repair_resume_engine", ADAPTER)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
HELPER, CORPUS, SHARED_LOCK = prior.HELPER, prior.CORPUS, prior.SHARED_LOCK
GROUP = prior.GROUP
TRACKER = GROUP.with_name("phase-2.json")
WORK_ID, PHASE = prior.WORK_ID, "summary-thinking-local-json-2"
MAX_POSTS, HARD_CEILING, SAMPLES = prior.MAX_POSTS, prior.HARD_CEILING, prior.SAMPLES
CONFIG = dict(prior.CONFIG)
io, os = prior.io, prior.os
read, versions, runtime_config, sample_plan = prior.read, prior.versions, prior.runtime_config, prior.sample_plan
_original = {name: getattr(prior, name) for name in (
    "base_context", "inventory_paths", "group_state", "plan", "runtime",
    "freeze", "check", "run", "verify_results", "durable", "close_phase")}
_base_load_codec = prior.base.load_codec


def base_context():
    """Redirect two private modules; the old source and results remain untouched."""
    for name in ("PROJECT", "REPORT", "RESULTS", "CORPUS", "GROUP", "TRACKER",
                 "SHARED_LOCK", "WORK_ID", "PHASE", "MAX_POSTS", "HARD_CEILING",
                 "SAMPLES", "CONFIG", "HELPER", "runtime", "versions", "asset_paths",
                 "group_state", "durable", "close_phase"):
        setattr(prior, name, globals()[name])
    prior.base_context = base_context
    _original["base_context"]()
    prior.base.load_codec = load_codec
    prior.base.decoded_response = decoded_response


def load_codec(frozen):
    """Load both schema and lossless JSON decoding from verified .bin snapshots."""
    codec = _base_load_codec(frozen)
    record = frozen["snapshots"]["backend/app/services/summary_json.py"]
    path = (RESULTS / record["file"]).resolve()
    if (not path.is_relative_to((RESULTS / "snapshots").resolve())
            or io.digest(path.read_bytes()) != record["sha256"]):
        raise RuntimeError("Frozen normalizer snapshot path/hash differs")
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("frozen_local_summary_json", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    normalizer = importlib.util.module_from_spec(spec)
    loader.exec_module(normalizer)
    codec.decode_summary_json = normalizer.decode_summary_json
    return codec


def decoded_response(frozen, ordinal, max_points, codec):
    raw = read(RESULTS / f"response-{ordinal:02d}.json")
    if (raw.get("http_status") != 200 or raw.get("model") != frozen["model"]
            or raw.get("finish_reason") != "stop"):
        raise RuntimeError("Raw response model/completion differs")
    content = raw.get("content")
    if not isinstance(content, str):
        raise RuntimeError("Raw public content missing")
    value = codec.decode_payload(codec.decode_summary_json(content), strict=False)
    summary, points = value.summary.strip(), [p.strip() for p in value.key_points if p.strip()]
    if not summary or not points or len(points) > max_points:
        raise RuntimeError("Raw summary business budget differs")
    return {"summary": summary, "key_points": points, "provider": frozen["provider"], "model": frozen["model"]}


def inventory_paths():
    base_context()
    return sorted(set(_original["inventory_paths"]() + [
        Path(__file__), ADAPTER,
        PROJECT / "backend/tests/test_summary_local_repair_evaluation.py",
        PROJECT / "backend/app/services/summary_json.py",
        PARENT_REPORT / "review-criteria.md", GROUP.with_name("phase-1.json"),
        *(PARENT_REPORT / "results" / name for name in (
            "closed-receipt.json", "request-ledger.json", "result-index.json", "provenance.json")),
    ]))


asset_paths = inventory_paths


def group_state():
    base_context()
    return _original["group_state"]()


def plan():
    base_context()
    return _original["plan"]()


def runtime():
    base_context()
    return _original["runtime"]()


def durable(path, value):
    base_context()
    return _original["durable"](path, value)


def close_phase(index, pending):
    base_context()
    return _original["close_phase"](index, pending)


def freeze():
    base_context()
    return _original["freeze"]()


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
