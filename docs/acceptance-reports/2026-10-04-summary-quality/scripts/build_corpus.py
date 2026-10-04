"""Build owned synthetic source fixtures; no remote source or personal data.

Engineering: skills outrank plans; UI skills/tokens; configurable abilities;
narrow service boundaries and yt-dlp only through ytdlp_service.py.
"""
from pathlib import Path
import hashlib
import json


ROOT = Path(__file__).resolve().parents[1]


def main():
    corpus = ROOT / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    short = "The community library is closed on Monday for maintenance.\n" * 4
    medium = """This is a planning meeting about a water-sensor trial at Maple Farm. The team wants to detect dry soil earlier, but this is only a trial, not proof that yields will increase.
The approved trial budget is 2400 yuan. That is a spending ceiling, not money already spent. No supplier invoice has arrived and the discussion gives no final unit price.
There are 18 sensors in the plan. Twelve go in the east plot and six go in the west plot. These are the entire trial; the farm is not deploying sensors to all fields.
Mei is responsible for installation. Arun is responsible for weekly data review. Their duties are different: installing the equipment does not make Mei the reviewer.
The team initially suggested starting on June 10, but the final start date is June 17 because the east plot access path needs repair. The trial runs for four weeks.
On each Tuesday morning Arun will compare sensor readings with a manual soil check. The team will keep both readings so that disagreement can be investigated, rather than automatically trusting the sensor.
The alert threshold is a moisture reading below 22 percent. An alert means a staff member checks the soil; it does not automatically start irrigation.
If there are three consecutive days of missing readings, the trial pauses until the connection is fixed. A single missed reading does not meet this rule.
No fertilizer change is part of this experiment. The team wants to keep other farm work consistent so the readings can be interpreted. Weather and access problems will be recorded in the trial notebook.
Staff asked whether the sensors would save water. The meeting supplied no water-saving measurement, percentage, or guarantee. That question is left for the trial results.
Staff also asked which vendor won the order. No vendor was selected in this discussion. Procurement must stay within the approved ceiling after quotations are reviewed.
Only Arun's weekly review and the manual check can support a later decision. The plan requires a review at the end of the four weeks before any expansion. Expansion has not been approved.
For clarity, the 2400 yuan is the ceiling, the 18 sensors are divided twelve and six, and the start is June 17. The early June 10 suggestion was superseded.
The closing decision is to approve this limited trial with manual verification and a pause rule, without approving wider deployment or promising a water-saving result.
"""
    lines = [
        "The Cedar archive migration meeting approves a 48000 yuan ceiling and a six-week pilot, using exactly 1200 records. The pilot is not permission for a full migration.",
        "Lin owns the checksum audit; Noor owns rollback rehearsal. Staff initially discuss moving the full archive on August 12, but that is a proposal, not a final decision.",
    ]
    # Unique, low-priority narrative logs keep a >40k stress source from being
    # collapsed by exact-line de-duplication. They are data, not new decisions.
    for index in range(1, 220):
        lines.append(
            f"Workshop note {index}: staff inspect one demonstration folder, compare its descriptive labels, check that the test copy opens, and discuss how a reviewer can find its matching source. "
            "This is a rehearsal observation within the existing pilot; it changes no budget, owner, schedule, approval or release decision. The group retains the original while checking the copy."
        )
        if index == 109:
            lines.append("The audit finds exactly 17 checksum mismatches among the 1200 pilot records. The team has not measured production downtime or approved a wider release.")
    lines.extend([
        "At the close, the August 12 full-archive proposal is explicitly rejected. The full migration is postponed to September 9, conditional on a clean checksum audit and a successful rollback rehearsal.",
        "The final decision gives Noor authority to stop release if the rollback rehearsal fails. The approval is still for the pilot only; no completion or production reliability claim has been made.",
    ])
    # Select enough whole source lines for exactly three default-size sections.
    long = "\n".join(lines[:2] + lines[2:112] + lines[-2:])
    if not 40000 < len(long) < 60000:
        raise ValueError(f"long fixture must exercise three default chunks: {len(long)}")
    sources = [
        ("short", "Library closure notice", short, ["Library is closed on Monday for maintenance."], ["Reopening time", "Alternative venue"], "One independent fact; do not pad key points."),
        ("medium", "Maple Farm limited trial decision", medium, ["2400 yuan ceiling, not actual spend", "18 sensors: 12 east and 6 west", "Final June 17 start supersedes June 10", "Four-week trial", "Below 22 percent prompts manual check, not automatic irrigation", "Three consecutive missing-data days pauses trial", "No expansion approved"], ["Vendor selection", "Unit price", "Water-saving percentage"], "Check numbers, superseded proposal, responsibilities and absence claims."),
        ("long", "Cedar migration pilot meeting stress transcript", long, ["48000 yuan ceiling", "1200 records in a six-week pilot", "17 checksum mismatches", "August 12 proposal rejected; September 9 conditional date", "Clean checksum audit and successful rollback are release conditions", "Noor can stop release if rollback fails"], ["Production downtime measured", "Full migration completed", "Production reliability proved"], "Tail decisions must survive three section summaries and merge."),
    ]
    manifest = {"ownership": "Self-authored artificial evaluation fixtures; redistributable with project.", "samples": []}
    for sample_id, title, source, required, absent, note in sources:
        path = corpus / f"{sample_id}.txt"
        path.write_text(source, encoding="utf-8")
        manifest["samples"].append({"id": sample_id, "title": title, "file": path.name, "characters": len(source), "sha256": hashlib.sha256(source.encode()).hexdigest(), "required_facts": required, "absent_facts": absent, "review_note": note})
    (corpus / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({s["id"]: s["characters"] for s in manifest["samples"]}))


if __name__ == "__main__":
    main()
