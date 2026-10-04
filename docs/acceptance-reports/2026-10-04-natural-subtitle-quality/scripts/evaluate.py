"""Opt-in natural-caption evaluation. Durable 24-POST ceiling; no HTTP retry.

Freeze source, prompt, manifest and facts before running each phase. Results,
phase locks and reservations are never reset, overwritten or resumed.
Engineering: skills outrank plans; UI skills and three-layer tokens; configurable
abilities; stable narrow services; yt-dlp only in ytdlp_service.py; visuals read-only.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx
from dotenv import load_dotenv

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
SERVICE = PROJECT / "backend/app/services/llm_service.py"
SETTINGS_SOURCE = PROJECT / "backend/app/config.py"
RESULTS = REPORT / "results"
CEILING = 24
CONFIG = {"llm_summary_chunk_chars": 20_000, "llm_max_input_chars": 60_000,
          "llm_summary_max_chunks": 16, "llm_summary_max_output_tokens": 4096}
sys.path.insert(0, str(PROJECT / "backend"))
load_dotenv(PROJECT / "backend/.env", override=False)
from app.config import settings
from app.services.llm_service import LLMServiceError, _summary_chunks, _summary_input, summarize_text
for config_key, config_value in CONFIG.items():
    setattr(settings, config_key, config_value)


def digest(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def exclusive_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def durable_json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".writing")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def system_prompt() -> str:
    tree = ast.parse(SERVICE.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "_summary_request")
    for node in ast.walk(function):
        if isinstance(node, ast.Dict):
            fields = {key.value: value for key, value in zip(node.keys, node.values)
                      if isinstance(key, ast.Constant)}
            role = fields.get("role")
            if isinstance(role, ast.Constant) and role.value == "system":
                return ast.literal_eval(fields["content"])
    raise RuntimeError("Summary prompt not found; refuse HTTP")


def request_guidance(source: str) -> tuple[str, str]:
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "_summary_request")
    assignment = next(node for node in ast.walk(function) if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "request_guidance"
                              for target in node.targets))
    return ast.literal_eval(assignment.value.body), ast.literal_eval(assignment.value.orelse)


def snapshot(*, include_output_controls: bool = False) -> dict:
    manifest_path = REPORT / "corpus/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = []
    for sample in manifest["samples"]:
        source_path = (REPORT / "corpus" / sample["file"]).resolve()
        if not source_path.is_relative_to((REPORT / "corpus").resolve()):
            raise RuntimeError("Corpus path outside report")
        data = source_path.read_bytes()
        if digest(data) != sample["sha256"]:
            raise RuntimeError("Corpus differs from frozen manifest")
        source = data.decode("utf-8")
        cleaned = _summary_input(source)
        samples.append({"id": sample["id"], "sha256": digest(data),
                        "input_chars": len(source), "cleaned_chars": len(cleaned),
                        "sections": len(_summary_chunks(cleaned, CONFIG["llm_summary_chunk_chars"]))})
    prompt = system_prompt()
    captured = {"service_sha256": digest(SERVICE.read_bytes()),
            "system_prompt": prompt, "system_prompt_sha256": digest(prompt),
            "manifest_sha256": digest(manifest_path.read_bytes()),
            "samples": samples, "config": CONFIG, "provider": settings.llm_provider,
            "model": settings.llm_model, "output_language": "zh-CN"}
    if include_output_controls:
        from app.services.llm_service import _summary_options
        captured.update(settings_source_sha256=digest(SETTINGS_SOURCE.read_bytes()),
                        summary_output_controls={"llm_summary_response_format": settings.llm_summary_response_format,
                                                 "llm_summary_thinking_mode": settings.llm_summary_thinking_mode},
                        resolved_summary_options=_summary_options())
    return captured


class BudgetClient:
    def __init__(self, http: httpx.Client, phase: str, frozen: dict):
        self.http, self.phase, self.frozen = http, phase, frozen
        self.sample = ""

    def post(self, url, *, headers, json):
        if digest(SERVICE.read_bytes()) != self.frozen["service_sha256"]:
            raise RuntimeError("Service changed during phase; POST prohibited")
        if digest(json["messages"][0]["content"]) != self.frozen["system_prompt_sha256"]:
            raise RuntimeError("Runtime prompt differs from frozen prompt")
        if "settings_source_sha256" in self.frozen:
            if digest(SETTINGS_SOURCE.read_bytes()) != self.frozen["settings_source_sha256"]:
                raise RuntimeError("Settings source changed during phase; POST prohibited")
            emitted = {key: json[key] for key in ("response_format", "thinking") if key in json}
            if emitted != self.frozen["resolved_summary_options"]:
                raise RuntimeError("Runtime output controls differ from compatible profile")
        ledger_path = RESULTS / "request-ledger.json"
        if not ledger_path.exists():
            exclusive_json(ledger_path, {"ceiling": CEILING, "requests": []})
        ledger = json_module.loads(ledger_path.read_text(encoding="utf-8"))
        if ledger["ceiling"] != CEILING or len(ledger["requests"]) >= CEILING:
            raise RuntimeError("Persisted 24-POST ceiling exhausted")
        ordinal = len(ledger["requests"]) + 1
        source = json["messages"][-1]["content"]
        row = {"ordinal": ordinal, "phase": self.phase, "sample": self.sample,
               "started_at_utc": now(), "status": "attempt_reserved",
               "stage": "merge" if "Section summaries:\n" in source else "section",
               "payload_sha256": digest(json_module.dumps(json, ensure_ascii=False, sort_keys=True)),
               "system_prompt_sha256": self.frozen["system_prompt_sha256"],
               "service_sha256": self.frozen["service_sha256"]}
        if "resolved_summary_options" in self.frozen:
            row["summary_options"] = self.frozen["resolved_summary_options"]
        ledger["requests"].append(row)
        durable_json(ledger_path, ledger)  # reservation persists BEFORE actual POST
        try:
            response = self.http.post(url, headers=headers, json=json)
            row.update(status="response", http_status=response.status_code)
            if response.is_success:
                data = response.json()
                # Store model output only, never headers/URLs/config/errors.
                content = data.get("choices", [{}])[0].get("message", {}).get("content")
                evidence = {"ordinal": ordinal, "phase": self.phase, "sample": self.sample,
                            "stage": row["stage"], "content": content, "usage": data.get("usage"),
                            "finish_reason": data.get("choices", [{}])[0].get("finish_reason")}
                exclusive_json(RESULTS / "responses" / f"{ordinal:02d}.json", evidence)
                row["response_sha256"] = digest((RESULTS / "responses" / f"{ordinal:02d}.json").read_bytes())
                usage = data.get("usage")
                if isinstance(usage, dict):
                    row["token_usage"] = {key: value for key, value in usage.items()
                                          if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                                          and isinstance(value, int)}
                    reasoning = usage.get("completion_tokens_details", {}).get("reasoning_tokens")
                    if isinstance(reasoning, int):
                        row["reasoning_tokens"] = reasoning
            return response
        except Exception as exc:
            row["status"] = type(exc).__name__
            raise
        finally:
            row["ended_at_utc"] = now()
            durable_json(ledger_path, ledger)


json_module = json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["before", "after", "validation-long", "compatible", "bounded", "concise-long"], required=True)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--system-proxy", action="store_true")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    provenance_path = RESULTS / f"{args.phase}-provenance.json"
    current = snapshot(include_output_controls=args.phase in {"compatible", "bounded", "concise-long"})
    if args.phase == "concise-long":
        merge, source = request_guidance(SERVICE.read_text(encoding="utf-8"))
        current.update(merge_guidance_sha256=digest(merge), source_guidance_sha256=digest(source))
    if args.freeze:
        if args.phase != "before":
            baseline = json.loads((RESULTS / "before-provenance.json").read_text(encoding="utf-8"))
            for key in ("manifest_sha256", "samples", "config", "provider", "model", "output_language"):
                if current[key] != baseline[key]:
                    raise RuntimeError("After phase must use baseline corpus, facts, configuration and model")
        if args.phase == "validation-long":
            after = json.loads((RESULTS / "after-provenance.json").read_text(encoding="utf-8"))
            if any(after[key] != value for key, value in current.items()):
                raise RuntimeError("Validation must use the exact frozen after source, prompt and inputs")
            current["selected_sample_ids"] = ["en-long"]
            current["trigger"] = "Root explicitly authorized one opt-in long-only validation after malformed model JSON; no automatic POST retry, no third attempt if validation fails."
        if args.phase == "compatible":
            current["trigger"] = "Root authorized a new compatible output-control profile after source-backed diagnosis of malformed JSON and reasoning-budget exhaustion. This is not another attempt with the original profile. One run only, stop after any failed sample."
        if args.phase == "bounded":
            compatible = json.loads((RESULTS / "compatible-provenance.json").read_text(encoding="utf-8"))
            for key in ("settings_source_sha256", "summary_output_controls", "resolved_summary_options"):
                if current[key] != compatible[key]:
                    raise RuntimeError("Bounded profile must retain compatible output controls and settings")
            current["trigger"] = "Root authorized one final all-sample profile after measured section/final point-count violations: strict 1-7 validation plus per-section/final topic-count instructions. Same output controls, corpus, facts, limits and model. Stop after any sample failure; no automatic retry."
        if args.phase == "concise-long":
            bounded = json.loads((RESULTS / "bounded-provenance.json").read_text(encoding="utf-8"))
            for key in ("settings_source_sha256", "summary_output_controls", "resolved_summary_options", "system_prompt_sha256"):
                if current[key] != bounded[key]:
                    raise RuntimeError("Concise-long must retain bounded settings, controls and system prompt")
            old_merge, old_source = request_guidance((RESULTS / "bounded-service.py").read_text(encoding="utf-8"))
            if current["source_guidance_sha256"] != digest(old_source):
                raise RuntimeError("Concise-long may change merge guidance only")
            current["previous_merge_guidance_sha256"] = digest(old_merge)
            current["selected_sample_ids"] = ["en-long"]
            current["trigger"] = "Root authorized a final long-only merge-organization profile after measured 426-character catch-all point. Only merge guidance changes; no sample-specific facts, truncation or retry. Expected total reaches 24-POST ceiling; no more calls afterwards."
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
        exclusive_json(provenance_path, {"captured_at_utc": now(), "git_head": revision, **current})
        with (RESULTS / f"{args.phase}-service.py").open("xb") as stream:
            stream.write(SERVICE.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        if args.phase in {"compatible", "bounded", "concise-long"}:
            with (RESULTS / f"{args.phase}-config.py").open("xb") as stream:
                stream.write(SETTINGS_SOURCE.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
        print(json.dumps({"phase": args.phase, "frozen": True, "samples": current["samples"]}))
        return
    frozen = json.loads(provenance_path.read_text(encoding="utf-8"))
    if any(frozen.get(key) != value for key, value in current.items()):
        raise RuntimeError("Current source, prompt, corpus or facts differ from phase provenance")
    if args.check_only:
        print(json.dumps({"phase": args.phase, "provenance_match": True}))
        return
    # mkdir is an atomic cross-process lock; never clear a stale lock silently.
    lock = RESULTS / ".http-session-lock"
    lock.mkdir()
    try:
        exclusive_json(RESULTS / f"{args.phase}-started.json", {"started_at_utc": now()})
        proxy = None
        if args.system_proxy:
            command = "$target=[Uri]'" + settings.llm_base_url.replace("'", "''") + "'; $proxy=[System.Net.WebRequest]::DefaultWebProxy.GetProxy($target); if ($proxy.AbsoluteUri -ne $target.AbsoluteUri) { $proxy.AbsoluteUri }"
            proxy = subprocess.check_output(["powershell", "-NoProfile", "-Command", command], text=True).strip() or None
        manifest = json.loads((REPORT / "corpus/manifest.json").read_text(encoding="utf-8"))
        with httpx.Client(timeout=settings.llm_timeout_seconds, proxy=proxy, trust_env=False) as http:
            client = BudgetClient(http, args.phase, frozen)
            written_samples = []
            for sample in manifest["samples"]:
                if sample["id"] not in frozen.get("selected_sample_ids", [entry["id"] for entry in manifest["samples"]]):
                    continue
                client.sample = sample["id"]
                source = (REPORT / "corpus" / sample["file"]).read_text(encoding="utf-8")
                started = time.monotonic()
                row = {"id": sample["id"], "phase": args.phase,
                       "source_sha256": sample["sha256"], "input_chars": len(source),
                       "cleaned_chars": len(_summary_input(source)),
                       "sections": len(_summary_chunks(_summary_input(source), CONFIG["llm_summary_chunk_chars"])),
                       "output_language": "zh-CN", "provider": settings.llm_provider,
                       "model": settings.llm_model, "proxy_used": bool(proxy)}
                try:
                    row["result"] = asdict(summarize_text(source, title=sample["title"], output_language="zh-CN", client=client))
                except LLMServiceError as exc:
                    row["error_type"] = exc.error_type
                except Exception as exc:
                    row["error_type"] = type(exc).__name__
                row["elapsed_seconds"] = round(time.monotonic() - started, 2)
                sample_path = RESULTS / f"{args.phase}-{sample['id']}.json"
                exclusive_json(sample_path, row)
                written_samples.append({"id": sample["id"], "file": sample_path.name,
                                        "sha256": digest(sample_path.read_bytes())})
                print(json.dumps({key: row[key] for key in ("id", "phase", "sections", "elapsed_seconds")}
                                 | {"error": row.get("error_type")}), flush=True)
                if "error_type" in row:
                    break  # do not silently spend more after failure
        ledger = json.loads((RESULTS / "request-ledger.json").read_text(encoding="utf-8"))
        phase_requests = [row for row in ledger["requests"] if row["phase"] == args.phase]
        exclusive_json(RESULTS / f"{args.phase}-index.json", {
            "completed_at_utc": now(), "manifest_and_facts_sha256": frozen["manifest_sha256"],
            "sample_results": written_samples,
            "phase_requests_sha256": digest(json.dumps(phase_requests, ensure_ascii=False, sort_keys=True)),
            "reserved_attempts": len(phase_requests),
            "confirmed_http_responses": sum(row.get("status") == "response" for row in phase_requests),
        })
        print(json.dumps({"reserved_attempts": len(ledger["requests"]),
                          "confirmed_http_responses": sum(row.get("status") == "response" for row in ledger["requests"]),
                          "ceiling": CEILING}))
    finally:
        lock.rmdir()


if __name__ == "__main__":
    main()
