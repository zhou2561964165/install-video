"""Offline read-only media inspection; writes new JSON, never changes source media."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", type=Path)
    parser.add_argument("--output-file", required=True, type=Path, help="New JSON path; overwrite is refused")
    parser.add_argument("--check-output-file", action="store_true", help="Validate paths without running ffprobe or writing files")
    args = parser.parse_args()
    source, destination = args.input_file.resolve(), args.output_file.resolve()
    if not source.is_file():
        parser.error("input_file must be an existing regular file")
    if destination.exists():
        parser.error("--output-file already exists; overwrite is refused")
    if args.check_output_file:
        print(json.dumps({"input_file": str(source), "output_file": str(destination), "valid": True, "offline": True}))
        return
    metadata = json.loads(subprocess.check_output(["ffprobe", "-v", "quiet", "-show_streams", "-show_format", "-of", "json", str(source)]))
    result = {"utc": datetime.now(timezone.utc).isoformat(), "scope": "offline inspection of existing saved file, no application or network requests", "bytes": source.stat().st_size, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "container": metadata["format"]["format_name"], "duration": metadata["format"]["duration"], "streams": [{"type": s["codec_type"], "codec": s["codec_name"], "width": s.get("width"), "height": s.get("height")} for s in metadata["streams"]]}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as target:
        json.dump(result, target, indent=2)


if __name__ == "__main__":
    main()
