"""Finite continuation after the closed three-POST quality-final phase.

Engineering: skill-first; UI primitive/semantic/component tokens; configurable
narrow interfaces; HTTP only llm_service, yt-dlp only ytdlp_service, scene read-only.
Historical corpus/rubric/outputs retain attribution and CC BY-NC-SA 4.0.
Default mode reads no user environment and makes no network request.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
RESULTS = REPORT / "results"
LEDGER = RESULTS / "request-ledger.json"
PARENT_REPORT = REPORT.parent / "2026-10-08-summary-quality-final"
PARENT_RESULTS = PARENT_REPORT / "results"
PARENT_LEDGER = PARENT_RESULTS / "request-ledger.json"
PARENT_EVALUATOR = PARENT_REPORT / "scripts/evaluate.py"
PARENT_CHECKER = PARENT_REPORT / "scripts/check_evidence.py"
CHECKER = Path(__file__).with_name("check_evidence.py")
GROUP = PROJECT / ".planning/2026-10-08-summary-quality-finish/budget-group.json"
PHASE, CEILING = "quality-repaired", 19
WORK_ID = "summary-quality-finish-20261008"

spec = importlib.util.spec_from_file_location("quality_followup_parent", PARENT_EVALUATOR)
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)  # Direct helper reuse, without changing any file identity.
base, CONFIG, MODULES = parent.base, dict(parent.CONFIG), dict(parent.MODULES)
HELPER, ORIGINAL_RUBRIC, CALLER_LOCK = parent.HELPER, parent.ORIGINAL_RUBRIC, parent.CALLER_LOCK
httpx = parent.httpx
read, same_json, read_user = parent.read, parent.same_json, parent.read_user
validate_usage, validate_completion = parent.validate_usage, parent.validate_completion
_parent_snapshot, _parent_load_runtime = parent.snapshot, parent.load_runtime
_parent_validate_ledger, _parent_validate_group = parent.validate_ledger, parent.validate_group


def bind():
    """Bind explicit phase globals; never impersonate a helper's __file__."""
    for key in ("REPORT", "PROJECT", "RESULTS", "LEDGER", "GROUP", "PHASE", "CEILING",
                "WORK_ID", "CHECKER", "HELPER", "ORIGINAL_RUBRIC", "CALLER_LOCK", "CONFIG", "MODULES"):
        setattr(parent, key, globals()[key])
    parent.snapshot, parent.verify = snapshot, verify
    parent.load_runtime, parent.validate_group = load_runtime, validate_group


def validate_ledger(path=None, phase=None, ceiling=None):
    bind()
    return _parent_validate_ledger(path, phase, ceiling)


def validate_group():
    bind()
    group, count = _parent_validate_group()
    rows = group["phases"]
    expected = [{"phase": "quality-final", "ceiling": 19, "ledger": str(PARENT_LEDGER)}]
    if len(rows) == 2:
        expected.append({"phase": PHASE, "ceiling": CEILING, "ledger": str(LEDGER)})
    if (not same_json(rows, expected) or not PARENT_LEDGER.is_file()
            or any(type(group.get(k)) is not int or group[k] != v for k, v in {
                "maximum_followup_phase_posts": 19, "followup_normal_posts": 13,
                "followup_maximum_work_posts": 22}.items())
            or not isinstance(group.get("followup_reason"), str) or not group["followup_reason"].strip()):
        raise RuntimeError("Invalid finite follow-up work allocation")
    old = _parent_validate_ledger(PARENT_LEDGER, "quality-final", 19)
    if len(old["requests"]) != 3 or any(r["status"] != "response" for r in old["requests"]):
        raise RuntimeError("Parent phase must contain exactly three completed POSTs")
    verify_parent_originals(old)
    if count > 22:
        raise RuntimeError("Follow-up allocation exceeded")
    if (group.get("status") not in ({"closed"} if len(rows) == 1 else {"frozen", "closed"})
            or type(group.get("reserved_posts")) is not int
            or group["reserved_posts"] != (3 if group["status"] == "frozen" else count)):
        raise RuntimeError("Work phase is not correctly closed/frozen")
    return group, count


def verify_parent_originals(ledger):
    """Check original hashes before allowing this closed phase as the parent."""
    frozen = read(PARENT_RESULTS / "quality-final-provenance.json")
    chain = {key: base.digest(path.read_bytes()) for key, path in {
        "entry": PARENT_EVALUATOR, "checker": PARENT_CHECKER, "helper": HELPER}.items()}
    if (frozen.get("phase") != "quality-final" or not same_json(frozen.get("ceiling"), 19)
            or frozen.get("work_id") != WORK_ID
            or not same_json(frozen.get("runner_chain_sha256"), chain)
            or set(frozen.get("module_sha256", {})) != set(MODULES)):
        raise RuntimeError("Parent frozen identity/helper mismatch")
    paths = {PARENT_RESULTS / f"quality-final-{key}.py": value
             for key, value in frozen["module_sha256"].items()}
    for row in ledger["requests"]:
        paths[PARENT_RESULTS / "payloads" / f"{row['ordinal']:02d}.json"] = row["payload_sha256"]
        response_path = PARENT_RESULTS / "responses" / f"{row['ordinal']:02d}.json"
        paths[response_path] = row["response_sha256"]
        response = read(response_path)
        if (response.get("phase") != "quality-final" or response.get("sample") != row["sample"]
                or response.get("stage") != row["stage"]
                or not same_json(response.get("ordinal"), row["ordinal"])
                or not same_json(response.get("http_status"), row["http_status"])
                or not same_json(response.get("usage"), row["usage"])):
            raise RuntimeError("Parent response metadata mismatch")
    index = read(PARENT_RESULTS / "quality-final-index.json")
    for row in index["sample_results"]:
        path = (PARENT_RESULTS / row["file"]).resolve()
        if not path.is_relative_to(PARENT_RESULTS.resolve()):
            raise RuntimeError("Parent public path escapes phase")
        paths[path] = row["sha256"]
        public = read(path)
        paths[PARENT_RESULTS / f"quality-final-{row['id']}-trace.json"] = public["trace_sha256"]
    if any(base.digest(path.read_bytes()) != value for path, value in paths.items()):
        raise RuntimeError("Parent original asset hash mismatch")


def runner_chain():
    return {key: base.digest(path.read_bytes()) for key, path in {
        "entry": Path(__file__), "checker": CHECKER, "parent_evaluator": PARENT_EVALUATOR,
        "parent_checker": PARENT_CHECKER, "helper": HELPER}.items()}


def parent_assets():
    """Pin the entire closed parent artifact tree, including all raw evidence."""
    return {path.relative_to(PARENT_RESULTS).as_posix(): base.digest(path.read_bytes())
            for path in sorted(PARENT_RESULTS.rglob("*")) if path.is_file()}


def load_runtime():
    bind()
    _parent_load_runtime()  # Safe existing dotenv loader; credentials are never persisted.


def snapshot():
    bind()
    current = _parent_snapshot()
    current.update(runner_chain_sha256=runner_chain(), parent_assets_sha256=parent_assets(),
        parent_phase="quality-final", parent_posts=3, maximum_work_posts=22)
    return current


def verify(frozen):
    current = snapshot()
    if any(not same_json(frozen.get(key), value) for key, value in current.items()):
        raise RuntimeError("Frozen inputs/code/config/parent changed; POST refused")
    for key, value in frozen["module_sha256"].items():
        if base.digest((RESULTS / f"{PHASE}-{key}.py").read_bytes()) != value:
            raise RuntimeError("Frozen module bytes changed")


class BudgetClient(parent.BudgetClient):
    def post(self, url, *, headers, json):
        bind()
        return super().post(url, headers=headers, json=json)

    def _post(self, url, *, headers, json):
        group, _ = validate_group()
        if group["status"] != "frozen" or len(group["phases"]) != 2:
            raise RuntimeError("Closed/unallocated phase cannot send a POST")
        return super()._post(url, headers=headers, json=json)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for flag in ("freeze", "check-only", "run"):
        modes.add_argument(f"--{flag}", action="store_true")
    args = parser.parse_args(argv)
    if not (args.freeze or args.check_only or args.run):
        print(json.dumps({"phase": PHASE, "ceiling": CEILING, "work_ceiling": 26,
            "expected_posts": 13, "maximum_work_posts": 22, "network": False, "config": CONFIG}))
        return
    bind()
    if not args.freeze:
        group, _ = validate_group()
        if len(group["phases"]) != 2 or (args.run and group["status"] != "frozen"):
            raise RuntimeError("Phase is not frozen or is already closed")
        parent.BudgetClient = BudgetClient
        parent.main(["--check-only" if args.check_only else "--run"])
        return
    # Same global caller lock as the original phase protects allocation/freeze.
    with base.directory_guard(CALLER_LOCK):
        group, count = validate_group()
        occupied = RESULTS.exists() and any(RESULTS.iterdir())
        if len(group["phases"]) != 1 or count != 3 or validate_ledger()["requests"] or occupied:
            raise RuntimeError("Cannot reopen or replace a follow-up phase")
        load_runtime()
        current = snapshot()
        base.exclusive(RESULTS / f"{PHASE}-provenance.json", {"frozen_utc": base.now(), **current})
        for key, source in MODULES.items():
            with (RESULTS / f"{PHASE}-{key}.py").open("xb") as stream:
                stream.write(source.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
        group["phases"].append({"phase": PHASE, "ledger": str(LEDGER), "ceiling": CEILING})
        group["status"] = "frozen"
        base.durable(GROUP, group)
        print(json.dumps({"frozen": True, "phase": PHASE, "normal_posts": 13,
            "maximum_posts": 19, "prior_posts": 3, "maximum_work_posts": 22, "work_ceiling": 26}))


if __name__ == "__main__":
    main()
