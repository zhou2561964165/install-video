"""Zero-paid guard faults through real loopback HTTP and synthetic temporary sources.

Default plan opens no socket. --run-zero-paid opens only 127.0.0.1 and uses the
immutable guard implementations with temporary fixture ledgers. Simulated POSTs
never consume or extend a vendor budget and do not establish model quality.
Engineering: skills first; UI three-layer tokens; narrow interfaces; yt-dlp only
ytdlp_service; scene read-only; historical artifacts remain immutable.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
from urllib.parse import urlsplit

import httpx

PROJECT = Path(__file__).resolve().parents[4]
REPORT = Path(__file__).resolve().parents[1]
REPAIR_SCRIPT = PROJECT / "docs/acceptance-reports/2026-10-09-adaptive-summary-repair/scripts/evaluate.py"
FINAL_SCRIPT = PROJECT / "docs/acceptance-reports/2026-10-09-adaptive-summary-final/scripts/evaluate.py"
MAX_POSTS = 20
CASE_NAMES = ("tracker_reservation_write_failure", "runtime_model_drift", "false_result_index",
    "transport_interrupt", "client_construction_failure", "success_without_request",
    "changed_prior_identity", "tampered_prior_snapshot", "changed_prior_runner", "third_request")


def plan():
    return {"mode": "plan", "socket_started": False, "paid_model_calls": 0,
        "maximum_loopback_posts": MAX_POSTS, "cases": list(CASE_NAMES),
        "source_scope": "synthetic fixture sources and simulated ledgers",
        "transport_scope": "explicit run uses real loopback HTTP supplier stub only",
        "vendor_budget_consumed": False, "model_quality_verified": False}


class FakeUpstream:
    """A bounded local listener; construction alone does not create a socket."""

    def __init__(self, *, maximum_posts=MAX_POSTS):
        if type(maximum_posts) is not int or not 1 <= maximum_posts <= MAX_POSTS:
            raise ValueError("Loopback HTTP cap must be an integer between 1 and 20")
        self.maximum_posts = maximum_posts
        self.received_posts = 0
        self.attempted_posts = 0
        self.lock = threading.Lock()
        self.shutdown_verified = False

    def __enter__(self):
        upstream = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                with upstream.lock:
                    if upstream.received_posts >= upstream.maximum_posts:
                        self.send_error(429, "Loopback cap reached")
                        return
                    upstream.received_posts += 1
                length = int(self.headers.get("Content-Length", "0"))
                if self.path != "/chat/completions" or not 0 < length <= 65536:
                    self.send_error(400, "Invalid simulation payload")
                    return
                payload = json.loads(self.rfile.read(length))
                body = json.dumps({"model": payload.get("model"), "usage": {"total_tokens": 0},
                    "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
                        "summary": "Synthetic high-level overview.", "key_points": ["Synthetic condition and example."]})}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.endpoint = f"http://127.0.0.1:{self.port}/chat/completions"
        self.thread = threading.Thread(target=self.server.serve_forever,
            kwargs={"poll_interval": 0.05}, name="zero-paid-supplier-stub", daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            listener_closed = probe.connect_ex(("127.0.0.1", self.port)) != 0
        self.shutdown_verified = listener_closed and not self.thread.is_alive()
        if not self.shutdown_verified:
            raise RuntimeError("Loopback listener/thread did not shut down")


class LoopbackTransport:
    def __init__(self, upstream):
        self.upstream = upstream
        self.http = httpx.Client(timeout=3, trust_env=False, follow_redirects=False)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.http.close()

    def post(self, url, *, headers, json):
        parts = urlsplit(url)
        if (parts.scheme != "http" or parts.hostname != "127.0.0.1" or parts.port != self.upstream.port
                or parts.path != "/chat/completions" or parts.username or parts.password
                or parts.query or parts.fragment or url != self.upstream.endpoint):
            raise ValueError("Only the exact running loopback stub destination is allowed")
        with self.upstream.lock:
            if self.upstream.attempted_posts >= self.upstream.maximum_posts:
                raise RuntimeError("Zero-paid loopback HTTP cap reached before send")
            self.upstream.attempted_posts += 1
        return self.http.post(url, headers=headers, json=json)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass
class SimulationSummary:
    summary: str
    key_points: list[str]
    provider: str
    model: str


def local_runtime(module, endpoint):
    settings, _, _ = module.runtime()

    class Service:
        _summary_input = staticmethod(lambda source: source.strip())
        _summary_chunks = staticmethod(lambda source, limit: [source])

        @staticmethod
        def summarize_text(source, *, title, output_language, client):
            response = client.post(endpoint, headers={}, json={"model": settings.llm_model,
                "messages": [{"role": "user", "content": source}], "max_tokens": 10})
            response.raise_for_status()
            data = json.loads(response.json()["choices"][0]["message"]["content"])
            return SimulationSummary(data["summary"], data["key_points"], settings.llm_provider, settings.llm_model)

    return settings, Service, endpoint


def repair_fixture(root, patches, endpoint):
    root.mkdir()
    # Reuse fixture setup, never invoke its pytest test functions or product runtime.
    fixture = load_module(PROJECT / "backend/tests/test_adaptive_repair_evaluation.py", "zero_paid_repair_fixture")
    module = fixture.entry.__wrapped__(root, patches)
    simulated = local_runtime(module, endpoint)
    patches.setattr(module, "runtime", lambda: simulated)
    return module


def final_fixture(root, patches, endpoint, transport):
    old = repair_fixture(root, patches, endpoint)
    old_runner = old.REPORT / "scripts/evaluate.py"
    old_runner.parent.mkdir(parents=True)
    old_runner.write_bytes(REPAIR_SCRIPT.read_bytes())
    helper = root / "helper.py"
    helper.write_bytes(old.HELPER.read_bytes())
    old_paths = old.asset_paths
    patches.setattr(old, "asset_paths", lambda: old_paths() + [old_runner, helper])
    old.freeze()
    old.check()
    old.run(transport=transport)  # Two actual loopback HTTP scaffold responses.
    module = load_module(FINAL_SCRIPT, "zero_paid_final_guard")
    for key in ("PROJECT", "CORPUS", "GROUP", "LONG_TRACKER", "SHORT_TRACKER", "SHARED_LOCK",
                "OLD_FINAL", "OLD_REPAIRED", "LONG_REPORT", "SHORT_REPORT"):
        patches.setattr(module, key, getattr(old, key))
    patches.setattr(module, "REPORT", root / "final-report")
    patches.setattr(module, "RESULTS", root / "final-report/results")
    patches.setattr(module, "TRACKER", root / "final-tracker.json")
    patches.setattr(module, "REPAIR_REPORT", old.REPORT)
    patches.setattr(module, "REPAIR_TRACKER", old.TRACKER)
    patches.setattr(module, "REPAIR_RUNNER", old_runner)
    patches.setattr(module, "HELPER", helper)
    patches.setattr(module, "load_repair_verifier", lambda: old)
    patches.setattr(module, "runtime", old.runtime)
    patches.setattr(module, "asset_paths", lambda: old_paths() + [old_runner, helper,
        old.TRACKER, *[p for p in old.RESULTS.rglob("*") if p.is_file()]])
    return module


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def expect_rejection(operation):
    try:
        operation()
    except RuntimeError:
        return
    raise AssertionError("Guard accepted the injected invalid state")


def ready(module):
    module.freeze()
    module.check()


def run_case(name, root, upstream, transport, patches):
    final = name in CASE_NAMES[6:]
    module = final_fixture(root, patches, upstream.endpoint, transport) if final else repair_fixture(root, patches, upstream.endpoint)
    if final and name != "third_request":
        if name == "changed_prior_identity":
            value = module.read(module.REPAIR_TRACKER)
            value["status"] = "running"
            module.io.durable(module.REPAIR_TRACKER, value)
        elif name == "tampered_prior_snapshot":
            value = module.read(module.REPAIR_REPORT / "results/provenance.json")
            record = next(iter(value["snapshots"].values()))
            (module.REPAIR_REPORT / "results" / record["file"]).write_bytes(b"injected snapshot failure")
        else:
            module.REPAIR_RUNNER.write_bytes(b"injected runner failure")
        expect_rejection(module.freeze)
        require(not module.RESULTS.exists(), "Invalid prior phase allocated final results")
        return {"guard_rejected": True, "simulated_scaffold_posts": 2, "simulated_case_posts": 0}

    ready(module)
    if name == "tracker_reservation_write_failure":
        original = module.io.durable
        injected = False

        def broken(path, value):
            nonlocal injected
            if path == module.TRACKER and value.get("reserved_posts") == 23 and not injected:
                injected = True
                raise OSError("injected durable pre-reservation fault")
            original(path, value)

        patches.setattr(module.io, "durable", broken)
        index = module.run(transport=transport)
        require(index["posts"] == 1 and index["stopped_on_error"], "Reservation failure was not counted and stopped")
        require(module.read(module.RESULTS / "request-ledger.json")["requests"][0]["status"] == "error", "Reservation attempt lacks error")
        module.verify_results()
        simulated_posts = 0
    elif name == "runtime_model_drift":
        settings, _, _ = module.runtime()

        class Drift:
            def post(self, *args, **kwargs):
                response = transport.post(*args, **kwargs)
                settings.llm_model = "injected-model-drift"
                return response

        index = module.run(transport=Drift())
        require(index["posts"] == 1 and index["stopped_on_error"], "Runtime drift did not stop later sends")
        module.verify_results()
        simulated_posts = 1
    elif name == "transport_interrupt":
        class Interrupted:
            def post(self, *args, **kwargs):
                transport.post(*args, **kwargs)
                raise KeyboardInterrupt()

        try:
            module.run(transport=Interrupted())
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("Injected interrupt was swallowed")
        require(module.read(module.RESULTS / "request-ledger.json")["requests"][0]["status"] == "error", "Interrupted attempt lacks durable error")
        module.verify_results()
        simulated_posts = 1
    elif name == "client_construction_failure":
        def constructor(*args, **kwargs):
            raise RuntimeError("injected client initialization failure")

        patches.setattr(httpx, "Client", constructor)
        expect_rejection(module.run)
        require(module.read(module.RESULTS / "result-index.json")["posts"] == 0, "Client initialization reserved a request")
        module.verify_results()
        simulated_posts = 0
    elif name == "third_request":
        settings, original, endpoint = module.runtime()

        class DoubleRequest(original):
            @staticmethod
            def summarize_text(source, *, title, output_language, client):
                result = original.summarize_text(source, title=title, output_language=output_language, client=client)
                if title == "en-medium":
                    original.summarize_text(source, title=title, output_language=output_language, client=client)
                return result

        patches.setattr(module, "runtime", lambda: (settings, DoubleRequest, endpoint))
        index = module.run(transport=transport)
        require(index["posts"] == 2 and index["stopped_on_error"], "Third request did not stop at two attempts")
        require(module.verify_results()["work_posts"] == 26, "Simulated final ledger exceeded or lost its ceiling")
        simulated_posts = 2
    else:
        module.run(transport=transport)
        index = module.read(module.RESULTS / "result-index.json")
        index["stopped_on_error"] = True
        if name == "success_without_request":
            ledger = module.read(module.RESULTS / "request-ledger.json")
            ledger["requests"] = []
            module.io.durable(module.RESULTS / "request-ledger.json", ledger)
            tracker = module.read(module.TRACKER)
            tracker["reserved_posts"] = 22
            module.io.durable(module.TRACKER, tracker)
            index.update(posts=0, phase_error_type="injected false state")
        module.io.durable(module.RESULTS / "result-index.json", index)
        expect_rejection(module.verify_results)
        simulated_posts = 2
    require(module.read(module.TRACKER)["status"] == "closed", "Case left a running simulated phase")
    return {"guard_rejected": True, "simulated_case_posts": simulated_posts,
        "simulated_scaffold_posts": 2 if final else 0, "simulated_tracker": str(module.TRACKER)}


def original_hashes():
    roots = [PROJECT / "docs/acceptance-reports" / name for name in (
        "2026-10-08-summary-quality-final", "2026-10-09-summary-quality-repaired",
        "2026-10-09-adaptive-summary", "2026-10-09-adaptive-short-medium",
        "2026-10-09-adaptive-summary-repair", "2026-10-09-adaptive-summary-final")]
    paths = [p for root in roots for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths.extend((PROJECT / ".planning/2026-10-08-summary-quality-finish").glob("budget*.json"))
    paths.extend(PROJECT / "backend/tests" / name for name in (
        "test_adaptive_repair_evaluation.py", "test_adaptive_final_evaluation.py"))
    return {str(p.relative_to(PROJECT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}


def run_zero_paid():
    import pytest

    temporary_base = (PROJECT / "tmp").resolve()
    if not temporary_base.is_relative_to(PROJECT.resolve()):
        raise ValueError("Simulation artifacts must stay within project tmp")
    temporary_base.mkdir(exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="online-guard-zero-paid-", dir=temporary_base)).resolve()
    before = original_hashes()
    cases = []
    upstream = FakeUpstream()
    with upstream:
        with LoopbackTransport(upstream) as transport:
            for name in CASE_NAMES:
                start_count = upstream.received_posts
                case = {"name": name, "workspace": str(workspace / name)}
                try:
                    with pytest.MonkeyPatch.context() as patches:
                        details = run_case(name, workspace / name, upstream, transport, patches)
                    expected_posts = details["simulated_case_posts"] + details["simulated_scaffold_posts"]
                    require(upstream.received_posts - start_count == expected_posts, "Actual HTTP count differs from expected simulated guard sends")
                    case.update(details, passed=True)
                except Exception as exc:
                    case.update(passed=False, error_type=type(exc).__name__, error=str(exc))
                case["loopback_http_posts"] = upstream.received_posts - start_count
                cases.append(case)
    after = original_hashes()
    report = {"mode": "zero-paid-real-loopback-http", "source_scope": "synthetic temporary fixture sources",
        "transport_scope": "actual HTTP over 127.0.0.1 to FakeUpstream; no vendor or product source",
        "simulation": True, "simulated_vendor_ledger": True, "vendor_budget_consumed": False,
        "paid_model_calls": 0, "model_quality_verified": False, "dotenv_read": False,
        "maximum_loopback_posts": MAX_POSTS, "loopback_http_posts": upstream.received_posts,
        "artifacts": str(workspace), "stub_port": upstream.port, "port_shutdown_verified": upstream.shutdown_verified,
        "server_thread_stopped": not upstream.thread.is_alive(), "child_processes_spawned": 0,
        "original_hashes_before": before, "original_hashes_after": after,
        "originals_unchanged": before == after, "cases": cases,
        "passed": before == after and upstream.shutdown_verified and all(c["passed"] for c in cases)}
    path = workspace / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {key: report[key] for key in ("mode", "passed", "paid_model_calls", "loopback_http_posts",
        "maximum_loopback_posts", "port_shutdown_verified", "originals_unchanged")} | {
        "report": str(path), "cases_passed": sum(c["passed"] for c in cases), "cases_total": len(cases)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-zero-paid", action="store_true")
    args = parser.parse_args(argv)
    result = run_zero_paid() if args.run_zero_paid else plan()
    print(json.dumps(result, ensure_ascii=False))
    if args.run_zero_paid and not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
