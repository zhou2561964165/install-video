"""Compact quality evaluation: offline default, exclusive freeze, bounded POSTs.

Engineering: skills first; UI three-layer tokens; narrow configurable interfaces;
HTTP only llm_service, yt-dlp only ytdlp_service, scene read-only. Historical
MIT-derived corpus/rubric/outputs retain attribution and CC BY-NC-SA 4.0.
"""
import argparse
from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import os
import sys
import time
from urllib.parse import urlsplit

import httpx

REPORT = Path(__file__).resolve().parents[1]
PROJECT = REPORT.parents[2]
RESULTS = REPORT / "results"
LEDGER = RESULTS / "request-ledger.json"
GROUP = PROJECT / ".planning/2026-10-08-summary-quality-finish/budget-group.json"
WORK_ID = "summary-quality-finish-20261008"
PHASE, CEILING = "quality-final", 19
HELPER = REPORT.parent / "2026-10-05-grounded-summary-evidence/scripts/evaluate.py"
CHECKER = Path(__file__).with_name("check_evidence.py")
ORIGINAL_RUBRIC = REPORT.parent / "2026-10-08-grounded-summary-clause/rubric.json"
CALLER_LOCK = REPORT.parent / "2026-10-05-grounded-summary/results/.http-session-lock"
spec = importlib.util.spec_from_file_location("quality_evidence_helpers", HELPER)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)  # Helpers only; no user environment or runtime.
CONFIG = {**base.CONFIG, "llm_max_input_chars": 100000,
          "llm_summary_facts_compose_max_output_tokens": 8192,
          "llm_summary_facts_audit_max_output_tokens": 8192,
          "llm_summary_format_retries": 1, "llm_summary_semantic_retries": 1,
          "llm_summary_max_extra_calls": 2, "llm_summary_quality_contract": "compact"}
MODULES = {**base.MODULES, **{name: PROJECT / f"backend/app/services/summary_{name}.py"
                            for name in ("normalization", "references", "retry", "audit_contract", "quality")}}
_CALLER_SESSION = None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeError("Duplicate evidence field")
        result[key] = value
    return result


def read(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def same_json(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_json(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same_json(a, b) for a, b in zip(left, right))
    return left == right


def validate_usage(value):
    """Accept only the safe numeric usage fields persisted by the caller."""
    if value is None:
        return
    counts = {"prompt_tokens", "completion_tokens", "total_tokens",
              "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"}
    details = {"prompt_tokens_details": {"cached_tokens", "audio_tokens"},
               "completion_tokens_details": {"reasoning_tokens", "audio_tokens",
                   "accepted_prediction_tokens", "rejected_prediction_tokens"}}
    if not isinstance(value, dict) or not set(value) <= counts | details.keys():
        raise RuntimeError("Invalid safe response usage")
    for key, count in value.items():
        if key in details:
            if (not isinstance(count, dict) or not set(count) <= details[key]
                    or any(type(number) is not int or number < 0 for number in count.values())):
                raise RuntimeError("Invalid safe response usage")
        elif type(count) is not int or count < 0:
            raise RuntimeError("Invalid safe response usage")


def validate_completion(row):
    """A reservation counts immediately; terminal metadata must be typed."""
    status = row["status"]
    if status == "reserved":
        return
    try:
        start, end = (datetime.fromisoformat(row[key]) for key in ("started_utc", "ended_utc"))
        if start.utcoffset() is None or end.utcoffset() is None or end < start:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("Invalid request completion time") from None
    if status in {"response", "http_error"}:
        code = row.get("http_status")
        if (type(code) is not int or not 100 <= code <= 599
                or (status == "response") != (200 <= code < 300)
                or "usage" not in row):
            raise RuntimeError("Invalid response completion metadata")
        validate_usage(row["usage"])
    elif status == "transport_error" and any(key in row for key in ("http_status", "response_sha256", "usage")):
        raise RuntimeError("Transport failure contains response metadata")


def validate_ledger(path=None, phase=None, ceiling=None):
    path, phase, ceiling = path or LEDGER, phase or PHASE, CEILING if ceiling is None else ceiling
    if not path.exists():
        return {"phase": phase, "ceiling": ceiling, "requests": []}
    ledger = read(path)
    if (not isinstance(ledger, dict) or ledger.get("phase") != phase
            or type(ledger.get("ceiling")) is not int or ledger["ceiling"] != ceiling
            or not isinstance(ledger.get("requests"), list) or len(ledger["requests"]) > ceiling):
        raise RuntimeError("Invalid phase ledger")
    counts = {}
    for ordinal, row in enumerate(ledger["requests"], 1):
        if not isinstance(row, dict) or row.get("phase") != phase:
            raise RuntimeError("Foreign phase request")
        sample = row.get("sample")
        if not isinstance(sample, str) or not sample:
            raise RuntimeError("Invalid sample identity")
        counts[sample] = counts.get(sample, 0) + 1
        if (type(row.get("ordinal")) is not int or row["ordinal"] != ordinal
                or type(row.get("sample_post")) is not int or row["sample_post"] != counts[sample]
                or type(row.get("attempt")) is not int or row["attempt"] < 1
                or row.get("stage") not in {"extract", "compose", "audit"}
                or row.get("recovery") not in {"none", "local_normalization", "model_format_repair", "semantic_revision"}
                or row.get("status") not in {"reserved", "response", "http_error", "transport_error", "evidence_error"}):
            raise RuntimeError("Invalid request ordinal")
        validate_completion(row)
    return ledger


def validate_group():
    group = read(GROUP)
    if (group.get("work_id") != WORK_ID or type(group.get("hard_ceiling")) is not int
            or group["hard_ceiling"] != 26 or type(group.get("initial_phase_ceiling")) is not int
            or group["initial_phase_ceiling"] != CEILING or not isinstance(group.get("phases"), list)):
        raise RuntimeError("Invalid work budget")
    count, identities = 0, set()
    for phase in group["phases"]:
        if (not isinstance(phase, dict) or not isinstance(phase.get("phase"), str)
                or not phase["phase"] or not isinstance(phase.get("ledger"), str) or not phase["ledger"]):
            raise RuntimeError("Invalid group phase")
        path = Path(phase.get("ledger", "")).resolve()
        if phase["phase"] in identities or not path.is_relative_to(PROJECT.resolve()):
            raise RuntimeError("Invalid group ledger path")
        identities.add(phase["phase"])
        ceiling = phase.get("ceiling")
        if type(ceiling) is not int or not 0 < ceiling <= group["hard_ceiling"]:
            raise RuntimeError("Invalid group phase ceiling")
        if path.exists():
            count += len(validate_ledger(path, phase["phase"], ceiling)["requests"])
    # Exact exhaustion remains readable for close/check; the POST guard uses >=.
    if count > group["hard_ceiling"]:
        raise RuntimeError("Work POST ceiling exceeded")
    return group, count


def load_runtime():
    sys.path.insert(0, str(PROJECT / "backend"))
    base.load_dotenv(PROJECT / "backend/.env", override=False)
    from app.config import settings
    from app.services import llm_service
    from app.services.summary_facts import FactLimits
    base.settings, base.service, base.FactLimits = settings, llm_service, FactLimits
    base.REPORT, base.RESULTS, base.CONFIG, base.MODULES = REPORT, RESULTS, CONFIG, MODULES
    for name, value in CONFIG.items():
        setattr(settings, name, value)


def snapshot():
    if any(not same_json(getattr(base.settings, k), v) for k, v in CONFIG.items()):
        raise RuntimeError("Runtime configuration changed")
    current = base.snapshot()
    endpoint = base.service._endpoint()
    parsed = urlsplit(endpoint)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError("Endpoint must not contain credentials or query secrets")
    current.update(phase=PHASE, ceiling=CEILING, ledger=str(LEDGER), work_id=WORK_ID,
        endpoint=endpoint, runtime_profile={"llm_base_url": base.settings.llm_base_url,
            "llm_timeout_seconds": base.settings.llm_timeout_seconds},
        original_rubric_sha256=base.digest(ORIGINAL_RUBRIC.read_bytes()),
        runner_chain_sha256={"entry": base.digest(Path(__file__).read_bytes()),
            "checker": base.digest(CHECKER.read_bytes()), "helper": base.digest(HELPER.read_bytes())},
        repair_prompts={stage: base.service._grounded_messages(stage, {"repair": {}},
            base.FactLimits(**current["fact_limits"]))[0]["content"] for stage in ("extract", "compose", "audit")})
    if current["expected_posts"] != 13 or len(current["samples"]) != 3:
        raise RuntimeError("Unexpected three-source plan")
    if current["rubric_sha256"] != current["original_rubric_sha256"]:
        raise RuntimeError("Original rubric bytes changed")
    for sample in current["samples"]:
        sample["maximum_posts"] = sample["expected_posts"] + 2
    return current


def verify(frozen):
    current = snapshot()
    if any(not same_json(frozen.get(k), value) for k, value in current.items()):
        raise RuntimeError("Frozen inputs/code/config changed; POST refused")
    for key, digest in frozen["module_sha256"].items():
        if base.digest((RESULTS / f"{PHASE}-{key}.py").read_bytes()) != digest:
            raise RuntimeError("Frozen module bytes changed")


class BudgetClient:
    def __init__(self, http, frozen, *, caller_locked=False):
        self.http, self.frozen, self.sample = http, frozen, ""
        self.latest, self.stopped = None, False
        self.caller_locked = caller_locked

    def post(self, url, *, headers, json):
        if self.caller_locked is not False and (
                _CALLER_SESSION is None or self.caller_locked is not _CALLER_SESSION or not CALLER_LOCK.is_dir()):
            raise RuntimeError("Invalid caller session")
        with nullcontext() if self.caller_locked is not False else base.directory_guard(CALLER_LOCK):
            return self._post(url, headers=headers, json=json)

    def _post(self, url, *, headers, json):
        if self.stopped:
            raise RuntimeError("Caller stopped after transport failure")
        verify(self.frozen)
        if url != self.frozen.get("endpoint"):
            raise RuntimeError("Transport destination differs from freeze")
        event = self.latest
        if not isinstance(event, dict) or not event.get("stages"):
            raise RuntimeError("Missing diagnostic reservation context")
        entry = event["stages"][-1]
        stage = entry.get("stage")
        if entry.get("status") != "requesting" or entry.get("paid_attempt") is not True:
            raise RuntimeError("Unplanned POST")
        if stage not in ("extract", "compose", "audit"):
            raise RuntimeError("Unknown stage")
        if (type(entry.get("attempt")) is not int or entry["attempt"] < 1
                or type(event.get("paid_calls")) is not int or event["paid_calls"] < 1
                or entry.get("recovery") not in {"none", "local_normalization", "model_format_repair", "semantic_revision"}):
            raise RuntimeError("Invalid attempt metadata")
        user = read_user(json)
        repaired = "repair" in user
        prompt = self.frozen["repair_prompts" if repaired else "stage_prompts"][stage]
        expected = {"model": self.frozen["model"], "temperature": 0.2,
            "max_tokens": self.frozen["stage_max_output_tokens"][stage], **self.frozen["options"]}
        if (not same_json({k: v for k, v in json.items() if k != "messages"}, expected)
                or not same_json(json["messages"][0], {"role": "system", "content": prompt})):
            raise RuntimeError("Transport differs from freeze")
        with base.directory_guard(RESULTS / "ledger.lock"):
            group, group_posts = validate_group()
            if not any(p["phase"] == PHASE and p["ledger"] == str(LEDGER) for p in group["phases"]):
                raise RuntimeError("Phase absent from work budget")
            ledger = validate_ledger()
            if len(ledger["requests"]) >= CEILING or group_posts >= group["hard_ceiling"]:
                raise RuntimeError("Hard POST ceiling exhausted")
            prior = [row for row in ledger["requests"] if row["sample"] == self.sample]
            plan = next((p for p in self.frozen["samples"] if p["id"] == self.sample), None)
            if plan is None or len(prior) >= plan["maximum_posts"]:
                raise RuntimeError("Sample POST ceiling exhausted")
            paid = [s for s in event["stages"] if s.get("paid_attempt") is True]
            if len(paid) != len(prior) + 1 or event.get("paid_calls") != len(paid):
                raise RuntimeError("Attempt identity differs from ledger")
            repairs = [read_user(read(RESULTS / "payloads" / f"{row['ordinal']:02d}.json")).get("repair")
                       for row in prior]
            repairs = [r for r in repairs if r is not None]
            if repaired:
                repair = user["repair"]
                category = repair.get("category") if isinstance(repair, dict) else None
                if (not prior or category not in ("format", "semantic") or len(repairs) >= 2
                        or sum(r["category"] == category for r in repairs) >= CONFIG[f"llm_summary_{category}_retries"]):
                    raise RuntimeError("Repair ceiling or category violated")
                previous = paid[-2]
                raw = read(RESULTS / "responses" / f"{prior[-1]['ordinal']:02d}.json")
                if (previous.get("status") != "failed" or previous.get("stage") != stage
                        or previous.get("error_category") != category or raw.get("http_status") != 200
                        or repair.get("reason") != previous.get("reason")
                        or not same_json(repair.get("failed_items"), previous.get("failed_items"))
                        or entry["attempt"] != previous["attempt"] + 1
                        or repair.get("previous_response") != (raw.get("content") or "").strip()):
                    raise RuntimeError("Repair feedback does not match failed attempt")
            elif prior and paid[-2].get("status") != "validated":
                raise RuntimeError("Failed attempt cannot start another stage")
            elif entry["attempt"] != 1:
                raise RuntimeError("Unexpected stage attempt")
            ordinal = len(ledger["requests"]) + 1
            path = RESULTS / "payloads" / f"{ordinal:02d}.json"
            base.exclusive(path, json)
            row = {"phase": PHASE, "ordinal": ordinal, "sample": self.sample, "sample_post": len(prior) + 1,
                "stage": stage, "attempt": entry["attempt"], "recovery": entry["recovery"],
                "started_utc": base.now(), "status": "reserved", "payload_sha256": base.digest(path.read_bytes())}
            ledger["requests"].append(row)
            base.durable(LEDGER, ledger)  # Persist before every potentially billable send.
        received = False
        try:
            response = self.http.post(url, headers=headers, json=json)
            received = True
            evidence = {"phase": PHASE, "ordinal": ordinal, "sample": self.sample, "stage": stage,
                "http_status": response.status_code, "body_sha256": base.digest(response.content)}
            try:
                data = response.json()
            except ValueError:
                evidence.update(content=None, finish_reason=None, usage=None, error_type="invalid_json")
            else:
                evidence.update(base.response_evidence(data) if response.is_success else {
                    "content": None, "finish_reason": None, "usage": None, "error_type": "http_error"})
                if response.is_success:
                    try:
                        base.service._content_from_payload(data)
                    except base.service.LLMServiceError as exc:
                        evidence["adapter_error_type"] = exc.error_type
            path = RESULTS / "responses" / f"{ordinal:02d}.json"
            base.exclusive(path, evidence)
            row.update(status="response" if response.is_success else "http_error", http_status=response.status_code,
                       response_sha256=base.digest(path.read_bytes()), usage=evidence["usage"])
            self.stopped = (not response.is_success or evidence.get("error_type") == "invalid_json"
                            or "adapter_error_type" in evidence)
            return response
        except Exception as exc:
            self.stopped = True
            row.update(status="evidence_error" if received else "transport_error", error_type=type(exc).__name__)
            raise
        finally:
            row["ended_utc"] = base.now()
            with base.directory_guard(RESULTS / "ledger.lock"):
                latest = validate_ledger()
                latest["requests"][ordinal - 1] = row
                base.durable(LEDGER, latest)


def read_user(payload):
    messages = payload.get("messages")
    if (not isinstance(messages, list) or len(messages) != 2
            or not isinstance(messages[1], dict) or set(messages[1]) != {"role", "content"}
            or messages[1]["role"] != "user" or not isinstance(messages[1]["content"], str)):
        raise RuntimeError("Invalid message contract")
    user = json_module.loads(messages[1]["content"], object_pairs_hook=unique_object)
    if not isinstance(user, dict):
        raise RuntimeError("Invalid user payload")
    return user


json_module = json


def main(argv=None):
    global _CALLER_SESSION
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    for flag in ("freeze", "check-only", "run"):
        modes.add_argument(f"--{flag}", action="store_true")
    args = parser.parse_args(argv)
    if not (args.freeze or args.check_only or args.run):
        print(json.dumps({"phase": PHASE, "ceiling": CEILING, "work_ceiling": 26,
            "expected_posts": 13, "network": False, "config": CONFIG}))
        return
    load_runtime()
    path = RESULTS / f"{PHASE}-provenance.json"
    if args.freeze:
        group, _ = validate_group()
        if group["phases"] or validate_ledger()["requests"]:
            raise RuntimeError("Cannot reopen a work phase")
        current = snapshot()
        base.exclusive(path, {"frozen_utc": base.now(), **current})
        for key, source in MODULES.items():
            with (RESULTS / f"{PHASE}-{key}.py").open("xb") as stream:
                stream.write(source.read_bytes()); stream.flush(); os.fsync(stream.fileno())
        group["phases"] = [{"phase": PHASE, "ledger": str(LEDGER), "ceiling": CEILING}]
        group["status"] = "frozen"
        base.durable(GROUP, group)
        print(json.dumps({"frozen": True, "phase": PHASE, "normal_posts": 13, "maximum_posts": CEILING}))
        return
    frozen = read(path)
    verify(frozen)
    if args.check_only:
        validate_group(); validate_ledger()
        print(json.dumps({"phase": PHASE, "match": True}))
        return
    with base.directory_guard(CALLER_LOCK):
        _CALLER_SESSION = object()
        if validate_ledger()["requests"]:
            raise RuntimeError("Existing requests prohibit phase restart")
        base.exclusive(RESULTS / f"{PHASE}-started.json", {"started_utc": base.now()})
        manifest = read(base.OLD / "corpus/manifest.json")
        written = []
        with httpx.Client(timeout=base.settings.llm_timeout_seconds, trust_env=False) as http:
            client = BudgetClient(http, frozen, caller_locked=_CALLER_SESSION)
            for sample in manifest["samples"]:
                client.sample = sample["id"]
                events = []
                def collect(event):
                    events.append(event)
                    client.latest = event
                source = (base.OLD / "corpus" / sample["file"]).read_text(encoding="utf-8")
                row = {"phase": PHASE, "id": sample["id"], "source_sha256": base.digest(source)}
                started = time.monotonic()
                try:
                    row["result"] = asdict(base.service.summarize_text(source, title=sample["title"],
                        output_language="zh-CN", client=client, diagnostic=collect))
                    calls = [r for r in validate_ledger()["requests"] if r["sample"] == sample["id"]]
                    if (not events or events[-1].get("status") != "completed"
                            or type(events[-1].get("paid_calls")) is not int
                            or events[-1]["paid_calls"] != len(calls)
                            or any(r["status"] != "response" for r in calls)):
                        row.pop("result", None)
                        raise RuntimeError("Successful public result lacks complete paid evidence")
                except Exception as exc:
                    row["error_type"] = getattr(exc, "error_type", type(exc).__name__)
                row["elapsed_seconds"] = round(time.monotonic() - started, 2)
                trace_path = RESULTS / f"{PHASE}-{sample['id']}-trace.json"
                base.exclusive(trace_path, {"phase": PHASE, "id": sample["id"], "events": events})
                row["trace_sha256"] = base.digest(trace_path.read_bytes())
                result_path = RESULTS / f"{PHASE}-{sample['id']}.json"
                base.exclusive(result_path, row)
                written.append({"id": sample["id"], "file": result_path.name,
                    "sha256": base.digest(result_path.read_bytes())})
                print(json.dumps({"id": sample["id"], "error": row.get("error_type"),
                    "posts": sum(r["sample"] == sample["id"] for r in validate_ledger()["requests"])}), flush=True)
                if "error_type" in row:
                    break
        base.exclusive(RESULTS / f"{PHASE}-index.json", {"ended_utc": base.now(), "sample_results": written})
        group, count = validate_group()
        group.update(status="closed", reserved_posts=count)
        base.durable(GROUP, group)
        _CALLER_SESSION = None


if __name__ == "__main__":
    main()
