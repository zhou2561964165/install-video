r"""Local browser acceptance: real app APIs and yt-dlp, simulated LLM upstream only.

Run from repository root: .venv\Scripts\python.exe docs/acceptance-reports/2026-10-04-browser-e2e/local_harness.py
Does not read .env or modify user databases. Generated media/db/logs stay in .planning.
"""
from __future__ import annotations

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
ARTIFACTS = ROOT / "docs/acceptance-reports/2026-10-04-browser-e2e"
WORK = ROOT / ".planning/2026-10-04-platform-browser-summary/browser"
WEB = WORK / "web"
LLM_STATE = {"fail": False, "requests": []}


class LocalLLM(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        if self.path == "/fixture/control":
            LLM_STATE["fail"] = bool(data.get("fail"))
            payload = {"fail": LLM_STATE["fail"]}
            status = 200
        elif self.path == "/v1/chat/completions":
            is_summary = "strict JSON" in data["messages"][0]["content"]
            LLM_STATE["requests"].append({"operation": "summary" if is_summary else "translate", "failed": LLM_STATE["fail"]})
            status = 503 if LLM_STATE["fail"] else 200
            content = json.dumps({"summary": "可靠工具需要测试，并在失败后恢复。", "key_points": ["构建可靠工具", "测试提前发现错误", "失败后恢复"]}, ensure_ascii=False) if is_summary else "我们构建可靠的工具。\n测试会提早发现错误。\n失败后恢复。"
            payload = {"error": "controlled upstream outage"} if LLM_STATE["fail"] else {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}
        else:
            status, payload = 404, {"error": "not found"}
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def ready(url, process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"Service exited with {process.returncode}")
        try:
            urllib.request.urlopen(url, timeout=1).close()
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"Service startup timeout: {url}")


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    WEB.mkdir(exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    for height, width in ((360, 640), (720, 1280)):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c=blue:s={width}x{height}:r=25", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(WEB / f"sample-{height}.mp4")], check=True)
        segment_dir = WEB / str(height)
        segment_dir.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(WEB / f"sample-{height}.mp4"), "-c", "copy", "-hls_time", "1", "-hls_list_size", "0", str(segment_dir / "index.m3u8")], check=True)
    (WEB / "master.m3u8").write_text('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=300000,RESOLUTION=640x360,CODECS="avc1.64001e,mp4a.40.2"\n360/index.m3u8\n#EXT-X-STREAM-INF:BANDWIDTH=600000,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"\n720/index.m3u8\n', encoding="utf-8")
    (WEB / "captions.vtt").write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nWe build reliable tools.\n\n00:00:01.000 --> 00:00:02.000\nTests catch errors early.\n\n00:00:02.000 --> 00:00:03.000\nRecover after failures.\n", encoding="utf-8")
    for filename, tracks in (("captioned.html", '<track kind="subtitles" src="captions.vtt" srclang="en" label="English" default>'), ("no-captions.html", "")):
        (WEB / filename).write_text(f'<!doctype html><title>Owned browser acceptance media</title><video controls><source src="master.m3u8" type="application/x-mpegurl">{tracks}</video>', encoding="utf-8")
    static = ThreadingHTTPServer(("127.0.0.1", 8052), functools.partial(SimpleHTTPRequestHandler, directory=str(WEB)))
    llm = ThreadingHTTPServer(("127.0.0.1", 8053), LocalLLM)
    for server in (static, llm):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    processes, logs = [], []
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("LLM_"):
            env.pop(name)
    stamp = str(time.time_ns())
    env.update(DB_URL=f"sqlite:///{(WORK / ('browser-' + stamp + '.db')).as_posix()}", TEMP_DIR=str(WORK / ("downloads-" + stamp)), LLM_BASE_URL="http://127.0.0.1:8053/v1", LLM_MODEL="deterministic-local-e2e", LLM_PROVIDER="simulated-local-upstream", LLM_API_KEY="", RATE_LIMIT="300", NO_PROXY="127.0.0.1,localhost")
    creation = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        for name, command, cwd in (("backend", [str(ROOT / ".venv/Scripts/python.exe"), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8051"], ROOT / "backend"), ("frontend", [shutil.which("node"), str(ROOT / "frontend/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", "5185", "--strictPort"], ROOT / "frontend")):
            output = (WORK / f"{name}.log").open("w", encoding="utf-8")
            logs.append(output)
            env["VITE_PROXY_TARGET"] = "http://127.0.0.1:8051"
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, creationflags=creation)
            processes.append(process)
            ready("http://127.0.0.1:8051/openapi.json" if name == "backend" else "http://127.0.0.1:5185", process)
        completed = subprocess.run([shutil.which("node"), str(ARTIFACTS / "browser_flow.mjs")], cwd=ROOT, env=env)
        if completed.returncode:
            raise RuntimeError(f"Browser acceptance exited with {completed.returncode}")
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for output in logs:
            output.close()
        for server in (static, llm):
            server.shutdown()
            server.server_close()
        (ARTIFACTS / "upstream-results.json").write_text(json.dumps(LLM_STATE, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
