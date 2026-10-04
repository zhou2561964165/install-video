"""Opt-in real-model evaluation with a persisted, shared 12-POST ceiling.

Never logs credentials, request headers, configuration or unsanitized errors.
Engineering: skills outrank plans; UI skills/tokens; configurable abilities;
narrow service boundaries and yt-dlp only through ytdlp_service.py.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import httpx
from dotenv import load_dotenv
from prompt_provenance import sha256, summary_system_prompt


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parents[2]
sys.path.insert(0, str(PROJECT / "backend"))
load_dotenv(PROJECT / "backend" / ".env", override=False)
from app.config import settings
from app.services.llm_service import LLMServiceError, _summary_chunks, _summary_input, summarize_text


class BudgetClient:
    def __init__(self, http, phase, ledger, expected_prompt_hash):
        self.http = http
        self.phase = phase
        self.ledger_path = ledger
        self.sample = ""
        self.expected_prompt_hash = expected_prompt_hash

    def post(self, url, *, headers, json):
        if sha256(json['messages'][0]['content']) != self.expected_prompt_hash:
            raise RuntimeError('Summary prompt differs from phase provenance; POST prohibited')
        ledger = json_module.loads(self.ledger_path.read_text(encoding="utf-8")) if self.ledger_path.exists() else {"ceiling": 12, "requests": []}
        if ledger["ceiling"] != 12 or len(ledger["requests"]) >= 12:
            raise RuntimeError("Persisted 12-request ceiling exhausted")
        row = {"ordinal": len(ledger["requests"]) + 1, "phase": self.phase, "sample": self.sample, "started_at_utc": datetime.now(timezone.utc).isoformat(), "source_chars_in_user_message": len(json["messages"][-1]["content"]), "status": "attempt_reserved"}
        ledger["requests"].append(row)
        self.ledger_path.write_text(json_module.dumps(ledger, indent=2), encoding="utf-8")
        # Each reserved POST is attempted exactly once; no retry transport.
        try:
            response = self.http.post(url, headers=headers, json=json)
            row["status"] = "response"
            row["http_status"] = response.status_code
            if response.is_success:
                usage = response.json().get("usage")
                if isinstance(usage, dict):
                    row["token_usage"] = {k: v for k, v in usage.items() if k in {"prompt_tokens", "completion_tokens", "total_tokens"} and isinstance(v, int)}
            return response
        except httpx.HTTPError as exc:
            row["status"] = type(exc).__name__
            raise
        finally:
            row["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
            self.ledger_path.write_text(json_module.dumps(ledger, indent=2), encoding="utf-8")


json_module = json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["before", "after"], required=True)
    parser.add_argument("--system-proxy", action="store_true")
    parser.add_argument("--check-provenance-only", action="store_true", help="Verify phase/source prompt hash and exit without HTTP or evidence changes")
    parser.add_argument("--samples", nargs="+", choices=["short", "medium", "long"], default=["short", "medium", "long"])
    args = parser.parse_args()
    provenance = json.loads((ROOT / 'results' / 'provenance.json').read_text(encoding='utf-8'))
    expected_prompt_hash = provenance['phases'][args.phase]['system_prompt_sha256_utf8']
    actual_prompt_hash = sha256(summary_system_prompt((PROJECT / 'backend/app/services/llm_service.py').read_text(encoding='utf-8')))
    if actual_prompt_hash != expected_prompt_hash:
        parser.error('Current summary prompt does not match selected phase provenance; POST prohibited')
    if args.check_provenance_only:
        print(json.dumps({'phase': args.phase, 'system_prompt_sha256': actual_prompt_hash, 'match': True}))
        return
    results_dir = ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    destination = results_dir / f"{args.phase}.json"
    if destination.exists():
        parser.error("phase evidence exists; never overwrite or repeat billable samples")
    proxy = None
    if args.system_proxy:
        command = "$target=[Uri]'" + settings.llm_base_url.replace("'", "''") + "'; $proxy=[System.Net.WebRequest]::DefaultWebProxy.GetProxy($target); if ($proxy.AbsoluteUri -ne $target.AbsoluteUri) { $proxy.AbsoluteUri }"
        proxy = subprocess.check_output(["powershell", "-NoProfile", "-Command", command], text=True).strip() or None
    manifest = json.loads((ROOT / "corpus" / "manifest.json").read_text(encoding="utf-8"))
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "phase": args.phase, "provider": settings.llm_provider, "model": settings.llm_model, "proxy_used": bool(proxy), "chunk_chars": settings.llm_summary_chunk_chars, "max_input_chars": settings.llm_max_input_chars, "samples": []}
    with httpx.Client(timeout=settings.llm_timeout_seconds, proxy=proxy, trust_env=False, transport=None) as http:
        client = BudgetClient(http, args.phase, results_dir / "request-ledger.json", expected_prompt_hash)
        for sample in manifest["samples"]:
            if sample["id"] not in args.samples:
                continue
            source = (ROOT / "corpus" / sample["file"]).read_text(encoding="utf-8")
            if hashlib.sha256(source.encode()).hexdigest() != sample["sha256"]:
                raise RuntimeError("Corpus hash mismatch")
            client.sample = sample["id"]
            started = time.monotonic()
            row = {"id": sample["id"], "source_sha256": sample["sha256"], "input_chars": len(source), "cleaned_chars": len(_summary_input(source)), "sections": len(_summary_chunks(_summary_input(source), min(settings.llm_summary_chunk_chars, settings.llm_max_input_chars)))}
            try:
                row["result"] = asdict(summarize_text(source, title=sample["title"], output_language="zh-CN", client=client))
            except LLMServiceError as exc:
                row["error_type"] = exc.error_type
            except Exception as exc:
                row["error_type"] = type(exc).__name__
            row["elapsed_seconds"] = round(time.monotonic() - started, 2)
            result["samples"].append(row)
            destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"phase": args.phase, "sample": sample["id"], "sections": row["sections"], "seconds": row["elapsed_seconds"], "error": row.get("error_type")}), flush=True)


if __name__ == "__main__":
    main()
