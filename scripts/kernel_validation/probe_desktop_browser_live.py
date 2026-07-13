"""Diagnostic: does DesktopBrowserController actually operate a browser (no CDP)?

Isolates the controller from the planner/LLM: launch the target browser, navigate
to a known public page, then read the page via the fused perception (OCR). Prints
what was observed so we can tell a CONTROLLER problem (focus/OCR) from a
planner/evidence-flow problem. Drives real mouse/keyboard briefly.

Usage: python scripts/kernel_validation/probe_desktop_browser_live.py [browser]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
os.environ.pop("FRIDAY_DRY_RUN", None)

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from friday.actions.system import SystemActions
from friday.actions.desktop_browser import DesktopBrowserController


def main() -> int:
    browser = sys.argv[1] if len(sys.argv) > 1 else "chrome"
    url = "https://en.wikipedia.org/wiki/Automation"

    print(f"[1] launching {browser} (clean window) ...")
    if browser.lower() in ("chrome", "google chrome"):
        from friday.actions.chrome_launcher import ensure_chrome_debug
        r = ensure_chrome_debug(force_dedicated=True)
        print(f"    clean-window launch ok={getattr(r, 'ok', None)}")
    else:
        SystemActions().launch_app(browser)
    time.sleep(4.0)

    c = DesktopBrowserController()
    print(f"[2] controller.available={c.available}")
    if not c.available or not c.start():
        print("[FAIL] controller unavailable")
        return 1
    win = getattr(c, "_window", None)
    print(f"[3] captured window: {getattr(win, 'title', None)!r}")

    print(f"[4] navigate -> {url}")
    r = c.navigate(url)
    print(f"    navigate result: {r}")
    time.sleep(3.0)

    print("[5] observe_interactive ...")
    snap = c.observe_interactive(limit=20)
    els = snap.get("elements", [])
    print(f"    observe ok={snap.get('ok')} elements={len(els)} title={snap.get('title')!r}")
    for e in els[:6]:
        print(f"      [{e['index']}] {e['tag']}:{e['role']} '{e['text'][:40]}' @({e['x']},{e['y']})")

    print("[6] read_text ...")
    text = c.read_text(1200)
    print(f"    read {len(text)} chars")
    print(f"    snippet: {text[:300]!r}")
    saw = "automation" in text.lower()
    print(f"[7] page-relevant text detected (OCR): {saw}")

    c.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
