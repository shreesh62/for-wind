"""Live multi-step validation — research on real Chrome → synthesize → save file.

Harder than the single web-agent goal: exercises the FULL operator loop with a
REAL browser doing REAL research (open pages, read), then LLM synthesis, then a
real file — verified by the Evidence Law. Dedicated CDP profile (no login).

Run:  python scripts/live_multistep.py
"""

import os, sys, time
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

os.environ["FRIDAY_DRY_RUN"] = "0"
os.environ.setdefault("FRIDAY_SEARCH_ENGINE", "duckduckgo")
from dotenv import load_dotenv
load_dotenv()


def main() -> int:
    from friday.actions.chrome_launcher import ensure_chrome_debug, cdp_reachable
    from friday.actions.browser_controller import BrowserController
    from friday.models.router import ModelRouter
    from friday.models.providers.nvidia_provider import NvidiaProvider
    from friday.operator import Operator

    print("=" * 70)
    print("LIVE MULTI-STEP - real Chrome research -> synthesize -> save")
    print("=" * 70)

    if not cdp_reachable(9222):
        launch = ensure_chrome_debug(port=9222, force_dedicated=True)
        print(f"launch ok: {launch.ok} | dedicated: {launch.used_dedicated_profile}")
        if not launch.ok:
            print(f"[FAIL] CDP: {launch.error}")
            return 1

    controller = BrowserController(remote_debug_port=9222, require_real_chrome=True)
    if not controller.start():
        print(f"[FAIL] controller: {controller.last_error}")
        return 1
    print(f"connected: mode={controller.connection_mode}")

    router = ModelRouter()
    nv = NvidiaProvider()
    if nv.available:
        router.register_provider(nv)

    operator = Operator(model_router=router, browser_controller=controller,
                        max_iterations=2)

    goal = ("Research what the Python programming language is mainly used for, "
            "then write a concise 5-point summary and save it to a file called "
            "python_uses.md")
    print(f"\nGOAL: {goal}\n")

    t0 = time.time()
    outcome = operator.run(goal)
    elapsed = time.time() - t0

    print(f"--- OUTCOME (in {elapsed:.1f}s) ---")
    print(f"completed        : {outcome.completed}")
    print(f"requirements_met : {outcome.requirements_met}/{outcome.requirements_total}")
    print(f"created_files    : {outcome.created_files}")
    print("\n--- TRACE ---")
    for line in outcome.trace:
        print(f"  {line}")

    ok = False
    for f in outcome.created_files:
        if os.path.exists(f) and os.path.getsize(f) > 0:
            ok = True
            print(f"\n[VERIFIED] {f} ({os.path.getsize(f)} bytes)")
            with open(f, encoding="utf-8", errors="replace") as fh:
                print("--- CONTENT ---")
                print(fh.read()[:700])

    print("\n" + "=" * 70)
    print("RESULT: live multi-step research+save WORKED [OK]" if ok
          else "RESULT: did not produce a verified file - see trace")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
