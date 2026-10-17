"""Finite normal-profile generation: two fresh leaves and one merge, cap 3.

Reuse the audited accounting engine without changing historical runners.
Engineering: skills first; UI three-tier tokens and both design skills; narrow
interfaces, yt-dlp only through its service, scene read-only. Preserve UI,
accounts/env, local models and all historical evidence. No paid retry/fallback.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import tempfile

ENTRY = Path(__file__).with_name("evaluate.py")
spec = importlib.util.spec_from_file_location("normal_generation_engine", ENTRY)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
PROJECT, REPORT, CORPUS = engine.PROJECT, engine.REPORT, engine.CORPUS
GROUP, SHARED_LOCK, WORK_ID = engine.GROUP, engine.SHARED_LOCK, engine.WORK_ID
SAMPLES, PHASE_POST_CAP = ("en-long",), 3
CONFIG = {key: value for key, value in engine.CONFIG.items()
          if key not in {"llm_model", "llm_provider"}} | {
    "llm_summary_strategy": "legacy", "llm_summary_length_mode": "adaptive",
    "llm_summary_generation_mode": "single", "llm_summary_fidelity_mode": "off",
    "llm_summary_thinking_mode": "auto", "llm_summary_response_format": "auto",
    "llm_summary_max_output_tokens": 4096, "llm_summary_output_token_ceiling": 8192,
    "llm_summary_format_retries": 0, "llm_summary_semantic_retries": 0,
    "llm_summary_max_extra_calls": 0,
}
read, io, os = engine.read, engine.io, engine.os
_live_runtime, _assets = engine.runtime, engine.asset_paths
_samples, _sources, _expected = engine.sample_plan, engine.frozen_sources, engine.expected_payload


def select_phase(phase):
    global PHASE, RESULTS, TRACKER
    if not isinstance(phase, str) or not re.fullmatch(r"phase-[1-9][0-9]*", phase) or int(phase[6:]) < 8:
        raise ValueError("Normal generation requires fresh phase-N with N>=8")
    PHASE = phase
    RESULTS, TRACKER = REPORT / "results" / phase, GROUP.with_name(phase + ".json")


select_phase("phase-8")


def bind():
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "WORK_ID",
                 "PHASE", "RESULTS", "TRACKER", "CONFIG", "SAMPLES"):
        setattr(engine, name, globals()[name])
    engine.asset_paths, engine.runtime = candidate_assets, runtime
    engine.sample_plan, engine.frozen_sources = sample_plan, frozen_sources
    engine.expected_payload = expected_payload


def candidate_assets():
    return sorted(set([*_assets(), Path(__file__),
        PROJECT / "backend/tests/test_long_normal_evaluation.py",
        PROJECT / "backend/tests/test_summary_scope_guidance.py",
        PROJECT / "docs/superpowers/plans/2026-10-15-normal-long-generation.md",
        REPORT / "reviews/phase-7-subject-checks-production-final.md",
        REPORT / "reviews/phase-8-normal-generation-tool.md"]))


def runtime():
    return _live_runtime()


def sample_plan():
    samples = _samples()
    if (len(samples) != 1 or samples[0]["id"] != "en-long"
            or len(samples[0]["chunks"]) != 2 or samples[0]["expected_posts"] != PHASE_POST_CAP):
        raise RuntimeError("Normal generation requires exactly two leaves and one merge, phase cap 3")
    return samples


def frozen_sources(frozen):
    _sources(frozen)
    if (frozen["planned_posts"] != PHASE_POST_CAP or len(frozen["sample_plan"]) != 1
            or frozen["sample_plan"][0]["id"] != "en-long"
            or frozen["sample_plan"][0]["expected_posts"] != PHASE_POST_CAP
            or [stage["stage"] for stage in frozen["stages"]["en-long"]] != ["extract", "extract", "merge"]):
        raise RuntimeError("Frozen normal generation exceeds phase cap 3")


def expected_payload(frozen, sample, sample_post, ledger, codec):
    if sample != "en-long" or not 1 <= sample_post <= PHASE_POST_CAP:
        raise RuntimeError("Unplanned normal generation stage")
    for row in ledger["requests"]:
        payload = RESULTS / f"payload-{row['ordinal']:02d}.json"
        if io.digest(payload.read_bytes()) != row.get("payload_sha256"):
            raise RuntimeError("Prior payload drift before next payment")
        if row.get("response_sha256"):
            raw = RESULTS / f"response-{row['ordinal']:02d}.json"
            if io.digest(raw.read_bytes()) != row["response_sha256"]:
                raise RuntimeError("Prior raw response drift before next payment")
    return _expected(frozen, sample, sample_post, ledger, codec)


def caller_guard(*, transport, caller):
    """Audit declarations are operational checks, not unforgeable identities."""
    if transport is not None:
        real_project = Path(__file__).resolve().parents[4]
        isolated = PROJECT.resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
        owned = (REPORT, CORPUS, GROUP, SHARED_LOCK, RESULTS, TRACKER)
        if (isolated == real_project or isolated.is_relative_to(real_project)
                or real_project.is_relative_to(isolated) or isolated == temp_root
                or not isolated.is_relative_to(temp_root)
                or any(not path.resolve().is_relative_to(isolated) for path in owned)):
            raise RuntimeError("Mock run requires isolated system-temp project and owned paths")
    elif caller != "root" or os.environ.get("CODEX_ACCEPTANCE_CALLER") != "root":
        raise RuntimeError("Real run requires --caller root and CODEX_ACCEPTANCE_CALLER=root")


def plan():
    bind()
    return engine.plan() | {"phase_post_cap": PHASE_POST_CAP}


def freeze():
    bind()
    return engine.freeze() | {"phase_post_cap": PHASE_POST_CAP}


def check():
    bind()
    return engine.check() | {"phase_post_cap": PHASE_POST_CAP}


def run(*, transport=None, caller=None):
    caller_guard(transport=transport, caller=caller)
    bind()
    return engine.run(transport=transport)


def verify_results():
    bind()
    return engine.verify_results() | {"phase_post_cap": PHASE_POST_CAP}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--caller", choices=("root",))
    flags = parser.add_mutually_exclusive_group(required=True)
    for name in ("plan", "freeze", "check", "run", "verify"):
        flags.add_argument(f"--{name}", action="store_true")
    args = parser.parse_args(argv)
    select_phase(args.phase)
    action = plan if args.plan else freeze if args.freeze else check if args.check else verify_results
    result = run(caller=args.caller) if args.run else action()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
