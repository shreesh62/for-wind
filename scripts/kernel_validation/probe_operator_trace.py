"""Diagnostic: trace ONE Operator run on the navigate goal via the desktop pipeline.

Prints the plan trace and the evidence kinds recorded, so we can see WHY a
web_independence benchmark fails (planner vs controller vs evidence flow).
Drives the desktop briefly (CDP disabled).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.pop("FRIDAY_DRY_RUN", None)
os.environ["FRIDAY_ENABLE_CDP"] = "0"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()
    os.environ["FRIDAY_ENABLE_CDP"] = "0"
except Exception:
    pass

GOAL = "Open a public information page about a given topic and read its contents."


def main() -> int:
    from friday.actions.chrome_launcher import ensure_chrome_debug
    from friday.actions.desktop_browser import DesktopBrowserController
    from friday.operator import Operator
    from friday.models.router import ModelRouter
    from friday.models.providers.nvidia_provider import NvidiaProvider
    from friday.verification.evidence_law import EvidenceKind

    r = ensure_chrome_debug(force_dedicated=True)
    print(f"clean window ok={getattr(r,'ok',None)}")
    time.sleep(3.0)

    ctrl = DesktopBrowserController()
    ctrl.start()
    print(f"controller window={getattr(getattr(ctrl,'_window',None),'title',None)!r}")

    router = ModelRouter()
    nv = NvidiaProvider()
    if nv.available:
        router.register_provider(nv)

    op = Operator(model_router=router, browser_controller=ctrl, max_iterations=4)
    outcome = op.run(GOAL)

    print("\n--- TRACE ---")
    for line in getattr(outcome, "trace", []) or []:
        print("  ", line)
    print("\n--- OUTCOME ---")
    print("completed:", getattr(outcome, "completed", None))
    print("summary:", (getattr(outcome, "summary", "") or "")[:200])
    ev = getattr(outcome, "evidence", None)
    if ev is not None:
        print("\n--- EVIDENCE KINDS ---")
        for k in EvidenceKind:
            n = len(ev.of_kind(k))
            if n:
                print(f"  {k.name}: {n}")
    try:
        ctrl.stop()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
