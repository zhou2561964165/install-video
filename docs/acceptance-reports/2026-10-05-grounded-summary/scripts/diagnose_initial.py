"""Offline record reasons from preserved failed extraction; no model call.

Engineering: skills/token/config/narrow boundaries; LLM only llm_service,
yt-dlp only ytdlp_service, visual scene read-only. MIT derivatives NC-SA4.0.
"""
import json
from pathlib import Path
import sys
import importlib.util

REPORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPORT.parents[2] / "backend"))
results = REPORT / "results"
spec = importlib.util.spec_from_file_location("initial_contract_frozen_codec", results / "initial-contract-facts.py")
codec = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = codec
spec.loader.exec_module(codec)
FactLimits, FactValidationError = codec.FactLimits, codec.FactValidationError
SourcePart, parse_facts = codec.SourcePart, codec.parse_facts
raw = json.loads((results / "responses/04.json").read_text(encoding="utf-8"))
payload = json.loads(raw["content"])
source = json.loads((results / "initial-contract-en-medium-trace.json").read_text(encoding="utf-8"))["events"][-1]["sources"][0]
part = SourcePart(source["id"], source["text"], source["global_start"])
rows = []
for index, fact in enumerate(payload["facts"], 1):
    try:
        parse_facts({"facts": [fact]}, part, FactLimits(), "F1_")
        reason = "valid"
    except FactValidationError as exc:
        reason = str(exc)
    rows.append({"fact": index, "quote_chars": len(fact["quote"]), "codec_reason": reason,
                 "named_attribution_in_quote": fact["attribution"] == "source" or fact["attribution"] in fact["quote"]})
evidence = {"phase": "initial-contract", "offline": True, "provider_calls": 0,
            "records": rows,
            "finding": "Whole extraction refused at first invalid record, without partial salvage or provider retry. First quote exceeds400 and named attribution is outside its quote; offline per-record reasons preserve all violations."}
path = results / "initial-contract-failure-diagnosis.json"
with path.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(evidence, stream, ensure_ascii=False, indent=2); stream.write("\n")
print(json.dumps(evidence, ensure_ascii=False))
