"""Phase-11 full-source diagnostic, one direct request and no retries.

Reuse mature production generation, Responses parsing and accounting. Only
source packaging changes; this is no product routing/default decision. Skills
first, narrow interfaces, UI three-tier tokens/design skills, yt-dlp only its
service and scene read-only. Preserve env/accounts/UI/models/history. Corpus
keeps its attributed license; old products are accounting evidence only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load(Path(__file__).with_name("native_merge_evaluate.py"), "direct_source_primitives")
engine, parent = base.engine, base.parent
PROJECT, REPORT, CORPUS = base.PROJECT, base.REPORT, base.CORPUS
GROUP, SHARED_LOCK, WORK_ID = base.GROUP, base.SHARED_LOCK, base.WORK_ID
CONFIG, SAMPLES, PHASE_POST_CAP = base.CONFIG, ("en-long",), 1
read, io = base.read, base.io
_live_runtime, _assets, _closed = base._live_runtime, base._assets, base._closed
_verifying = False


def select_phase(phase):
    global PHASE, RESULTS, TRACKER
    if phase != "phase-11":
        raise ValueError("This diagnostic only allocates fresh phase-11")
    PHASE, RESULTS, TRACKER = phase, REPORT / "results" / phase, GROUP.with_name(phase + ".json")


select_phase("phase-11")


def bind():
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "WORK_ID",
                 "PHASE", "RESULTS", "TRACKER", "CONFIG", "SAMPLES"):
        setattr(base, name, globals()[name])
    base.sample_plan, base.runtime = sample_plan, runtime
    base.asset_paths, base.frozen_sources = asset_paths, frozen_sources
    base.bind()
    engine.runtime, engine.asset_paths = runtime, asset_paths
    engine.sample_plan, engine.frozen_sources = sample_plan, frozen_sources
    engine.expected_payload, engine.closed_binding = expected_payload, closed_binding


def prior_closed_guard():
    group = engine.group_state()
    rows = [row for row in group["phases"] if row.get("phase") == "phase-10"]
    own = [row for row in group["phases"] if row.get("phase") == PHASE]
    if (len(rows) != 1 or rows[0].get("status") != "closed" or rows[0].get("reserved_posts") != 1
            or group["reserved_posts"] != 16 + sum(row["reserved_posts"] for row in own)):
        raise RuntimeError("Expected closed phase-10 and existing cumulative count 16")
    return group, rows[0]


def parent_evidence():
    group, row = prior_closed_guard()
    paths = _closed(row, WORK_ID)
    binding = {"paths": {}, "sha256": {}}
    for key, path in zip(("tracker", "ledger", "receipt", "index", "provenance", "product"),
                         [*paths, Path(row["ledger"]).parent / "en-long.json"]):
        path = path.resolve()
        if not path.is_relative_to(PROJECT.resolve()):
            raise RuntimeError("Parent evidence escapes project")
        binding["paths"][key] = path.relative_to(PROJECT).as_posix()
        binding["sha256"][key] = io.digest(path.read_bytes())
    return binding, row


def source_identity_guard(sample, manifest_sha256, old):
    """Bind this diagnostic to the source identity already frozen in phase 10."""
    originals = [row for row in old["sample_plan"] if row.get("id") == "en-long"]
    manifest_name = (CORPUS / "manifest.json").resolve().relative_to(PROJECT.resolve()).as_posix()
    fields = ("id", "file", "raw_path", "sha256", "raw_sha256", "title", "license", "attribution",
              "cleaned_sha256", "cleaned_chars")
    if (len(originals) != 1 or any(sample.get(key) != originals[0].get(key) for key in fields)
            or manifest_sha256 != old["snapshots"].get(manifest_name, {}).get("sha256")
            or sample.get("manifest_sha256") != manifest_sha256):
        raise RuntimeError("Frozen phase-10 source identity differs")


def sample_plan():
    manifest = read(CORPUS / "manifest.json")
    rows = [row for row in manifest["samples"] if row.get("id") == "en-long"]
    if len(rows) != 1:
        raise RuntimeError("Source identity is ambiguous")
    row = rows[0]
    for name, checksum in (("file", "sha256"), ("raw_path", "raw_sha256")):
        path = (CORPUS / row[name]).resolve()
        if not path.is_relative_to(CORPUS.resolve()) or io.digest(path.read_bytes()) != row[checksum]:
            raise RuntimeError("Source path/hash differs")
    text = engine.cleaned((CORPUS / row["file"]).read_text(encoding="utf-8"))
    if not text or len(text) > CONFIG["llm_max_input_chars"]:
        raise RuntimeError("Complete source exceeds finite input limit; no truncation")
    binding, parent_row = parent_evidence()
    old = read(PROJECT / binding["paths"]["provenance"])
    sample = {key: row[key] for key in ("id", "file", "raw_path", "sha256", "raw_sha256", "title", "license", "attribution")}
    sample |= {"cleaned_chars": len(text), "cleaned_sha256": io.digest(text),
               "manifest_sha256": io.digest((CORPUS / "manifest.json").read_bytes())}
    source_identity_guard(sample, sample["manifest_sha256"], old)
    return [sample
        | {"expected_posts": 1,
           "parent_evidence": binding, "parent_group_row": parent_row,
           "request_path": "direct_source", "parent_provider": old["provider"],
           # Native freeze's endpoint compatibility interface expects chat form.
           "parent_endpoint": old["endpoint"].removesuffix("/responses") + "/chat/completions"}]


def candidate_assets():
    return sorted(set([*_assets(), Path(__file__), Path(base.__file__), Path(parent.__file__), base.SCHEMA_ENTRY,
        PROJECT / "backend/tests/test_direct_source_evaluation.py",
        PROJECT / "docs/superpowers/plans/2026-10-15-full-source-direct-diagnostic.md",
        REPORT / "reviews/phase-11-direct-source-tool.md"]))


def asset_paths():
    return sorted(set([*candidate_assets(), *(PROJECT / p for p in sample_plan()[0]["parent_evidence"]["paths"].values())]))


class ServiceAdapter:
    def __init__(self, service, sample):
        self.service, self.sample = service, sample

    def __getattr__(self, name):
        return getattr(self.service, name)

    def _endpoint(self):
        return self.service._endpoint(responses=True)

    def direct_content(self, transcript):
        text = self.service._summary_input(transcript)
        if (len(text) > CONFIG["llm_max_input_chars"] or len(text) != self.sample["cleaned_chars"]
                or io.digest(text) != self.sample["cleaned_sha256"]):
            raise RuntimeError("Full normalized direct source differs or exceeds input limit")
        return text

    def merge_content(self, transcript):
        text = self.direct_content(transcript)
        return text, len(text)

    def _summary_request(self, content_text, **options):
        # The reused freeze capture passes merge=True; only this private adapter
        # translates it. Both capture and execution call production merge=False.
        options["merge"] = False
        return self.service._summary_request(content_text, **options)

    def summarize_text(self, transcript, *, title, output_language, client=None):
        text = self.direct_content(transcript)
        return self._summary_request(text, title=title, output_language=output_language,
            client=client, merge=False, source_chars=len(text))


def runtime():
    settings, service, ignored = _live_runtime()
    adapter = ServiceAdapter(service, sample_plan()[0])
    return settings, adapter, adapter._endpoint()


def plan():
    bind()
    group, ignored = prior_closed_guard()
    return {"work_id": WORK_ID, "phase": PHASE, "planned_posts": 1, "phase_post_cap": 1,
        "budget_mode": "uncapped", "hard_ceiling": None, "work_reserved_posts": group["reserved_posts"],
        "network": False, "dotenv_read": False, "samples": sample_plan(), "config": CONFIG,
        "format_posts": 0, "semantic_posts": 0, "historical_semantic_quality_verified": False}


def freeze():
    # Reuse the mature freeze/register implementation. Its historical stage
    # name "merge" denotes the single final stage; request_path and payload
    # below explicitly bind the direct production request (merge=False).
    bind()
    prior_closed_guard()
    return base.freeze()


def frozen_sources(frozen):
    sample = frozen["sample_plan"][0]
    binding = sample["parent_evidence"]
    paths = {key: engine.snapshot_path(frozen, name) for key, name in binding["paths"].items()}
    if any(io.digest(path.read_bytes()) != binding["sha256"][key] for key, path in paths.items()):
        raise RuntimeError("Frozen parent evidence hash differs")
    tracker, ledger, receipt, index, old, product = [read(paths[key]) for key in ("tracker", "ledger", "receipt", "index", "provenance", "product")]
    row = sample["parent_group_row"]
    if (any(obj.get("work_id") != WORK_ID or obj.get("phase") != "phase-10" for obj in (tracker, ledger, receipt, index, old))
            or row.get("phase") != "phase-10" or row.get("status") != "closed" or row.get("reserved_posts") != 1
            or tracker.get("status") != "closed" or tracker.get("reserved_posts") != 1 or receipt.get("status") != "closed"
            or receipt.get("posts") != 1 or receipt.get("work_posts") != 16 or index.get("posts") != 1
            or len(ledger.get("requests", [])) != 1 or len(index.get("samples", [])) != 1
            or any(obj.get("closed_receipt_sha256") != binding["sha256"]["receipt"] for obj in (row, tracker))
            or receipt.get("ledger_sha256") != binding["sha256"]["ledger"] or receipt.get("index_sha256") != binding["sha256"]["index"]
            or any(obj.get("provenance_sha256") != binding["sha256"]["provenance"] for obj in (row, tracker, receipt))
            or ledger["requests"][0].get("result_sha256") != binding["sha256"]["product"]
            or index["samples"][0].get("result_sha256") != binding["sha256"]["product"] or product.get("sample") != "en-long"):
        raise RuntimeError("Closed phase-10 historical binding differs")
    manifest_path = engine.snapshot_path(frozen, (CORPUS / "manifest.json").relative_to(PROJECT).as_posix())
    manifest = read(manifest_path)
    source_identity_guard(sample, io.digest(manifest_path.read_bytes()), old)
    matches = [item for item in manifest["samples"] if item.get("id") == "en-long"]
    if len(matches) != 1 or any(matches[0].get(key) != sample.get(key) for key in ("file", "raw_path", "sha256", "raw_sha256", "title", "license", "attribution")):
        raise RuntimeError("Frozen attributed source manifest differs")
    source = engine.snapshot_path(frozen, (CORPUS / sample["file"]).relative_to(PROJECT).as_posix())
    captions = engine.snapshot_path(frozen, (CORPUS / sample["raw_path"]).relative_to(PROJECT).as_posix())
    helpers, codec = engine.merge_helpers(frozen), engine.load_codec(frozen)
    text = helpers._summary_input(source.read_text(encoding="utf-8"))
    stages = frozen["stages"]["en-long"]
    payload = stages[0]["payload"]
    if (frozen["config"] != CONFIG or io.digest(source.read_bytes()) != sample["sha256"]
            or io.digest(captions.read_bytes()) != sample["raw_sha256"] or io.digest(text) != sample["cleaned_sha256"]
            or len(text) != sample["cleaned_chars"] or not 0 < len(text) <= CONFIG["llm_max_input_chars"]
            or "notes" in sample or "leaf_evidence" in sample or frozen["parent_posts"] != 16
            or frozen["planned_posts"] != 1 or frozen["phase_post_cap"] != 1 or sample["expected_posts"] != 1
            or len(stages) != 1 or stages[0]["stage"] != "merge" or sample.get("request_path") != "direct_source" or stages[0]["max_points"] != 14
            or payload.get("model") != "deepseek-v4-pro" or payload.get("max_output_tokens") != 8192
            or payload.get("reasoning") != {"effort": "none"}
            or payload.get("text") != {"format": {"type": "json_schema", "name": "video_summary", "schema": codec.output_schema(14, None)}}
            or not payload["input"][-1]["content"].endswith("Transcript:\n" + text)
            or sum(len(message["content"]) for message in payload["input"]) + len(payload["instructions"]) > CONFIG["llm_max_input_chars"]):
        raise RuntimeError("Frozen full-source direct payload differs")


def closed_binding(row, work_id):
    if (engine._closing or _verifying) and row.get("phase") == "phase-10":
        frozen = read(RESULTS / "provenance.json")
        frozen_sources(frozen)
        sample = frozen["sample_plan"][0]
        if work_id != WORK_ID or row != sample["parent_group_row"]:
            raise RuntimeError("Closed parent group row differs")
        return [engine.snapshot_path(frozen, sample["parent_evidence"]["paths"][key]) for key in ("tracker", "ledger", "receipt", "index", "provenance")]
    return _closed(row, work_id)


def expected_payload(frozen, sample, sample_post, ledger, codec):
    if sample != "en-long" or sample_post != 1 or ledger["requests"]:
        raise RuntimeError("Only one frozen direct request is allowed")
    return frozen["stages"][sample][0]["payload"]


def check():
    bind()
    return engine.check()


def run(*, transport=None, caller=None):
    for name in ("PROJECT", "REPORT", "CORPUS", "GROUP", "SHARED_LOCK", "RESULTS", "TRACKER"):
        setattr(parent, name, globals()[name])
    parent.caller_guard(transport=transport, caller=caller)
    bind()
    with io.directory_guard(SHARED_LOCK):
        prior_closed_guard()
    return engine.run(transport=transport)


def verify_results():
    global _verifying
    bind()
    _verifying = True
    try:
        return engine.verify_results()
    finally:
        _verifying = False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--caller", choices=("root",))
    flags = parser.add_mutually_exclusive_group(required=True)
    for name in ("plan", "freeze", "check", "run", "verify"):
        flags.add_argument(f"--{name}", action="store_true")
    args = parser.parse_args(argv)
    select_phase(args.phase)
    action = plan if args.plan else freeze if args.freeze else check if args.check else verify_results
    print(json.dumps(run(caller=args.caller) if args.run else action(), ensure_ascii=False))


if __name__ == "__main__":
    main()
