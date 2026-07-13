"""One-time setup: log into your sites in FRIDAY's dedicated browser profile.

Why this exists (Chrome 127+/136+ reality):
  * Chrome ignores --remote-debugging-port on your default profile dir, so FRIDAY
    cannot attach to your daily-driver Chrome.
  * App-Bound Encryption means cookies copied from your live profile won't decrypt
    elsewhere (a clone lands logged-out).

The reliable answer: FRIDAY drives a PERSISTENT dedicated Chrome profile. You log
into your sites here ONCE; those logins persist on disk and every future FRIDAY
run reuses them automatically. Your normal Chrome is never touched or locked.

Usage (from repo root, your normal Chrome can stay open):
    python scripts/friday_browser_login.py

A Chrome window opens on FRIDAY's profile. Sign into the sites you want FRIDAY to
operate (Gmail, Instagram, etc.), then just leave it — you're done. Re-run this
anytime you need to refresh a login.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001
    pass

import os

from friday.actions.chrome_launcher import ensure_chrome_debug, cdp_reachable, _debug_profile_dir


def main() -> int:
    port = int(os.environ.get("CHROME_REMOTE_DEBUG_PORT", "9222"))
    profile_dir = _debug_profile_dir()

    print("=" * 64)
    print("  FRIDAY browser — one-time login setup")
    print("=" * 64)
    print(f"Dedicated profile dir : {profile_dir}")
    print(f"Debug port            : {port}")

    if cdp_reachable(port):
        print(f"\n[OK] A FRIDAY Chrome is already running on port {port}.")
        print("     Use that window to sign into your sites, then leave it open.")
        return 0

    print("\nOpening FRIDAY's Chrome profile ...")
    result = ensure_chrome_debug(port=port, force_dedicated=True)
    print(f"  chrome_path   : {result.chrome_path or '(not found)'}")
    print(f"  user_data_dir : {result.user_data_dir or '(default)'}")
    print(f"  launched      : {result.launched}")

    if not result.ok:
        print(f"\n[FAIL] {result.error}")
        return 1

    print("\n[OK] FRIDAY's Chrome is open with the debug port.")
    print("     1. Sign into the sites you want FRIDAY to operate (Gmail, Instagram, ...).")
    print("     2. Leave the window open (or just close it — the logins are saved).")
    print("     3. That's it. Every future FRIDAY run reuses these logins automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
