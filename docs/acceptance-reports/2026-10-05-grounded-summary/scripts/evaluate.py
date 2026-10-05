"""Opt-in grounded pipeline evaluation: exclusive freeze, 24 durable POST limit.

No HTTP retries, provider capability probes, secret/header/reasoning persistence,
old artifact writes or phase restarts. Engineering: applicable skills first;
UI ui-ux-pro-max/design-system and three-layer tokens; narrow interfaces,
yt-dlp only ytdlp_service; LLM only llm_service; visual scene read-only.
MIT-derived source/outputs/review retain original authors and CC BY-NC-SA4.0.
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
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
OLD = REPORT.parent / "2026-10-04-natural-subtitle-quality"
BASE = REPORT.parent / "2026-10-04-schema-summary-quality"
RESULTS = REPORT / "results"
MODULES = {"service": PROJECT / "backend/app/services/llm_service.py",
           "config": PROJECT / "backend/app/config.py",
           "facts": PROJECT / "backend/app/services/summary_facts.py"}
CEILING = 24
CONFIG = {"llm_summary_strategy": "facts", "llm_summary_response_format": "auto",
          "llm_summary_thinking_mode": "auto", "llm_summary_chunk_chars": 20000,
          "llm_max_input_chars": 60000, "llm_summary_max_chunks": 16,
          "llm_summary_max_output_tokens": 4096, "llm_summary_max_point_chars": 240,
          "llm_summary_source_context_chars": 1200,
          "llm_summary_facts_max_source_chars": 40000,
          "llm_summary_facts_max_per_chunk": 12,
          "llm_summary_facts_max_quote_chars": 400}
sys.path.insert(0, str(PROJECT / "backend"))
load_dotenv(PROJECT / "backend/.env", override=False)
from app.config import settings
from app.services import llm_service as service
from app.services.summary_facts import FactLimits


def digest(value):
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def exclusive(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded(value)); stream.flush(); os.fsync(stream.fileno())


def durable(path, value):
    temporary = path.with_name(path.name + ".writing")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded(value)); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def snapshot():
    manifest_path = OLD / "corpus/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rubric = json.loads((REPORT / "rubric.json").read_text(encoding="utf-8"))
    samples = []
    for sample in manifest["samples"]:
        path = (OLD / "corpus" / sample["file"]).resolve()
        if not path.is_relative_to((OLD / "corpus").resolve()) or digest(path.read_bytes()) != sample["sha256"]:
            raise RuntimeError("Original corpus path/hash mismatch")
        clean = service._summary_input(path.read_text(encoding="utf-8"))
        chunks = service._summary_chunks(clean, CONFIG["llm_summary_chunk_chars"])
        samples.append({"id": sample["id"], "sha256": sample["sha256"],
                        "cleaned_sha256": digest(clean), "cleaned_chars": len(clean),
                        "sections": len(chunks), "expected_posts": len(chunks) + 2})
    for row in rubric["baseline"]["sample_results"]:
        if digest((BASE / "results" / row["file"]).read_bytes()) != row["sha256"]:
            raise RuntimeError("Old baseline bytes changed")
    # All string literals are frozen alongside exact source bytes. Actual stage
    # system messages and payload hashes are also captured at POST time.
    source = MODULES["service"].read_text(encoding="utf-8")
    literals = [node.value for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    limits = FactLimits(max_facts_per_chunk=CONFIG["llm_summary_facts_max_per_chunk"],
                        max_quote_chars=CONFIG["llm_summary_facts_max_quote_chars"],
                        max_point_chars=CONFIG["llm_summary_max_point_chars"])
    prompts = {stage: service._grounded_system(stage, limits) for stage in ("extract", "compose", "audit")}
    return {"module_sha256": {key: digest(path.read_bytes()) for key, path in MODULES.items()},
            "runner_sha256": digest(Path(__file__).read_bytes()), "resolved_strategy": "facts",
            "stage_prompts": prompts, "stage_prompt_sha256": {key: digest(value) for key, value in prompts.items()},
            "fact_limits": asdict(limits),
            "service_string_literals_sha256": digest(encoded(literals)),
            "service_string_literals": literals, "config": CONFIG,
            "manifest_sha256": digest(manifest_path.read_bytes()),
            "rubric_sha256": digest((REPORT / "rubric.json").read_bytes()),
            "baseline": rubric["baseline"], "samples": samples,
            "provider": settings.llm_provider, "model": settings.llm_model,
            "expected_posts": sum(row["expected_posts"] for row in samples),
            "output_language": "zh-CN", "options": service._summary_options()}


def response_evidence(data):
    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {})
    return {"content": message.get("content"), "finish_reason": choice.get("finish_reason"),
            "usage": data.get("usage")}


class BudgetClient:
    def __init__(self, http, phase, frozen):
        self.http, self.phase, self.frozen = http, phase, frozen
        self.sample = ""
        self.sample_post = 0

    def post(self, url, *, headers, json):
        for key, path in MODULES.items():
            if digest(path.read_bytes()) != self.frozen["module_sha256"][key]:
                raise RuntimeError("Product bytes changed after freeze; POST refused")
        if digest((REPORT / "rubric.json").read_bytes()) != self.frozen["rubric_sha256"]:
            raise RuntimeError("Rubric changed; POST refused")
        if any(getattr(settings, key) != value for key, value in CONFIG.items()):
            raise RuntimeError("Runtime settings changed; POST refused")
        plan = next(row for row in self.frozen["samples"] if row["id"] == self.sample)
        if self.sample_post >= plan["expected_posts"]:
            raise RuntimeError("Unplanned stage/hidden retry refused")
        options = {key: value for key, value in json.items() if key != "messages"}
        expected_options = {"model": self.frozen["model"], "temperature": 0.2,
                            "max_tokens": CONFIG["llm_summary_max_output_tokens"], **self.frozen["options"]}
        if options != expected_options:
            raise RuntimeError("Transport/schema/options differ from freeze")
        ledger_path = RESULTS / "request-ledger.json"
        if not ledger_path.exists():
            exclusive(ledger_path, {"ceiling": CEILING, "requests": []})
        ledger = json_module.loads(ledger_path.read_text(encoding="utf-8"))
        if ledger["ceiling"] != CEILING or len(ledger["requests"]) >= CEILING:
            raise RuntimeError("Hard durable 24-POST ceiling exhausted")
        ordinal = len(ledger["requests"]) + 1
        stage = "extract" if self.sample_post < plan["sections"] else (
            "compose" if self.sample_post == plan["sections"] else "audit")
        if json["messages"][0]["content"] != self.frozen["stage_prompts"][stage]:
            raise RuntimeError("Actual stage prompt differs from freeze")
        payload_path = RESULTS / "payloads" / f"{ordinal:02d}.json"
        exclusive(payload_path, json)
        system = json["messages"][0]["content"]
        endpoint = urlsplit(url)
        row = {"ordinal": ordinal, "phase": self.phase, "sample": self.sample,
               "stage": stage, "sample_post": self.sample_post + 1,
               "started_utc": now(), "status": "reserved", "endpoint_host": endpoint.hostname,
               "endpoint_path": endpoint.path, "payload_sha256": digest(payload_path.read_bytes()),
               "system_prompt_sha256": digest(system), "module_sha256": self.frozen["module_sha256"]}
        ledger["requests"].append(row)
        durable(ledger_path, ledger)  # fsync+replace BEFORE any billable send
        self.sample_post += 1
        try:
            response = self.http.post(url, headers=headers, json=json)
            row.update(status="response", http_status=response.status_code)
            if response.is_success:
                evidence = {"ordinal": ordinal, "phase": self.phase, "sample": self.sample,
                            "stage": stage, **response_evidence(response.json())}
                path = RESULTS / "responses" / f"{ordinal:02d}.json"
                exclusive(path, evidence)
                row.update(response_sha256=digest(path.read_bytes()), usage=evidence["usage"])
            return response
        except Exception as exc:
            row["status"] = type(exc).__name__ if "http_status" not in row else "evidence_error"
            raise
        finally:
            row["ended_utc"] = now(); durable(ledger_path, ledger)


json_module = json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["initial", "initial-contract", "refined"], required=True)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--system-proxy", action="store_true")
    args = parser.parse_args()
    if args.phase == "refined":
        CONFIG["llm_summary_facts_max_quote_chars"] = 600
    for key, value in CONFIG.items():
        if not hasattr(settings, key):
            raise RuntimeError("Grounded settings unavailable; refuse")
        setattr(settings, key, value)
    current = snapshot()
    path = RESULTS / f"{args.phase}-provenance.json"
    if args.freeze:
        exclusive(path, {"frozen_utc": now(), "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(), **current})
        for key, module in MODULES.items():
            with (RESULTS / f"{args.phase}-{key}.py").open("xb") as stream:
                stream.write(module.read_bytes()); stream.flush(); os.fsync(stream.fileno())
        print(json.dumps({"phase": args.phase, "frozen": True, "expected_posts": current["expected_posts"],
                          "module_sha256": current["module_sha256"], "rubric_sha256": current["rubric_sha256"]})); return
    frozen = json.loads(path.read_text(encoding="utf-8"))
    if any(frozen.get(key) != value for key, value in current.items()):
        raise RuntimeError("Source/config/prompt/corpus/rubric does not match frozen phase")
    if args.check_only:
        print(json.dumps({"phase": args.phase, "match": True})); return
    RESULTS.mkdir(parents=True, exist_ok=True)
    lock = RESULTS / ".http-session-lock"
    lock.mkdir()  # global sole caller lock, stale locks not automatically removed
    try:
        exclusive(RESULTS / f"{args.phase}-started.json", {"started_utc": now()})
        proxy = None
        if args.system_proxy:
            command = "$t=[Uri]'" + settings.llm_base_url.replace("'", "''") + "'; $p=[System.Net.WebRequest]::DefaultWebProxy.GetProxy($t); if($p.AbsoluteUri -ne $t.AbsoluteUri){$p.AbsoluteUri}"
            proxy = subprocess.check_output(["powershell", "-NoProfile", "-Command", command], text=True).strip() or None
        manifest = json.loads((OLD / "corpus/manifest.json").read_text(encoding="utf-8"))
        written = []
        with httpx.Client(timeout=settings.llm_timeout_seconds, proxy=proxy, trust_env=False) as http:
            client = BudgetClient(http, args.phase, frozen)
            for sample in manifest["samples"]:
                client.sample, client.sample_post = sample["id"], 0
                source = (OLD / "corpus" / sample["file"]).read_text(encoding="utf-8")
                row = {"phase": args.phase, "id": sample["id"], "source_sha256": digest(source),
                       "proxy_used": bool(proxy)}
                trace = []
                def collect(event):
                    # JSON serialization here catches unsupported hidden objects.
                    trace.append(json.loads(json.dumps(event, ensure_ascii=False)))
                started = time.monotonic()
                try:
                    row["result"] = asdict(service.summarize_text(source, title=sample["title"],
                        output_language="zh-CN", client=client, diagnostic=collect))
                except service.LLMServiceError as exc:
                    row["error_type"] = exc.error_type
                except Exception as exc:
                    row["error_type"] = type(exc).__name__
                row["elapsed_seconds"] = round(time.monotonic() - started, 2)
                trace_path = RESULTS / f"{args.phase}-{sample['id']}-trace.json"
                exclusive(trace_path, {"phase": args.phase, "id": sample["id"], "events": trace})
                row["trace_sha256"] = digest(trace_path.read_bytes())
                result_path = RESULTS / f"{args.phase}-{sample['id']}.json"
                exclusive(result_path, row)
                written.append({"id": sample["id"], "file": result_path.name,
                                "sha256": digest(result_path.read_bytes()), "posts": client.sample_post})
                print(json.dumps({"phase": args.phase, "id": sample["id"],
                                  "error": row.get("error_type"), "posts": client.sample_post}), flush=True)
                if "error_type" in row:
                    break  # preserve failure and stop phase; no paid retries
        exclusive(RESULTS / f"{args.phase}-index.json", {"ended_utc": now(), "sample_results": written})
    finally:
        lock.rmdir()


if __name__ == "__main__":
    main()
