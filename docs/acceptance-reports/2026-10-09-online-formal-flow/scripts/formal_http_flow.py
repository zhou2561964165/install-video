"""Real localhost app API/source flow, with a strictly loopback-only model fixture.

This zero-paid preparation is not public MIT extraction or model-quality proof.
No product/evidence files are modified. Existing account identity is copied without
its password into a temporary DB; an ephemeral test JWT is used only there.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime
import functools
import hashlib
import html
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
CORPUS = ROOT / "docs/acceptance-reports/2026-10-04-natural-subtitle-quality/corpus"
OLD_WEB = ROOT / ".planning/2026-10-04-platform-browser-summary/browser/web"
MAX_LOCAL_POSTS = 20


class LoopbackGate:
    """Reserve finite attempts before transport; never consult environment proxies."""
    def __init__(self, endpoint, state, httpx_module):
        self.endpoint, self.state, self.httpx = endpoint, state, httpx_module

    def client(self, *args, **kwargs):
        kwargs.update(trust_env=False, follow_redirects=False)
        client = self.httpx.Client(*args, **kwargs)
        gate = self
        class AllowedClient:
            def post(self, url, **options):
                if url != gate.endpoint:
                    raise RuntimeError("Zero-paid model gate refused a non-owned endpoint")
                if options.get("follow_redirects"):
                    raise RuntimeError("Zero-paid model gate refused redirects")
                with gate.state["lock"]:
                    if gate.state["transport_reservations"] >= MAX_LOCAL_POSTS:
                        raise RuntimeError("Local transport reservation limit reached")
                    gate.state["transport_reservations"] += 1
                return client.post(url, **options)
            def close(self):
                client.close()
        return AllowedClient()


def start_http(stack, handler, threads):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    stack.callback(server.server_close)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    threads.append(thread)
    def stop():
        server.shutdown()
        thread.join(5)
    stack.callback(stop)
    return server


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def existing_identity():
    from dotenv import dotenv_values
    config = dotenv_values(ROOT / "backend/.env")
    url = config.get("DB_URL") or "sqlite:///" + (ROOT / "backend/jobs.db").as_posix()
    if not url.startswith("sqlite:///"):
        raise RuntimeError("Read-only account isolation requires the current SQLite database")
    path = Path(url[len("sqlite:///"):])
    if not path.is_absolute():
        path = ROOT / "backend" / path
    path = path.resolve()
    with sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
        row = connection.execute("select id,email,created_at from user where email=?",
                                 ("manual-test@example.com",)).fetchone()
    if row is None:
        raise RuntimeError("Existing manual account not found; no account will be created")
    return path, digest(path), row


class SilentStatic(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def write_json(handler, status, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass


class LocalSupplier(BaseHTTPRequestHandler):
    state = None

    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        with self.state["lock"]:
            if self.state["posts"] >= MAX_LOCAL_POSTS:
                write_json(self, 429, {"error": "local fixture limit reached"})
                return
            self.state["posts"] += 1
            ordinal = self.state["posts"]
            mode = self.state["mode"]
            self.state["events"].append({"ordinal": ordinal, "mode": mode,
                                         "model": body.get("model")})
        if mode == "disconnect":
            self.close_connection = True
            self.connection.close()
            return
        if mode == "http_503":
            write_json(self, 503, {"error": "controlled loopback outage"})
            return
        if mode == "non_json":
            self.send_response(200)
            self.send_header("Content-Length", "1")
            self.end_headers()
            self.wfile.write(b"{")
            return
        if mode == "timeout":
            time.sleep(1.2)
        result = {} if mode == "invalid_summary" else {
            "summary": "Controlled HTTP serialization fixture; not a source-quality result.",
            "key_points": ["Only API/source transport and presentation are being checked."]}
        write_json(self, 200, {"model": "formal-local-only",
            "choices": [{"finish_reason": "length" if mode == "length" else "stop",
                         "message": {"content": json.dumps(result)}}]})


def prepare_web(work):
    web = work / "web"
    web.mkdir()
    shutil.copyfile(OLD_WEB / "master.m3u8", web / "master.m3u8")
    for height in ("360", "720"):
        shutil.copytree(OLD_WEB / height, web / height)
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    for sample in manifest["samples"]:
        sid = sample["id"]
        shutil.copyfile(CORPUS / f"{sid}.vtt", web / f"{sid}.vtt")
        markup = ('<!doctype html><meta charset="utf-8"><title>' + html.escape(sample["title"]) +
            '</title><video controls><source src="master.m3u8" type="application/x-mpegurl">' +
            f'<track kind="subtitles" src="{sid}.vtt" srclang="{sample["language"]}" default></video>')
        (web / f"{sid}.html").write_text(markup, encoding="utf-8")
    (web / "no-captions.html").write_text('<title>Owned no-caption fixture</title><video controls>'
        '<source src="master.m3u8" type="application/x-mpegurl"></video>', encoding="utf-8")
    return web, manifest["samples"]


def run_zero_paid(browser_hold=False, browser_only=False):
    import httpx
    import uvicorn

    (ROOT / "tmp").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="formal-api-zero-", dir=ROOT / "tmp"))
    source_db, source_db_before, identity = existing_identity()
    web, samples = prepare_web(work)
    state = {"lock": threading.Lock(), "mode": "healthy", "posts": 0, "transport_reservations": 0, "events": []}
    LocalSupplier.state = state
    threads = []
    stack = ExitStack()
    try:
        static = start_http(stack, functools.partial(SilentStatic, directory=str(web)), threads)
        supplier = start_http(stack, LocalSupplier, threads)
        source_base = f"http://127.0.0.1:{static.server_port}"
        supplier_endpoint = f"http://127.0.0.1:{supplier.server_port}/v1/chat/completions"
        for key in list(os.environ):
            if key.startswith("LLM_"):
                os.environ.pop(key)
        os.environ.update(DB_URL="sqlite:///" + (work / "isolated.db").as_posix(),
            TEMP_DIR=str(work / "downloads"), JWT_SECRET=secrets.token_hex(32),
            LLM_BASE_URL=supplier_endpoint.rsplit("/chat/completions", 1)[0],
            LLM_PROVIDER="simulated-local-upstream", LLM_MODEL="formal-local-only", LLM_API_KEY="",
            LLM_SUMMARY_STRATEGY="legacy", LLM_SUMMARY_LENGTH_MODE="adaptive", RATE_LIMIT="300",
            NO_PROXY="127.0.0.1,localhost")
        sys.path.insert(0, str(ROOT / "backend"))
        from app.main import app
        from app.db import engine
        stack.callback(engine.dispose)
        from app.services.auth import create_token
        from app.services import llm_service as service
        from app.config import settings
        from app.services import ytdlp_service
        # Silence extractor diagnostics; selection/URL/extraction logic stays native.
        original_extract = ytdlp_service.yt_dlp.YoutubeDL
        class QuietLogger:
            def debug(self, *_): pass
            def warning(self, *_): pass
            def error(self, *_): pass
        ytdlp_service.yt_dlp.YoutubeDL = lambda options: original_extract({**options, "logger": QuietLogger()})
        stack.callback(setattr, ytdlp_service.yt_dlp, "YoutubeDL", original_extract)
        # Preserve SQLite's original timestamp bytes; do not reinterpret it as
        # a naive ORM datetime with the newer timezone-aware bind processor.
        with sqlite3.connect(work / "isolated.db") as connection:
            connection.execute("insert into user(id,email,created_at,password_hash) values(?,?,?,?)",
                (*identity, "disabled-isolated-session"))
        token = create_token(identity[0])
        headers = {"Authorization": "Bearer " + token}
        if browser_hold:
            from fastapi.responses import HTMLResponse
            # Ephemeral owned session only; token never enters files or tool output.
            @app.get("/api/__owned_session", include_in_schema=False)
            def browser_session():
                return HTMLResponse("<script>localStorage.setItem('auth_token'," +
                    json.dumps(token) + ");location.replace('/');</script>",
                    headers={"Cache-Control": "no-store"})
        actual_httpx = service.httpx
        gate = LoopbackGate(supplier_endpoint, state, actual_httpx)
        class Facade:
            Client = gate.client
            def __getattr__(self, name): return getattr(actual_httpx, name)
        service.httpx = Facade()
        stack.callback(setattr, service, "httpx", actual_httpx)
        sock = socket.socket()
        stack.callback(sock.close)
        sock.bind(("127.0.0.1", 0))
        sock.listen(128)
        api_port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
        api_thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        api_thread.start()
        threads.append(api_thread)
        def stop_api():
            server.should_exit = True
            api_thread.join(10)
        stack.callback(stop_api)
        api_base = f"http://127.0.0.1:{api_port}"
        outcomes = []
        report = {"real_vendor_posts": 0, "model_quality_verified": False, "browser_only": browser_only,
            "existing_account_identity": True, "passwords_read": False, "password_login_tested": False,
            "isolated_session": True, "api": api_base, "source_kind": "loopback HTML5 + unmodified original VTT",
            "public_native_success_claimed": False, "work": str(work), "cases": outcomes}
        def request(client, name, path, body=None, *, authorized=True):
            before = state["posts"]
            response = client.post(api_base + path, json=body,
                headers=headers if authorized else {}) if body is not None else client.get(api_base + path,
                headers=headers if authorized else {})
            try: data = response.json()
            except ValueError: data = {}
            detail = data.get("detail") if isinstance(data, dict) else None
            outcome = {"case": name, "status": response.status_code,
                "error_type": detail.get("error_type") if isinstance(detail, dict) else None,
                "local_supplier_posts": state["posts"] - before}
            outcomes.append(outcome)
            return response, data, outcome
        for _ in range(100):
            if server.started: break
            if not api_thread.is_alive(): raise RuntimeError("API server stopped during startup")
            time.sleep(0.05)
        if not server.started: raise RuntimeError("API startup timed out")
        if not browser_only:
            with httpx.Client(timeout=45, trust_env=False) as client:
                request(client, "unauthenticated_summary", "/api/summary",
                    {"url": source_base + "/zh-short.html"}, authorized=False)
                request(client, "existing_session_me", "/api/auth/me")
                request(client, "invalid_url", "/api/summary", {"url": "not-a-url"})
                request(client, "no_subtitle", "/api/subtitle", {"url": source_base + "/no-captions.html"})
                for sample in samples:
                    sid = sample["id"]
                    url = source_base + f"/{sid}.html"
                    request(client, sid + "_parse", "/api/parse", {"url": url})
                    response, data, outcome = request(client, sid + "_subtitle", "/api/subtitle", {"url": url})
                    if response.status_code != 200:
                        outcome["native_loopback_tracks"] = False
                        continue
                    text = data["text"]
                    expected = (CORPUS / sample["file"]).read_text(encoding="utf-8")
                    outcome["original_text_exact"] = text == expected
                    outcome["normalized_text_exact"] = service._summary_input(text) == service._summary_input(expected)
                    response, data, _ = request(client, sid + "_summary_fixture", "/api/summary", {"url": url})
                    if response.status_code == 200:
                        (work / f"{sid}-api-fixture.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                for mode, expected_error in [("http_503", "llm_error"), ("non_json", "llm_error"),
                        ("invalid_summary", "llm_invalid_response"), ("disconnect", "llm_error"),
                        ("timeout", "llm_error"), ("length", "llm_incomplete_response")]:
                    state["mode"] = mode
                    settings.llm_timeout_seconds = 1 if mode == "timeout" else 90
                    _, _, outcome = request(client, mode, "/api/summary", {"url": source_base + "/zh-short.html"})
                    outcome["expected_error_type"] = expected_error
                    outcome["passed"] = outcome["status"] == 502 and outcome["error_type"] == expected_error
                state["mode"] = "healthy"
                settings.llm_model = ""
                _, _, outcome = request(client, "unconfigured_model", "/api/summary", {"url": source_base + "/zh-short.html"})
                outcome["passed"] = outcome["status"] == 503 and outcome["error_type"] == "llm_unconfigured" and outcome["local_supplier_posts"] == 0
        if browser_hold:
            settings.llm_model = "formal-local-only"
            settings.llm_timeout_seconds = 90
            probe = socket.socket()
            with probe:
                probe.bind(("127.0.0.1", 0))
                frontend_port = probe.getsockname()[1]
            frontend_log = open(work / "frontend.log", "w", encoding="utf-8")
            stack.callback(frontend_log.close)
            child_env = {**os.environ, "VITE_PROXY_TARGET": api_base}
            child = subprocess.Popen(["node", str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                "--host", "127.0.0.1", "--port", str(frontend_port), "--strictPort"],
                cwd=ROOT / "frontend", env=child_env, stdout=frontend_log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            def stop_frontend():
                if child.poll() is None:
                    child.terminate()
                    try: child.wait(10)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(5)
            stack.callback(stop_frontend)
            ready = {"frontend": f"http://127.0.0.1:{frontend_port}",
                "session_path": "/api/__owned_session", "source": source_base,
                "control": str(work / "browser-control.json"), "work": str(work)}
            (work / "browser-ready.json").write_text(json.dumps(ready), encoding="utf-8")
            print(json.dumps({"browser_ready": str(work / "browser-ready.json")}), flush=True)
            until = time.monotonic() + 600
            control_path = work / "browser-control.json"
            while time.monotonic() < until:
                if control_path.exists():
                    command = json.loads(control_path.read_text(encoding="utf-8"))
                    state["mode"] = command.get("mode", "healthy")
                    if command.get("stop"):
                        report["browser"] = command.get("evidence", {})
                        break
                if child.poll() is not None:
                    report["browser_start_failed"] = True
                    break
                time.sleep(0.1)
            else:
                report["browser_hold_timed_out"] = True
    finally:
        stack.close()
        if "report" not in locals():
            report = {"cases": [], "real_vendor_posts": 0, "initialization_failed": True}
        report["local_supplier_posts"] = state["posts"]
        report["transport_reservations"] = state["transport_reservations"]
        report["local_supplier_cap"] = MAX_LOCAL_POSTS
        report["supplier_events"] = state["events"]
        report["threads_stopped"] = not any(t.is_alive() for t in threads)
        report["live_database_unchanged"] = digest(source_db) == source_db_before
        report["request_headers_and_tokens_saved"] = False
        path = work / "report.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report": str(path), "real_vendor_posts": 0, "local_supplier_posts": state["posts"],
            "threads_stopped": report["threads_stopped"], "live_database_unchanged": report["live_database_unchanged"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-zero-paid", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--browser-hold", action="store_true")
    parser.add_argument("--browser-only", action="store_true")
    args = parser.parse_args()
    result = run_zero_paid(args.browser_hold or args.browser_only, args.browser_only) if args.run_zero_paid else {
        "mode": "plan", "network": False, "real_vendor_posts": 0,
        "local_supplier_cap": MAX_LOCAL_POSTS, "live_budget": "pending user answer"}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
