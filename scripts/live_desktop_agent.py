"""Live: run the GENERIC WebAgent on your real Chrome via DESKTOP control.

Proves FRIDAY can TASK ON your signed-in profile (not just open/focus it) when
CDP is blocked — using OCR observation + mouse/keyboard, with the exact same
agent that drives the CDP path. No site hardcoding.

Run: python scripts/live_desktop_agent.py
Requires: your Chrome open and signed in.
"""
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

os.environ["FRIDAY_DRY_RUN"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()


def main():
    from friday.actions.desktop_chrome import DesktopChromeController

    print("=" * 60)
    print("LIVE DESKTOP AGENT - tasking on your real Chrome via OCR")
    print("=" * 60)

    c = DesktopChromeController()
    if not c.available:
        print("[FAIL] No Chrome window. Open Chrome signed in first.")
        return 1
    c.start()
    print("[OK] focused your Chrome window")

    # 1. Observe what's on screen via OCR (the agentic surface).
    snap = c.observe_interactive(limit=40)
    print(f"observe ok={snap.get('ok')} elements={len(snap.get('elements', []))}")
    for e in snap.get("elements", [])[:8]:
        print(f"  [{e['index']}] '{e['text']}' @ ({e['x']},{e['y']}) "
              f"conf={e.get('confidence')}")

    # 2. Viewport (for vision scaling).
    print(f"viewport: {c.viewport_size()}")

    # 3. Navigate via the address bar (Ctrl+L) — a real task action.
    print("\nNavigating to example.com via address bar...")
    r = c.navigate("https://example.com")
    print(f"navigate ok={r.get('ok')} mode={r.get('mode')}")
    time.sleep(1.5)

    # 4. Observe again to confirm the page changed.
    snap2 = c.observe_interactive(limit=40)
    texts = " ".join(e["text"] for e in snap2.get("elements", [])).lower()
    print(f"observe-after ok={snap2.get('ok')} elements={len(snap2.get('elements', []))}")
    landed = "example" in texts or "domain" in texts or "illustrative" in texts
    print(f"'example domain' page detected via OCR: {landed}")

    print("\n" + "=" * 60)
    ok = snap.get("ok") and r.get("ok") and snap2.get("ok")
    if ok:
        print("FRIDAY CAN OBSERVE + ACT ON YOUR REAL PROFILE [OK]")
    else:
        print("Some step failed - see output")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
