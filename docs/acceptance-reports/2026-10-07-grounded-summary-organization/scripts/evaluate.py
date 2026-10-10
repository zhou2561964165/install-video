"""Bounded organization evaluation; no provider calls without explicit --run.

Engineering: applicable skills before plans; UI ui-ux-pro-max/design-system and
primitive/semantic/component tokens; configurable capabilities, narrow interfaces,
yt-dlp only ytdlp_service, LLM only llm_service, visual scene read-only.
Reuses the frozen attributed corpus and rubric; keeps old reports and ledgers intact.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import importlib.util
import json
from pathlib import Path
import sys


REPORT = Path(__file__).resolve().parents[1]
RESULTS = REPORT / "results"
LEDGER = RESULTS / "request-ledger.json"
BASE_PATH = REPORT.parent / "2026-10-05-grounded-summary-evidence/scripts/evaluate.py"
CALLER_LOCK = REPORT.parent / "2026-10-05-grounded-summary/results/.http-session-lock"
PHASE = "organization-slots"
CEILING = 13

_spec = importlib.util.spec_from_file_location("organization_base_evaluator", BASE_PATH)
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)  # Budget helpers only; does not load production or .env.
_base_snapshot = base.snapshot

CONFIG = {**base.CONFIG,
          "llm_summary_facts_chunk_chars": 8000,
          "llm_summary_facts_max_summary_chars": 800,
          "llm_max_input_chars": 100000,
          "llm_summary_max_output_tokens": 4096,
          "llm_summary_facts_compose_max_output_tokens": 8192,
          "llm_summary_facts_audit_max_output_tokens": 8192}


def caller_guard():
    return base.directory_guard(CALLER_LOCK)


class BudgetClient(base.BudgetClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.failed = False

    def post(self, url, *, headers, json):
        # Standalone clients must also bind the independent ceiling and ledger.
        with configured_base():
            return super().post(url, headers=headers, json=json)

    def _post(self, url, *, headers, json):
        if self.failed:
            raise RuntimeError("Organization client stopped after failed request; retry refused")
        try:
            verify(self.frozen)  # Complete freeze BEFORE reservation.
            response = super()._post(url, headers=headers, json=json)
        except Exception:
            self.failed = True
            raise
        self.failed = not response.is_success
        return response


@contextmanager
def configured_base(*, session_locked=False):
    overrides = {"CONFIG": CONFIG, "REPORT": REPORT, "RESULTS": RESULTS, "SHARED_LEDGER": LEDGER,
                 "CEILING": CEILING, "BudgetClient": BudgetClient, "snapshot": snapshot,
                 "caller_guard": nullcontext if session_locked else caller_guard}
    previous = {key: getattr(base, key) for key in overrides}
    try:
        for key, value in overrides.items():
            setattr(base, key, value)
        yield
    finally:
        for key, value in previous.items():
            setattr(base, key, value)


def load_runtime():
    # Explicit freeze/check/run resolve the same configuration before imports.
    # Default plan/import does not read .env; its secrets are never persisted.
    sys.path.insert(0, str(base.PROJECT / "backend"))
    base.load_dotenv(base.PROJECT / "backend/.env", override=False)
    from app.config import settings
    from app.services import llm_service
    from app.services.summary_facts import FactLimits
    base.settings, base.service, base.FactLimits = settings, llm_service, FactLimits
    for key, value in CONFIG.items():
        if not hasattr(settings, key):
            raise RuntimeError("Grounded organization settings unavailable; refuse")
        setattr(settings, key, value)


def snapshot():
    if any(getattr(base.settings, key) != value for key, value in CONFIG.items()):
        raise RuntimeError("Runtime organization config changed; POST refused")
    with configured_base():
        current = _base_snapshot()
    return {**current, "entrypoint_sha256": base.digest(Path(__file__).read_bytes()),
            "phase": PHASE, "ceiling": CEILING,
            "ledger": str(LEDGER), "caller_lock": str(CALLER_LOCK)}


def verify(frozen):
    if any(frozen.get(key) != value for key, value in snapshot().items()):
        raise RuntimeError("Source/config/prompt/codec/budget/entrypoint/runner differs from freeze; POST refused")


def check_budget(frozen):
    # Three unmodified sources must consume the entire fresh 13-POST allowance.
    samples = frozen["samples"]
    if (len(samples) != 3 or frozen["expected_posts"] != CEILING
            or sum(row["expected_posts"] for row in samples) != CEILING):
        raise RuntimeError("Frozen three-source budget plan must equal 13; refuse")
    with configured_base():
        with base.ledger_guard():
            if LEDGER.exists():
                ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
                if ledger["ceiling"] != CEILING:
                    raise RuntimeError("Independent ledger ceiling differs; refuse")
                remaining = CEILING - len(ledger["requests"])
            else:
                remaining = CEILING
            if remaining < frozen["expected_posts"]:
                raise RuntimeError("Insufficient independent POST budget for frozen plan; refuse")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--freeze", action="store_true")
    modes.add_argument("--check-only", action="store_true")
    modes.add_argument("--run", action="store_true")
    parser.add_argument("--system-proxy", action="store_true")
    args = parser.parse_args(argv)
    if not (args.freeze or args.check_only or args.run):
        print(json.dumps({"phase": PHASE, "ceiling": CEILING, "expected_posts": 13,
                          "config": CONFIG, "ledger": str(LEDGER), "network": False,
                          "stage_max_output_tokens": {"extract": 4096, "compose": 8192, "audit": 8192}}))
        return
    load_runtime()
    current = snapshot()
    path = RESULTS / f"{PHASE}-provenance.json"
    if args.freeze:
        check_budget(current)
        base.exclusive(path, {"frozen_utc": base.now(), **current})
        for key, module in base.MODULES.items():
            with (RESULTS / f"{PHASE}-{key}.py").open("xb") as stream:
                stream.write(module.read_bytes())
                stream.flush()
                base.os.fsync(stream.fileno())
        print(json.dumps({"phase": PHASE, "frozen": True, "expected_posts": current["expected_posts"]}))
        return
    frozen = json.loads(path.read_text(encoding="utf-8"))
    verify(frozen)
    if args.check_only:
        print(json.dumps({"phase": PHASE, "match": True}))
        return
    with caller_guard():
        check_budget(frozen)  # Under the shared caller lock, before live main or any send.
        with configured_base(session_locked=True):
            live_args = ["--phase", PHASE]
            if args.system_proxy:
                live_args.append("--system-proxy")
            return base.main(live_args, phase_choices=[PHASE])


if __name__ == "__main__":
    main()
