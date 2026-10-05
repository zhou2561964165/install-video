"""Read-only GET connectivity probe. No keys, headers, response bodies persisted.

Engineering: skills first, configurable interfaces, scene read-only, yt-dlp boundary.
These GET attempts are independent of the durable paid POST ledger.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import httpx

REPORT = Path(__file__).resolve().parents[1]
TARGETS = {"provider_root": "https://api.deepseek.com/", "provider_models": "https://api.deepseek.com/models"}


def main():
    rows = []
    for label, url in TARGETS.items():
        command = "$target=[Uri]'" + url + "'; $proxy=[System.Net.WebRequest]::DefaultWebProxy.GetProxy($target); if ($proxy.AbsoluteUri -ne $target.AbsoluteUri) { $proxy.AbsoluteUri }"
        proxy = subprocess.check_output(["powershell", "-NoProfile", "-Command", command], text=True).strip() or None
        row = {"target": label, "method": "GET", "system_proxy_used": bool(proxy), "credentials_sent": False,
               "started_utc": datetime.now(timezone.utc).isoformat()}
        try:
            with httpx.Client(proxy=proxy, timeout=15, trust_env=False, follow_redirects=False) as client:
                response = client.get(url)
            row.update(http_status=response.status_code, tls_http_reached=True)
        except httpx.HTTPError as exc:
            row.update(error_type=type(exc).__name__, tls_http_reached=False)
        rows.append(row)
    result = {"read_only_gets": True, "post_count": 0, "probes": rows}
    target = REPORT / "results/network-get-probe.json"
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
