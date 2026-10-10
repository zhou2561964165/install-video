"""Reuse the owned zero-paid API fixture without rerunning prior API cases."""
import importlib.util
from pathlib import Path

root = Path(__file__).resolve().parents[4]
script = root / "docs/acceptance-reports/2026-10-09-online-formal-flow/scripts/formal_http_flow.py"
spec = importlib.util.spec_from_file_location("owned_zero_paid_ui_fixture", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if __name__ == "__main__":
    import json
    print(json.dumps(module.run_zero_paid(browser_hold=True, browser_only=True)))
