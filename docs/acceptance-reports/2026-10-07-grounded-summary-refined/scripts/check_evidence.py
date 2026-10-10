"""Offline refined evidence check using hash-validated frozen codec and own ledger.

Engineering: skills first; UI ui-ux-pro-max/design-system and three-layer tokens;
configurable narrow interfaces; LLM only llm_service, yt-dlp only ytdlp_service,
visual scene read-only. Lexical evidence does not establish semantic accuracy.
MIT derivatives retain original authors and CC BY-NC-SA 4.0.
"""
import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path


REPORT = Path(__file__).resolve().parents[1]
RESULTS = REPORT / "results"
LEDGER = RESULTS / "request-ledger.json"
PHASE = "organization-refined"
CEILING = 13
CHECKER = REPORT.parent / "2026-10-05-grounded-summary-evidence/scripts/check_evidence.py"

_spec = importlib.util.spec_from_file_location("refined_frozen_checker", CHECKER)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)  # Pure offline checker; no production imports.


@contextmanager
def configured_checker():
    overrides = {"REPORT": REPORT, "RESULTS": RESULTS, "SHARED_LEDGER": LEDGER}
    previous = {key: getattr(checker, key) for key in overrides}
    try:
        for key, value in overrides.items():
            setattr(checker, key, value)
        yield
    finally:
        for key, value in previous.items():
            setattr(checker, key, value)


def check_phase():
    with configured_checker():
        ledger = checker.read(LEDGER)
        checker.require(type(ledger["ceiling"]) is int and ledger["ceiling"] == CEILING,
                        "Refined ledger ceiling mismatch")
        checker.require(all(row["phase"] == PHASE for row in ledger["requests"]),
                        "Foreign phase in refined ledger")
        # The existing checker verifies frozen module hashes BEFORE importing
        # the pure codec or compiling the frozen cleanup function.
        return checker.check_phase(PHASE)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    result = check_phase()
    if args.write:
        with (RESULTS / f"{PHASE}-offline-check.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
