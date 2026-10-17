"""Phase-10 single-variable global merge guidance contrast; cap one POST.

Reuse phase-9's audited native Responses/accounting engine and phase-8's two
accepted leaves plus complete source. No retry, model/default/limit changes or
failed draft input. Engineering: skills first, mature narrow interfaces, protect
env/accounts/UI/models/history; UI uses three-tier tokens; scene read-only and
yt-dlp confined to its service. Historical assets remain read-only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load(Path(__file__).with_name("native_merge_evaluate.py"), "global_merge_native_base")
PROJECT, REPORT, CORPUS = base.PROJECT, base.REPORT, base.CORPUS
GROUP, SHARED_LOCK, WORK_ID = base.GROUP, base.SHARED_LOCK, base.WORK_ID
CONFIG, SAMPLES, PHASE_POST_CAP = base.CONFIG, base.SAMPLES, 1
read, io = base.read, base.io
_base_assets = base.candidate_assets


def select_phase(phase):
    global PHASE, RESULTS, TRACKER
    if phase != "phase-10":
        raise ValueError("This contrast only allocates fresh phase-10")
    PHASE, RESULTS, TRACKER = phase, REPORT / "results" / phase, GROUP.with_name(phase + ".json")


select_phase("phase-10")


def candidate_assets():
    return sorted(set([*_base_assets(), Path(__file__),
        PROJECT / "backend/tests/test_global_merge_evaluation.py",
        PROJECT / "docs/superpowers/plans/2026-10-15-global-merge-prompt.md",
        REPORT / "reviews/phase-10-global-merge-tool.md",
        *(REPORT / f"phase-{phase}-{kind}.md" for phase in (8, 9)
          for kind in ("report", "content-diagnosis"))]))


def bind():
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "WORK_ID",
                 "PHASE", "RESULTS", "TRACKER", "CONFIG", "SAMPLES"):
        setattr(base, name, globals()[name])
    base.candidate_assets = candidate_assets
    base.bind()


def prior_closed_guard():
    """Keep phase-9's closed metadata checks; it supplies no generation notes."""
    group = base.engine.group_state()
    rows = [row for row in group["phases"] if row.get("phase") == "phase-9"]
    if len(rows) != 1 or rows[0].get("status") != "closed" or rows[0].get("reserved_posts") != 1:
        raise RuntimeError("Expected closed phase-9 with exactly one prior POST")
    # The mature group_state above verifies receipt/ledger/provenance byte bindings.
    own = [row for row in group["phases"] if row.get("phase") == PHASE]
    if group["reserved_posts"] != 15 + sum(row["reserved_posts"] for row in own):
        raise RuntimeError("Phase-10 must continue the existing 15 prior reservations")


def plan():
    bind()
    prior_closed_guard()
    return base.plan()


def freeze():
    bind()
    prior_closed_guard()
    return base.freeze()


def check():
    bind()
    return base.check()


def run(*, transport=None, caller=None):
    bind()
    # Refuse an untrusted historical ledger before the inherited engine marks
    # this phase running; closing also requires valid closed historical rows.
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "RESULTS", "TRACKER"):
        setattr(base.parent, name, globals()[name])
    base.parent.caller_guard(transport=transport, caller=caller)
    with io.directory_guard(SHARED_LOCK):
        prior_closed_guard()
    return base.run(transport=transport, caller=caller)


def verify_results():
    bind()
    return base.verify_results()


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
    print(json.dumps(run(caller=args.caller) if args.run else action(), ensure_ascii=False))


if __name__ == "__main__":
    main()
