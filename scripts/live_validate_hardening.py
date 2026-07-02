"""Live validation of browser-agent hardening (ADR-046 through ADR-050).

Tests in real Chrome (CDP dedicated profile):
  1. Connect + observe_interactive (includes iframe/shadow traversal logic)
  2. viewport_size returns real values (not 1280x800 default)
  3. list_tabs + navigate opens new content
  4. scroll returns actual scroll delta
  5. networkidle-aware navigate completes without fixed sleeps
  6. Full web-agent loop: Wikipedia search (reuses live_web_agent goal)
  7. Tab management: open a new tab, list, switch back

Run:  python scripts/live_validate_hardening.py
Requires: Chrome closed. Uses dedicated CDP profile (port 9222).
"""

import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

os.environ["FRIDAY_DRY_RUN"] = "0"
os.environ.setdefault("FRIDAY_SEARCH_ENGINE", "duckduckgo")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()


def main() -> int:
    from friday.actions.chrome_launcher import ensure_chrome_debug, cdp_reachable
    from friday.actions.browser_controller import BrowserController

    print("=" * 70)
    print("LIVE HARDENING VALIDATION (ADR-046 through ADR-050)")
    print("=" * 70)

    # --- LAUNCH ---
    if not cdp_reachable(9222):
        launch = ensure_chrome_debug(port=9222, force_dedicated=True)
        print(f"launch: ok={launch.ok} dedicated={launch.used_dedicated_profile}")
        if not launch.ok:
            print(f"[FAIL] CDP launch: {launch.error}")
            return 1
    else:
        print("CDP already reachable on 9222")

    ctrl = BrowserController(remote_debug_port=9222, require_real_chrome=True)
    if not ctrl.start():
        print(f"[FAIL] controller start: {ctrl.last_error}")
        return 1
    print(f"[OK] connected mode={ctrl.connection_mode}")

    passed = 0
    failed = 0

    def check(name, cond, detail=""):
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  [PASS] {name} {detail}")
        else:
            failed += 1
            print(f"  [FAIL] {name} {detail}")

    # --- TEST 1: observe_interactive ---
    print("\n1. observe_interactive (iframe/shadow-DOM walker)")
    ctrl.navigate("https://en.wikipedia.org/wiki/Main_Page")
    time.sleep(1)
    snap = ctrl.observe_interactive()
    check("observe ok", snap.get("ok") is True)
    check("elements found", len(snap.get("elements", [])) > 5,
          f"({len(snap.get('elements', []))} elements)")
    check("elements have x/y", all("x" in e and "y" in e
          for e in snap.get("elements", [])[:5]))

    # --- TEST 2: viewport_size ---
    print("\n2. viewport_size (CDP fix - real dimensions + DPR)")
    vs = ctrl.viewport_size()
    check("width > 0", vs.get("width", 0) > 0, f"width={vs.get('width')}")
    check("height > 0", vs.get("height", 0) > 0, f"height={vs.get('height')}")
    check("device_pixel_ratio present",
          "device_pixel_ratio" in vs, f"dpr={vs.get('device_pixel_ratio')}")
    # On real CDP it should NOT be 1280x800 exactly (those are the old defaults)
    real_dims = (vs.get("width"), vs.get("height"))
    check("not default 1280x800", real_dims != (1280, 800), f"actual={real_dims}")

    # --- TEST 3: list_tabs ---
    print("\n3. list_tabs")
    tabs = ctrl.list_tabs()
    check("at least 1 tab", len(tabs) >= 1, f"({len(tabs)} tabs)")
    if tabs:
        check("active flag present", any(t.get("active") for t in tabs))
        check("url populated", tabs[0].get("url", "").startswith("http"))

    # --- TEST 4: scroll ---
    print("\n4. scroll (down + up)")
    sr = ctrl.scroll("down", 600)
    check("scroll down ok", sr.get("ok") is True)
    check("scrolled flag true", sr.get("scrolled") is True, f"y={sr.get('y')}")
    sr2 = ctrl.scroll("up", 600)
    check("scroll up ok", sr2.get("ok") is True)

    # --- TEST 5: networkidle navigate ---
    print("\n5. navigate with networkidle")
    t0 = time.time()
    nr = ctrl.navigate("https://example.com")
    elapsed = time.time() - t0
    check("navigate ok", nr.get("ok") is True)
    check("completed in <15s", elapsed < 15, f"({elapsed:.1f}s)")
    check("url updated", "example" in nr.get("url", "").lower())

    # --- TEST 6: web agent loop ---
    print("\n6. web-agent loop (Wikipedia search)")
    try:
        from friday.models.router import ModelRouter
        from friday.models.providers.nvidia_provider import NvidiaProvider
        from friday.capabilities.web_agent import WebAgent
        from friday.verification.evidence_law import ExecutionEvidence

        router = ModelRouter()
        nv = NvidiaProvider()
        if nv.available:
            router.register_provider(nv)
            ctrl.navigate("https://en.wikipedia.org/wiki/Main_Page")
            time.sleep(1)
            evidence = ExecutionEvidence()
            agent = WebAgent(ctrl, router, max_steps=8)
            goal = ("Use Wikipedia's search to find the article about 'Python "
                    "programming language' and open it.")
            result = agent.run(goal, evidence=evidence)
            check("agent achieved or found python",
                  result.achieved or "python" in (result.final_url or "").lower(),
                  f"steps={result.steps_taken} url={result.final_url}")
        else:
            print("  [SKIP] NVIDIA provider not available (no API key)")
    except Exception as exc:
        check("web-agent no crash", False, str(exc))

    # --- TEST 7: tab management ---
    print("\n7. tab management (open + list + switch)")
    ctrl.navigate("https://example.com")
    time.sleep(0.5)
    tabs_before = ctrl.list_tabs()
    # Use JS to open a new tab.
    try:
        ctrl._submit(ctrl._page.evaluate("() => window.open('https://httpbin.org/get', '_blank')"))
        time.sleep(2)
    except Exception:
        pass
    tabs_after = ctrl.list_tabs()
    check("new tab appeared", len(tabs_after) > len(tabs_before),
          f"before={len(tabs_before)} after={len(tabs_after)}")
    if len(tabs_after) > 1:
        sw = ctrl.switch_tab(0)
        check("switch_tab ok", sw.get("ok") is True)
        check("back on first tab", "example" in sw.get("url", "").lower())

    # --- SUMMARY ---
    print("\n" + "=" * 70)
    total = passed + failed
    print(f"RESULTS: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print("ALL HARDENING FEATURES VALIDATED ON REAL CHROME [OK]")
    else:
        print("SOME CHECKS FAILED - see above")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
