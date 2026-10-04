"""Acquire three authentic MIT OCW captions; no LLM calls or application secrets.

Engineering: UI skills/tokens, skills before plans, configurable narrow interfaces,
yt-dlp only through ytdlp_service, visual scene read-only. This evidence tool uses
official caption HTTP URLs directly, so does not need a yt-dlp extractor.
"""
from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
BASE = "https://ocw.mit.edu/"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"
POLICY_URL = "https://ocw.mit.edu/pages/privacy-and-terms-of-use/"
SOURCES = [
    {"id": "zh-short", "language": "zh-Hans", "title": "Creating an Immersive Classroom Environment (Chinese)",
     "creator": "Dr. Haohsiang Liao / Massachusetts Institute of Technology, MIT OpenCourseWare",
     "page": BASE + "courses/21g-101-chinese-i-regular-fall-2014/resources/mit21g_101f14_immersive_environment_chinese-2/",
     "caption": BASE + "courses/21g-101-chinese-i-regular-fall-2014/50e5414eeb1e526bbb94593453e9c84a_MIT21G_101F14_Immersive_Environment_Chinese.vtt"},
    {"id": "en-medium", "language": "en", "title": "Daily Grading System",
     "creator": "Dr. Haohsiang Liao / Massachusetts Institute of Technology, MIT OpenCourseWare",
     "page": BASE + "courses/21g-101-chinese-i-regular-fall-2014/resources/daily-grading-system/"},
    {"id": "en-long", "language": "en", "title": "Lecture 1: What is Computation?",
     "creator": "Dr. Ana Bell / Massachusetts Institute of Technology, MIT OpenCourseWare",
     "page": BASE + "courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/resources/lecture-1-what-is-computation/"},
]


class Tracks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tracks = []

    def handle_starttag(self, tag, attrs):
        if tag == "track":
            self.tracks.append(dict(attrs))


def clean_caption(raw: bytes) -> str:
    """Remove only WebVTT timing, IDs, markup, and adjacent exact repetitions."""
    result = []
    for block in re.split(r"\n\s*\n", raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")):
        lines = block.strip().splitlines()
        if not lines or lines[0].startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        timestamp = next((i for i, line in enumerate(lines) if " --> " in line), None)
        if timestamp is None:
            continue
        for line in lines[timestamp + 1:]:
            line = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", line))).strip()
            if line and (not result or result[-1] != line):
                result.append(line)
    if not result:
        raise ValueError("caption is empty")
    return "\n".join(result)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_once(path: Path, data: bytes):
    if path.exists():
        if path.read_bytes() != data:
            raise RuntimeError(f"immutable evidence differs: {path.name}")
    else:
        path.write_bytes(data)


def acquire(output: Path):
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise RuntimeError("output directory must be new or empty; frozen evidence will not be overwritten")
    output.mkdir(parents=True, exist_ok=True)
    metadata = []
    probe_rows = []
    # 3 caption groups + one policy request, no retries or authentication.
    with httpx.Client(timeout=15, follow_redirects=False,
                      headers={"User-Agent": "VideoIntelligenceNoncommercialAcceptance/1.0"}) as client:
        policy = client.get(POLICY_URL)
        policy.raise_for_status()
        if "CC BY-NC-SA 4.0" not in policy.text or "Permitted Use of AI Training" not in policy.text:
            raise RuntimeError("official policy changed; review before collecting captions")
        policy_evidence = {"url": POLICY_URL, "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                           "response_sha256": sha(policy.content), "status": policy.status_code,
                           "license": "CC BY-NC-SA 4.0", "license_url": LICENSE_URL,
                           "ai_section_heading": "Permitted Use of AI Training",
                           "interpretation": "Noncommercial evaluation only; attribution and ShareAlike retained. No model training occurs."}
        save_once(output / "license-evidence.json", json.dumps(policy_evidence, ensure_ascii=False, indent=2).encode("utf-8"))
        for source in SOURCES:
            row = {**source, "retrieved_utc": datetime.now(timezone.utc).isoformat()}
            page = client.get(source["page"])
            page.raise_for_status()
            if "creativecommons.org/licenses/by-nc-sa/4.0" not in page.text:
                raise RuntimeError("source page has no expected license footer")
            row["source_page_sha256"] = sha(page.content)
            caption_url = source.get("caption")
            if not caption_url:
                parser = Tracks()
                parser.feed(page.text)
                track = next(t for t in parser.tracks if t.get("srclang") == source["language"])
                caption_url = urljoin(source["page"], track["src"])
            caption = client.get(caption_url)
            caption.raise_for_status()
            if len(caption.content) > 2_000_000:
                raise RuntimeError("caption exceeds evidence byte limit")
            text = clean_caption(caption.content)
            raw_name, text_name = source["id"] + ".vtt", source["id"] + ".txt"
            save_once(output / raw_name, caption.content)
            save_once(output / text_name, text.encode("utf-8"))
            row.update({"caption": caption_url, "raw_path": raw_name, "file": text_name,
                        "raw_sha256": sha(caption.content), "sha256": sha(text.encode("utf-8")),
                        "cleaned_chars": len(text), "cleaned_lines": len(text.splitlines()),
                        "license": "CC BY-NC-SA 4.0", "license_url": LICENSE_URL,
                        "changes": "Removed only VTT headers, timestamps, cue IDs, markup, and adjacent exact duplicate lines; no added or corrected words.",
                        "source_is_natural_caption": True,
                        "attribution": source["creator"] + "; " + source["title"] + "; " + source["page"],
                        "expectations": [], "forbidden_inventions": [], "semantic_duplicate_groups": []})
            metadata.append(row)
            probe_rows.append({"id": source["id"], "page_status": page.status_code, "caption_status": caption.status_code,
                               "caption_url": caption_url, "cleaned_chars": len(text)})
            print(json.dumps(probe_rows[-1]), flush=True)
    save_once(output / "acquisition.json", json.dumps({"samples": metadata, "probes": probe_rows}, ensure_ascii=False, indent=2).encode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=CORPUS)
    args = parser.parse_args()
    acquire(args.output_dir)


if __name__ == "__main__":
    main()
