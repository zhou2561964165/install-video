"""Offline exact frozen-codec reasons for refined failed extraction.

Engineering: skill priority, UI skills/tokens, config/narrow boundaries;
yt-dlp only ytdlp_service, LLM only llm_service; scene read-only.
MIT derivatives retain authors/URLs and CC BY-NC-SA4.0 noncommercial SA.
"""
import importlib.util
import json
from pathlib import Path
import sys

REPORT = Path(__file__).resolve().parents[1]
results = REPORT / "results"
spec = importlib.util.spec_from_file_location("refined_frozen_codec", results / "refined-facts.py")
codec = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = codec
spec.loader.exec_module(codec)
raw = json.loads((results / "responses/05.json").read_text(encoding="utf-8"))
payload = json.loads(raw["content"])
source = json.loads((results / "refined-zh-short-trace.json").read_text(encoding="utf-8"))["events"][-1]["sources"][0]
part = codec.SourcePart(source["id"], source["text"], source["global_start"])
rows = []
for index, fact in enumerate(payload["facts"], 1):
    try:
        codec.parse_facts({"facts": [fact]}, part, codec.FactLimits(max_quote_chars=600), "F1_")
        reason = "valid"
    except codec.FactValidationError as exc:
        reason = str(exc)
    rows.append({"fact": index, "quote_chars": len(fact["quote"]), "codec_reason": reason,
                 "qualifiers_not_in_quote": [value for value in fact["qualifiers"]
                    if " ".join(value.split()) not in " ".join(fact["quote"].split())]})
evidence = {"phase": "refined", "offline": True, "provider_calls": 0,
            "codec_source": "refined-facts.py", "max_quote_chars": 600, "records": rows,
            "finding": "Record3 qualifier 第一个 is not quoted text 一个就是. Whole extraction refused qualifier_not_found; no partial salvage, repair stage or provider retry. Metadescription count-only fact persists despite refined prompt. No accepted source spans or delivered result for this candidate."}
path = results / "refined-failure-diagnosis.json"
with path.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(evidence, stream, ensure_ascii=False, indent=2); stream.write("\n")
print(json.dumps(evidence, ensure_ascii=False))
