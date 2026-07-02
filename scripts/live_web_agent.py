"""Live web-agent validation — real Chrome (CDP), real observe→decide→act loop.

Uses the dedicated CDP profile (100% reliable, no login needed) and a public
goal so it works regardless of Google's auth lock. Proves the generic web
agent operates a real browser: observe interactive elements -> LLM decides ->
act -> repeat -> done, with vision escalation available.

Run:  python scripts/live_web_agent.py
"""

import os
import sys
import time

# Force UTF-8 stdout so prints never crash on the cp1252 Windows console.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

os.environ["FRIDAY_DRY_RUN"] = "0"          # real run
os.environ.setdefault("FRIDAY_SEARCH_ENGINE", "duckduckgo")

from dotenv import load_dotenv
load_dotenv()


def build_router():
    from friday.models.router import ModelRouter
    from friday.models.providers.nvidia_provider import NvidiaProvider
    router = ModelRouter()
    nv = NvidiaProvider()
    if nv.available:
        router.register_provider(nv)
    return router


def main() -> int:
    from friday.actions.chrome_launcher import ensure_chrome_debug, cdp_reachable
    from friday.actions.browser_controller import BrowserController
    from friday.capabilities.web_agent import WebAgent
    from friday.verification.evidence_law import ExecutionEvidence, EvidenceKind

    print("=" * 70)
    print("LIVE WEB AGENT - real Chrome, observe-decide-act on a public site")
    print("=" * 70)

    # Tier 2: dedicated CDP profile (reliable, no login needed).
    if not cdp_reachable(9222):
        launch = ensure_chrome_debug(port=9222, force_dedicated=True)
        print(f"launch ok: {launch.ok} | dedicated: {launch.used_dedicated_profile}")
        if not launch.ok:
            print(f"[FAIL] could not bring up CDP: {launch.error}")
            return 1

    controller = BrowserController(remote_debug_port=9222, require_real_chrome=True)
    if not controller.start():
        print(f"[FAIL] controller: {controller.last_error}")
        return 1
    print(f"connected: mode={controller.connection_mode}")

    # Seed a starting page so the agent has somewhere to act.
    controller.navigate("https://en.wikipedia.org/wiki/Main_Page")
    time.sleep(1)

    router = build_router()
    evidence = ExecutionEvidence()
    agent = WebAgent(controller, router, max_steps=10)

    goal = ("On Wikipedia, use the search box to find the article about the "
            "Python programming language, open it, and confirm the article "
            "page is showing.")
    print(f"\nGOAL: {goal}\n")

    t0 = time.time()
    result = agent.run(goal, evidence=evidence)
    elapsed = time.time() - t0

    print(f"--- RESULT (in {elapsed:.1f}s) ---")
    print(f"achieved   : {result.achieved}")
    print(f"steps      : {result.steps_taken}")
    print(f"final_url  : {result.final_url}")
    if result.stuck_reason:
        print(f"stuck      : {result.stuck_reason}")
    print("\n--- HISTORY ---")
    for h in result.history:
        print(f"  {h}")

    navs = evidence.of_kind(EvidenceKind.NAVIGATION)
    shots = evidence.of_kind(EvidenceKind.SCREENSHOT)
    print(f"\nevidence: {len(navs)} navigations, {len(shots)} screenshots")
    if result.final_url:
        print(f"final URL contains 'Python': {'python' in result.final_url.lower()}")

    print("\n" + "=" * 70)
    ok = result.achieved or "python" in (result.final_url or "").lower()
    print("RESULT: web agent operated real Chrome successfully [OK]" if ok
          else "RESULT: did not reach the target — see history/stuck reason")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
