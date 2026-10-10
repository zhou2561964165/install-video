"""Offline follow-up replay; all helpers and six modules are hash-bound.

Engineering: skills first, UI tokens, narrow service interfaces, scene read-only;
historical evidence untouched, MIT-derived corpus retains CC BY-NC-SA 4.0.
"""
import importlib.util
from pathlib import Path

ENTRY = Path(__file__).with_name("evaluate.py")
spec = importlib.util.spec_from_file_location("marker_checker_entry", ENTRY)
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)
spec = importlib.util.spec_from_file_location("marker_checker_core", wrapper.CHECKER_CORE)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
entry = wrapper.core
checker.entry = entry


def verify_assets():
    require, digest = checker.require, checker.digest
    results, phase = entry.RESULTS, entry.PHASE
    frozen = entry.read(results / f"{phase}-provenance.json")
    require(frozen.get("phase") == phase and type(frozen.get("ceiling")) is int
        and frozen["ceiling"] == 16 and frozen.get("work_id") == entry.WORK_ID,
        "Follow-up identity mismatch")
    require(entry.same_json(frozen.get("config"), entry.CONFIG), "Configuration mismatch")
    chain = {"entry": digest(wrapper.CORE), "checker": digest(Path(__file__)),
        "helper": digest(entry.HELPER), "revision_entry": digest(ENTRY),
        "checker_core": digest(wrapper.CHECKER_CORE)}
    require(entry.same_json(frozen.get("runner_chain_sha256"), chain), "Follow-up helper hash mismatch")
    modules = frozen.get("module_sha256")
    require(isinstance(modules, dict) and set(modules) == set(entry.MODULES), "Missing frozen module")
    for key, value in modules.items():
        require(digest(results / f"{phase}-{key}.py") == value, "Frozen module hash mismatch")
    require(digest(entry.REPORT / "rubric.json") == frozen["rubric_sha256"], "Rubric hash mismatch")
    path = entry.base.OLD / "corpus/manifest.json"
    require(digest(path) == frozen["manifest_sha256"], "Manifest hash mismatch")
    manifest = entry.read(path)
    require([s["id"] for s in manifest["samples"]] == [s["id"] for s in frozen["samples"]],
            "Sample ordering mismatch")
    require(type(frozen.get("expected_posts")) is int and frozen["expected_posts"] == 13,
            "Normal POST budget mismatch")
    for sample, plan in zip(manifest["samples"], frozen["samples"]):
        path = (entry.base.OLD / "corpus" / sample["file"]).resolve()
        require(path.is_relative_to((entry.base.OLD / "corpus").resolve())
            and digest(path) == sample["sha256"] == plan["sha256"], "Source bytes mismatch")
        require(type(plan.get("sections")) is int and plan["sections"] >= 1
            and type(plan.get("expected_posts")) is int and plan["expected_posts"] == plan["sections"] + 2
            and type(plan.get("maximum_posts")) is int and plan["maximum_posts"] == plan["sections"] + 3,
            "Sample repair budget mismatch")
    require(sum(s["maximum_posts"] for s in frozen["samples"]) == 16, "Phase budget mismatch")
    for row in frozen["baseline"]["sample_results"]:
        require(digest(entry.base.BASE / "results" / row["file"]) == row["sha256"], "Baseline hash mismatch")
    return frozen, manifest


checker.verify_assets = verify_assets
_check_phase = checker.check_phase


def check_phase():
    result = _check_phase()
    checker.require(result["posts"] <= 16, "Follow-up phase budget overflow")
    result["ceiling"] = 16
    return result


checker.check_phase = check_phase


if __name__ == "__main__":
    checker.main()
