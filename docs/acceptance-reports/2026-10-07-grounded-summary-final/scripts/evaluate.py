"""Final bounded acceptance; default prints an offline plan.

Engineering: skills before plans; UI ui-ux-pro-max/design-system and three-layer
tokens; configurable narrow interfaces; LLM only llm_service, yt-dlp only
ytdlp_service, visual scene read-only. Historical runners remain intact.
"""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path


REPORT = Path(__file__).resolve().parents[1]
RESULTS = REPORT / "results"
LEDGER = RESULTS / "request-ledger.json"
ORGANIZATION_PATH = REPORT.parent / "2026-10-07-grounded-summary-organization/scripts/evaluate.py"
CHECKER_PATH = Path(__file__).with_name("check_evidence.py")
CHECKER_RUNNER_PATH = REPORT.parent / "2026-10-05-grounded-summary-evidence/scripts/check_evidence.py"

_spec = importlib.util.spec_from_file_location("final_organization_evaluator", ORGANIZATION_PATH)
organization = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(organization)  # Helpers only; no runtime/environment load.
base = organization.base
CONFIG = dict(organization.CONFIG)
CALLER_LOCK = organization.CALLER_LOCK
PHASE = "organization-final"
CEILING = 13
_organization_snapshot = organization.snapshot
_organization_check_budget = organization.check_budget


class BudgetClient(organization.BudgetClient):
    def post(self, url, *, headers, json):
        if self.phase != PHASE:
            raise RuntimeError("Foreign phase refused by final client")
        # Inherited _post resolves organization.verify dynamically, so the new
        # entrypoint hash is checked before the inherited durable reservation.
        with configured_base():
            return super().post(url, headers=headers, json=json)

    def _post(self, url, *, headers, json):
        # The inherited post owns the shared caller lock here. Validate existing
        # ledger identity before the inherited reservation or any billable send.
        try:
            with base.ledger_guard():
                validate_ledger()
            return super()._post(url, headers=headers, json=json)
        except Exception:
            self.failed = True
            raise


@contextmanager
def configured_organization():
    overrides = {"REPORT": REPORT, "RESULTS": RESULTS, "LEDGER": LEDGER,
                 "PHASE": PHASE, "CONFIG": CONFIG, "CEILING": CEILING,
                 "CALLER_LOCK": CALLER_LOCK, "BudgetClient": BudgetClient,
                 "snapshot": snapshot, "verify": verify, "check_budget": check_budget}
    previous = {key: getattr(organization, key) for key in overrides}
    runtime = {key: getattr(base, key) for key in ("settings", "service", "FactLimits")}
    try:
        for key, value in overrides.items():
            setattr(organization, key, value)
        yield
    finally:
        for key, value in previous.items():
            setattr(organization, key, value)
        for key, value in runtime.items():
            setattr(base, key, value)


@contextmanager
def configured_base(*, session_locked=False):
    with configured_organization():
        with organization.configured_base(session_locked=session_locked):
            yield


def snapshot():
    with configured_organization():
        current = _organization_snapshot()
    # The inherited entrypoint hash belongs to organization.__file__. Preserve
    # it explicitly; the active entrypoint hash must bind this final file.
    return {**current, "organization_wrapper_sha256": current["entrypoint_sha256"],
            "entrypoint_sha256": base.digest(Path(__file__).read_bytes()),
            "evidence_checker_sha256": base.digest(CHECKER_PATH.read_bytes()),
            "evidence_checker_runner_sha256": base.digest(CHECKER_RUNNER_PATH.read_bytes())}


def verify(frozen):
    if any(frozen.get(key) != value for key, value in snapshot().items()):
        raise RuntimeError("Source/config/prompt/codec/budget/entrypoint/runner differs from final freeze; POST refused")


def validate_ledger():
    if not LEDGER.exists():
        return
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    requests = ledger.get("requests") if isinstance(ledger, dict) else None
    if (not isinstance(ledger, dict) or type(ledger.get("ceiling")) is not int
            or ledger["ceiling"] != CEILING or not isinstance(requests, list)
            or len(requests) > CEILING
            or any(not isinstance(row, dict) or type(row.get("ordinal")) is not int
                   or row["ordinal"] != position or row.get("phase") != PHASE
                   for position, row in enumerate(requests, 1))):
        raise RuntimeError("Invalid independent final ledger identity or ceiling; POST refused")


def check_budget(frozen):
    # The inherited fresh-plan guard still requires all 13 unused reservations.
    # This adds typed identity validation without modifying historical helpers.
    with configured_base():
        with base.ledger_guard():
            validate_ledger()
        _organization_check_budget(frozen)


def main(argv=None):
    # Reuse the mutually exclusive, explicit freeze/check/run parser and the
    # fail-closed session/ledger/stage/retry guards without copying the runner.
    with configured_organization():
        return organization.main(argv)


if __name__ == "__main__":
    main()
