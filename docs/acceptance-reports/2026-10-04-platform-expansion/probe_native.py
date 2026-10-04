"""Public native subtitle probes with no caption text or signed URL retention.

Engineering: UI skills and three-layer tokens; skills before plans; configurable
narrow interfaces; yt-dlp only via ytdlp_service.py; visual scene read-only.
Run with repository Python and a temporary shell HTTPS_PROXY if required.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(DIRECTORY.parents[2] / "backend"))
from app.config import settings
from app.services import subtitle_sources, subtitle_service


def main():
    settings.subtitle_timeout_seconds = 12
    settings.network_retries = 0
    samples = [
        ("bilibili-native-captions", "https://www.bilibili.com/video/BV12N4y1M7rh", "access probe only; no transcript retained; no LLM", True),
        ("bilibili-second-video", "https://www.bilibili.com/video/BV1jL41167ZG", "access metadata only; no transcript retained", False),
        ("archive-long", "https://archive.org/details/lca2019-Awesome_Monitoring_Infrastructure_Using_the_Elastic_Stack", "CC BY 4.0; prior manifest ../2026-10-03-single-platform-subtitles/manifest.json", False),
    ]
    results = []
    for sample, url, permission, fetch_body in samples:
        row = {"id": sample, "url": url, "utc": datetime.now(timezone.utc).isoformat(), "permission": permission}
        started = time.monotonic()
        try:
            payload = subtitle_sources.resolve_public_subtitles(url)
            row["tracks"] = [{"language": t["language"], "is_auto": t["is_auto"], "source_hosts": [urlsplit(f["url"]).hostname for f in t["formats"]]} for t in payload["tracks"]]
            row["outcome"] = "tracks_received" if payload["tracks"] else "no_public_tracks"
            if fetch_body and payload["tracks"]:
                # Use the production caption document path with already-resolved metadata,
                # avoiding redundant public requests and expensive fallback on this probe.
                with httpx.Client(timeout=12) as client:
                    document = subtitle_service._document_from_tracks(payload, None, client=client)
                row.update(outcome="caption_text_received", language=document.language, is_auto=document.is_auto,
                           chars=len(document.text), lines=len(document.text.splitlines()), sha256=hashlib.sha256(document.text.encode()).hexdigest())
        except (httpx.HTTPError, ValueError, subtitle_service.SubtitleServiceError) as exc:
            # HTTP errors can contain expiring auth_key URLs; retain class/status only.
            row["outcome"] = "native_access_failure"
            row["error_type"] = getattr(exc, "error_type", type(exc).__name__)
            if isinstance(exc, httpx.HTTPStatusError):
                row["http_status"] = exc.response.status_code
        row["elapsed_seconds"] = round(time.monotonic() - started, 3)
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    with httpx.Client(timeout=12) as client:
        row = {"id": "youtube-access", "url": "https://www.youtube.com/watch?v=hVimVzgtD6w", "utc": datetime.now(timezone.utc).isoformat(), "permission": "HTTP access probe only; no transcript retained"}
        try:
            response = client.get(row["url"])
            row.update(http_status=response.status_code, outcome="page_access_only_not_caption_proof")
        except httpx.HTTPError as exc:
            row.update(outcome="network_failure", error_type=type(exc).__name__)
        results.append(row)
        print(json.dumps(row), flush=True)
    (DIRECTORY / "native-probes.json").write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
