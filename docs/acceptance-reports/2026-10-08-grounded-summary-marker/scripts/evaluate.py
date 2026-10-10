"""One bounded follow-up after the offline-verified extraction marker fix.

Skills first; narrow configurable modules, UI three-layer tokens, LLM/yt-dlp
service boundaries, scene read-only. Preserve old frozen evidence and attributed
MIT corpus/rubric under CC BY-NC-SA 4.0. Offline default; root is the only caller.
"""
import argparse
import importlib.util
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
CORE = REPORT.parent / "2026-10-08-grounded-summary-normalized/scripts/evaluate.py"
CHECKER_CORE = CORE.with_name("check_evidence.py")
CHECKER = Path(__file__).with_name("check_evidence.py")
spec = importlib.util.spec_from_file_location("marker_evaluation_core", CORE)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
PHASE, CEILING = "normalized-marker", 16
core.REPORT, core.RESULTS = REPORT, REPORT / "results"
core.LEDGER, core.PHASE, core.CEILING = core.RESULTS / "request-ledger.json", PHASE, CEILING
core.CHECKER = CHECKER
core.CONFIG = {**core.CONFIG, "llm_summary_max_extra_calls": 1}
_snapshot, _validate_group = core.snapshot, core.validate_group


def validate_group():
    # initial_phase_ceiling describes the closed first phase, not this phase.
    current = core.CEILING
    try:
        core.CEILING = 19
        return _validate_group()
    finally:
        core.CEILING = current


def snapshot():
    frozen = _snapshot()
    for sample in frozen["samples"]:
        sample["maximum_posts"] = sample["expected_posts"] + 1
    frozen["runner_chain_sha256"].update(revision_entry=core.base.digest(Path(__file__).read_bytes()),
                                         checker_core=core.base.digest(CHECKER_CORE.read_bytes()))
    return frozen


class BudgetClient(core.BudgetClient):
    def _post(self, url, *, headers, json):
        if "repair" in core.read_user(json):
            calls = [r for r in core.validate_ledger()["requests"] if r["sample"] == self.sample]
            count = sum("repair" in core.read_user(core.read(core.RESULTS / "payloads" /
                f"{r['ordinal']:02d}.json")) for r in calls)
            if count >= 1:
                raise RuntimeError("Follow-up extra-call ceiling exhausted")
        return super()._post(url, headers=headers, json=json)


core.snapshot, core.validate_group, core.BudgetClient = snapshot, validate_group, BudgetClient


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for flag in ("freeze", "check-only", "run"):
        modes.add_argument(f"--{flag}", action="store_true")
    args = parser.parse_args(argv)
    if not args.freeze:
        return core.main(argv)
    core.load_runtime()
    group, count = validate_group()
    if (group.get("status") != "closed" or count != 8 or core.validate_ledger()["requests"]
            or any(p["phase"] == PHASE for p in group["phases"]) or count + CEILING > group["hard_ceiling"]):
        raise RuntimeError("Follow-up requires the closed 8-POST phase and a finite remaining allocation")
    current = snapshot()
    core.base.exclusive(core.RESULTS / f"{PHASE}-provenance.json", {"frozen_utc": core.base.now(), **current})
    for key, source in core.MODULES.items():
        with (core.RESULTS / f"{PHASE}-{key}.py").open("xb") as stream:
            stream.write(source.read_bytes()); stream.flush(); core.os.fsync(stream.fileno())
    group["phases"].append({"phase": PHASE, "ledger": str(core.LEDGER), "ceiling": CEILING})
    group.update(status="frozen", followup_reason="Offline-verified json_object extraction marker normalization",
                 followup_max_extra_calls_per_sample=1)
    core.base.durable(core.GROUP, group)
    print(core.json.dumps({"phase": PHASE, "frozen": True, "normal_posts": 13,
                          "maximum_posts": CEILING, "work_maximum_posts": count + CEILING}))


if __name__ == "__main__":
    main()
