"""Bounded public metadata probes; never stores captions or cookies.

Engineering: UI skills and three-layer tokens; skills before plans; configurable
narrow interfaces; yt-dlp only via ytdlp_service.py; visual scene read-only.
"""
from __future__ import annotations

import json
import time
from urllib.parse import urlsplit
from datetime import datetime, timezone
from pathlib import Path

import httpx

DIRECTORY = Path(__file__).resolve().parent
COMMONS_TITLE = "File:Die_Temperaturkurve_der_Erde_(ZDF,_Terra_X)_720p_HD_50FPS.webm"


def main():
    results = []
    with httpx.Client(timeout=12, headers={"User-Agent": "VideoIntelligenceAcceptance/1.0 (public metadata probe)"}) as client:
        requests = [
            ("commons-climate", "https://commons.wikimedia.org/w/api.php", {"action": "query", "format": "json", "formatversion": "2", "prop": "videoinfo", "viprop": "timedtext", "titles": COMMONS_TITLE}),
            ("commons-film", "https://commons.wikimedia.org/w/api.php", {"action": "query", "format": "json", "formatversion": "2", "prop": "videoinfo", "viprop": "timedtext", "titles": "File:Elephants_Dream.ogv"}),
            ("bilibili-view", "https://api.bilibili.com/x/web-interface/view", {"bvid": "BV12N4y1M7rh"}),
            ("archive-short", "https://archive.org/metadata/youtube-6k-kbg3_Drc", {}),
        ]
        for sample, endpoint, params in requests:
            row = {"id": sample, "utc": datetime.now(timezone.utc).isoformat(), "endpoint": str(httpx.URL(endpoint, params=params)), "permission": "access metadata only; no transcript retained"}
            start = time.monotonic()
            try:
                response = client.get(endpoint, params=params)
                row["http_status"] = response.status_code
                response.raise_for_status()
                payload = response.json()
                if sample.startswith("commons"):
                    pages = payload.get("query", {}).get("pages", [])
                    row["pages"] = [{"title": p.get("title"), "missing": p.get("missing", False), "timedtext": [v.get("timedtext", []) for v in p.get("videoinfo", [])]} for p in pages]
                elif sample == "bilibili-view":
                    row["code"] = payload.get("code")
                    data = payload.get("data") or {}
                    row["cid"] = data.get("cid")
                    row["aid"] = data.get("aid")
                    if row["cid"] and row["aid"]:
                        player_params = {"aid": row["aid"], "oid": row["cid"], "type": 1}
                        player_url = "https://api.bilibili.com/x/v2/dm/view"
                        player = client.get(player_url, params=player_params)
                        row["caption_metadata_endpoint"] = str(httpx.URL(player_url, params=player_params))
                        row["caption_metadata_status"] = player.status_code
                        player.raise_for_status()
                        player_payload = player.json()
                        player_data = player_payload.get("data") or {}
                        row["caption_metadata_code"] = player_payload.get("code")
                        row["need_login_subtitle"] = player_data.get("need_login_subtitle")
                        row["track_count"] = len((player_data.get("subtitle") or {}).get("subtitles") or [])
                        row["tracks"] = [{"lan": s.get("lan"), "type": s.get("type"), "source_host": urlsplit(s.get("subtitle_url", "")).hostname} for s in (player_data.get("subtitle") or {}).get("subtitles") or []]
                else:
                    row["caption_names"] = [f.get("name") for f in payload.get("files", []) if str(f.get("name", "")).endswith((".srt", ".vtt", ".ttml", ".json3"))]
                row["outcome"] = "metadata_received"
            except (httpx.HTTPError, ValueError) as exc:
                row["outcome"] = "access_or_network_failure"
                row["error_type"] = type(exc).__name__
                row["error"] = str(exc)[:250]
            row["elapsed_seconds"] = round(time.monotonic() - start, 3)
            results.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    (DIRECTORY / "public-probes.json").write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
