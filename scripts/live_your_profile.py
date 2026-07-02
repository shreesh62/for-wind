"""Live validation on YOUR Chrome profile (Shreesh / Profile 1).

Launches your real profile with CDP. Validates observe, viewport, tabs.
Run: python scripts/live_your_profile.py
Requires: Chrome completely closed first.
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
    from friday.actions.chrome_launcher import ensure_chrome_debug, cdp_reachable
    from friday.actions.browser_controller import BrowserController

    print("=" * 60)
    print("LIVE TEST - YOUR PROFILE (Shreesh / Profile 1)")
    print("=" * 60)

    udd = r"C:\Users\Shreesh\AppData\Local\Google\Chrome\User Data"

    result = ensure_chrome_debug(
        port=9222,
        user_data_dir=udd,
        profile_directory="Profile 1",
        force_dedicated=False,
        allow_dedicated_profile=False,
    )
    print(f"launch ok={result.ok} launched={result.launched} "
          f"dedicated={result.used_dedicated_profile}")
    print(f"user_data_dir={result.user_data_dir}")
    if not result.ok:
        print(f"ERROR: {result.error}")
        return 1

    ctrl = BrowserController(remote_debug_port=9222, require_real_chrome=True)
    if not ctrl.start():
        print(f"controller FAIL: {ctrl.last_error}")
        return 1
    print(f"connected mode={ctrl.connection_mode}")
    print(f"current url: {ctrl.current_url()}")

    # Observe
    snap = ctrl.observe_interactive()
    n_els = len(snap.get("elements", []))
    print(f"observe ok={snap.get('ok')} elements={n_els}")

    # Viewport
    vs = ctrl.viewport_size()
    print(f"viewport: {vs}")

    # Tabs
    tabs = ctrl.list_tabs()
    print(f"tabs: {len(tabs)}")
    for t in tabs[:5]:
        print(f"  {t.get('url', '')[:70]} active={t.get('active')}")

    # Navigate to a non-Google site to prove CDP control works
    print("\nNavigating to Wikipedia...")
    r = ctrl.navigate("https://en.wikipedia.org/wiki/Main_Page")
    print(f"navigate ok={r.get('ok')} url={r.get('url', '')[:60]}")

    # Observe again
    snap2 = ctrl.observe_interactive()
    n2 = len(snap2.get("elements", []))
    print(f"observe after nav: ok={snap2.get('ok')} elements={n2}")

    # Scroll
    sr = ctrl.scroll("down")
    print(f"scroll down: ok={sr.get('ok')} scrolled={sr.get('scrolled')}")

    print("\n" + "=" * 60)
    ok = (snap.get("ok") and r.get("ok") and vs.get("width", 0) > 0
          and len(tabs) >= 1)
    if ok:
        print("YOUR PROFILE WORKS WITH CDP - ALL FEATURES OPERATIONAL [OK]")
    else:
        print("SOME FEATURES FAILED - see output above")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
