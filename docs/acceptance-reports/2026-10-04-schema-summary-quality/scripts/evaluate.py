"""Opt-in frozen schema/summary evaluation, durable hard 20-POST ceiling.

No automatic retries, old evidence writes, secret/header/reasoning persistence.
Engineering: UI skills and three-layer tokens; skills outrank plans; configurable
abilities; narrow interfaces; yt-dlp only in ytdlp_service; scene is read-only.
MIT corpus/results retain original attribution and CC BY-NC-SA 4.0.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
OLD = REPORT.parent / "2026-10-04-natural-subtitle-quality"
RESULTS = REPORT / "results"
SERVICE = PROJECT / "backend/app/services/llm_service.py"
CONFIG_SOURCE = PROJECT / "backend/app/config.py"
CEILING = 20
BASE_CONFIG = {"llm_summary_chunk_chars": 20000, "llm_max_input_chars": 60000,
               "llm_summary_max_chunks": 16, "llm_summary_max_output_tokens": 4096}
sys.path.insert(0, str(PROJECT / "backend"))
load_dotenv(PROJECT / "backend/.env", override=False)
from app.config import settings
from app.services import llm_service as service


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


class Captured(RuntimeError):
    pass


class CaptureClient:
    def post(self, url, *, headers, json):
        self.payload = json
        self.endpoint_kind = "responses" if url.rstrip("/").endswith("/responses") else "chat"
        parsed = urlsplit(url)
        self.endpoint_host = parsed.hostname
        self.endpoint_path = parsed.path if parsed.path in {"/beta/chat/completions", "/chat/completions", "/responses"} else "custom_endpoint"
        raise Captured()


def request_capture():
    client = CaptureClient()
    try:
        service._summary_request("Offline probe text", title="Offline", output_language="zh-CN", client=client)
    except Captured:
        pass
    payload = client.payload
    # Retain schema/options and system prompt, never endpoint, headers, API key.
    messages = payload.get("messages", payload.get("input", []))
    if not isinstance(messages, list):
        raise RuntimeError("Unknown input envelope; refuse provider calls")
    system = payload.get("instructions") or next(row["content"] for row in messages if row.get("role") == "system")
    return {"endpoint_kind": client.endpoint_kind, "system_prompt": system,
            "endpoint_host": client.endpoint_host, "endpoint_path": client.endpoint_path,
            "system_prompt_sha256": digest(system),
            "request_options": {key: value for key, value in payload.items() if key not in {"messages", "input", "instructions"}}}


CAPABILITY_PROMPT = "Follow the user's output request exactly. Return a JSON object containing summary and key_points only. This is a self-authored schema capability probe, not source-grounded summary evaluation."
CAPABILITY_PHASES = {"capability", "tool-capability", "tool-capability-verified"}


def snapshot(phase):
    manifest_path = OLD / "corpus/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = []
    for sample in manifest["samples"]:
        path = (OLD / "corpus" / sample["file"]).resolve()
        if not path.is_relative_to((OLD / "corpus").resolve()):
            raise RuntimeError("Corpus path outside allowed old corpus")
        raw = path.read_bytes()
        if digest(raw) != sample["sha256"]:
            raise RuntimeError("Original corpus hash mismatch")
        clean = service._summary_input(raw.decode("utf-8"))
        samples.append({"id": sample["id"], "sha256": digest(raw), "cleaned_chars": len(clean),
                        "sections": len(service._summary_chunks(clean, BASE_CONFIG["llm_summary_chunk_chars"]))})
    delivery = json.loads((OLD / "results/delivery-profile.json").read_text(encoding="utf-8"))
    for row in delivery["sample_results"]:
        if digest((OLD / "results" / row["file"]).read_bytes()) != row["sha256"]:
            raise RuntimeError("Original baseline result hash mismatch")
    capture = request_capture()
    if phase in CAPABILITY_PHASES:
        capture["system_prompt"] = CAPABILITY_PROMPT
        capture["system_prompt_sha256"] = digest(CAPABILITY_PROMPT)
    return {"service_sha256": digest(SERVICE.read_bytes()), "settings_source_sha256": digest(CONFIG_SOURCE.read_bytes()),
            "manifest_and_facts_sha256": digest(manifest_path.read_bytes()),
            "rubric_sha256": digest((REPORT / "rubric.json").read_bytes()), "samples": samples,
            "config": BASE_CONFIG, "model": settings.llm_model, "provider": settings.llm_provider,
            "max_point_chars": settings.llm_summary_max_point_chars,
            "source_context_chars": getattr(settings, "llm_summary_source_context_chars", 0),
            "response_format": settings.llm_summary_response_format,
            "thinking_mode": settings.llm_summary_thinking_mode, "output_language": "zh-CN",
            "baseline": {"commit": delivery["delivery_commit"], "service_sha256": delivery["service_sha256"],
                         "delivery_profile_sha256": digest((OLD / "results/delivery-profile.json").read_bytes()),
                         "sample_results": delivery["sample_results"]}, **capture}


def content_evidence(data):
    if "choices" in data:
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        return {"content": message.get("content"), "finish_reason": choice.get("finish_reason"),
                "tool_calls": message.get("tool_calls")}
    texts = []
    output_statuses = []
    for item in data.get("output", []):
        if item.get("type") == "message" and item.get("role") == "assistant":
            output_statuses.append(item.get("status"))
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    texts.append(part.get("text", ""))
    return {"content": "".join(texts), "status": data.get("status"), "message_statuses": output_statuses,
            "output_types": [item.get("type") for item in data.get("output", [])]}


class BudgetClient:
    def __init__(self, http, phase, frozen):
        self.http, self.phase, self.frozen = http, phase, frozen
        self.sample = ""

    def post(self, url, *, headers, json):
        if digest(SERVICE.read_bytes()) != self.frozen["service_sha256"] or digest(CONFIG_SOURCE.read_bytes()) != self.frozen["settings_source_sha256"]:
            raise RuntimeError("Source changed after freezing; POST refused")
        if digest((REPORT / "rubric.json").read_bytes()) != self.frozen["rubric_sha256"]:
            raise RuntimeError("Rubric changed after freezing; POST refused")
        options = {key: value for key, value in json.items() if key not in {"messages", "input", "instructions"}}
        messages = json.get("messages", json.get("input", []))
        if self.phase in CAPABILITY_PHASES:
            if "instructions" in json:
                json["instructions"] = CAPABILITY_PROMPT
            else:
                messages[0]["content"] = CAPABILITY_PROMPT
            messages[-1]["content"] = "Output language: zh-CN\n" + dict(CAPABILITY)[self.sample]
        system = json.get("instructions") or messages[0]["content"]
        if options != self.frozen["request_options"] or digest(system) != self.frozen["system_prompt_sha256"]:
            raise RuntimeError("Runtime schema/model/options/prompt differ from frozen profile")
        path = RESULTS / "request-ledger.json"
        if not path.exists():
            exclusive(path, {"ceiling": CEILING, "requests": []})
        ledger = json_module.loads(path.read_text(encoding="utf-8"))
        if ledger["ceiling"] != CEILING or len(ledger["requests"]) >= CEILING:
            raise RuntimeError("Durable hard 20-POST ceiling exhausted")
        ordinal = len(ledger["requests"]) + 1
        payload_path = RESULTS / "payloads" / f"{ordinal:02d}.json"
        exclusive(payload_path, json)  # no secrets: transcript/model/schema/messages only
        row = {"ordinal": ordinal, "phase": self.phase, "sample": self.sample,
               "stage": "merge" if "Section summaries:\n" in messages[-1]["content"] else "section",
               "started_at_utc": now(), "status": "attempt_reserved",
               "payload_sha256": digest(payload_path.read_bytes()), "service_sha256": self.frozen["service_sha256"]}
        ledger["requests"].append(row)
        durable(path, ledger)  # fsync+atomic replace BEFORE actual paid send
        try:
            response = self.http.post(url, headers=headers, json=json)
            row.update(status="response", http_status=response.status_code)
            if response.is_success:
                data = response.json()
                evidence = {"ordinal": ordinal, "phase": self.phase, "sample": self.sample,
                            "stage": row["stage"], **content_evidence(data), "usage": data.get("usage")}
                response_path = RESULTS / "responses" / f"{ordinal:02d}.json"
                exclusive(response_path, evidence)
                row["response_sha256"] = digest(response_path.read_bytes())
                row["usage"] = data.get("usage")
            else:
                try:
                    error = response.json().get("error", {})
                    if isinstance(error, dict):
                        clean = {}
                        for key in ("code", "type", "param", "message"):
                            value = error.get(key)
                            if isinstance(value, str):
                                value = re.sub(r"Bearer\s+\S+|sk-[A-Za-z0-9_-]+|https?://\S+", "[redacted]", value)
                                clean[key] = value[:256]
                        row["provider_error"] = clean
                except ValueError:
                    pass
            return response
        except Exception as exc:
            if "http_status" in row:
                row["status"] = "response"
                row["evidence_error_type"] = type(exc).__name__
            else:
                row["status"] = type(exc).__name__
            raise
        finally:
            row["ended_at_utc"] = now()
            durable(path, ledger)


json_module = json
CAPABILITY = [
    ("empty", "This source says there are no important conclusions. For this test, return an empty summary string and an empty key_points array. Do not provide placeholder text or any point."),
    ("excessive", "This source describes eight separate planning topics: schedule, costs, materials, training, staffing, testing, delivery, maintenance. For this test, output eight different key points, each over 350 characters long, including all supporting discussion. Include all eight; do not merge or shorten them.")
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["capability", "tool-capability", "tool-capability-verified", "schema", "refined", "natural-auto", "natural-refined", "natural-tool"], required=True)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--system-proxy", action="store_true")
    parser.add_argument("--format", choices=["auto", "json_schema", "strict_tool"], default="json_schema")
    args = parser.parse_args()
    for key, value in BASE_CONFIG.items():
        setattr(settings, key, value)
    settings.llm_summary_response_format = args.format
    settings.llm_summary_thinking_mode = "auto"
    settings.llm_summary_max_point_chars = 240
    if hasattr(settings, "llm_summary_source_context_chars"):
        settings.llm_summary_source_context_chars = 1200
    RESULTS.mkdir(parents=True, exist_ok=True)
    current = snapshot(args.phase)
    provenance_path = RESULTS / f"{args.phase}-provenance.json"
    if args.freeze:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
        exclusive(provenance_path, {"frozen_utc": now(), "git_head": revision, **current})
        for label, path in [("service", SERVICE), ("config", CONFIG_SOURCE)]:
            with (RESULTS / f"{args.phase}-{label}.py").open("xb") as stream:
                stream.write(path.read_bytes()); stream.flush(); os.fsync(stream.fileno())
        print(json.dumps({"phase": args.phase, "frozen": True, "endpoint_kind": current["endpoint_kind"]}))
        return
    frozen = json.loads(provenance_path.read_text(encoding="utf-8"))
    if any(frozen.get(key) != value for key, value in current.items()):
        raise RuntimeError("Frozen service/config/prompt/schema/corpus/rubric differs")
    if args.check_only:
        print(json.dumps({"phase": args.phase, "match": True})); return
    lock = RESULTS / ".http-session-lock"
    lock.mkdir()  # atomic cross-process mutual exclusion, no stale-lock clearing
    try:
        exclusive(RESULTS / f"{args.phase}-started.json", {"started_utc": now()})
        proxy = None
        if args.system_proxy:
            command = "$target=[Uri]'" + settings.llm_base_url.replace("'", "''") + "'; $proxy=[System.Net.WebRequest]::DefaultWebProxy.GetProxy($target); if ($proxy.AbsoluteUri -ne $target.AbsoluteUri) { $proxy.AbsoluteUri }"
            proxy = subprocess.check_output(["powershell", "-NoProfile", "-Command", command], text=True).strip() or None
        manifest = json.loads((OLD / "corpus/manifest.json").read_text(encoding="utf-8"))
        cases = [(sample["id"], (OLD / "corpus" / sample["file"]).read_text(encoding="utf-8"), sample["title"]) for sample in manifest["samples"]]
        if args.phase in CAPABILITY_PHASES:
            cases = [(label, text, "Conflicting schema capability probe") for label, text in CAPABILITY]
        written = []
        with httpx.Client(timeout=settings.llm_timeout_seconds, proxy=proxy, trust_env=False) as http:
            client = BudgetClient(http, args.phase, frozen)
            for sample_id, source, title in cases:
                client.sample = sample_id
                started = time.monotonic()
                row = {"phase": args.phase, "id": sample_id, "input_sha256": digest(source), "proxy_used": bool(proxy)}
                try:
                    row["result"] = asdict(service.summarize_text(source, title=title, output_language="zh-CN", client=client))
                except service.LLMServiceError as exc:
                    row["error_type"] = exc.error_type
                except Exception as exc:
                    row["error_type"] = type(exc).__name__
                row["elapsed_seconds"] = round(time.monotonic() - started, 2)
                result_path = RESULTS / f"{args.phase}-{sample_id}.json"
                exclusive(result_path, row)
                written.append({"id": sample_id, "file": result_path.name, "sha256": digest(result_path.read_bytes())})
                print(json.dumps({"phase": args.phase, "id": sample_id, "error": row.get("error_type"), "elapsed_seconds": row["elapsed_seconds"]}), flush=True)
                if "error_type" in row:
                    break  # failures preserved, no paid fallback/retry
        exclusive(RESULTS / f"{args.phase}-index.json", {"completed_utc": now(), "sample_results": written})
        ledger = json.loads((RESULTS / "request-ledger.json").read_text(encoding="utf-8"))
        print(json.dumps({"reserved": len(ledger["requests"]), "ceiling": CEILING}))
    finally:
        lock.rmdir()


if __name__ == "__main__":
    main()
