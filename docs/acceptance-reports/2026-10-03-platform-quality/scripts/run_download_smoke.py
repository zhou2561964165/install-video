"""Exercise real registration, parsing and server download with an isolated API.

Engineering: skill-first UI, three-layer tokens, configurable abilities, narrow
service interfaces; this acceptance script never imports download internals.
"""
import argparse
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
    parser.add_argument("--url", default="https://download.samplelib.com/mp4/sample-5s.mp4")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download-dir", type=Path, required=True)
    args = parser.parse_args()
    record = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "url": args.url, "pass": False}
    try:
        with httpx.Client(base_url=args.base_url, timeout=120, trust_env=False) as http:
            credentials = {"email": f"download-{secrets.token_hex(4)}@example.test", "password": secrets.token_urlsafe(18)}
            response = http.post("/api/auth/register", json=credentials)
            response.raise_for_status()
            response = http.post("/api/auth/login", json=credentials)
            response.raise_for_status()
            http.headers["Authorization"] = f"Bearer {response.json()['token']}"
            record["quota_before"] = http.get("/api/auth/me").json()["quota"]
            response = http.post("/api/parse", json={"url": args.url})
            record["parse_status"] = response.status_code
            response.raise_for_status()
            parsed = response.json()
            record["parsed"] = parsed
            response = http.post("/api/download", json={"url": args.url, "format_id": parsed["formats"][0]["format_id"], "force_server": True})
            record["download_status"] = response.status_code
            response.raise_for_status()
            download = response.json()
            if download.get("mode") != "server" or not download.get("job_id"):
                raise RuntimeError("force_server request did not return a server job")
            job_id = download["job_id"]
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                response = http.get(f"/api/job/{job_id}")
                response.raise_for_status()
                job = response.json()
                if job["status"] in {"done", "error"}:
                    break
                time.sleep(3)
            record["job"] = job
            if job["status"] != "done":
                raise RuntimeError("download did not finish successfully")
            response = http.get(f"/api/file/{job_id}")
            response.raise_for_status()
            data = response.content
            args.download_dir.mkdir(parents=True, exist_ok=True)
            (args.download_dir / "sample-5s.mp4").write_bytes(data)
            record["file"] = {"status": response.status_code, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "mp4_ftyp": data[4:8] == b"ftyp", "content_disposition": response.headers.get("content-disposition")}
            record["quota_after"] = http.get("/api/auth/me").json()["quota"]
            record["pass"] = bool(data) and record["file"]["mp4_ftyp"] and record["quota_after"]["used"] == record["quota_before"]["used"] + 1
    except (httpx.HTTPError, ValueError, RuntimeError, KeyError) as error:
        record.update(error_type=type(error).__name__, error=str(error)[:400])
        if isinstance(error, httpx.HTTPStatusError):
            record["detail"] = error.response.json()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False), flush=True)
    if not record["pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
