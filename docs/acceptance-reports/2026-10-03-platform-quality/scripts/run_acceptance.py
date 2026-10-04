"""Opt-in live API acceptance. Never outputs tokens, keys, or full transcripts.

Engineering: UI skills/tokens, config-driven abilities, narrow service boundaries.
Run against an isolated local backend, not a production user database.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import time

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--transcript-dir", type=Path, required=True)
    parser.add_argument("--summaries", nargs="*", default=[])
    parser.add_argument("--sample-ids", nargs="*")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    samples = json.loads((Path(__file__).parents[1] / "samples.json").read_text(encoding="utf-8"))["samples"]
    known = {sample["id"] for sample in samples if sample.get("license_url")}
    if set(args.summaries) - known:
        parser.error("summaries must refer to licensed sample IDs")
    if args.sample_ids is not None:
        if set(args.sample_ids) - {sample["id"] for sample in samples}:
            parser.error("unknown sample ID")
        samples = [sample for sample in samples if sample["id"] in args.sample_ids]
    if not samples or not 1 <= args.workers <= 3:
        parser.error("select at least one sample and 1-3 workers")
    if set(args.summaries) - {sample["id"] for sample in samples}:
        parser.error("summary IDs must be included in selected samples")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.transcript_dir.mkdir(parents=True, exist_ok=True)
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "samples": [], "summaries": []}
    with httpx.Client(base_url=args.base_url, timeout=120, trust_env=False) as http:
        result["unauthenticated"] = {
            path: http.post(path, json={"url": samples[0]["url"]}).status_code
            for path in ("/api/parse", "/api/download", "/api/subtitle", "/api/summary", "/api/subtitle/translate")
        }
        credentials = {"email": f"acceptance-{secrets.token_hex(4)}@example.test", "password": secrets.token_urlsafe(18)}
        response = http.post("/api/auth/register", json=credentials)
        response.raise_for_status()
        response = http.post("/api/auth/login", json=credentials)
        response.raise_for_status()
        http.headers["Authorization"] = f"Bearer {response.json()['token']}"
        result["quota_before"] = http.get("/api/auth/me").json()["quota"]

        def check(sample):
            started = time.monotonic()
            row = {"id": sample["id"], "platform": sample["platform"], "url": sample["url"], "requested_language": sample.get("language"), "expected": sample["expected"]}
            try:
                payload = {"url": sample["url"], "language": sample.get("language")}
                response = http.post("/api/subtitle", json=payload)
                row["http_status"] = response.status_code
                body = response.json()
                if response.is_success:
                    text = body.pop("text")
                    row.update(body)
                    row["characters"] = len(text)
                    row["text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
                    row["content_pass"] = bool(text.strip())
                    if sample.get("license_url"):
                        (args.transcript_dir / f"{sample['id']}.txt").write_text(text, encoding="utf-8")
                    row["expectation_met"] = sample["expected"] in {"content", "observe"} and row["content_pass"]
                else:
                    row["detail"] = body.get("detail", body)
                    row["content_pass"] = False
                    row["expectation_met"] = isinstance(row["detail"], dict) and row["detail"].get("error_type") == sample["expected"]
            except (httpx.HTTPError, ValueError) as error:
                row.update(content_pass=False, expectation_met=False, error_type=type(error).__name__, error=str(error)[:400])
            row["elapsed_seconds"] = round(time.monotonic() - started, 2)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            return row

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            result["samples"] = list(pool.map(check, samples))
        for sample_id in args.summaries:
            sample = next(item for item in samples if item["id"] == sample_id)
            row = {"id": sample_id}
            started = time.monotonic()
            try:
                response = http.post("/api/summary", json={"url": sample["url"], "subtitle_language": sample.get("language"), "output_language": "zh-CN"})
                row.update(http_status=response.status_code, result=response.json())
            except (httpx.HTTPError, ValueError) as error:
                row.update(error_type=type(error).__name__, error=str(error)[:400])
            row["elapsed_seconds"] = round(time.monotonic() - started, 2)
            result["summaries"].append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        result["quota_after_ai"] = http.get("/api/auth/me").json()["quota"]
        result["quota_unchanged_by_ai"] = result["quota_after_ai"] == result["quota_before"]
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if any(code != 401 for code in result["unauthenticated"].values()) or not result["quota_unchanged_by_ai"]:
        raise SystemExit(1)
    if any(not row["expectation_met"] for row in result["samples"] if row["expected"] != "observe") or any(row.get("http_status") != 200 for row in result["summaries"]):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
