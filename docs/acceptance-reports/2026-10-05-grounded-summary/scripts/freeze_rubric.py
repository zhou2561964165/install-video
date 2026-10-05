"""Freeze independent MIT-source rubric before any new output or provider POST.

Engineering: skills before applicable work; UI ui-ux-pro-max/design-system;
three-layer tokens/configuration; narrow single-direction interfaces;
yt-dlp only ytdlp_service, LLM only llm_service, visual scene read-only.
MIT source/derived rubric CC BY-NC-SA 4.0, original attribution retained.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
OLD = REPORT.parent / "2026-10-04-natural-subtitle-quality"
BASE = REPORT.parent / "2026-10-04-schema-summary-quality"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest_path = OLD / "corpus/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    baseline = json.loads((BASE / "results/natural-refined-index.json").read_text(encoding="utf-8"))
    samples = []
    for sample in manifest["samples"]:
        path = OLD / "corpus" / sample["file"]
        assert digest(path) == sample["sha256"]
        samples.append({key: sample[key] for key in (
            "id", "title", "creator", "page", "caption", "attribution", "license",
            "license_url", "file", "sha256", "expectations", "forbidden_inventions",
            "semantic_duplicate_groups", "content_limitations")})
    baseline_files = []
    for row in baseline["sample_results"]:
        assert digest(BASE / "results" / row["file"]) == row["sha256"]
        baseline_files.append(row)
    rubric = {
        "version": 1, "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_before_any_new_output": True, "new_provider_calls_at_freeze": 0,
        "manifest_sha256": digest(manifest_path), "samples": samples,
        "baseline": {"commit": "be2bdd5", "phase": "natural-refined",
            "directory": "../2026-10-04-schema-summary-quality/results",
            "delivery_profile_sha256": digest(BASE / "results/delivery-profile.json"),
            "review_sha256": digest(BASE / "results/natural-refined-review.json"),
            "sample_results": baseline_files, "fully_retained": 12,
            "partially_retained": 2, "missing": 0, "long_catch_all_chars": 365},
        "coverage": "Unchanged 14 original compound essential facts across final summary/key_points. Each clause required for retained; incomplete is partial. Optional detail omission is not coverage failure. No keyword grading.",
        "precision": [
            "Daily-grading belief/effort assertion attributed to instructor, not universal guarantee.",
            "Usually after class stays usually, not always/every class.",
            "Engrade stores comments/private account access AND entering grades; all needed for en3 full.",
            "Cultural response illustration remains lecturer/course illustration, not universal Chinese rule.",
            "Object types constrain available operations; scalar/non-scalar and expression values alone cannot fully retain long5.",
            "First-three operator result-type rule scope limited to +,-,*; / exception distinct; avoid generalization to all arithmetic.",
            "Radius/previously computed area concrete example stays specific; no universal rule about arbitrary dependent objects.",
            "Program consequences include unintended result, crash, nontermination; tail unchanged-area consequence must survive.",
            "Included numerical quantities and examples/tolerances exact and scoped; optional absence not failure."],
        "organization": {"max_points": 7, "min_points": 1, "point_chars_limit": 240,
            "criterion": "Distinct concise thematic points without losing essential conditions or consequences; unrelated last-point packing fails even below 240.",
            "duplicates": "Same proposition without new relevant condition/consequence is duplicate; distinct implications sharing a theme are not."},
        "trace": {"quote_lexical_check": "Whitespace-only normalization mapped to caller-cleaned input spans/hash, not original VTT timestamps. Every extracted and audit-added fact independently rechecked offline.",
            "semantic_check": "Valid quote, known ID and model checks=true do not prove entailment, factual precision, complete coverage or independent human review. Inspect claims and source independently.",
            "audit": "Check repairs/new facts must be caller-validated; all stages, including failures, count against 24 durable POST ceiling."},
        "limitations": "Three samples/two MIT courses; one inference per candidate; agent review, no independent external human raters, exhaustive truth guarantee, model training or statistical stability claim.",
        "licensing": "MIT OCW original source, fact excerpts and derived summaries/review CC BY-NC-SA 4.0. Noncommercial local inference evaluation; attribution and ShareAlike retained; product/scripts not relicensed. Original creator/page/caption supplied per sample."}
    REPORT.mkdir(parents=True, exist_ok=True)
    path = REPORT / "rubric.json"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(rubric, stream, ensure_ascii=False, indent=2)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps({"rubric_sha256": digest(path), "essential_facts": sum(
        row["priority"] == "essential" for sample in samples for row in sample["expectations"]),
        "provider_calls": 0}))


if __name__ == "__main__":
    main()
