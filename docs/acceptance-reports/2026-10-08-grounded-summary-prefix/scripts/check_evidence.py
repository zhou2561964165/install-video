"""Offline prefix contracts evidence check with an explicit complete code chain.

Engineering: skills before plans; UI ui-ux-pro-max/design-system, three-layer
tokens; configurable narrow interfaces; llm_service/ytdlp_service boundaries;
scene read-only. Preserve MIT authors and CC BY-NC-SA 4.0 attribution. Lexical
and contract evidence does not establish semantic accuracy or source entailment.
"""
import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
RESULTS = REPORT / "results"
LEDGER = RESULTS / "request-ledger.json"
PHASE = "organization-prefix"
CEILING = 13
CONTRACT_CHECKER_PATH = REPORT.parent / "2026-10-07-grounded-summary-contracts/scripts/check_evidence.py"
CHECKER = REPORT.parent / "2026-10-05-grounded-summary-evidence/scripts/check_evidence.py"
CHAIN_PATHS = {
    "prefix": Path(__file__).with_name("evaluate.py"),
    "contracts": REPORT.parent / "2026-10-07-grounded-summary-contracts/scripts/evaluate.py",
    "final": REPORT.parent / "2026-10-07-grounded-summary-final/scripts/evaluate.py",
    "organization": REPORT.parent / "2026-10-07-grounded-summary-organization/scripts/evaluate.py",
    "runner": REPORT.parent / "2026-10-05-grounded-summary-evidence/scripts/evaluate.py",
    "contracts-checker": CONTRACT_CHECKER_PATH,
    "final-checker": REPORT.parent / "2026-10-07-grounded-summary-final/scripts/check_evidence.py",
}
_spec = importlib.util.spec_from_file_location("prefix_contract_binding_checker", CONTRACT_CHECKER_PATH)
contracts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(contracts)
checker = contracts.checker
read, same_json = contracts.read, contracts.same_json
require_count = contracts.require_count


@contextmanager
def configured_checker():
    bindings = {
        contracts: {"REPORT": REPORT, "RESULTS": RESULTS, "LEDGER": LEDGER,
                    "PHASE": PHASE, "CEILING": CEILING},
        checker: {"REPORT": REPORT, "RESULTS": RESULTS, "SHARED_LEDGER": LEDGER, "read": read},
    }
    previous = {module: {key: getattr(module, key) for key in values} for module, values in bindings.items()}
    try:
        for module, values in bindings.items():
            for key, value in values.items():
                setattr(module, key, value)
        yield
    finally:
        for module, values in previous.items():
            for key, value in values.items():
                setattr(module, key, value)


def require_payload_transport(frozen, row):
    """Bind actual POST fields before executing any hash-verified frozen code."""
    require = checker.require
    stage = row.get("stage")
    require(isinstance(stage, str) and stage in frozen["stage_max_output_tokens"],
            "Payload transport stage mismatch")
    path = RESULTS / "payloads" / f"{row['ordinal']:02d}.json"
    require(checker.digest(path) == row.get("payload_sha256"), "Payload hash mismatch")
    payload = read(path)
    require(isinstance(payload, dict) and isinstance(frozen.get("options"), dict),
            "Payload transport object mismatch")
    # Match the historical caller's expected_options construction, including
    # every frozen option and every actual non-message top-level field. Unlike
    # Python equality, same_json distinguishes bool/int/float recursively.
    actual = {key: value for key, value in payload.items() if key != "messages"}
    expected = {"model": frozen["model"], "temperature": 0.2,
                "max_tokens": frozen["stage_max_output_tokens"][stage], **frozen["options"]}
    require(type(payload.get("max_tokens")) is int
            and payload["max_tokens"] == frozen["stage_max_output_tokens"][stage]
            and same_json(actual, expected), "Payload transport differs from freeze")
    messages = payload.get("messages")
    require(isinstance(messages, list) and len(messages) == 2
            and same_json(messages[0], {"role": "system", "content": frozen["stage_prompts"][stage]})
            and isinstance(messages[1], dict) and set(messages[1]) == {"role", "content"}
            and messages[1]["role"] == "user" and isinstance(messages[1]["content"], str),
            "Payload message contract differs from freeze")


def check_phase():
    with configured_checker():
        require = checker.require
        frozen = read(RESULTS / f"{PHASE}-provenance.json")
        require(frozen.get("phase") == PHASE and type(frozen.get("ceiling")) is int
                and frozen["ceiling"] == CEILING and frozen.get("ledger") == str(LEDGER),
                "Frozen phase ledger identity mismatch")
        require_count(frozen.get("expected_posts"), CEILING, "Frozen POST count must be an integer and match")
        plans = frozen.get("samples")
        require(isinstance(plans, list) and len(plans) == 3, "Frozen sample count mismatch")
        for plan in plans:
            require(isinstance(plan, dict) and type(plan.get("sections")) is int and plan["sections"] >= 1,
                    "Frozen section count must be an integer")
            require_count(plan.get("expected_posts"), plan["sections"] + 2,
                          "Frozen sample POST count must be an integer and match")
            require(type(plan.get("cleaned_chars")) is int and plan["cleaned_chars"] >= 1,
                    "Frozen source count must be an integer")
        require(sum(plan["expected_posts"] for plan in plans) == CEILING, "Frozen total POST count mismatch")
        require(isinstance(frozen.get("stage_max_output_tokens"), dict)
                and all(type(frozen["stage_max_output_tokens"].get(stage)) is int
                        and frozen["stage_max_output_tokens"][stage] > 0 for stage in ("extract", "compose", "audit")),
                "Frozen stage budget must be an integer")
        # Unlike calling contracts.check_phase(), this validates the new wrapper
        # identity directly. The actual reused contracts checker remains a
        # separate digest; no __file__ substitution conceals executed code.
        paths = {**CHAIN_PATHS, "checker": Path(__file__), "checker-runner": CHECKER}
        chain = {key: checker.digest(path) for key, path in paths.items()}
        require(same_json(frozen.get("runner_chain_sha256"), chain), "Runner/checker chain hash mismatch")
        require(frozen.get("entrypoint_sha256") == chain["prefix"]
                and frozen.get("contracts_wrapper_sha256") == chain["contracts"]
                and frozen.get("final_wrapper_sha256") == chain["final"]
                and frozen.get("organization_wrapper_sha256") == chain["organization"]
                and frozen.get("runner_sha256") == chain["runner"], "Entrypoint chain identity mismatch")
        require(frozen.get("evidence_checker_sha256") == chain["checker"]
                and frozen.get("evidence_checker_runner_sha256") == chain["checker-runner"], "Checker hash mismatch")
        # Verify raw generation inputs here too: the historical checker validates
        # individual source bytes after loading the codec. This phase requires
        # every original source to be bound before any frozen code executes.
        require(checker.digest(REPORT / "rubric.json") == frozen["rubric_sha256"], "Rubric hash mismatch")
        require(set(frozen["module_sha256"]) == {"service", "config", "facts"}, "Missing frozen module")
        for key, value in frozen["module_sha256"].items():
            require(checker.digest(RESULTS / f"{PHASE}-{key}.py") == value, "Frozen module hash mismatch")
        manifest_path = checker.OLD / "corpus/manifest.json"
        require(checker.digest(manifest_path) == frozen["manifest_sha256"], "Frozen manifest hash mismatch")
        manifest = read(manifest_path)
        require([row["id"] for row in plans] == [row["id"] for row in manifest["samples"]], "Frozen samples mismatch")
        for source, plan in zip(manifest["samples"], plans):
            path = (checker.OLD / "corpus" / source["file"]).resolve()
            require(path.is_relative_to((checker.OLD / "corpus").resolve()), "Frozen corpus path mismatch")
            require(checker.digest(path) == source["sha256"] == plan["sha256"], "Frozen source hash mismatch")
        for row in frozen["baseline"]["sample_results"]:
            require(checker.digest(checker.BASE / "results" / row["file"]) == row["sha256"], "Baseline hash mismatch")
        ledger = read(LEDGER)
        require(type(ledger.get("ceiling")) is int and ledger["ceiling"] == CEILING
                and isinstance(ledger.get("requests"), list), "Prefix ledger ceiling mismatch")
        sample_posts = {}
        for ordinal, row in enumerate(ledger["requests"], 1):
            require(isinstance(row, dict) and row.get("phase") == PHASE, "Foreign phase in prefix ledger")
            require_count(row.get("ordinal"), ordinal, "Prefix ledger ordinal identity mismatch")
            sample = row.get("sample")
            require(isinstance(sample, str), "Prefix ledger sample identity mismatch")
            sample_posts[sample] = sample_posts.get(sample, 0) + 1
            require_count(row.get("sample_post"), sample_posts[sample], "Prefix ledger sample_post identity mismatch")
            require_payload_transport(frozen, row)
        # Historical check_phase validates frozen service/config/facts, rubric,
        # manifest and baseline hashes before its pure codec/cleanup execution.
        result = checker.check_phase(PHASE)
        codec, _ = checker.frozen_helpers(PHASE)
        require(callable(getattr(codec, "parse_extraction", None))
                and callable(getattr(codec, "parse_planned_composition", None)), "Frozen prefix codec missing")
        limits = codec.FactLimits(**frozen["fact_limits"])
        index = read(RESULTS / f"{PHASE}-index.json")
        for sample, row in zip(result["samples"], index["sample_results"]):
            public = read(RESULTS / row["file"])
            trace = read(RESULTS / f"{PHASE}-{row['id']}-trace.json")
            last = trace["events"][-1] if trace["events"] else {}
            calls = [r for r in ledger["requests"] if r["sample"] == row["id"]]
            sample.update(contracts.bind_sample(codec, limits, frozen, public, calls, last))
        return result


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
