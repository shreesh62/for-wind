"""One-command launcher: start the user's real Chrome on the CDP debug port.

Usage (from repo root):
    python scripts/launch_chrome_debug.py

After this prints OK, FRIDAY can connect to the real (logged-in) Chrome via
BrowserController(require_real_chrome=True).

If Chrome is ALREADY open without the debug flag, close it fully first
(check the tray), then run this again.
"""

import sys

from friday.actions.chrome_launcher import ensure_chrome_debug, cdp_reachable
from friday.config.browser_config import resolve_browser_choice


def main() -> int:
    port = 9222
    print(f"Checking CDP on port {port} ...")
    if cdp_reachable(port):
        print(f"[OK] CDP already reachable on {port}. FRIDAY can use real Chrome.")
        return 0

    choice = resolve_browser_choice(use_dedicated_if_unset=True)
    print(f"Profile choice  : {choice.display_name} (source={choice.source})")
    if choice.source == "dedicated":
        print("  No profile configured — using FRIDAY's dedicated debug profile.")
        print("  To use your own profile: python scripts/select_chrome_profile.py")

    print("Launching Chrome with the debug port ...")
    result = ensure_chrome_debug(
        port=port,
        user_data_dir=choice.user_data_dir,
        profile_directory=choice.profile_directory,
    )

    print(f"  chrome_path   : {result.chrome_path or '(not found)'}")
    print(f"  user_data_dir : {result.user_data_dir or '(default)'}")
    print(f"  dedicated     : {result.used_dedicated_profile}")
    print(f"  already_running: {result.already_running}")
    print(f"  launched      : {result.launched}")

    if result.ok:
        print(f"[OK] CDP reachable on {port}. FRIDAY can now operate real Chrome.")
        if result.used_dedicated_profile and choice.source == "configured":
            print()
            print(f"NOTE: You chose the '{choice.display_name}' profile, but your main")
            print("      Chrome is already open, so Chrome locked that profile and")
            print("      FRIDAY used a dedicated profile instead (no logins yet).")
            print(f"      To use '{choice.display_name}' WITH your logins:")
            print("        1. Fully close Chrome (check the system tray).")
            print("        2. Run this script again.")
        return 0

    print(f"[FAIL] {result.error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
