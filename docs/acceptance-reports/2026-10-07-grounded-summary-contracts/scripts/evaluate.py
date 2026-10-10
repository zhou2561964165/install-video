"""Independent finite-contract acceptance; default is an offline plan.

Engineering: skills before plans; UI ui-ux-pro-max/design-system with primitive,
semantic and component tokens; configurable narrow interfaces; llm_service and
ytdlp_service boundaries; visual scene read-only; no historical asset changes.
MIT-derived corpus retains authors and CC BY-NC-SA 4.0 attribution.
"""
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys

REPORT = Path(__file__).resolve().parents[1]
RESULTS = REPORT / "results"
LEDGER = RESULTS / "request-ledger.json"
FINAL_PATH = REPORT.parent / "2026-10-07-grounded-summary-final/scripts/evaluate.py"
CHECKER_PATH = Path(__file__).with_name("check_evidence.py")
CHECKER_RUNNER_PATH = REPORT.parent / "2026-10-05-grounded-summary-evidence/scripts/check_evidence.py"
_spec = importlib.util.spec_from_file_location("contracts_final_evaluator", FINAL_PATH)
final = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(final)  # Helpers only; no environment/runtime load.
organization, base = final.organization, final.base
CONFIG = dict(final.CONFIG)
CALLER_LOCK = final.CALLER_LOCK
PHASE = "organization-contracts"
CEILING = 13


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def read(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def validate_ledger():
    if not LEDGER.exists():
        return
    try:
        ledger = read(LEDGER)
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError("Invalid independent contracts ledger JSON; POST refused") from None
    requests = ledger.get("requests") if isinstance(ledger, dict) else None
    if (not isinstance(ledger, dict) or type(ledger.get("ceiling")) is not int
            or ledger["ceiling"] != CEILING or not isinstance(requests, list)
            or len(requests) > CEILING
            or any(not isinstance(row, dict) or type(row.get("ordinal")) is not int
                   or row["ordinal"] != position or row.get("phase") != PHASE
                   for position, row in enumerate(requests, 1))):
        raise RuntimeError("Invalid independent contracts ledger identity or ceiling; POST refused")


class BudgetClient(final.BudgetClient):
    def post(self, url, *, headers, json):
        if self.phase != PHASE:
            raise RuntimeError("Foreign phase refused by contracts client")
        with configured_final():
            return super().post(url, headers=headers, json=json)


@contextmanager
def configured_final():
    overrides = {"REPORT": REPORT, "RESULTS": RESULTS, "LEDGER": LEDGER,
                 "PHASE": PHASE, "CEILING": CEILING, "CONFIG": CONFIG,
                 "CALLER_LOCK": CALLER_LOCK, "BudgetClient": BudgetClient,
                 "snapshot": snapshot, "verify": verify, "validate_ledger": validate_ledger}
    previous = {key: getattr(final, key) for key in overrides}
    try:
        for key, value in overrides.items():
            setattr(final, key, value)
        yield
    finally:
        for key, value in previous.items():
            setattr(final, key, value)


@contextmanager
def configured_base(*, session_locked=False):
    with configured_final():
        with final.configured_base(session_locked=session_locked):
            yield


_final_snapshot = final.snapshot


def chain_paths():
    return {"contracts": Path(__file__), "final": Path(final.__file__),
            "organization": Path(organization.__file__), "runner": Path(base.__file__),
            "checker": CHECKER_PATH, "checker-runner": CHECKER_RUNNER_PATH,
            "final-checker": final.CHECKER_PATH}


def snapshot():
    # Validate every input JSON artifact before historical helpers read it.
    # Their ordinary readers remain unchanged for the historical phases.
    read(base.OLD / "corpus/manifest.json")
    read(REPORT / "rubric.json")
    with configured_final():
        current = _final_snapshot()
    chain = {key: base.digest(path.read_bytes()) for key, path in chain_paths().items()}
    return {**current, "final_wrapper_sha256": current["entrypoint_sha256"],
            "entrypoint_sha256": chain["contracts"],
            "evidence_checker_sha256": chain["checker"],
            "evidence_checker_runner_sha256": chain["checker-runner"],
            "runner_chain_sha256": chain}


def verify(frozen):
    if any(frozen.get(key) != value for key, value in snapshot().items()):
        raise RuntimeError("Source/config/prompt/codec/runner/checker differs from contracts freeze; POST refused")


def main(argv=None):
    flags = sys.argv[1:] if argv is None else argv
    path = RESULTS / f"{PHASE}-provenance.json"
    if (sum(flag in flags for flag in ("--freeze", "--run", "--check-only")) == 1
            and ("--run" in flags or "--check-only" in flags) and path.exists()):
        read(path)
    with configured_final():
        return final.main(argv)


if __name__ == "__main__":
    main()
