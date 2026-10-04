"""Owned temporary services; no .env, application database, model or media changes.

Run at repository root with .venv/Scripts/python.exe and this script path.
Evidence is written to a new directory, ignored by default. Frozen reports are never overwritten.
"""
from __future__ import annotations

import json
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
WORK = ROOT / ".planning/2026-10-04-public-mobile-gpu"


def ready(url, process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"Service exited: {process.returncode}")
        try:
            urllib.request.urlopen(url, timeout=1).close()
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"Service startup timed out: {url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="New empty evidence directory; defaults to a timestamped ignored directory")
    parser.add_argument("--check-output-dir", action="store_true", help="Validate destination offline without starting services or creating files")
    args = parser.parse_args()
    output_dir = (args.output_dir or WORK / str(time.time_ns()) / "evidence").resolve()
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        parser.error("--output-dir must be a new or empty directory; existing evidence will not be overwritten")
    if args.check_output_dir:
        print(json.dumps({"output_dir": str(output_dir), "valid": True, "offline": True}))
        return
    WORK.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("LLM_"):
            env.pop(key)
    proxy = subprocess.check_output([
        "powershell", "-NoProfile", "-Command",
        "[System.Net.WebRequest]::DefaultWebProxy.GetProxy([uri]'https://archive.org').AbsoluteUri",
    ], text=True).strip()
    if proxy and not proxy.startswith("https://archive.org"):
        env.update(HTTP_PROXY=proxy, HTTPS_PROXY=proxy)
    stamp = str(time.time_ns())
    env.update(DB_URL=f"sqlite:///{(WORK / ('acceptance-' + stamp + '.db')).as_posix()}",
               TEMP_DIR=str(WORK / ("downloads-" + stamp)), RATE_LIMIT="300",
               LLM_BASE_URL="", LLM_API_KEY="", LLM_MODEL="",
               NO_PROXY="127.0.0.1,localhost", VITE_PROXY_TARGET="http://127.0.0.1:8062")
    handles, processes = [], []
    creation = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        for name, command, cwd, url in (
            ("backend", [str(ROOT / ".venv/Scripts/python.exe"), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8062"], ROOT / "backend", "http://127.0.0.1:8062/openapi.json"),
            ("frontend", [shutil.which("node"), str(ROOT / "frontend/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", "5187", "--strictPort"], ROOT / "frontend", "http://127.0.0.1:5187"),
        ):
            log = (WORK / f"{name}-{stamp}.log").open("w", encoding="utf-8")
            handles.append(log)
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=creation)
            processes.append(process)
            ready(url, process)
        result = subprocess.run([shutil.which("node"), str(HERE / "browser_acceptance.mjs"), "--output-dir", str(output_dir)], cwd=ROOT, env=env, timeout=600)
        if result.returncode:
            raise RuntimeError(f"Browser acceptance exited {result.returncode}")
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for log in handles:
            log.close()
        output_dir.mkdir(parents=True, exist_ok=True)
        service_result = output_dir / "service-results.json"
        with service_result.open("x", encoding="utf-8") as result_file:
            json.dump({"ports": [8062, 5187], "processes_stopped": all(p.poll() is not None for p in processes), "llm_configured": False, "temporary_work": str(WORK.relative_to(ROOT)), "proxy_from_system": True}, result_file, indent=2)


if __name__ == "__main__":
    main()
