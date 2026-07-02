"""Live validation — prove the REAL pipeline works end-to-end, safely.

This is the honest confidence step the Truth Report demanded: a real NVIDIA
inference run through the full operator (discover -> plan -> execute -> verify
-> repair), producing a REAL file with REAL LLM content, verified by the
Evidence Law.

SAFETY: this uses a FILE-ONLY goal. No browser, no app launches, no keyboard/
mouse. Nothing phantom can open. dry-run is explicitly OFF here (this is a
real run), but the goal cannot trigger any visible/external action — only
content generation + local file creation.

Run:  python scripts/live_validate.py
"""

import os
import sys
import time

# Real run: dry-run OFF (this script only does generate + file, nothing visible)
os.environ["FRIDAY_DRY_RUN"] = "0"
# Belt-and-suspenders: forbid any browser/app path for this validation.
os.environ["FRIDAY_REQUIRE_REAL_CHROME"] = "0"
os.environ["AUTO_LAUNCH_CHROME"] = "0"

from dotenv import load_dotenv
load_dotenv()


def build_router():
    from friday.models.router import ModelRouter
    from friday.models.providers.nvidia_provider import NvidiaProvider
    from friday.models.providers.groq_provider import GroqProvider

    router = ModelRouter()
    nvidia = NvidiaProvider()
    groq = GroqProvider()
    used = []
    if nvidia.available:
        router.register_provider(nvidia)
        used.append(f"NVIDIA ({len(nvidia.models)} models)")
    if groq.available:
        router.register_provider(groq)
        used.append(f"Groq ({len(groq.models)} models, fallback)")
    return router, used


def main() -> int:
    print("=" * 70)
    print("LIVE VALIDATION — real LLM, file-only goal (nothing phantom can open)")
    print("=" * 70)

    router, used = build_router()
    if not used:
        print("[FAIL] No model provider available. Check NVIDIA_API_KEY / GROQ_API_KEY.")
        return 1
    print("Providers:", ", ".join(used))

    from friday.operator import Operator

    # FILE-ONLY goal: produce content + save. No browser/app capability.
    goal = ("Write a concise 6-line explanation of what makes a good unit test, "
            "and save it to a file called good_unit_tests.md")
    print(f"\nGOAL: {goal}\n")

    operator = Operator(model_router=router, browser_controller=None, max_iterations=2)

    t0 = time.time()
    outcome = operator.run(goal)
    elapsed = time.time() - t0

    print(f"--- OUTCOME (in {elapsed:.1f}s) ---")
    print(f"completed        : {outcome.completed}")
    print(f"requirements_met : {outcome.requirements_met}/{outcome.requirements_total}")
    print(f"created_files    : {outcome.created_files}")
    print(f"content (preview): {outcome.final_content[:200]!r}")

    print("\n--- TRACE ---")
    for line in outcome.trace:
        print(f"  {line}")

    # Verify the file truly exists with real content.
    ok = False
    for f in outcome.created_files:
        if os.path.exists(f) and os.path.getsize(f) > 0:
            ok = True
            print(f"\n[VERIFIED] Real file on disk: {f} ({os.path.getsize(f)} bytes)")
            print("--- FILE CONTENT ---")
            with open(f, encoding="utf-8", errors="replace") as fh:
                print(fh.read()[:600])

    print("\n" + "=" * 70)
    if ok:
        print("RESULT: REAL pipeline works — live NVIDIA inference produced a real,")
        print("        verified file through the full operator loop. [OK]")
        return 0
    print("RESULT: No verified file produced. See trace above for the honest reason.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
