"""Freeze source-first manual facts; never reads model outputs or calls a model."""
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent / "corpus"
FACTS = {
    "zh-short": [
        ("zh1", "essential", "MIT中文课从第二天开始全中文教学；第一天讲准备方法、大纲及期望。", [(1, 4)]),
        ("zh2", "essential", "维持全中文课堂有两个关键：学生听懂固定课堂用语，课前准备与课堂练习任务一致。", [(5, 13)]),
        ("zh3", "essential", "课堂用语不能随意换说法；请你再说一遍与请你再说一次对初学者不同。", [(14, 16)]),
        ("zh4", "essential", "前45分钟用中文；英文问题可在最后5分钟、下课后或邮件中提出。", [(17, 21)]),
    ],
    "en-medium": [
        ("en1", "essential", "The instructor adopts daily grading: evaluate each class performance; persistent consistent effort is expected to yield good Chinese skills.", [(7, 20)]),
        ("en2", "essential", "Written after-class feedback covers language and cultural behavior to show students what to improve next time.", [(21, 29)]),
        ("en3", "essential", "Engrade allows both grades and private comments; each student reads feedback through their own account.", [(30, 40)]),
        ("en4", "essential", "Feedback depends on performance: pronunciation or culturally appropriate compliment responses; the instructor contrasts American thanks with Chinese humility, and grounds feedback in course/textbook material.", [(41, 53), (56, 80), (81, 95)]),
    ],
    "en-long": [
        ("long1", "essential", "Computers calculate and remember results; the programmer must explicitly specify the operations.", [(275, 292), (319, 336)]),
        ("long2", "essential", "Declarative knowledge states facts; imperative knowledge gives a recipe/sequence of steps. An algorithm needs steps, control flow, and a stopping condition.", [(340, 344), (373, 382), (554, 588)]),
        ("long3", "essential", "Stored-program computers store changeable instruction sequences and execute them; tests/control flow can skip or repeat instructions.", [(628, 642), (735, 754)]),
        ("long4", "essential", "Programming expressions have syntax, static semantics, and intended meaning; a program can execute exactly as written yet produce an unintended result, crash, or fail to stop.", [(854, 889), (920, 943), (991, 1022)]),
        ("long5", "essential", "Python manipulates typed objects, including scalar and structured non-scalar objects; object types constrain available operations and expressions evaluate to values.", [(1054, 1066), (1090, 1114), (1229, 1241)]),
        ("long6", "essential", "Assignment binds a name to a value; rebinding radius alone does not recalculate the already computed area. This is the final example before next lecture's control flow.", [(1307, 1336), (1460, 1472), (1493, 1515)]),
        ("long7", "detail_if_present", "The square-root example uses x=16 and initial guess g=3; average g with x/g repeatedly and stop when g*g is sufficiently close to x; .01/.001 are possible tolerances, not a mandatory fixed tolerance.", [(507, 547), (578, 584)]),
        ("long8", "detail_if_present", "Converting a float to int truncates rather than rounds; float(3) becomes 3.0.", [(1149, 1167)]),
        ("long9", "detail_if_present", "True and False are the two Boolean values; NoneType has the single value None.", [(1122, 1134)]),
        ("long10", "detail_if_present", "The lecture says Python / division produces a float regardless of operand types; +,-,* preserve int for int operands and yield float if an operand is float.", [(1242, 1265)]),
        ("long11", "detail_if_present", "In the final rebinding example radius starts at 2.2 and radius=radius+1 yields 3.2 while area stays unchanged until explicitly recomputed.", [(1437, 1442), (1460, 1472), (1493, 1507)]),
    ],
}
FORBIDDEN = {
    "zh-short": ["全英文或中英各一半教学", "从第一天就全中文", "永远禁止英文提问", "45分钟中文加15分钟英文", "教授改变课堂用语是鼓励而非约束"],
    "en-medium": ["Automatically generated grading or comments", "Public class-wide disclosure of private student comments", "Fixed numeric scoring weights or named grades absent from the captions", "The cultural example is a universal rule applying to every Chinese or American person", "Engrade is a current recommendation verified in 2026"],
    "en-long": ["Rebinding radius automatically updates the previously calculated area", "int conversion rounds to nearest integer", "Square-root iteration always uses a mandatory .001 tolerance", "The course is primarily neural-network training", "An invented course date, grade weight, test score, or implementation outcome", "Treating incidental raffle numbers as a final settled range when the spoken range changes (266,271,272)"],
}
DUPLICATES = {
    "zh-short": [{"id": "zh-preparation", "meaning": "课前准备与课堂任务一致", "facts": ["zh2"], "rule": "Do not split synonyms of preparation/task consistency into multiple points."}],
    "en-medium": [{"id": "en-feedback", "meaning": "Daily individualized feedback", "facts": ["en1", "en2", "en3"], "rule": "Daily assessment, feedback contents and private delivery are distinct details; repetition of generic individualized improvement without new detail is duplication."}, {"id": "en-culture", "meaning": "Compliment humility example", "facts": ["en4"], "rule": "Do not spend separate points repeating the same compliment/humility example."}],
    "en-long": [{"id": "long-explicit", "meaning": "Computer only executes instructions", "facts": ["long1", "long4", "long6"], "rule": "Different implications (error semantics, no automatic recomputation) are distinct; repeated generic obedience claim with no new implication is duplicate."}, {"id": "long-assignment", "meaning": "Name binding and rebinding", "facts": ["long6", "long11"], "rule": "A worked numeric illustration can support one concept point; separate points restating the same rebinding consequence are duplicate."}],
}


def main():
    acquisition = json.loads((ROOT / "acquisition.json").read_text(encoding="utf-8"))
    for sample in acquisition["samples"]:
        text = (ROOT / sample["file"]).read_text(encoding="utf-8")
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == sample["sha256"]
        lines = text.splitlines(keepends=True)
        facts = []
        for fact_id, priority, claim, ranges in FACTS[sample["id"]]:
            evidence = []
            for start, end in ranges:
                offset = sum(len(x) for x in lines[:start - 1])
                excerpt = "".join(lines[start - 1:end]).rstrip("\n")
                assert text[offset:offset + len(excerpt)] == excerpt
                evidence.append({"line_start": start, "line_end": end, "char_start": offset,
                                 "char_end": offset + len(excerpt), "excerpt": excerpt})
            facts.append({"id": fact_id, "priority": priority, "claim": claim, "evidence": evidence,
                          "scoring": "essential: semantic retained/partial/missing; detail_if_present: correctness only, omission is not a coverage failure"})
        sample["expectations"] = facts
        sample["forbidden_inventions"] = FORBIDDEN[sample["id"]]
        sample["semantic_duplicate_groups"] = DUPLICATES[sample["id"]]
        sample["length_category"] = {"zh-short": "short", "en-medium": "medium", "en-long": "long"}[sample["id"]]
        sample["content_limitations"] = ("Original speech contains fillers and repetition; no manual wording correction." if sample["id"] != "en-long" else
                                        "Transcript contains self-corrections (raffle ranges, syntactically correct/incorrect), deictic references to slides and pedagogical simplifications. Expectations evaluate source fidelity, not independent correctness of all lecture claims.")
    manifest = {"schema_version": 1, "frozen_utc": datetime.now(timezone.utc).isoformat(),
                "curation_independent_of_model_outputs": True,
                "curator_has_read_model_outputs": False,
                "intended_use": "Noncommercial local inference evaluation; no training; MIT does not endorse this software or model outputs.",
                "sample_design": "Three separate authentic official-caption samples: native Chinese short, English medium, English long. No assembled, translated, repeated, or artificially lengthened sample.",
                "rubric": {"coverage": "Assess essential facts semantically, allowing Chinese output for English source. Missing optional details do not fail coverage.",
                           "precision": "Verify every model claim against the source; do not equate keyword presence with correctness.",
                           "numbers_conditions": "If included, exact numbers and limiting conditions must agree; preserve the final assignment outcome.",
                           "tail": "Long6 is an essential near-tail example; assess unchanged-area consequence, not merely keyword radius.",
                           "duplication": "Count two points as duplicate only if they restate the same proposition without a distinct relevant fact.",
                           "limits": "Small manually curated sample, no universal performance/accuracy estimate and no exhaustive source fact check."},
                "samples": acquisition["samples"]}
    path = ROOT / "manifest.json"
    if path.exists():
        raise RuntimeError("expectations already frozen; do not overwrite after evaluation")
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(path))
    print(hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
