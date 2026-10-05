"""Read-only sizes and paid-attempt statistics; no semantic accuracy claims.

Engineering: skills before changes, configurable interfaces, token UI,
yt-dlp only in ytdlp_service, scene read-only.
MIT-derived summaries retain attribution and CC BY-NC-SA 4.0.
"""
import json
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
RESULTS = REPORT / "results"
OLD = REPORT.parent / "2026-10-04-natural-subtitle-quality/results"


def main():
    ledger = json.loads((RESULTS / "request-ledger.json").read_text(encoding="utf-8"))
    samples = []
    for phase in ("natural-auto", "natural-refined", "natural-tool"):
        for sample_id in ("zh-short", "en-medium", "en-long"):
            path = RESULTS / f"{phase}-{sample_id}.json"
            if not path.exists():
                continue
            result = json.loads(path.read_text(encoding="utf-8"))
            baseline = json.loads((OLD / f"bounded-{sample_id}.json").read_text(encoding="utf-8"))["result"]
            row = {"phase": phase, "id": sample_id,
                   "baseline_point_count": len(baseline["key_points"]),
                   "baseline_point_chars": [len(point) for point in baseline["key_points"]]}
            if "result" in result:
                row.update(point_count=len(result["result"]["key_points"]),
                           point_chars=[len(point) for point in result["result"]["key_points"]])
            else:
                row["error_type"] = result.get("error_type")
            samples.append(row)
    print(json.dumps({"read_only": True, "sizes_are_not_quality": True,
                      "reserved_post_attempts": len(ledger["requests"]),
                      "confirmed_http_responses": sum(row.get("status") == "response" for row in ledger["requests"]),
                      "reported_tokens": sum(row.get("usage", {}).get("total_tokens", 0) for row in ledger["requests"]),
                      "samples": samples}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
