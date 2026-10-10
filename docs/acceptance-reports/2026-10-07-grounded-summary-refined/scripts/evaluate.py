"""Refined bounded acceptance; default prints an offline plan.

Engineering: skills before plans; UI ui-ux-pro-max/design-system and three-layer
tokens; configurable narrow interfaces; LLM only llm_service, yt-dlp only
ytdlp_service, visual scene read-only. Historical runners remain intact.
"""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
from pathlib import Path


REPORT = Path(__file__).resolve().parents[1]
RESULTS = REPORT / "results"
LEDGER = RESULTS / "request-ledger.json"
ORGANIZATION_PATH = REPORT.parent / "2026-10-07-grounded-summary-organization/scripts/evaluate.py"

_spec = importlib.util.spec_from_file_location("refined_organization_evaluator", ORGANIZATION_PATH)
organization = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(organization)  # Helpers only; no runtime/environment load.
base = organization.base
CONFIG = dict(organization.CONFIG)
CALLER_LOCK = organization.CALLER_LOCK
PHASE = "organization-refined"
CEILING = 13
_organization_snapshot = organization.snapshot


class BudgetClient(organization.BudgetClient):
    def post(self, url, *, headers, json):
        if self.phase != PHASE:
            raise RuntimeError("Foreign phase refused by refined client")
        # Inherited _post resolves organization.verify dynamically, so the new
        # entrypoint hash is checked before the inherited durable reservation.
        with configured_base():
            return super().post(url, headers=headers, json=json)


@contextmanager
def configured_organization():
    overrides = {"REPORT": REPORT, "RESULTS": RESULTS, "LEDGER": LEDGER,
                 "PHASE": PHASE, "CONFIG": CONFIG, "CEILING": CEILING,
                 "CALLER_LOCK": CALLER_LOCK, "BudgetClient": BudgetClient,
                 "snapshot": snapshot, "verify": verify}
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
    # it explicitly; the active entrypoint hash must bind this refined file.
    return {**current, "organization_wrapper_sha256": current["entrypoint_sha256"],
            "entrypoint_sha256": base.digest(Path(__file__).read_bytes())}


def verify(frozen):
    if any(frozen.get(key) != value for key, value in snapshot().items()):
        raise RuntimeError("Source/config/prompt/codec/budget/entrypoint/runner differs from refined freeze; POST refused")


def main(argv=None):
    # Reuse the mutually exclusive, explicit freeze/check/run parser and the
    # fail-closed session/ledger/stage/retry guards without copying the runner.
    with configured_organization():
        return organization.main(argv)


if __name__ == "__main__":
    main()
