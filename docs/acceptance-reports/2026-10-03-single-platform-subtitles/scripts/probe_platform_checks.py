"""Probe the real app subtitle service on one URL per sampled IA video."""

from __future__ import annotations

import json
import socket
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace

REPORT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = REPORT_DIR.parents[2]
socket.setdefaulttimeout(30)

VIDEOS = [
    {"identifier": "lca2019-Awesome_Monitoring_Infrastructure_Using_the_Elastic_Stack", "language": "eng"},
    {"identifier": "youtube-6k-kbg3_Drc", "language": "en"},
    {"identifier": "mnn_23214_387", "language": None},
]


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    config = types.ModuleType("app.config")
    config.settings = SimpleNamespace(ffmpeg_path="ffmpeg", subtitle_max_bytes=32 * 1024 * 1024)
    sys.modules["app.config"] = config
    from app.services import subtitle_service, ytdlp_service

    checks = []
    for video in VIDEOS:
        identifier = video["identifier"]
        url = f"https://archive.org/details/{identifier}"
        observed = []
        original = ytdlp_service.extract_subtitle_tracks

        def observe(source_url: str) -> dict:
            payload = original(source_url)
            observed.append({
                "returned_track_count": len(payload.get("tracks", [])),
                "languages": [track.get("language") for track in payload.get("tracks", [])],
                "formats": sorted({fmt.get("ext") for track in payload.get("tracks", []) for fmt in track.get("formats", [])}),
                "title": payload.get("title"),
            })
            return payload

        ytdlp_service.extract_subtitle_tracks = observe
        started = time.perf_counter()
        try:
            document = subtitle_service.fetch_subtitle_document(url, language=video["language"])
            status = "pass"
            error_type = None
            text_characters = len(document.text)
        except Exception as exc:
            status = "fail"
            error_type = getattr(exc, "error_type", type(exc).__name__)
            text_characters = None
        finally:
            ytdlp_service.extract_subtitle_tracks = original

        checks.append({
            "source_id": identifier,
            "source_url": url,
            "language_requested": video["language"],
            "status": status,
            "error_type": error_type,
            "extractor_observation": observed[0] if observed else None,
            "text_characters": text_characters,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "caption_http_attempted_by_application": bool(observed and observed[0]["returned_track_count"] > 0),
        })

    target = REPORT_DIR / "platform-checks.json"
    target.write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
