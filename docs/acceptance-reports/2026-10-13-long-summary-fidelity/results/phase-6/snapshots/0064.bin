"""Phase-6: bounded Responses/schema checks then declared final revision.

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
from contextlib import nullcontext
from dataclasses import asdict
from urllib.parse import urlsplit

PARENT_ENTRY = Path(__file__).with_name("pro_review_evaluate.py")


def load_reference(name):
    spec = importlib.util.spec_from_file_location(name, PARENT_ENTRY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reference = load_reference("structured_checks_phase_adapter")
parent_reader = load_reference("structured_checks_closed_parent_reader")
engine = reference.engine
inventory = reference.load_engine("structured_checks_immutable_inventory")
PROJECT, REPORT, CORPUS, GROUP, SHARED_LOCK = (
    reference.PROJECT, reference.REPORT, reference.CORPUS, reference.GROUP, reference.SHARED_LOCK)
WORK_ID, SAMPLES = reference.WORK_ID, reference.SAMPLES
CONFIG = reference.CONFIG | {"llm_summary_fidelity_mode": "checks",
    "llm_summary_thinking_mode": "disabled", "llm_summary_response_format": "json_object"}
read, io, os = reference.read, reference.io, reference.os
_live_runtime = reference._live_runtime
_reference_bind, _reference_sample_plan = reference.bind, reference.sample_plan
_reference_expected_payload = reference.expected_payload
_reference_plan = reference.plan
_closed_binding = reference._closed_binding
_building_freeze = False
_captured_endpoints = []
PHASE_POST_CAP = 2
PHASE_CAP_PURPOSE = "phase_post_cap_and_production_arity_not_work_budget"


def phase_plan():
    plan = _reference_plan()
    plan["phase_post_cap"] = PHASE_POST_CAP
    plan["stage_count_purpose"] = PHASE_CAP_PURPOSE
    return plan


def select_phase(phase):
    global PHASE, RESULTS, TRACKER
    if phase != "phase-6":
        raise ValueError("Structured checks entry only allocates phase-6; never reopen phase-1 through phase-5")
    PHASE = phase
    RESULTS, TRACKER = REPORT / "results" / phase, GROUP.with_name(phase + ".json")


select_phase("phase-6")


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
    reference.plan = phase_plan
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
        PARENT_ENTRY.with_name("checks_evaluate.py"),
        PROJECT / "backend/tests/test_long_structured_checks_evaluation.py",
        PROJECT / "backend/tests/test_complete_source_checks.py",
        PROJECT / "backend/tests/test_summary_source_review.py",
        PROJECT / "backend/tests/test_summary_source_revision.py",
        PROJECT / "backend/tests/test_summary_scope_guidance.py",
        PROJECT / "docs/superpowers/specs/2026-10-14-long-summary-scope-check-hardening.md",
        REPORT / "reviews/phase-6-scope-check-production-final.md",
        REPORT / "reviews/phase-6-structured-checks-tool-final.md"]


def capture_request(service, text, sample):
    global _captured_endpoints
    class Captured(BaseException):
        pass
    class Capture:
        payloads = []
        endpoints = []
        def post(self, url, *, headers, json):
            self.payloads.append(json)
            self.endpoints.append(url)
            if len(self.payloads) == 2:
                raise Captured
            import httpx
            targets = [sample["draft"]["summary"], *sample["draft"]["key_points"]]
            quote = next(line.strip() for line in text.splitlines() if line.strip())[:80]
            checks = {f"target_{index}": {"assessment": "uncertain", "source_quote": quote,
                "finding": "Freeze-only synthetic finding; not semantic verification."}
                for index, target in enumerate(targets)}
            return httpx.Response(200, request=httpx.Request("POST", url), json={"object": "response",
                "status": "completed", "output": [{"type": "message", "role": "assistant",
                    "status": "completed", "content": [{"type": "output_text",
                        "text": globals()["json"].dumps(checks, ensure_ascii=False)}]}]})
    client = Capture()
    try:
        service.summarize_text(text, title=sample["title"], output_language="zh-CN", client=client)
    except Captured:
        pass
    if len(client.payloads) != 2:
        raise RuntimeError("Complete checks/revision capture must have exactly two requests")
    _captured_endpoints = list(client.endpoints)
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
        frozen["phase_post_cap"] = PHASE_POST_CAP
        frozen["stage_count_purpose"] = PHASE_CAP_PURPOSE
        frozen["stages"][sample["id"]][0]["target_count"] = len(sample["draft"]["key_points"]) + 1
        for stage, endpoint in zip(frozen["stages"][sample["id"]], _captured_endpoints):
            stage["endpoint"] = endpoint
            stage["transport"] = "responses" if "text" in stage["payload"] else "chat"
            stage["max_output_tokens"] = stage["payload"].get("max_output_tokens", stage["payload"].get("max_tokens"))
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


def review_module(frozen):
    path = engine.snapshot_path(frozen, "backend/app/services/summary_review.py")
    loader = SourceFileLoader("frozen_structured_source_checks", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def payload_messages(payload):
    if "text" not in payload:
        return payload.get("messages", [])
    return [{"role": "system", "content": payload.get("instructions")}, *payload.get("input", [])]


def planned_endpoint(frozen, position):
    base = frozen["endpoint"]
    if not base.endswith("/chat/completions"):
        raise RuntimeError("Frozen base transport is not the declared Chat endpoint")
    return base[:-len("/chat/completions")] + "/responses" if position == 0 or "text" in frozen["stages"]["en-long"][position]["payload"] else base


def frozen_sources(frozen):
    sample = frozen["sample_plan"][0]
    if (type(frozen.get("phase_post_cap")) is not int or frozen.get("phase_post_cap") != PHASE_POST_CAP
            or frozen.get("stage_count_purpose") != PHASE_CAP_PURPOSE
            or frozen["planned_posts"] != PHASE_POST_CAP
            or [row.get("id") for row in frozen["sample_plan"]] != list(SAMPLES)
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
    module = review_module(frozen)
    review_tokens = module.checks_output_tokens(len(draft["key_points"]))
    review_payload = review["payload"]
    if (review.get("target_count") != len(draft["key_points"]) + 1
            or payload_messages(review_payload) != render_frozen_review_messages(frozen, text, draft, sample["title"])
            or review_tokens > frozen["config"]["llm_summary_review_max_output_tokens"]
            or review_payload.get("text") != {"format": {"type": "json_schema", "name": "video_summary_review",
                "schema": module.checks_schema(len(draft["key_points"]))}}
            or review_payload.get("reasoning") != {"effort": "none"}
            or set(review_payload) != {"model", "temperature", "instructions", "input", "max_output_tokens", "text", "reasoning"}):
        raise RuntimeError("Frozen checks target count or actual bound-draft prompt differs")
    for position, stage in enumerate(frozen["stages"][sample["id"]]):
        payload, messages = stage["payload"], payload_messages(stage["payload"])
        if len(messages) != 2 or [message.get("role") for message in messages] != ["system", "user"]:
            raise RuntimeError("Frozen checks message roles differ")
        _, marker, serialized = messages[1]["content"].rpartition("Evidence and draft:\n")
        evidence = json.loads(serialized) if marker else None
        keys = {"original_transcript", "draft"} | ({"review_feedback"} if position else set())
        tokens = review_tokens if position == 0 else expected_tokens
        expected_transport = "responses" if "text" in payload else "chat"
        endpoint = stage.get("endpoint")
        parts = urlsplit(endpoint) if type(endpoint) is str else None
        if (not isinstance(evidence, dict) or set(evidence) != keys or evidence["original_transcript"] != text
                or evidence["draft"] != draft or payload.get("model") != frozen["model"]
                or payload.get("max_output_tokens" if expected_transport == "responses" else "max_tokens") != tokens
                or stage.get("max_output_tokens") != tokens or stage.get("transport") != expected_transport
                or endpoint != planned_endpoint(frozen, position)
                or parts is None or parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment
                or payload.get("temperature") != 0.2 or stage.get("max_points") != expected_points
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
    module = review_module(frozen)
    service_path = engine.snapshot_path(frozen, "backend/app/services/llm_service.py")
    nodes = [node for node in ast.parse(service_path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef) and node.name == "_staged_json_payload"]
    if len(nodes) != 1 or nodes[0].decorator_list:
        raise RuntimeError("Frozen duplicate-safe checks JSON parser differs")
    tree = ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module="__future__",
        names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[]))
    namespace = {"json": json, "re": engine.re, "_StagedFormatError": RuntimeError, "LLMServiceError": RuntimeError}
    exec(compile(tree, str(service_path), "exec", dont_inherit=True), namespace)
    evidence = json.loads(payload_messages(frozen["stages"]["en-long"][0]["payload"])[1]["content"].rpartition("Evidence and draft:\n")[2])
    return module.parse_checks(namespace["_staged_json_payload"](raw.get("content")),
        source=evidence["original_transcript"], draft=evidence["draft"])


def expected_payload(frozen, sample, sample_post, ledger, codec):
    for row in ledger["requests"]:
        if io.digest((RESULTS / f"payload-{row['ordinal']:02d}.json").read_bytes()) != row.get("payload_sha256"):
            raise RuntimeError("Persisted prior payload drift before next payment")
        if row.get("status") == "response" and io.digest((RESULTS / f"response-{row['ordinal']:02d}.json").read_bytes()) != row.get("response_sha256"):
            raise RuntimeError("Persisted prior raw drift before next payment")
    payload = json.loads(json.dumps(frozen["stages"][sample][sample_post - 1]["payload"]))
    if sample_post == 2:
        rows = ledger["requests"]
        if len(rows) != 1 or rows[0]["status"] != "response" or rows[0]["stage"] != "review":
            raise RuntimeError("Revision requires exactly one successful structured review")
        messages = payload_messages(payload)
        prefix, marker, serialized = messages[1]["content"].rpartition("Evidence and draft:\n")
        evidence = json.loads(serialized) if marker else None
        planned = next(row for row in frozen["sample_plan"] if row["id"] == sample)
        if (not isinstance(evidence, dict) or set(evidence) != {"original_transcript", "draft", "review_feedback"}
                or evidence["draft"] != {"key_points": planned["draft"]["key_points"], "summary": planned["draft"]["summary"]}):
            raise RuntimeError("Frozen source/draft/feedback template differs")
        evidence["review_feedback"] = feedback_from_raw(frozen, rows[0]["ordinal"])
        messages[1]["content"] = prefix + marker + json.dumps(evidence, ensure_ascii=False)
        if "text" in payload:
            payload["input"] = messages[1:]
        else:
            payload["messages"] = messages
    if len("\n".join(message["content"] for message in payload_messages(payload))) > frozen["config"]["llm_max_input_chars"]:
        raise RuntimeError("Complete source/draft/checks feedback exceeds capacity")
    return payload


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
    with io.directory_guard(SHARED_LOCK):
        frozen, ledger, tracker = engine.frozen_state(live=True)
        group = engine.group_state()
        if (tracker["status"] != "frozen" or ledger["requests"] or group["status"] != "active"
                or type(frozen.get("phase_post_cap")) is not int
                or frozen.get("phase_post_cap") != PHASE_POST_CAP):
            raise RuntimeError("Offline check requires a fresh frozen finite phase")
        receipt = {"phase": PHASE, "phase_post_cap": PHASE_POST_CAP,
            "provenance_sha256": tracker["provenance_sha256"], "network": False, "dotenv_read": False}
        receipt_path = RESULTS / "offline-check.json"
        if receipt_path.exists():
            persisted = read(receipt_path)
            if (type(persisted.get("phase_post_cap")) is not int or persisted != receipt):
                raise RuntimeError("Offline check receipt differs")
        else:
            io.exclusive(receipt_path, receipt)
        return receipt | {"freeze_valid": True}


def run(*, transport=None):
    bind()
    with io.directory_guard(SHARED_LOCK):
        tracker = read(TRACKER)
        if tracker.get("status") != "frozen" or (RESULTS / "result-index.json").exists():
            raise RuntimeError("One-shot structured checks phase already started; never reopen")
        receipt = {"phase": PHASE, "phase_post_cap": PHASE_POST_CAP,
            "provenance_sha256": tracker["provenance_sha256"], "network": False, "dotenv_read": False}
        offline_check = read(RESULTS / "offline-check.json") if (RESULTS / "offline-check.json").exists() else None
        if (type(offline_check) is not dict or type(offline_check.get("phase_post_cap")) is not int
                or offline_check != receipt):
            raise RuntimeError("Persisted offline check required")
        index = {"work_id": WORK_ID, "phase": PHASE, "posts": 0, "stopped_on_error": False, "samples": []}
        pending = None
        tracker["status"] = "running"
        try:
            engine.durable(TRACKER, tracker)
            frozen, ledger, tracker = engine.frozen_state(live=True)
            settings, service, endpoint = engine.runtime()
            engine.match_runtime(settings, service, endpoint, frozen)
            codec = engine.load_codec(frozen)
            manager = nullcontext(transport) if transport is not None else __import__("httpx").Client(
                timeout=float(settings.llm_timeout_seconds), transport=__import__("httpx").HTTPTransport(retries=0))
            with manager as http:
                for sample in frozen["sample_plan"]:
                    before = len(read(RESULTS / "request-ledger.json")["requests"])
                    class Client:
                        def post(self, url, *, headers, json):
                            nonlocal pending
                            current, ledger, tracker = engine.frozen_state(live=True)
                            engine.match_runtime(settings, service, endpoint, current)
                            group = engine.group_state()
                            ordinal = len(ledger["requests"]) + 1
                            sample_post = ordinal - before
                            if (tracker["status"] != "running" or group["status"] != "active"
                                    or sample_post > sample["expected_posts"]
                                    or type(current.get("phase_post_cap")) is not int
                                    or ordinal > current["phase_post_cap"]):
                                raise RuntimeError("Unplanned production stage; arity audit refused")
                            stage = current["stages"][sample["id"]][sample_post - 1]
                            if url != stage["endpoint"]:
                                raise RuntimeError("Actual stage endpoint differs from freeze")
                            expected = expected_payload(current, sample["id"], sample_post, ledger, codec)
                            if json != expected:
                                raise RuntimeError("Actual payload/options/source differ from freeze")
                            path = RESULTS / f"payload-{ordinal:02d}.json"
                            io.exclusive(path, expected)
                            row = {"ordinal": ordinal, "sample": sample["id"], "sample_post": sample_post,
                                "stage": stage["stage"], "endpoint": url, "transport": stage["transport"],
                                "max_output_tokens": stage["max_output_tokens"], "status": "reserved",
                                "reserved_utc": io.now(), "payload_sha256": io.digest(path.read_bytes())}
                            pending = row
                            group["reserved_posts"] += 1
                            owner = next(item for item in group["phases"] if item["phase"] == PHASE)
                            owner.update(status="running", reserved_posts=ordinal)
                            ledger["requests"].append(row)
                            tracker["reserved_posts"] = ordinal
                            try:
                                engine.durable(GROUP, group)
                                engine.durable(RESULTS / "request-ledger.json", ledger)
                                engine.durable(TRACKER, tracker)
                                response = http.post(url, headers=headers, json=json)
                                try:
                                    body = response.json()
                                except ValueError:
                                    body = None
                                safe = response_evidence(body, responses=stage["transport"] == "responses")
                                safe.update(http_status=response.status_code, received_utc=io.now(), endpoint=url,
                                    transport=stage["transport"], max_output_tokens=stage["max_output_tokens"],
                                    model=current["model"] if isinstance(body, dict) and body.get("model") == current["model"] else "mismatch")
                                raw_path = RESULTS / f"response-{ordinal:02d}.json"
                                io.exclusive(raw_path, safe)
                                row.update(status="response", http_status=response.status_code,
                                    usage=safe["usage"], response_sha256=io.digest(raw_path.read_bytes()))
                                engine.durable(RESULTS / "request-ledger.json", ledger)
                                pending = None
                                if safe["model"] != current["model"]:
                                    raise RuntimeError("Raw provider model drift")
                                return response
                            except BaseException as exc:
                                row.update(status="error", error_type=type(exc).__name__)
                                engine.durable(GROUP, group)
                                engine.durable(RESULTS / "request-ledger.json", ledger)
                                engine.durable(TRACKER, tracker)
                                pending = None
                                raise
                    try:
                        summary = service.summarize_text((CORPUS / sample["file"]).read_text(encoding="utf-8"),
                            title=sample["title"], output_language="zh-CN", client=Client())
                        engine.match_runtime(settings, service, endpoint, frozen)
                        engine.frozen_state(live=True)
                        after = read(RESULTS / "request-ledger.json")
                        if len(after["requests"]) != before + sample["expected_posts"]:
                            raise RuntimeError("Sample production arity differs")
                        public = asdict(summary)
                        if public != engine.decoded_response(frozen, len(after["requests"]),
                                frozen["stages"][sample["id"]][-1]["max_points"], codec):
                            raise RuntimeError("Public result differs from last raw")
                        result = {"sample": sample["id"], "source_sha256": sample["sha256"], "success": True, "result": public}
                    except Exception as exc:
                        index["stopped_on_error"] = True
                        result = {"sample": sample["id"], "source_sha256": sample["sha256"], "success": False,
                            "error_type": getattr(exc, "error_type", type(exc).__name__)}
                    path = RESULTS / f"{sample['id']}.json"
                    io.exclusive(path, result)
                    checksum = io.digest(path.read_bytes())
                    ledger = read(RESULTS / "request-ledger.json")
                    for row in ledger["requests"][before:]:
                        row["result_sha256"] = checksum
                    engine.durable(RESULTS / "request-ledger.json", ledger)
                    index["samples"].append({"sample": sample["id"], "success": result["success"],
                        "result_sha256": checksum, "posts": len(ledger["requests"]) - before})
                    if index["stopped_on_error"]:
                        break
        except BaseException as exc:
            index.update(stopped_on_error=True, phase_error_type=type(exc).__name__)
            raise
        finally:
            engine.close_phase(index, pending)
        return index


def response_evidence(body, *, responses):
    """Save only public output, classified completion and numeric supplier usage."""
    if not responses:
        return io.response_evidence(body)
    if not isinstance(body, dict):
        return {"content": None, "finish_reason": None, "usage": None, "response_status": None}
    status = body.get("status")
    allowed = {"completed", "incomplete", "in_progress", "failed", "cancelled", "queued"}
    status = status if status in allowed else None
    texts = []
    output = body.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message" or item.get("role") != "assistant":
                continue
            if isinstance(item.get("content"), list):
                texts.extend(part["text"] for part in item["content"] if isinstance(part, dict)
                    and part.get("type") == "output_text" and isinstance(part.get("text"), str))
    usage = body.get("usage")
    safe_usage = None
    if isinstance(usage, dict):
        safe_usage = {key: usage[key] for key in ("input_tokens", "output_tokens", "total_tokens")
            if type(usage.get(key)) is int and usage[key] >= 0}
        for key in ("input_tokens_details", "output_tokens_details"):
            details = usage.get(key)
            if isinstance(details, dict):
                safe_usage[key] = {field: details[field] for field in ("cached_tokens", "reasoning_tokens")
                    if type(details.get(field)) is int and details[field] >= 0}
    return {"content": "".join(texts) or None,
        "finish_reason": "stop" if status == "completed" else "length" if status in {"incomplete", "in_progress"} else None,
        "usage": safe_usage, "response_status": status}


def verify_results():
    bind()
    result = reference.verify_results()
    frozen = read(RESULTS / "provenance.json")
    offline_check = read(RESULTS / "offline-check.json")
    if (frozen.get("phase_post_cap") != PHASE_POST_CAP
            or type(frozen.get("phase_post_cap")) is not int
            or type(offline_check.get("phase_post_cap")) is not int
            or offline_check.get("phase_post_cap") != PHASE_POST_CAP
            or result.get("posts", 0) > PHASE_POST_CAP):
        raise RuntimeError("Frozen finite phase POST cap differs")
    for row in read(RESULTS / "request-ledger.json")["requests"]:
        stage = frozen["stages"][row["sample"]][row["sample_post"] - 1]
        if any(row.get(key) != stage[key] for key in ("endpoint", "transport", "max_output_tokens")):
            raise RuntimeError("Closed stage endpoint/transport/output budget differs")
        if row.get("response_sha256"):
            raw = read(RESULTS / f"response-{row['ordinal']:02d}.json")
            if any(raw.get(key) != stage[key] for key in ("endpoint", "transport", "max_output_tokens")) or raw.get("usage") != row.get("usage"):
                raise RuntimeError("Closed safe response stage/usage receipt differs")
    return result


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
