"""One-shot content resume: new phase <=5 POST, independent group <=10.

Reuses the immutable source-first guard engine through an import adapter.
Help/plan/check/verify never load dotenv or send HTTP; explicit freeze reads
runtime with zero POST. Root alone may run. Historical closed work remains
bound by byte hashes and counts, never reopened or counted as fresh capacity.
Engineering: skills first; UI primitive/semantic/component tokens; narrow
interfaces; yt-dlp only through ytdlp_service; scene read-only. Corpus and
derived outputs retain their existing CC BY-NC-SA 4.0 attribution.
"""
from __future__ import annotations

import argparse
import importlib.util
import io as binary_io
import json
from pathlib import Path
import re
import zipfile

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
RESULTS = REPORT / "results"
ADAPTER = REPORT.parent / "2026-10-10-source-first-summary-live/scripts/evaluate.py"
spec = importlib.util.spec_from_file_location("resume_source_first_engine", ADAPTER)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
HELPER, CORPUS, SHARED_LOCK = base.HELPER, base.CORPUS, base.SHARED_LOCK
GROUP = PROJECT / ".planning/2026-10-11-summary-content-resume/budget-group.json"
TRACKER = GROUP.with_name("phase-1.json")
WORK_ID, PHASE = "summary-content-resume-20261011", "summary-thinking-single-1"
MAX_POSTS, HARD_CEILING, SAMPLES = 5, 10, base.SAMPLES
CONFIG = base.CONFIG | {
    "llm_summary_generation_mode": "single",
    "llm_summary_thinking_mode": "enabled",
    "llm_summary_max_output_tokens": 8192,
    "llm_summary_output_token_ceiling": 16384,
    "llm_summary_format_retries": 0,
    "llm_summary_semantic_retries": 0,
    "llm_summary_max_extra_calls": 0,
}
io, os = base.io, base.os
read, runtime_config = base.read, base.runtime_config
_base_versions = base.versions
sample_plan = base.sample_plan
_original = {name: getattr(base, name) for name in (
    "group_state", "plan", "runtime", "freeze", "check", "run",
    "verify_results", "durable", "close_phase")}
_closing = False


def versions():
    # These distributions are imported by the existing service even when the
    # selected generation path is single. Record metadata, never invoke SDKs.
    from importlib.metadata import version
    return _base_versions() | {name: version(name) for name in ("langchain-core", "langsmith")}


def base_context():
    """Rebind only our privately imported engine, never the old on-disk phase."""
    for name in ("PROJECT", "REPORT", "RESULTS", "CORPUS", "GROUP", "TRACKER",
                 "SHARED_LOCK", "WORK_ID", "PHASE", "MAX_POSTS", "HARD_CEILING",
                 "SAMPLES", "CONFIG", "HELPER", "runtime", "versions", "asset_paths",
                 "group_state", "durable", "close_phase"):
        setattr(base, name, globals()[name])


def historical_state(group):
    """Validate exact closed JSON/ZIP bytes without extracting archive members.

    ZIP receipt/ledger member lists are explicit, ordered, and paired. Their
    parent_posts form a continuation chain; a separate JSON26 is independent.
    Only bounded JSON metadata is read from ZIP; historical raw is untouched.
    """
    records = group.get("historical_parents")
    if not isinstance(records, list) or not records:
        raise RuntimeError("Historical parents are required")
    paths, total, archive_bases = set(), 0, []
    for row in records:
        if (not isinstance(row, dict) or row.get("status") != "closed"
                or type(row.get("posts")) is not int or row["posts"] < 0
                or not isinstance(row.get("path"), str)
                or not isinstance(row.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
            raise RuntimeError("Historical parent identity/count/status differs")
        path = Path(row["path"])
        if not path.is_absolute():
            path = PROJECT / path
        path = path.resolve()
        if (not path.is_relative_to(PROJECT.resolve()) or path in paths
                or path in {GROUP.resolve(), TRACKER.resolve()}
                or path.is_relative_to(RESULTS.resolve())
                or path.suffix.lower() not in {".json", ".zip"}
                or path.name.lower().startswith(".env") or "credential" in path.name.lower()):
            raise RuntimeError("Historical parent path is unsafe or ambiguous")
        paths.add(path)
        try:
            raw = path.read_bytes()
            if io.digest(raw) != row["sha256"]:
                raise RuntimeError("Historical parent byte hash differs")
            if path.suffix.lower() == ".json":
                state = json.loads(raw)
                if (state.get("status") != "closed" or type(state.get("reserved_posts")) is not int
                        or state["reserved_posts"] != row["posts"]):
                    raise RuntimeError("Historical JSON parent is not closed with exact posts")
            else:
                receipts, ledgers = row.get("receipt_members"), row.get("ledger_members")
                if (not isinstance(receipts, list) or not receipts or not isinstance(ledgers, list)
                        or len(receipts) != len(ledgers)
                        or any(not isinstance(name, str) for name in receipts + ledgers)
                        or len(set(receipts + ledgers)) != len(receipts + ledgers)):
                    raise RuntimeError("Historical ZIP metadata inventory differs")
                posts, previous = 0, None
                with zipfile.ZipFile(binary_io.BytesIO(raw)) as archive:
                    names = archive.namelist()
                    for receipt_name, ledger_name in zip(receipts, ledgers):
                        for name in (receipt_name, ledger_name):
                            if (name.startswith(("/", "\\")) or ".." in Path(name).parts
                                    or names.count(name) != 1 or archive.getinfo(name).file_size > 2_000_000):
                                raise RuntimeError("Historical ZIP metadata path/size differs")
                        receipt, ledger = (json.loads(archive.read(name)) for name in (receipt_name, ledger_name))
                        count, parent = receipt.get("posts"), receipt.get("parent_posts")
                        requests = ledger.get("requests")
                        if (receipt.get("status") != "closed" or ledger.get("status") != "closed"
                                or type(count) is not int or count < 0 or type(parent) is not int or parent < 0
                                or not isinstance(requests, list) or len(requests) != count
                                or previous is not None and parent != previous):
                            raise RuntimeError("Historical ZIP closed counts/continuation chain differs")
                        if previous is None:
                            archive_bases.append(parent)
                        previous, posts = parent + count, posts + count
                if posts != row["posts"]:
                    raise RuntimeError("Historical ZIP posts differ from attempts")
        except (OSError, ValueError, KeyError, AttributeError, zipfile.BadZipFile) as exc:
            raise RuntimeError("Historical parent metadata is unreadable") from exc
        total += row["posts"]
    # ZIP continuation starts from a listed JSON parent, not an invented base.
    json_counts = {row["posts"] for row in records if Path(row["path"]).suffix.lower() == ".json"}
    if any(parent not in json_counts for parent in archive_bases):
        raise RuntimeError("Historical ZIP initial parent is unbound")
    return {"historical_parents": records, "historical_posts": total}


def group_state():
    base_context()
    group = _original["group_state"]()
    if _closing:
        # An external parent drift is an error, but must not prevent spending
        # reservations from sealing. This bypass exists only in close_phase.
        return group
    historical_state(group)
    provenance = RESULTS / "provenance.json"
    if provenance.exists() and group["historical_parents"] != read(provenance)["group_at_freeze"].get("historical_parents"):
        raise RuntimeError("Historical parent inventory differs from freeze")
    return group


def inventory_paths():
    paths = [Path(__file__), ADAPTER, HELPER,
        PROJECT / "backend/tests/test_summary_resume_evaluation.py",
        PROJECT / "backend/tests/test_source_first_evaluation.py",
        PROJECT / "pyproject.toml", PROJECT / "uv.lock",
        PROJECT / "backend/app/config.py", PROJECT / "backend/app/services/llm_service.py",
        REPORT / "review-criteria.md"]
    paths.extend(REPORT.parent / name for name in (
        "2026-10-09-summary-quality-repaired/rubric.json",
        "2026-10-09-adaptive-short-medium/review-criteria.md",
        "2026-10-09-adaptive-summary-final/review-criteria.md",
        "2026-10-09-adaptive-summary/report.md",
    ))
    paths.extend((PROJECT / "backend/app/services").glob("summary_*.py"))
    paths.extend(path for path in CORPUS.rglob("*") if path.is_file())
    return sorted(set(paths))


asset_paths = inventory_paths


def plan():
    base_context()
    return _original["plan"]() | historical_state(group_state()) | {
        "normal_posts": 5, "format_posts_ceiling": 0, "semantic_posts_ceiling": 0,
        "historical_semantic_quality_verified": False,
    }


def runtime():
    base_context()
    settings, service, endpoint = _original["runtime"]()
    if any(getattr(settings, key) != value for key, value in CONFIG.items()):
        raise RuntimeError("Runtime does not apply explicit single/thinking candidate")
    return settings, service, endpoint


def durable(path, value):
    base_context()
    return _original["durable"](path, value)


def close_phase(index, pending):
    global _closing
    base_context()
    _closing = True
    try:
        return _original["close_phase"](index, pending)
    finally:
        _closing = False


def freeze():
    base_context()
    return _original["freeze"]()


def check():
    base_context()
    return _original["check"]()


def run(*, transport=None):
    base_context()
    return _original["run"](transport=transport)


def verify_results():
    base_context()
    return _original["verify_results"]()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    flags = parser.add_mutually_exclusive_group()
    for name in ("freeze", "check", "run", "verify"):
        flags.add_argument(f"--{name}", action="store_true")
    args = parser.parse_args(argv)
    action = freeze if args.freeze else check if args.check else run if args.run else verify_results if args.verify else plan
    print(json.dumps(action(), ensure_ascii=False))


if __name__ == "__main__":
    main()
