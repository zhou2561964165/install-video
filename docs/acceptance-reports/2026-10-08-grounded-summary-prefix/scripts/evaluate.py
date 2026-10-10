"""Independent bounded prefix-contract acceptance; default is an offline plan.

Engineering: skills precede plans; UI ui-ux-pro-max/design-system with primitive,
semantic and component tokens; configurable narrow interfaces; LLM only through
llm_service, yt-dlp only through ytdlp_service; visual scene read-only. Preserve
historical evidence and attributed MIT-derived CC BY-NC-SA 4.0 corpus/rubric.
"""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys

REPORT = Path(__file__).resolve().parents[1]
RESULTS = REPORT / "results"
LEDGER = RESULTS / "request-ledger.json"
CONTRACTS_PATH = REPORT.parent / "2026-10-07-grounded-summary-contracts/scripts/evaluate.py"
CONTRACT_CHECKER_PATH = CONTRACTS_PATH.with_name("check_evidence.py")
CHECKER_PATH = Path(__file__).with_name("check_evidence.py")
CHECKER_RUNNER_PATH = REPORT.parent / "2026-10-05-grounded-summary-evidence/scripts/check_evidence.py"
_spec = importlib.util.spec_from_file_location("prefix_contracts_evaluator", CONTRACTS_PATH)
contracts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(contracts)  # Pure helper imports; no runtime or .env.
final, organization, base = contracts.final, contracts.organization, contracts.base
CONFIG = dict(contracts.CONFIG)
CALLER_LOCK = contracts.CALLER_LOCK
PHASE = "organization-prefix"
CEILING = 13
_contracts_snapshot = contracts.snapshot
read = contracts.read


def validate_ledger():
    # Reuse strict duplicate-key parsing and exact integer/phase validation
    # without weakening or writing the historical ledger.
    with configured_contracts():
        _contracts_validate_ledger()
    if LEDGER.exists():
        posts = {}
        for row in read(LEDGER)["requests"]:
            sample = row.get("sample")
            if not isinstance(sample, str) or not sample:
                raise RuntimeError("Invalid independent prefix ledger sample identity; POST refused")
            posts[sample] = posts.get(sample, 0) + 1
            if type(row.get("sample_post")) is not int or row["sample_post"] != posts[sample]:
                raise RuntimeError("Invalid independent prefix ledger sample_post identity; POST refused")


_contracts_validate_ledger = contracts.validate_ledger


class BudgetClient(contracts.BudgetClient):
    def post(self, url, *, headers, json):
        if self.phase != PHASE:
            self.failed = True
            raise RuntimeError("Foreign phase refused by prefix client")
        with configured_contracts():
            return super().post(url, headers=headers, json=json)


@contextmanager
def configured_contracts():
    overrides = {"REPORT": REPORT, "RESULTS": RESULTS, "LEDGER": LEDGER,
                 "PHASE": PHASE, "CEILING": CEILING, "CONFIG": CONFIG,
                 "CALLER_LOCK": CALLER_LOCK, "BudgetClient": BudgetClient,
                 "snapshot": snapshot, "verify": verify, "validate_ledger": validate_ledger}
    previous = {key: getattr(contracts, key) for key in overrides}
    runtime = {key: getattr(base, key) for key in ("settings", "service", "FactLimits")}
    try:
        for key, value in overrides.items():
            setattr(contracts, key, value)
        yield
    finally:
        for key, value in previous.items():
            setattr(contracts, key, value)
        for key, value in runtime.items():
            setattr(base, key, value)


@contextmanager
def configured_base(*, session_locked=False):
    with configured_contracts():
        with contracts.configured_base(session_locked=session_locked):
            yield


def chain_paths():
    return {"prefix": Path(__file__), "contracts": Path(contracts.__file__),
            "final": Path(final.__file__), "organization": Path(organization.__file__),
            "runner": Path(base.__file__), "checker": CHECKER_PATH,
            "contracts-checker": CONTRACT_CHECKER_PATH, "checker-runner": CHECKER_RUNNER_PATH,
            "final-checker": final.CHECKER_PATH}


def snapshot():
    read(base.OLD / "corpus/manifest.json")
    read(REPORT / "rubric.json")
    with configured_contracts():
        current = _contracts_snapshot()
    chain = {key: base.digest(path.read_bytes()) for key, path in chain_paths().items()}
    return {**current, "contracts_wrapper_sha256": current["entrypoint_sha256"],
            "entrypoint_sha256": chain["prefix"],
            "evidence_checker_sha256": chain["checker"],
            "evidence_checker_runner_sha256": chain["checker-runner"],
            "runner_chain_sha256": chain}


def verify(frozen):
    if any(frozen.get(key) != value for key, value in snapshot().items()):
        raise RuntimeError("Source/config/prompt/codec/runner/checker differs from prefix freeze; POST refused")


def main(argv=None):
    flags = sys.argv[1:] if argv is None else argv
    path = RESULTS / f"{PHASE}-provenance.json"
    if (sum(flag in flags for flag in ("--freeze", "--run", "--check-only")) == 1
            and ("--run" in flags or "--check-only" in flags) and path.exists()):
        read(path)
    with configured_contracts():
        return contracts.main(argv)


if __name__ == "__main__":
    main()
