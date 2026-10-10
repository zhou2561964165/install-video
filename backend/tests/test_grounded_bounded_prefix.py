"""Regression coverage for sparse trailing slots in grounded model codecs."""

import json
from pathlib import Path
import re

from app.services import summary_facts as codec


ROOT = Path(__file__).resolve().parents[2]


def one_fact():
    source = codec.SourcePart("C1", "Noor introduces the release policy.\nRelease requires a clean audit.")
    facts = codec.parse_facts({"facts": [{
        "topic": "Release",
        "claim": "Release requires a clean audit.",
        "evidence": [2],
        "attribution": "Noor",
        "importance": "core",
    }]}, source, codec.FactLimits(), "F")
    return facts


def sparse_composition():
    return {
        "summary": [{"text": "Release requires a clean audit.", "fact_ids": ["F1"]}],
        "point_1": {"topic": "Release", "text": "Release requires a clean audit.", "fact_ids": ["F1"]},
        "theme_plan": {"theme_1": {
            "topic": "Release",
            "principle": "Release requires a clean audit.",
            "conditions": [],
            "consequences": [],
            "fact_ids": ["F1"],
        }},
    }


def test_captured_organization_contracts_six_fact_response_is_accepted():
    report = ROOT / "docs" / "acceptance-reports" / "2026-10-07-grounded-summary-contracts" / "results"
    response = json.loads((report / "responses" / "01.json").read_text(encoding="utf-8"))
    request = json.loads((report / "payloads" / "01.json").read_text(encoding="utf-8"))
    source_request = json.loads(request["messages"][1]["content"])["source"]
    source_text = "\n".join(re.sub(r"^\[\d+\] ", "", line)
                            for line in source_request["text"].splitlines())

    assert response["phase"] == "organization-contracts"
    assert response["stage"] == "extract"
    facts = codec.parse_extraction(
        response["content"], codec.SourcePart(source_request["id"], source_text),
        codec.FactLimits(), "C2_F",
    )

    assert tuple(fact.id for fact in facts) == tuple(f"C2_F{i}" for i in range(1, 7))
    assert facts[-1].claim.startswith("当学生真的有问题、听不懂要用英文问时")


def test_planned_composition_accepts_sparse_point_and_theme_prefixes():
    payload = sparse_composition()
    payload["point_2"] = None
    payload["theme_plan"]["theme_2"] = None

    parsed = codec.parse_planned_composition(payload, one_fact(), codec.FactLimits())

    assert parsed.candidate.key_points[0].id == "P1"
    assert tuple(theme.id for theme in parsed.themes) == ("T1",)


def test_planned_composition_accepts_raw_json_with_omitted_unused_tails():
    payload = sparse_composition()

    parsed = codec.parse_planned_composition(json.dumps(payload), one_fact(), codec.FactLimits())

    assert parsed.candidate.public_summary == "Release requires a clean audit."
    assert parsed.candidate.public_key_points == ("Release requires a clean audit.",)
    assert parsed.themes[0].fact_ids == ("F1",)
