"""Full long-source final acceptance: 3 fresh POSTs, cumulative 13 -> 16.

Reuse the complete source-first execution guards and frozen lossless decoder,
not old paid notes. Root alone may run; plan/check/verify are offline. No
retry, paid fallback, SDK, telemetry, reasoning persistence or default change.
Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp
only through ytdlp_service; scene remains read-only. Corpus and derived
outputs retain their existing MIT authors and CC BY-NC-SA 4.0 attribution.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import inspect
import json
from pathlib import Path
from types import CodeType, FunctionType

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
RESULTS = REPORT / "results"
PARENT_REPORT = REPORT.parent / "2026-10-12-summary-content-capacity-repair"
ADAPTER = REPORT.parent / "2026-10-11-summary-content-local-repair/scripts/evaluate.py"
spec = importlib.util.spec_from_file_location("long_final_complete_source_engine", ADAPTER)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
engine = prior.prior.base
PARENT_GROUP = prior.GROUP.with_name("budget-continuation-capacity.json")
PARENT_TRACKER = prior.GROUP.with_name("phase-3.json")
PARENT_PHASE = "summary-thinking-capacity-3"
HELPER, CORPUS, SHARED_LOCK = prior.HELPER, prior.CORPUS, prior.SHARED_LOCK
GROUP = prior.GROUP.with_name("budget-continuation-long-final.json")
TRACKER = GROUP.with_name("phase-4.json")
WORK_ID, PHASE = prior.WORK_ID, "summary-long-full-final-4"
MAX_POSTS, HARD_CEILING, SAMPLES = 3, 16, ("en-long",)
CONFIG = prior.CONFIG | {"llm_summary_max_output_tokens": 16384,
    "llm_summary_output_token_ceiling": 24576}
io, os = prior.io, prior.os
read, versions, runtime_config = prior.read, prior.versions, prior.runtime_config
_original = {name: getattr(prior, name) for name in (
    "base_context", "inventory_paths", "group_state", "runtime", "freeze", "check",
    "run", "verify_results", "durable", "close_phase")}
_base_samples = engine.sample_plan
_base_verify = engine.verify_results
_all_samples = tuple(engine.SAMPLES)
_closing = False


def build_verifier():
    """Adapt exactly one trusted verifier AST comparison; preserve every other node."""
    if Path(inspect.getsourcefile(_base_verify)).resolve() != Path(engine.__file__).resolve():
        raise RuntimeError("Verifier source is outside the trusted base script")
    source = inspect.getsource(_base_verify)
    tree = ast.parse(source)
    if (len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef)
            or tree.body[0].name != "verify_results" or tree.body[0].decorator_list
            or tree.body[0].args.args or tree.body[0].args.kwonlyargs
            or tree.body[0].args.vararg or tree.body[0].args.kwarg):
        raise RuntimeError("Verifier function shape differs")
    before = ast.dump(tree)
    matches = [node for node in ast.walk(tree) if isinstance(node, ast.Compare)
        and len(node.ops) == len(node.comparators) == 1 and isinstance(node.ops[0], ast.NotEq)
        and isinstance(node.left, ast.Call) and isinstance(node.left.func, ast.Name)
        and node.left.func.id == "len" and not node.left.keywords and len(node.left.args) == 1
        and isinstance(node.left.args[0], ast.Name) and node.left.args[0].id == "samples"
        and isinstance(node.comparators[0], ast.Constant)
        and type(node.comparators[0].value) is int and node.comparators[0].value == 3]
    if len(matches) != 1:
        raise RuntimeError("Verifier sample-count AST match must be exactly one")
    matches[0].comparators[0] = ast.copy_location(ast.Call(func=ast.Name(id="len", ctx=ast.Load()),
        args=[ast.Name(id="SAMPLES", ctx=ast.Load())], keywords=[]), matches[0].comparators[0])
    ast.fix_missing_locations(tree)
    compiled = compile(tree, str(Path(engine.__file__).resolve()), "exec", dont_inherit=True)
    code = [value for value in compiled.co_consts if isinstance(value, CodeType) and value.co_name == "verify_results"]
    if len(code) != 1:
        raise RuntimeError("Adapted verifier code identity differs")
    return FunctionType(code[0], engine.__dict__, "verify_results"), {
        "source_sha256": io.digest(source), "ast_before_sha256": io.digest(before),
        "ast_after_sha256": io.digest(ast.dump(tree)), "matched_comparisons": len(matches),
        "changed_condition": "len(samples) != len(SAMPLES)"}


_verify, VERIFY_ADAPTATION = build_verifier()


def base_context():
    for name in ("PROJECT", "REPORT", "RESULTS", "CORPUS", "GROUP", "TRACKER",
                 "SHARED_LOCK", "WORK_ID", "PHASE", "MAX_POSTS", "HARD_CEILING",
                 "SAMPLES", "CONFIG", "HELPER", "runtime", "versions", "asset_paths",
                 "group_state", "durable", "close_phase"):
        setattr(prior, name, globals()[name])
    prior.base_context = base_context
    _original["base_context"]()
    engine.sample_plan = sample_plan


def sample_plan():
    """Read the mature three-source accounting, retaining only the true long source."""
    previous = engine.SAMPLES
    try:
        engine.SAMPLES = _all_samples
        return [sample for sample in _base_samples() if sample["id"] in SAMPLES]
    finally:
        engine.SAMPLES = previous


def parent_state(group):
    """Bind the closed13 parent and its receipt chain without importing its runner."""
    cache = {}
    def get(path):
        path = Path(path).resolve()
        if not path.is_relative_to(PROJECT.resolve()):
            raise RuntimeError("Parent evidence path is outside project")
        if path not in cache:
            cache[path] = path.read_bytes()
        return cache[path]
    def data(path):
        return json.loads(get(path))
    try:
        binding, parent_bytes = group.get("continuation_parent", {}), get(PARENT_GROUP)
        parent = json.loads(parent_bytes)
        if (binding.get("path") != str(PARENT_GROUP) or binding.get("parent_posts") != 13
                or binding.get("sha256") != io.digest(parent_bytes)
                or group.get("parent_posts") != 13 or group.get("reserved_posts", -1) < 13
                or group.get("budget_adjustment") != {"from": 13, "to": 16}
                or parent.get("work_id") != WORK_ID or parent.get("status") != "closed"
                or parent.get("hard_ceiling") != 13 or parent.get("reserved_posts") != 13
                or len(parent.get("phases", [])) != 3
                or group.get("phases", [])[:3] != parent["phases"]
                or [p.get("phase") for p in parent["phases"]] != [
                    "summary-thinking-single-1", "summary-thinking-local-json-2", PARENT_PHASE]
                or [p.get("reserved_posts") for p in parent["phases"]] != [5, 5, 3]
                or any(p.get("status") != "closed" for p in parent["phases"])
                or group.get("historical_parents") != parent.get("historical_parents")):
            raise RuntimeError("Continuation closed13 parent/count/phase prefix differs")
        phase = parent["phases"][-1]
        paths = {name: PARENT_REPORT / "results" / name for name in (
            "closed-receipt.json", "provenance.json", "request-ledger.json", "result-index.json")}
        receipt, frozen, ledger, index = [data(paths[name]) for name in paths]
        tracker = data(PARENT_TRACKER)
        if any(obj.get("work_id") != WORK_ID or obj.get("phase") != PARENT_PHASE
                for obj in (receipt, frozen, ledger, index, tracker)):
            raise RuntimeError("Parent phase identity differs")
        receipt_hash, provenance_hash = io.digest(get(paths["closed-receipt.json"])), io.digest(get(paths["provenance.json"]))
        if (phase.get("tracker") != str(PARENT_TRACKER) or phase.get("ledger") != str(paths["request-ledger.json"])
                or phase.get("maximum_posts") != 3 or tracker.get("maximum_posts") != 3
                or tracker.get("status") != "closed" or tracker.get("reserved_posts") != 3
                or tracker.get("hard_ceiling") != 13 or tracker.get("parent_posts") != 10
                or tracker.get("ledger") != str(paths["request-ledger.json"])
                or any(obj.get("closed_receipt_sha256") != receipt_hash for obj in (phase, tracker))
                or any(obj.get("provenance_sha256") != provenance_hash for obj in (phase, tracker, receipt))
                or receipt.get("status") != "closed" or receipt.get("posts") != 3
                or receipt.get("work_posts") != 13 or receipt.get("hard_ceiling") != 13
                or receipt.get("ledger_sha256") != io.digest(get(paths["request-ledger.json"]))
                or receipt.get("index_sha256") != io.digest(get(paths["result-index.json"]))
                or frozen.get("config") != CONFIG or frozen.get("parent_posts") != 10
                or frozen.get("hard_ceiling") != 13 or frozen.get("maximum_posts") != 3
                or index.get("posts") != 3 or len(ledger.get("requests", [])) != 3):
            raise RuntimeError("Parent closed receipt/ledger/provenance differs")
        return binding
    except (KeyError, IndexError, TypeError, ValueError, OSError) as exc:
        raise RuntimeError("Parent evidence is unreadable or invalid") from exc


def group_state():
    base_context()
    group = _original["group_state"]()
    if not _closing:
        parent_state(group)
        provenance = RESULTS / "provenance.json"
        if provenance.exists() and read(provenance)["group_at_freeze"].get("continuation_parent") != group.get("continuation_parent"):
            raise RuntimeError("Continuation parent binding differs from freeze")
    return group


def plan():
    base_context()
    group = group_state()
    return {"work_id": WORK_ID, "phase": PHASE, "network": False, "dotenv_read": False,
        "maximum_posts": MAX_POSTS, "normal_posts": MAX_POSTS, "hard_ceiling": HARD_CEILING,
        "work_reserved_posts": group["reserved_posts"], "config": CONFIG, "samples": sample_plan(),
        "format_posts_ceiling": 0, "semantic_posts_ceiling": 0,
        "source_input_mode": "full_transcript", "fresh_leaf_posts": 2,
        "verify_adaptation": VERIFY_ADAPTATION,
        "historical_semantic_quality_verified": False} | prior.prior.historical_state(group)


def parent_asset_paths():
    return [PARENT_GROUP, PARENT_TRACKER,
        *(PARENT_REPORT / "results" / name for name in (
            "provenance.json", "request-ledger.json", "closed-receipt.json", "result-index.json"))]


def inventory_paths():
    base_context()
    return sorted(set(_original["inventory_paths"]() + parent_asset_paths() + [
        Path(__file__), ADAPTER, PROJECT / "backend/tests/test_summary_long_final_evaluation.py",
        REPORT.parent / "2026-10-11-summary-content-local-repair/review-criteria.md",
        PARENT_REPORT / "review-criteria.md", PROJECT / "backend/tests/test_summary_json.py",
        PROJECT / "backend/tests/test_summary_json_integration.py", PROJECT / "backend/tests/test_llm_service.py",
    ]))


asset_paths = inventory_paths


def runtime():
    base_context()
    return _original["runtime"]()


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
    return _verify()


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
