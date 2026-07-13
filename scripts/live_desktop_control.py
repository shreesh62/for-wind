"""Live desktop-control validation — operate the user's NORMAL open Chrome.

This is the universal fallback (ADR-030/037): no CDP, no cloning. It focuses
the visible Chrome window and operates it via keyboard + screen OCR — using the
user's REAL logged-in session exactly as-is. Works for Google-gated sites that
CDP can't touch.

SAFETY: this moves the real mouse/keyboard and operates YOUR open Chrome. Run
only when you're watching. It performs a benign, read-only navigation (opens a
new tab and goes to a URL via the omnibox, then reads the screen).

Prereq: your normal Chrome is OPEN and signed in. Run:
    python scripts/live_desktop_control.py
"""

import os, sys, time
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

os.environ["FRIDAY_DRY_RUN"] = "0"
from dotenv import load_dotenv
load_dotenv()


def main() -> int:
    from friday.actions.desktop_browser import DesktopBrowserController

    print("=" * 70)
    print("LIVE DESKTOP CONTROL - operate your active browser window (no CDP)")
    print("=" * 70)

    c = DesktopBrowserController()
    if not c.available:
        print("[FAIL] Desktop control unavailable (pyautogui missing).")
        return 1

    if not c.start():
        print("[FAIL] could not focus Chrome window")
        return 1
    print("focused Chrome window OK")

    # Benign, observable action: open a new tab to a public URL via the omnibox.
    url = "https://en.wikipedia.org/wiki/Automation"
    print(f"navigating (desktop omnibox) to: {url}")
    res = c.navigate(url)
    print(f"navigate ok: {res.get('ok')} | mode: {res.get('mode')}")
    time.sleep(2)

    # Read the screen via OCR to prove we can perceive the real window.
    text = c.read_text(800)
    print(f"\nscreen OCR captured {len(text)} chars")
    print("snippet:", repr(text[:200]))

    saw_automation = "automation" in text.lower()
    print(f"\npage-relevant text detected: {saw_automation}")

    print("\n" + "=" * 70)
    if res.get("ok"):
        print("RESULT: desktop control operated your real Chrome [OK]")
        print("        (keyboard navigation + screen OCR on your live session)")
    else:
        print("RESULT: desktop control could not complete - see output")
    print("=" * 70)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
