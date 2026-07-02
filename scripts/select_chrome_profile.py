"""Interactive Chrome profile selection — works for ANY user, any device.

Lists the Chrome profiles found on this machine and lets the user choose
which one FRIDAY should operate. The choice is persisted to the device
config (~/.friday/config.json). No profile is hardcoded.

Usage:
    python scripts/select_chrome_profile.py            # interactive
    python scripts/select_chrome_profile.py --list     # just list
    python scripts/select_chrome_profile.py "Shreesh"  # set directly
"""

import sys

from friday.actions.chrome_profiles import discover_profiles, resolve_profile
from friday.config.browser_config import (
    get_configured_profile,
    set_configured_profile,
)


def main(argv) -> int:
    profiles = discover_profiles()
    if not profiles:
        print("No Chrome profiles found on this device.")
        print("Set FRIDAY_CHROME_USER_DATA_DIR if Chrome is installed elsewhere.")
        return 1

    current = get_configured_profile()
    print("Chrome profiles found on this device:")
    for i, p in enumerate(profiles, 1):
        marker = "  <- current" if current and current.lower() in (
            p.display_name.lower(), p.directory.lower()) else ""
        print(f"  {i}. {p.label}{marker}")

    # Direct set: argument provided
    args = [a for a in argv if not a.startswith("--")]
    if "--list" in argv:
        return 0
    if args:
        sel = args[0]
        p = resolve_profile(sel)
        if not p:
            print(f"No profile matches '{sel}'.")
            return 1
        set_configured_profile(p.display_name)
        print(f"[OK] FRIDAY will use profile: {p.label}")
        return 0

    # Interactive
    try:
        choice = input("\nSelect a profile number (or blank to cancel): ").strip()
    except EOFError:
        print("No input; cancelled.")
        return 1
    if not choice:
        print("Cancelled.")
        return 0
    try:
        idx = int(choice) - 1
        p = profiles[idx]
    except (ValueError, IndexError):
        print("Invalid selection.")
        return 1

    set_configured_profile(p.display_name)
    print(f"[OK] FRIDAY will use profile: {p.label}")
    print("Tip: this is stored in ~/.friday/config.json and can be changed anytime.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
