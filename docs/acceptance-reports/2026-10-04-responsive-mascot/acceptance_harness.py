"""Real local app + owned media, no LLM calls or existing database changes."""
from __future__ import annotations
import argparse
import functools
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

def ready(url, process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"Service exited: {process.returncode}")
        try:
            urllib.request.urlopen(url, timeout=1).close()
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"Service startup timeout: {url}")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--check-output-dir", action="store_true")
    parser.add_argument("--focus-only", action="store_true")
    parser.add_argument("--gesture-only", action="store_true")
    args = parser.parse_args()
    stamp = str(time.time_ns())
    work = ROOT / ".planning/2026-10-04-responsive-mascot" / stamp
    output = (args.output_dir or work / "evidence").resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("output-dir must be new or empty; evidence is never overwritten")
    if args.check_output_dir:
        print(json.dumps({"output_dir": str(output), "valid": True, "offline": True}))
        return
    web = work / "web"
    web.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=640x360:r=25", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(web / "owned.mp4")], check=True)
    (web / "owned.html").write_text('<!doctype html><title>Owned responsive acceptance</title><video controls src="owned.mp4"></video>', encoding="utf-8")
    static = ThreadingHTTPServer(("127.0.0.1", 8064), functools.partial(SimpleHTTPRequestHandler, directory=str(web)))
    threading.Thread(target=static.serve_forever, daemon=True).start()
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("LLM_"):
            env.pop(key)
    env.update(DB_URL=f"sqlite:///{(work / 'owned.db').as_posix()}", TEMP_DIR=str(work / "downloads"),
               LLM_BASE_URL="", LLM_API_KEY="", LLM_MODEL="", RATE_LIMIT="300",
               NO_PROXY="127.0.0.1,localhost", VITE_PROXY_TARGET="http://127.0.0.1:8063")
    processes, logs = [], []
    creation = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        for name, command, cwd, url in (
            ("backend", [str(ROOT / ".venv/Scripts/python.exe"), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8063"], ROOT / "backend", "http://127.0.0.1:8063/openapi.json"),
            ("frontend", [shutil.which("node"), str(ROOT / "frontend/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", "5188", "--strictPort"], ROOT / "frontend", "http://127.0.0.1:5188"),
        ):
            log = (work / f"{name}.log").open("w", encoding="utf-8")
            logs.append(log)
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=creation)
            processes.append(process)
            ready(url, process)
        command = [shutil.which("node"), str(HERE / "browser_acceptance.mjs"), "--output-dir", str(output)]
        if args.focus_only:
            command.append("--focus-only")
        if args.gesture_only:
            command.append("--gesture-only")
        completed = subprocess.run(command, cwd=ROOT, env=env, timeout=600)
        if completed.returncode:
            raise RuntimeError(f"Browser acceptance exited: {completed.returncode}")
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for log in logs:
            log.close()
        static.shutdown()
        static.server_close()
        output.mkdir(parents=True, exist_ok=True)
        with (output / "service-results.json").open("x", encoding="utf-8") as stream:
            json.dump({"ports": [8063, 8064, 5188], "processes_stopped": all(p.poll() is not None for p in processes), "static_stopped": True, "llm_configured": False, "work": str(work.relative_to(ROOT))}, stream, indent=2)

if __name__ == "__main__":
    main()
