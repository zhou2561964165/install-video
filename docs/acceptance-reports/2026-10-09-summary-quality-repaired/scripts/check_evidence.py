"""Independent expanded-chain verification before reusing pure offline replay.

Engineering: skill-first; UI three-layer tokens; configurable narrow interfaces;
HTTP only llm_service, yt-dlp only ytdlp_service, scene read-only. Historical
corpus/rubric/outputs retain attribution and CC BY-NC-SA 4.0. No semantic score.
"""
import importlib.util
from pathlib import Path

ENTRY = Path(__file__).with_name("evaluate.py")
spec = importlib.util.spec_from_file_location("quality_followup_checker_entry", ENTRY)
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
spec = importlib.util.spec_from_file_location("quality_followup_parent_checker", entry.PARENT_CHECKER)
parent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
require = parent.require
_original_frozen_runtime = parent.frozen_runtime


def digest(path):
    return entry.base.digest(path.read_bytes())


def verify_assets():
    results, phase = entry.RESULTS, entry.PHASE
    frozen = entry.read(results / f"{phase}-provenance.json")
    require(frozen.get("phase") == phase and type(frozen.get("ceiling")) is int
            and frozen["ceiling"] == 19 and frozen.get("work_id") == entry.WORK_ID
            and frozen.get("ledger") == str(entry.LEDGER),
            "Frozen phase identity mismatch")
    require(entry.same_json(frozen.get("config"), entry.CONFIG), "Frozen configuration mismatch")
    require(entry.same_json(frozen.get("runner_chain_sha256"), entry.runner_chain()),
            "Runner/checker/parent/helper hash mismatch")
    require(entry.same_json(frozen.get("parent_assets_sha256"), entry.parent_assets()),
            "Closed parent artifacts changed")
    require(frozen.get("parent_phase") == "quality-final"
            and entry.same_json(frozen.get("parent_posts"), 3)
            and entry.same_json(frozen.get("maximum_work_posts"), 22), "Parent metadata mismatch")
    require(frozen.get("runner_sha256") == digest(entry.HELPER), "Source helper identity mismatch")
    modules = frozen.get("module_sha256")
    require(isinstance(modules, dict) and set(modules) == set(entry.MODULES), "Missing frozen module")
    for key, value in modules.items():
        require(digest(results / f"{phase}-{key}.py") == value, "Frozen module hash mismatch")
    require(digest(entry.REPORT / "rubric.json") == frozen["rubric_sha256"], "Rubric hash mismatch")
    require(digest(entry.ORIGINAL_RUBRIC) == frozen.get("original_rubric_sha256")
            == frozen["rubric_sha256"], "Original rubric mismatch")
    require(entry.same_json(frozen.get("baseline"), entry.read(entry.REPORT / "rubric.json")["baseline"]),
            "Frozen baseline metadata mismatch")
    manifest_path = entry.base.OLD / "corpus/manifest.json"
    require(digest(manifest_path) == frozen["manifest_sha256"], "Manifest hash mismatch")
    manifest = entry.read(manifest_path)
    require([s["id"] for s in manifest["samples"]] == [s["id"] for s in frozen["samples"]],
            "Frozen samples mismatch")
    require(type(frozen.get("expected_posts")) is int and frozen["expected_posts"] == 13,
            "Normal POST count mismatch")
    for sample, plan in zip(manifest["samples"], frozen["samples"]):
        path = (entry.base.OLD / "corpus" / sample["file"]).resolve()
        require(path.is_relative_to((entry.base.OLD / "corpus").resolve())
                and digest(path) == sample["sha256"] == plan["sha256"], "Source bytes mismatch")
        require(type(plan.get("sections")) is int and plan["sections"] >= 1
                and type(plan.get("expected_posts")) is int and plan["expected_posts"] == plan["sections"] + 2
                and type(plan.get("maximum_posts")) is int and plan["maximum_posts"] == plan["sections"] + 4,
                "Frozen sample budget mismatch")
    require(sum(s["maximum_posts"] for s in frozen["samples"]) == 19, "Maximum POST count mismatch")
    for row in frozen["baseline"]["sample_results"]:
        require(digest(entry.base.BASE / "results" / row["file"]) == row["sha256"], "Baseline hash mismatch")
    return frozen, manifest



def frozen_runtime(frozen):
    return _original_frozen_runtime(frozen)


def bind():
    parent.entry = entry
    parent.verify_assets = verify_assets
    parent.frozen_runtime = frozen_runtime


def check_phase():
    bind()
    return parent.check_phase()


def main(argv=None):
    bind()
    return parent.main(argv)


if __name__ == "__main__":
    main()

