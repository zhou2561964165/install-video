"""Bounded, root-only Ragas diagnostic caller; no production imports or retries.

Engineering: mature components, narrow interfaces and single-direction dependency;
UI changes require ui-ux-pro-max/design-system and three-layer tokens. Historical
evidence stays read-only. Scores do not establish semantic or coverage acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import platform
import re
import sys
import tempfile
import tomllib

import httpx

PROJECT = Path(__file__).resolve().parents[2]
TOOL = "tools/semantic_eval"
GROUP = ".planning/2026-10-13-long-summary-fidelity/call-group.json"
PHASE7 = ".planning/2026-10-13-long-summary-fidelity/phase-7.json"
IO_HELPER = "docs/acceptance-reports/2026-10-05-grounded-summary-evidence/scripts/evaluate.py"
LOCK = "docs/acceptance-reports/2026-10-05-grounded-summary/results/.http-session-lock"
DEFAULT_OUTPUT = "docs/acceptance-reports/2026-10-15-ragas-semantic/results/phase-1"
ASSETS = ("runner.py", "ragas_adapter.py", "tests/test_runner.py", "tests/test_adapter.py",
          "pyproject.toml", "uv.lock", "cases.json", "CASE_NOTES.md", "bound_sources.json", "review.md")
OPTIONS = {"endpoint": "https://api.deepseek.com/responses", "model": "deepseek-v4-pro",
           "max_posts": 16, "max_case_posts": 2, "max_output_tokens": 4096, "max_input_chars": 60000}


def module_from(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Only these four safe IO functions are used; no historical caller is executed.
_io = module_from(PROJECT / IO_HELPER, "semantic_eval_safe_io")
directory_guard, exclusive, durable, digest = _io.directory_guard, _io.exclusive, _io.durable, _io.digest


def read(path):
    return strict_json(path.read_text(encoding="utf-8"))


def strict_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique)


def now():
    return datetime.now(timezone.utc).isoformat()


def dependencies():
    if Path(sys.prefix).resolve() != (PROJECT / TOOL / ".venv").resolve():
        raise RuntimeError("Use the dedicated locked evaluator environment")
    normalize = lambda name: re.sub(r"[-_.]+", "-", name).lower()
    packages = dict(sorted((normalize(dist.metadata["Name"]), dist.version)
                           for dist in importlib.metadata.distributions()))
    lock = tomllib.loads((PROJECT / TOOL / "uv.lock").read_text(encoding="utf-8"))
    locked = {}
    for package in lock["package"]:
        locked.setdefault(normalize(package["name"]), set()).add(package["version"])
    if packages.get("ragas") != "0.4.3" or any(version not in locked.get(name, set()) for name, version in packages.items()):
        raise RuntimeError("Installed package versions differ from uv.lock")
    return {"python": platform.python_version(), "packages": packages, "lock_versions_verified": True}


def project_path(relative):
    path = (PROJECT / relative).resolve()
    if not path.is_relative_to(PROJECT.resolve()) or path == PROJECT.resolve():
        raise RuntimeError("Asset path escapes project")
    return path


def validate_cases(cases):
    if not isinstance(cases, list) or not cases or len(cases) * 2 > OPTIONS["max_posts"]:
        raise RuntimeError("Cases exceed finite phase budget")
    ids = set()
    for case in cases:
        if (not isinstance(case, dict) or not isinstance(case.get("id"), str)
                or not re.fullmatch(r"[A-Za-z0-9_-]+", case["id"]) or case["id"] in ids
                or type(case.get("expected_supported")) is not bool
                or any(not isinstance(case.get(key), str) or not case[key].strip()
                       for key in ("source", "response", "error_kind"))
                or not isinstance(case.get("core_questions"), list)
                or any(not isinstance(q, str) for q in case["core_questions"])):
            raise RuntimeError("Invalid case schema")
        if len(case["source"]) + len(case["response"]) > OPTIONS["max_input_chars"]:
            raise RuntimeError("Case exceeds input budget")
        ids.add(case["id"])
    return cases


def freeze(output):
    output = Path(output).resolve()
    cases = validate_cases(read(PROJECT / TOOL / "cases.json"))
    if read(PROJECT / GROUP).get("reserved_posts") != 10:
        raise RuntimeError("Historical group no longer at bound 10 POST")
    prior = read(PROJECT / PHASE7)
    if prior.get("status") != "frozen" or prior.get("reserved_posts") != 0:
        raise RuntimeError("Phase 7 must stay frozen with zero POST")
    paths = [f"{TOOL}/{name}" for name in ASSETS] + [GROUP, PHASE7, IO_HELPER]
    bound = read(PROJECT / TOOL / "bound_sources.json")
    for row in bound["assets"]:
        path = project_path(row["path"])
        if digest(path.read_bytes()) != row["sha256"]:
            raise RuntimeError("Bound source hash mismatch")
        paths.append(row["path"])
    blobs = {name: project_path(name).read_bytes() for name in dict.fromkeys(paths)}
    manifest = {name: digest(blob) for name, blob in blobs.items()}
    frozen = {"version": 1, "created_utc": now(), "options": OPTIONS,
              "assets": manifest, "dependencies": dependencies(), "cases": cases,
              "historical_reserved_posts": 10, "phase7_reserved_posts": 0,
              "planned_posts": len(cases) * 2, "network": False, "dotenv_read": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()  # Never replace an existing phase, even an incomplete freeze.
    for name, blob in blobs.items():
        path = output / "snapshot" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(blob)
    exclusive(output / "provenance.json", frozen)
    exclusive(output / "request-ledger.json", {"status": "frozen", "max_posts": 16, "requests": []})
    exclusive(output / "freeze-receipt.json", {"provenance_sha256": digest((output / "provenance.json").read_bytes())})
    return {"planned_posts": frozen["planned_posts"], "network": False, "dotenv_read": False}


def check_freeze(output, *, live):
    frozen = read(output / "provenance.json")
    if digest((output / "provenance.json").read_bytes()) != read(output / "freeze-receipt.json")["provenance_sha256"]:
        raise RuntimeError("Freeze provenance changed")
    if frozen["options"] != OPTIONS or frozen["dependencies"] != dependencies():
        raise RuntimeError("Frozen options or dependency versions changed")
    for relative, expected in frozen["assets"].items():
        project_path(relative)  # Reject traversal before joining snapshot paths.
        if digest((output / "snapshot" / relative).read_bytes()) != expected:
            raise RuntimeError("Frozen snapshot changed")
        if live and digest(project_path(relative).read_bytes()) != expected:
            raise RuntimeError("Live asset differs from freeze")
    if frozen["cases"] != read(output / "snapshot" / TOOL / "cases.json"):
        raise RuntimeError("Frozen cases mismatch")
    validate_cases(frozen["cases"])
    return frozen


def evaluate(source, response, complete, adapter_path):
    # The adapter itself is byte-bound and checked before every paid request.
    adapter = module_from(adapter_path, "semantic_eval_adapter")
    return adapter.evaluate(source, response, complete)


def load_key():
    # Import and read secrets only inside an explicitly authorized run.
    from dotenv import dotenv_values
    key = dotenv_values(PROJECT / "backend/.env").get("LLM_API_KEY")
    if not isinstance(key, str) or not key.strip():
        raise RuntimeError("Missing configured provider key")
    return key.strip()


def public_response(body, key):
    texts = []
    if isinstance(body, dict) and isinstance(body.get("output"), list):
        for message in body["output"]:
            if (isinstance(message, dict) and message.get("type") == "message"
                    and message.get("role") == "assistant" and isinstance(message.get("content"), list)):
                texts.extend(p["text"] for p in message["content"] if isinstance(p, dict)
                             and p.get("type") == "output_text" and isinstance(p.get("text"), str))
    text = "".join(texts)
    leaked = key in text
    def contains_credential(value):
        if isinstance(value, str):
            return key in value
        if isinstance(value, (list, tuple)):
            return any(contains_credential(item) for item in value)
        return False
    if not leaked:
        try:
            # Preserve every object key/value, including duplicate keys, while
            # decoding escapes. Strict protocol validation still happens later.
            decoded = json.loads(text, object_pairs_hook=lambda pairs: pairs)
        except ValueError:
            pass  # The unchanged malformed text is rejected by strict_json.
        else:
            leaked = contains_credential(decoded)
    usage = body.get("usage", {}) if isinstance(body, dict) else {}
    usage = {name: usage[name] for name in ("input_tokens", "output_tokens", "total_tokens")
             if isinstance(usage, dict) and type(usage.get(name)) is int and usage[name] >= 0}
    status = body.get("status") if isinstance(body, dict) else None
    return {"output_text": "[redacted]" if leaked else text,
            "usage": usage, "status": status if status in {"completed", "incomplete", "failed", "cancelled", "queued", "in_progress"} else None,
            "model": OPTIONS["model"] if isinstance(body, dict) and body.get("model") == OPTIONS["model"] else None}, leaked


def statistics(cases, results):
    return {"cases": len(results),
            "false_accepts": sum(r["evaluation"]["all_supported"] and not c["expected_supported"] for c, r in zip(cases, results)),
            "false_rejects": sum(not r["evaluation"]["all_supported"] and c["expected_supported"] for c, r in zip(cases, results))}


def check_requests(output, ledger):
    if read(output / "request-ledger.json") != ledger:
        raise RuntimeError("Durable ledger drifted")
    for row in ledger["requests"]:
        for folder, field in (("payloads", "payload_sha256"), ("raw", "raw_sha256")):
            if field in row and digest((output / folder / f"{row['ordinal']:02d}.json").read_bytes()) != row[field]:
                raise RuntimeError("Consumed evidence drifted")


def test_transport_guard(output, transport):
    if transport is None:
        return
    temp_root = Path(tempfile.gettempdir()).resolve()
    project = PROJECT.resolve()
    if (not isinstance(transport, httpx.MockTransport) or project == temp_root
            or not project.is_relative_to(temp_root) or not output.is_relative_to(project)
            or not (project / LOCK).resolve().is_relative_to(project)):
        raise RuntimeError("Mock transport is restricted to an owned system-temp project")


def run(output, *, caller, transport=None):
    if caller != "root":
        raise RuntimeError("Only the root caller may run")
    output = Path(output).resolve()
    test_transport_guard(output, transport)
    with directory_guard(PROJECT / LOCK):
        ledger = read(output / "request-ledger.json")
        if ledger.get("status") != "frozen" or ledger.get("requests"):
            raise RuntimeError("Phase cannot be reopened")
        ledger["status"] = "running"
        durable(output / "request-ledger.json", ledger)
        results, error, case_posts = [], None, 0
        try:
            frozen = check_freeze(output, live=True)
            key = load_key()
            with httpx.Client(transport=transport, timeout=120, follow_redirects=False, trust_env=False) as client:
                for case in frozen["cases"]:
                    case_posts = 0
                    def complete(prompt, response_model):
                        nonlocal case_posts
                        check_freeze(output, live=True)
                        check_requests(output, ledger)
                        if (not isinstance(prompt, str) or len(prompt) > 60000
                                or case_posts >= 2 or len(ledger["requests"]) >= 16):
                            raise RuntimeError("Finite call/input limit reached")
                        schema = response_model.model_json_schema()
                        payload = {"model": OPTIONS["model"], "temperature": 0,
                                   "input": prompt, "max_output_tokens": 4096,
                                   "reasoning": {"effort": "none"},
                                   "text": {"format": {"type": "json_schema", "name": "ragas_response", "schema": schema}}}
                        if key in json.dumps(payload, ensure_ascii=False):
                            raise RuntimeError("Credential echo blocked")
                        number = len(ledger["requests"]) + 1
                        row = {"ordinal": number, "case": case["id"], "case_post": case_posts + 1,
                               "status": "reserved", "reserved_utc": now()}
                        ledger["requests"].append(row)
                        durable(output / "request-ledger.json", ledger)  # Nonrefundable, before send.
                        case_posts += 1
                        payload_path = output / "payloads" / f"{number:02d}.json"
                        exclusive(payload_path, payload)
                        row["payload_sha256"] = digest(payload_path.read_bytes())
                        durable(output / "request-ledger.json", ledger)
                        response = client.post(OPTIONS["endpoint"], headers={"Authorization": "Bearer " + key}, json=payload)
                        try:
                            body = strict_json(response.text)
                        except ValueError:
                            body = {}
                        public, leaked = public_response(body, key)
                        raw_path = output / "raw" / f"{number:02d}.json"
                        exclusive(raw_path, public)
                        row.update(status="received", http_status=response.status_code, raw_sha256=digest(raw_path.read_bytes()))
                        durable(output / "request-ledger.json", ledger)
                        if (not response.is_success or leaked or public["status"] != "completed"
                                or public["model"] != OPTIONS["model"] or not public["output_text"]):
                            raise RuntimeError("Provider response rejected")
                        parsed = strict_json(public["output_text"])
                        if not isinstance(parsed, dict):
                            raise RuntimeError("Structured response must be an object")
                        return parsed  # Adapter validates original JSON types without coercion.
                    evaluation = evaluate(case["source"], case["response"], complete, output / "snapshot" / TOOL / "ragas_adapter.py")
                    check_requests(output, ledger)
                    if case_posts != 2:
                        raise RuntimeError("A complete two-stage evaluation is required")
                    results.append({"id": case["id"], "evaluation": evaluation})
        except Exception:
            # Exception messages, URLs, headers and arbitrary provider fields are never persisted.
            error = "evaluation_error"
        finally:
            ledger["status"] = "closed"
            ledger["closed_utc"] = now()
            durable(output / "request-ledger.json", ledger)
            cases = read(output / "provenance.json")["cases"]
            result = {"status": "closed", "outcome": "error" if error else "completed",
                      "error": error, "reserved_posts": len(ledger["requests"]), "results": results,
                      "statistics": statistics(cases, results),
                      "limitations": ["Diagnostic scores do not prove semantic correctness or core-topic coverage."]}
            exclusive(output / "result.json", result)
            exclusive(output / "closed-receipt.json", {name: digest((output / name).read_bytes())
                      for name in ("provenance.json", "request-ledger.json", "result.json")})
        if error:
            raise RuntimeError("Evaluation failed; phase closed, evidence retained") from None
        return result


def verify(output):
    output = Path(output).resolve()
    frozen = check_freeze(output, live=False)
    receipt = read(output / "closed-receipt.json")
    for name in ("provenance.json", "request-ledger.json", "result.json"):
        if digest((output / name).read_bytes()) != receipt[name]:
            raise RuntimeError("Closed evidence changed")
    ledger, result = read(output / "request-ledger.json"), read(output / "result.json")
    rows = ledger["requests"]
    if ledger["status"] != "closed" or result["status"] != "closed" or len(rows) > 16 or result["reserved_posts"] != len(rows):
        raise RuntimeError("Invalid closed ledger")
    for number, row in enumerate(rows, 1):
        if row["ordinal"] != number:
            raise RuntimeError("Ledger ordinal mismatch")
        for folder, field in (("payloads", "payload_sha256"), ("raw", "raw_sha256")):
            if field in row and digest((output / folder / f"{number:02d}.json").read_bytes()) != row[field]:
                raise RuntimeError("Request evidence changed")
    for case, stored in zip(frozen["cases"], result["results"]):
        matching = [row for row in rows if row["case"] == case["id"]]
        if stored["id"] != case["id"] or len(matching) != 2:
            raise RuntimeError("Incomplete case result")
        replay = iter(matching)
        def complete(prompt, response_model):
            row = next(replay)
            payload = read(output / "payloads" / f"{row['ordinal']:02d}.json")
            if payload["input"] != prompt or payload["text"]["format"]["schema"] != response_model.model_json_schema():
                raise RuntimeError("Replay prompt/schema mismatch")
            raw = read(output / "raw" / f"{row['ordinal']:02d}.json")
            if row["status"] != "received" or raw["status"] != "completed":
                raise RuntimeError("Replay response was not complete")
            return strict_json(raw["output_text"])
        if evaluate(case["source"], case["response"], complete, output / "snapshot" / TOOL / "ragas_adapter.py") != stored["evaluation"] or next(replay, None) is not None:
            raise RuntimeError("Recomputed evaluation mismatch")
    if (result["statistics"] != statistics(frozen["cases"], result["results"])
            or (result["outcome"] == "completed" and (len(result["results"]) != len(frozen["cases"]) or len(rows) != frozen["planned_posts"]))):
        raise RuntimeError("Incomplete phase or inconsistent statistics")
    return {"status": "closed", "outcome": result["outcome"], "reserved_posts": len(rows), "network": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    for action in ("freeze", "run", "verify"):
        actions.add_argument("--" + action, action="store_true")
    parser.add_argument("--output", type=Path, default=PROJECT / DEFAULT_OUTPUT)
    parser.add_argument("--caller", choices=["root"])
    args = parser.parse_args()
    try:
        result = freeze(args.output) if args.freeze else run(args.output, caller=args.caller) if args.run else verify(args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception:
        parser.exit(1, "Evaluation refused or failed; inspect preserved phase evidence.\n")


if __name__ == "__main__":
    main()
