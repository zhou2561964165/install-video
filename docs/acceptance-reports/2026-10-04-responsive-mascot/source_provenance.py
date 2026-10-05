"""Offline source provenance. Historical variants are explicitly reconstructed, not run-time captures."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FILES = ["App.jsx", "components/EntryScene.jsx", "components/ui/ExpressionMenu.jsx", "pixi/mascot.js", "pixi/mascotConfig.js", "pixi/stage.js", "styles/global.css"]
FOCUS = """  html {
    scroll-padding-top: var(--space-safe-header);
    scroll-padding-bottom: var(--space-safe-footer);
  }
  .ui :is(button, input, select, textarea, a) {
    scroll-margin-top: var(--space-safe-header);
    scroll-margin-bottom: var(--space-safe-footer);
  }
"""
STAGE = """  // PIXI 初始化会写 inline touchAction:none；在此按配置恢复原生纵向滚动。
  app.view.style.touchAction = PLACEMENT.touchAction;
  // TouchEvent 被 PIXI 归一化后默认 preventDefault；关闭它让允许的手势交给浏览器。
  app.renderer.plugins.interaction.autoPreventDefault = PLACEMENT.autoPreventDefault;
"""

def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Source changed since frozen provenance; expected one exact edit anchor")
    return text.replace(old, new, 1)

def hashes(sources):
    return {name: hashlib.sha256(source).hexdigest() for name, source in sources.items()}

def historical(current, *, focus, cancel, native):
    text = {name: raw.decode("utf-8") for name, raw in current.items()}
    if not focus:
        text["styles/global.css"] = once(text["styles/global.css"], FOCUS, "")
    if not cancel:
        text["pixi/mascot.js"] = once(text["pixi/mascot.js"], "    function onCancel() { endDrag(false); }\n", "")
        text["pixi/mascot.js"] = once(text["pixi/mascot.js"], "removeEventListener('pointercancel', onCancel)", "removeEventListener('pointercancel', onUp)")
        text["pixi/mascot.js"] = once(text["pixi/mascot.js"], "addEventListener('pointercancel', onCancel)", "addEventListener('pointercancel', onUp)")
    if not native:
        text["pixi/stage.js"] = once(text["pixi/stage.js"], "import { PLACEMENT } from './mascotConfig.js';\n", "")
        text["pixi/stage.js"] = once(text["pixi/stage.js"], STAGE, "")
        text["pixi/mascotConfig.js"] = once(text["pixi/mascotConfig.js"], ", touchAction: 'pan-y pinch-zoom', autoPreventDefault: false", "")
        text["styles/global.css"] = once(text["styles/global.css"], "  .mascot-menu-trigger--compact { display: block; }\n", "  .mascot-menu-trigger--compact { display: block; }\n  .stage canvas { touch-action: pan-y; }\n")
    return {name: source.encode("utf-8") for name, source in text.items()}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--final-results", type=Path, required=True)
    args = parser.parse_args()
    current = {name: (ROOT / "frontend/src" / name).read_bytes() for name in FILES}
    final = json.loads(args.final_results.read_text(encoding="utf-8"))
    if final.get("sourceSha256") != hashes(current):
        raise ValueError("Current source bytes do not match the final run's directly captured SHA256")
    phases = {
        "main-matrix": {"focus": False, "cancel": False, "native": False},
        "native-focus-before": {"focus": False, "cancel": False, "native": False},
        "native-focus-after": {"focus": True, "cancel": False, "native": False},
        "gesture-cancel-before": {"focus": True, "cancel": False, "native": False},
        "gesture-cancel-after-before-native": {"focus": True, "cancel": True, "native": False},
    }
    payload = {"historical_method": "Retrospective exact inverse of unique source edits recorded in this session; not hashes captured during old browser runs", "reconstruction_limit": "Historical JSON was not source-instrumented; these hashes identify reconstructed source variants, not independent proof of which bytes executed", "final_method": "Read current bytes and compare to SHA256 captured at final browser run startup", "final_sha256": hashes(current), "reconstructed_sha256": {phase: hashes(historical(current, **config)) for phase, config in phases.items()}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
