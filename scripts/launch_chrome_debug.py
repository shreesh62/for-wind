"""One-command launcher: bring up FRIDAY's dedicated Chrome on the CDP debug port.

Usage (from repo root):
    python scripts/launch_chrome_debug.py

After this prints OK, FRIDAY can connect via BrowserController(require_real_chrome=True).

This uses FRIDAY's PERSISTENT dedicated profile (not your daily-driver Chrome):
Chrome 136+ blocks remote debugging on the default profile dir and Chrome 127+
App-Bound Encryption prevents cloning your existing logins. Sign into your sites
once in the dedicated profile via `python scripts/friday_browser_login.py`; those
logins then persist for every run. Your normal Chrome is never touched.
"""

import sys

from friday.actions.chrome_launcher import ensure_chrome_debug, cdp_reachable


def main() -> int:
    port = 9222
    print(f"Checking CDP on port {port} ...")
    if cdp_reachable(port):
        print(f"[OK] CDP already reachable on {port}. FRIDAY can use real Chrome.")
        return 0

    # Reliable path (Chrome 127+/136+): drive FRIDAY's PERSISTENT dedicated
    # profile. CDP is blocked on the default User-Data dir and App-Bound
    # Encryption stops cookie cloning, so the user's live profile can't be
    # attached to. The dedicated profile always attaches and keeps its own
    # logins (sign in once via scripts/friday_browser_login.py).
    print("Launching FRIDAY's dedicated Chrome profile with the debug port ...")
    result = ensure_chrome_debug(port=port, force_dedicated=True)

    print(f"  chrome_path   : {result.chrome_path or '(not found)'}")
    print(f"  user_data_dir : {result.user_data_dir or '(default)'}")
    print(f"  dedicated     : {result.used_dedicated_profile}")
    print(f"  already_running: {result.already_running}")
    print(f"  launched      : {result.launched}")

    if result.ok:
        print(f"[OK] CDP reachable on {port}. FRIDAY can now operate its Chrome.")
        print("     First time? Sign into your sites once:")
        print("       python scripts/friday_browser_login.py")
        return 0

    print(f"[FAIL] {result.error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
