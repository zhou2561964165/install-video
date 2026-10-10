"""Read-only organization evidence check using its frozen codec and own ledger.

Engineering: skills first, configurable limits, narrow interfaces; UI uses
ui-ux-pro-max/design-system and three-layer tokens; yt-dlp only ytdlp_service,
LLM only llm_service, scene read-only. MIT derivatives retain CC BY-NC-SA4.0.
"""
import argparse
import importlib.util
import json
from pathlib import Path


REPORT = Path(__file__).resolve().parents[1]
PHASE = "organization-slots"
CHECKER = REPORT.parent / "2026-10-05-grounded-summary-evidence/scripts/check_evidence.py"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("organization_frozen_checker", CHECKER)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    checker.REPORT = REPORT
    checker.RESULTS = REPORT / "results"
    checker.SHARED_LEDGER = checker.RESULTS / "request-ledger.json"
    result = checker.check_phase(PHASE)
    if args.write:
        with (checker.RESULTS / f"{PHASE}-offline-check.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
