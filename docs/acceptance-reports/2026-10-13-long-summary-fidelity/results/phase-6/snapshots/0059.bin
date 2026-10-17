"""Phase-5: complete checks then revision of the bound closed phase-4 draft.

Root alone may call the provider. Two-stage arity is not an uncapped work budget;
reservations remain cumulative, never refunded or retried. Coverage and quote
origin are mechanical checks, not semantic certification. No telemetry, env
writes or reasoning persistence. Engineering: skills first; UI three-layer
tokens; narrow interfaces; yt-dlp only ytdlp_service; scene read-only.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
from pathlib import Path
from importlib.machinery import SourceFileLoader
from types import SimpleNamespace

PARENT_ENTRY = Path(__file__).with_name("pro_review_evaluate.py")


def load_reference(name):
    spec = importlib.util.spec_from_file_location(name, PARENT_ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reference = load_reference("checks_phase_adapter")
parent_reader = load_reference("checks_closed_parent_reader")
engine = reference.engine
inventory = reference.load_engine("checks_immutable_inventory")
PROJECT, REPORT, CORPUS, GROUP, SHARED_LOCK = (
    reference.PROJECT, reference.REPORT, reference.CORPUS, reference.GROUP, reference.SHARED_LOCK)
WORK_ID, SAMPLES = reference.WORK_ID, reference.SAMPLES
CONFIG = reference.CONFIG | {"llm_summary_fidelity_mode": "checks"}
read, io, os = reference.read, reference.io, reference.os
_live_runtime = reference._live_runtime
_reference_bind, _reference_sample_plan = reference.bind, reference.sample_plan
_reference_expected_payload = reference.expected_payload
_closed_binding = reference._closed_binding
_building_freeze = False


def select_phase(phase):
    global PHASE, RESULTS, TRACKER
    if phase != "phase-5":
        raise ValueError("Complete checks entry only allocates phase-5; never reopen phase-4")
    PHASE = phase
    RESULTS, TRACKER = REPORT / "results" / phase, GROUP.with_name(phase + ".json")


select_phase("phase-5")


def bind():
    # Rebind only our privately imported module; old frozen files stay untouched.
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "WORK_ID",
                 "PHASE", "RESULTS", "TRACKER", "CONFIG", "SAMPLES"):
        setattr(reference, name, globals()[name])
    reference._live_runtime = _live_runtime
    reference.parent_evidence, reference.sample_plan = parent_evidence, sample_plan
    reference.candidate_assets, reference.frozen_sources = candidate_assets, prepare_or_validate_frozen_sources
    reference.capture_request, reference.closed_binding = capture_request, closed_binding
    reference.feedback_from_raw, reference.expected_payload = feedback_from_raw, expected_payload
    reference.bind = bind
    _reference_bind()


def prior_context():
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK"):
        setattr(parent_reader, name, globals()[name])
    parent_reader.select_phase("phase-4")
    parent_reader.bind()


def parent_evidence():
    prior_context()
    checked = parent_reader.verify_results()
    if checked["stopped_on_error"] or checked["posts"] != 2:
        raise RuntimeError("Phase-4 must be closed and structurally successful with two stages")
    parent = parent_reader.engine
    frozen, product = read(parent.RESULTS / "provenance.json"), read(parent.RESULTS / "en-long.json")
    source = frozen["sample_plan"][0]
    if product.get("success") is not True or source["id"] != "en-long" or source["expected_posts"] != 2:
        raise RuntimeError("Only the bound successful phase-4 draft may be checked")
    paths = {name: parent.RESULTS / file for name, file in (
        ("provenance", "provenance.json"), ("receipt", "closed-receipt.json"),
        ("ledger", "request-ledger.json"), ("index", "result-index.json"),
        ("product", "en-long.json"), ("raw", "response-02.json"))}
    paths["tracker"] = parent.TRACKER
    source_names = {"source": (CORPUS / source["file"]).relative_to(PROJECT).as_posix(),
        "original_captions": (CORPUS / source["raw_path"]).relative_to(PROJECT).as_posix(),
        "codec": "backend/app/services/summary_output.py", "normalizer": "backend/app/services/summary_json.py",
        "preparation": "backend/app/services/llm_service.py"}
    paths.update({name: parent.snapshot_path(frozen, original) for name, original in source_names.items()})
    binding = {"phase": "phase-4", "paths": {}, "sha256": {}}
    for name, path in paths.items():
        path = path.resolve()
        if not path.is_relative_to(PROJECT.resolve()):
            raise RuntimeError("Parent evidence path escapes project")
        binding["paths"][name] = path.relative_to(PROJECT.resolve()).as_posix()
        binding["sha256"][name] = io.digest(path.read_bytes())
    text = parent.merge_helpers(frozen)._summary_input(paths["source"].read_text(encoding="utf-8"))
    return source, product["result"], binding, text, frozen


def sample_plan():
    return _reference_sample_plan()


def candidate_assets():
    return [*inventory.asset_paths(), Path(__file__), PARENT_ENTRY,
        PARENT_ENTRY.with_name("review_evaluate.py"), PARENT_ENTRY.with_name("refine_evaluate.py"),
        PROJECT / "backend/tests/test_long_checks_evaluation.py",
        PROJECT / "backend/tests/test_complete_source_checks.py",
        PROJECT / "backend/tests/test_summary_source_review.py",
        PROJECT / "docs/superpowers/specs/2026-10-14-complete-source-checks-design.md",
        REPORT / "review-checks-final.md"]


def capture_request(service, text, sample):
    class Captured(BaseException):
        pass
    class Capture:
        payloads = []
        def post(self, url, *, headers, json):
            self.payloads.append(json)
            if len(self.payloads) == 2:
                raise Captured
            import httpx
            targets = [sample["draft"]["summary"], *sample["draft"]["key_points"]]
            quote = next(line.strip() for line in text.splitlines() if line.strip())[:80]
            checks = {"checks": [{"target": index, "draft_quote": target,
                "source_quote": quote, "finding": "Freeze-only synthetic finding; not semantic verification."}
                for index, target in enumerate(targets)]}
            return httpx.Response(200, request=httpx.Request("POST", url), json={"choices": [{
                "message": {"content": globals()["json"].dumps(checks, ensure_ascii=False)}, "finish_reason": "stop"}]})
    client = Capture()
    try:
        service.summarize_text(text, title=sample["title"], output_language="zh-CN", client=client)
    except Captured:
        pass
    if len(client.payloads) != 2:
        raise RuntimeError("Complete checks/revision capture must have exactly two requests")
    return client.payloads


def closed_binding(phase, work_id):
    if (engine._closing or reference._verifying) and phase.get("phase") == "phase-4":
        frozen = read(RESULTS / "provenance.json")
        frozen_sources(frozen)
        prior = [row for row in frozen["group_at_freeze"]["phases"] if row["phase"] == "phase-4"]
        if work_id != WORK_ID or len(prior) != 1 or phase != prior[0]:
            raise RuntimeError("Closed parent group row differs from frozen owner")
        binding = frozen["sample_plan"][0]["draft_evidence"]
        return [engine.snapshot_path(frozen, binding["paths"][name]) for name in (
            "tracker", "ledger", "receipt", "index", "provenance")]
    return _closed_binding(phase, work_id)


def prepare_or_validate_frozen_sources(frozen):
    # The reusable freezer constructs this new dictionary before its first write.
    # Add phase-specific metadata only there; persisted verification is read-only.
    if _building_freeze:
        sample = frozen["sample_plan"][0]
        frozen["stages"][sample["id"]][0]["target_count"] = len(sample["draft"]["key_points"]) + 1
    return frozen_sources(frozen)


def render_frozen_review_messages(frozen, source, draft, title):
    path = engine.snapshot_path(frozen, "backend/app/services/llm_service.py")
    nodes = [node for node in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef) and node.name == "_summary_review_messages"]
    if len(nodes) != 1 or nodes[0].decorator_list:
        raise RuntimeError("Frozen pure checks prompt helper inventory differs")
    tree = ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module="__future__",
        names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[]))
    namespace = {"json": json, "settings": SimpleNamespace(**frozen["runtime_config"])}
    exec(compile(tree, str(path), "exec", dont_inherit=True), namespace)
    return namespace["_summary_review_messages"](source, draft, title=title, output_language=frozen["output_language"])


def frozen_sources(frozen):
    sample = frozen["sample_plan"][0]
    if ([row.get("id") for row in frozen["sample_plan"]] != list(SAMPLES)
            or frozen["config"].get("llm_summary_fidelity_mode") != "checks"
            or frozen["config"].get("llm_model") != "deepseek-v4-pro" or frozen.get("model") != "deepseek-v4-pro"
            or frozen.get("model_comparison") != {"parent_model": sample["parent_model"],
                "candidate_model": "deepseek-v4-pro", "mode": "explicit_comparison_no_fallback_no_default_change"}):
        raise RuntimeError("Frozen checks/profile/source identity differs")
    binding = sample["draft_evidence"]
    if binding["phase"] != "phase-4":
        raise RuntimeError("Checks must bind phase-4 evidence")
    paths = {name: engine.snapshot_path(frozen, original) for name, original in binding["paths"].items()}
    if any(io.digest(path.read_bytes()) != binding["sha256"][name] for name, path in paths.items()):
        raise RuntimeError("Frozen parent hash differs")
    old, receipt, ledger, index, product, tracker = (read(paths[name]) for name in (
        "provenance", "receipt", "ledger", "index", "product", "tracker"))
    if (any(value.get("work_id") != WORK_ID or value.get("phase") != "phase-4" for value in (
                old, receipt, ledger, index, tracker))
            or tracker.get("status") != "closed" or receipt.get("status") != "closed"
            or index.get("stopped_on_error") is not False or product.get("success") is not True
            or len(ledger.get("requests", [])) != 2 or receipt.get("posts") != 2 or index.get("posts") != 2
            or receipt.get("provenance_sha256") != binding["sha256"]["provenance"]
            or tracker.get("provenance_sha256") != binding["sha256"]["provenance"]
            or tracker.get("closed_receipt_sha256") != binding["sha256"]["receipt"]
            or receipt.get("ledger_sha256") != binding["sha256"]["ledger"]
            or receipt.get("index_sha256") != binding["sha256"]["index"]
            or ledger["requests"][-1].get("response_sha256") != binding["sha256"]["raw"]
            or any(row.get("result_sha256") != binding["sha256"]["product"] for row in ledger["requests"])
            or product.get("source_sha256") != sample["sha256"] or product.get("result") != sample["draft"]):
        raise RuntimeError("Frozen closed parent receipt/draft ownership differs")
    projection = old | {"snapshots": {key: frozen["snapshots"][binding["paths"][name]] for name, key in (
        ("codec", "backend/app/services/summary_output.py"), ("normalizer", "backend/app/services/summary_json.py"),
        ("preparation", "backend/app/services/llm_service.py"))}}
    codec, raw = engine.load_codec(projection), read(paths["raw"])
    decoded = codec.decode_payload(codec.decode_summary_json(raw.get("content")), strict=False)
    public = {"summary": decoded.summary.strip(), "key_points": [p.strip() for p in decoded.key_points if p.strip()],
        "provider": old["provider"], "model": old["model"]}
    original, helpers = old["sample_plan"][0], engine.merge_helpers(projection)
    text = helpers._summary_input(paths["source"].read_text(encoding="utf-8"))
    chunks = helpers._summary_chunks(text, min(old["config"]["llm_summary_chunk_chars"], old["config"]["llm_max_input_chars"]))
    current_source = engine.snapshot_path(frozen, (CORPUS / sample["file"]).relative_to(PROJECT).as_posix())
    if (raw.get("http_status") != 200 or raw.get("model") != old["model"] or raw.get("finish_reason") != "stop"
            or not public["summary"] or not public["key_points"] or public != sample["draft"]
            or old["model"] != sample["parent_model"] or old["provider"] != sample["parent_provider"]
            or old["endpoint"] != sample["parent_endpoint"] or old["model"] != frozen["model"]
            or len(public["key_points"]) > old["stages"][sample["id"]][-1]["max_points"]
            or io.digest(paths["source"].read_bytes()) != sample["sha256"]
            or io.digest(current_source.read_bytes()) != sample["sha256"]
            or io.digest(paths["original_captions"].read_bytes()) != sample["raw_sha256"]
            or io.digest(text) != sample["cleaned_sha256"] or len(text) != sample["cleaned_chars"]
            or [io.digest(part) for part in chunks] != sample["chunks"]
            or any(sample[key] != original[key] for key in (
                "file", "raw_path", "sha256", "raw_sha256", "title", "cleaned_chars", "cleaned_sha256", "chunks"))
            or sample["expected_posts"] != 2 or frozen["planned_posts"] != 2
            or [stage["stage"] for stage in frozen["stages"][sample["id"]]] != ["review", "refine"]):
        raise RuntimeError("Frozen source/raw/draft checks binding differs")
    expected_tokens, expected_points = reference.source_budget(frozen, len(text))
    draft = {"key_points": sample["draft"]["key_points"], "summary": sample["draft"]["summary"]}
    review = frozen["stages"][sample["id"]][0]
    if (review.get("target_count") != len(draft["key_points"]) + 1
            or review["payload"].get("messages") != render_frozen_review_messages(frozen, text, draft, sample["title"])):
        raise RuntimeError("Frozen checks target count or actual bound-draft prompt differs")
    for position, stage in enumerate(frozen["stages"][sample["id"]]):
        payload, messages = stage["payload"], stage["payload"].get("messages", [])
        if len(messages) != 2 or [message.get("role") for message in messages] != ["system", "user"]:
            raise RuntimeError("Frozen checks message roles differ")
        _, marker, serialized = messages[1]["content"].rpartition("Evidence and draft:\n")
        evidence = json.loads(serialized) if marker else None
        keys = {"original_transcript", "draft"} | ({"review_feedback"} if position else set())
        tokens = frozen["config"]["llm_summary_review_max_output_tokens"] if position == 0 else expected_tokens
        if (not isinstance(evidence, dict) or set(evidence) != keys or evidence["original_transcript"] != text
                or evidence["draft"] != draft or payload.get("model") != frozen["model"]
                or payload.get("max_tokens") != tokens or stage.get("max_points") != expected_points
                or len("\n".join(message["content"] for message in messages)) > frozen["config"]["llm_max_input_chars"]):
            raise RuntimeError("Frozen complete source/draft/checks budget differs")


def feedback_from_raw(frozen, ordinal):
    rows = read(RESULTS / "request-ledger.json")["requests"]
    raw_path = RESULTS / f"response-{ordinal:02d}.json"
    if (type(ordinal) is not int or ordinal != 1 or len(rows) < ordinal
            or rows[ordinal - 1].get("ordinal") != ordinal or rows[ordinal - 1].get("status") != "response"
            or io.digest(raw_path.read_bytes()) != rows[ordinal - 1].get("response_sha256")):
        raise RuntimeError("Persisted checks raw differs from its durable attempt")
    raw = read(raw_path)
    if raw.get("http_status") != 200 or raw.get("model") != frozen["model"] or raw.get("finish_reason") != "stop":
        raise RuntimeError("Checks provider/model/completion differs")
    path = engine.snapshot_path(frozen, "backend/app/services/summary_review.py")
    loader = SourceFileLoader("frozen_complete_source_checks", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    service_path = engine.snapshot_path(frozen, "backend/app/services/llm_service.py")
    nodes = [node for node in ast.parse(service_path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef) and node.name == "_staged_json_payload"]
    if len(nodes) != 1 or nodes[0].decorator_list:
        raise RuntimeError("Frozen duplicate-safe checks JSON parser differs")
    tree = ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module="__future__",
        names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[]))
    namespace = {"json": json, "re": engine.re, "_StagedFormatError": RuntimeError, "LLMServiceError": RuntimeError}
    exec(compile(tree, str(service_path), "exec", dont_inherit=True), namespace)
    evidence = json.loads(frozen["stages"]["en-long"][0]["payload"]["messages"][1]["content"].rpartition("Evidence and draft:\n")[2])
    return module.parse_checks(namespace["_staged_json_payload"](raw.get("content")),
        source=evidence["original_transcript"], draft=evidence["draft"])


def expected_payload(frozen, sample, sample_post, ledger, codec):
    for row in ledger["requests"]:
        if io.digest((RESULTS / f"payload-{row['ordinal']:02d}.json").read_bytes()) != row.get("payload_sha256"):
            raise RuntimeError("Persisted prior payload drift before next payment")
        if row.get("status") == "response" and io.digest((RESULTS / f"response-{row['ordinal']:02d}.json").read_bytes()) != row.get("response_sha256"):
            raise RuntimeError("Persisted prior raw drift before next payment")
    return _reference_expected_payload(frozen, sample, sample_post, ledger, codec)


def plan():
    bind()
    return reference.plan()


def freeze():
    global _building_freeze
    bind()
    _building_freeze = True
    try:
        return reference.freeze()
    finally:
        _building_freeze = False


def check():
    bind()
    return reference.check()


def run(*, transport=None):
    bind()
    return reference.run(transport=transport)


def verify_results():
    bind()
    return reference.verify_results()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    flags = parser.add_mutually_exclusive_group(required=True)
    for name in ("plan", "freeze", "check", "run", "verify"):
        flags.add_argument(f"--{name}", action="store_true")
    args = parser.parse_args(argv)
    select_phase(args.phase)
    action = plan if args.plan else freeze if args.freeze else check if args.check else run if args.run else verify_results
    print(json.dumps(action(), ensure_ascii=False))


if __name__ == "__main__":
    main()
