"""M14 — runnable capability-benchmark entry point (real machine).

Executes the five domain suites, scores each domain via the Evidence Law, runs
the competence ratchet against the persisted baseline, and prints a
CompetenceScorecard. Intended to be driven on a REAL machine with a real Operator
factory + browser/desktop controllers; `requires_live` benchmarks are skipped
under FRIDAY_DRY_RUN (never fabricated).

Usage (real machine):
    python -m scripts.kernel_validation.run_capability_benchmarks

This tool changes no production default. Real scores are recorded into
friday/benchmarks/capability/baseline.json only when explicitly confirmed.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Bootstrap: make `friday` importable when this script is run directly
# (`python scripts/kernel_validation/run_capability_benchmarks.py`) without
# needing PYTHONPATH set. Project root is three levels up from this file.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from typing import Any, Callable, Dict, Optional, Tuple

from friday.benchmarks.capability.domains import (
    all_domain_suites,
    CapabilityBenchmark,
    web_independence_suite,
)
from friday.benchmarks.capability.ratchet import (
    CompetenceRatchet,
    CompetenceScorecard,
    DomainScore,
)
from friday.benchmarks.capability.scoring import score_benchmark, score_domain


_BASELINE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "friday", "benchmarks", "capability", "baseline.json"
)


def _is_dry_run() -> bool:
    return os.environ.get("FRIDAY_DRY_RUN") == "1"


def _parse_target_browser() -> Optional[str]:
    """Read an optional ``--target-browser <name>`` CLI arg (M23 web-independence)."""
    argv = sys.argv
    for i, arg in enumerate(argv):
        if arg == "--target-browser" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--target-browser="):
            return arg.split("=", 1)[1]
    return None


def _parse_only_benchmarks() -> Optional[set]:
    """Read an optional ``--only a,b,c`` filter of web_independence capability suffixes."""
    argv = sys.argv
    raw = None
    for i, arg in enumerate(argv):
        if arg == "--only" and i + 1 < len(argv):
            raw = argv[i + 1]
            break
        if arg.startswith("--only="):
            raw = arg.split("=", 1)[1]
            break
    if not raw:
        return None
    return {s.strip() for s in raw.split(",") if s.strip()}


def _build_desktop_controller_for_web(target_browser: Optional[str]):
    """Launch the target browser (if named) and return a started, CDP-free
    DesktopBrowserController operating the active window. None if unavailable."""
    if target_browser:
        launched = False
        # Chromium browsers on a machine whose main profile is already open show a
        # profile-picker on a bare launch (no address bar → can't navigate). Open a
        # CLEAN dedicated-profile window instead so the desktop pipeline gets a real
        # browsing window. This is a LAUNCH convenience for the proof only — the
        # execution path stays CDP-free (we do NOT connect Playwright/CDP).
        if target_browser.lower() in ("chrome", "google chrome"):
            try:
                from friday.actions.chrome_launcher import ensure_chrome_debug
                r = ensure_chrome_debug(force_dedicated=True)
                launched = bool(getattr(r, "ok", False))
                if launched:
                    print("[info] opened a clean Chrome window (dedicated profile, no picker).")
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] clean-window launch failed: {exc}")
        if not launched:
            try:
                from friday.actions.system import SystemActions
                SystemActions().launch_app(target_browser)
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] could not launch '{target_browser}': {exc}")
        time.sleep(4.0)  # let the window come to the foreground
    try:
        from friday.actions.desktop_browser import DesktopBrowserController
        c = DesktopBrowserController()
        if c.available and c.start():
            print("[ok] Desktop browser controller started (no CDP).")
            return c
        print("[warn] desktop browser controller unavailable (pyautogui missing?).")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] desktop controller error: {exc}")
    return None


def run_web_independence(router, timeout_s: float) -> int:
    """M23 — run the web-independence proof suite with CDP DISABLED.

    Domain-general goals run against a target browser via the desktop pipeline.
    Results are printed honestly (measured/unmeasured) and are NOT recorded to
    the competence baseline (this is a proof suite, not a competence domain).
    """
    print("\n[web-independence] CDP optimization DISABLED — desktop pipeline only.")
    os.environ["FRIDAY_ENABLE_CDP"] = "0"
    suite = web_independence_suite()

    if router is None:
        print("[warn] no model providers — cannot execute; all benchmarks UNMEASURED.")
        for b in suite:
            print(f"    [bench] {b.id} ... UNMEASURED (no provider)")
        return 0

    # Optional safety filter: --only <comma-separated capability suffixes> runs just
    # those benchmarks (e.g. the read-only public subset launch,navigate,search),
    # leaving side-effecting ones (login/upload/download/dialog/crash) out of a run.
    only = _parse_only_benchmarks()
    if only:
        suite = tuple(b for b in suite if b.id.split(".", 1)[1] in only)
        print(f"[info] --only filter active: running {[b.id for b in suite]}")

    target = _parse_target_browser()
    controller = _build_desktop_controller_for_web(target)
    execute = _real_execute_factory(router, browser_controller=controller)
    label = target or "active window"
    print(f"[info] target browser: {label}; per-benchmark timeout {timeout_s:.0f}s")
    print(f"\n[run] domain: web_independence ({len(suite)} benchmarks)", flush=True)
    score = run_domain("web_independence", suite, execute, timeout_s=timeout_s)

    print("\n# Web-Independence Scorecard (CDP disabled)")
    print(f"- Target browser: {label}")
    print(f"- Score: {score:.4f}" if score is not None else "- Score: unmeasured")
    print("- Not recorded to the competence baseline (proof suite only).")
    if controller is not None:
        try:
            controller.stop()
        except Exception:  # noqa: BLE001
            pass
    return 0


def _parse_only_domain() -> Optional[str]:
    """Read an optional ``--domain <name>`` CLI arg to run one domain only."""
    argv = sys.argv
    for i, arg in enumerate(argv):
        if arg == "--domain" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--domain="):
            return arg.split("=", 1)[1]
    return None


def _parse_timeout(default: float = 180.0) -> float:
    """Read an optional ``--timeout <seconds>`` CLI arg (per-benchmark wall clock)."""
    argv = sys.argv
    for i, arg in enumerate(argv):
        if arg == "--timeout" and i + 1 < len(argv):
            try:
                return max(1.0, float(argv[i + 1]))
            except ValueError:
                break
        if arg.startswith("--timeout="):
            try:
                return max(1.0, float(arg.split("=", 1)[1]))
            except ValueError:
                break
    return default


def run_domain(
    domain: str,
    benchmarks: Tuple[CapabilityBenchmark, ...],
    execute: Callable[[CapabilityBenchmark], Any],
    *,
    timeout_s: Optional[float] = None,
) -> Optional[float]:
    """Run one domain's benchmarks; return its [0,1] score, or None if unmeasured
    (all benchmarks skipped because they require a live machine).

    ``execute(benchmark) -> ExecutionEvidence`` runs the goal and returns the
    evidence bundle. On a real machine this drives the Operator/kernel path.

    Prints per-benchmark progress (flushed) so a slow real run is distinguishable
    from a hang, and enforces an optional per-benchmark ``timeout_s`` so a single
    wedged benchmark (e.g. a stalled browser launch or network call) scores as a
    fail instead of blocking the entire run forever.
    """
    import concurrent.futures as _cf

    results = []
    measured_any = False
    for b in benchmarks:
        if b.requires_live and _is_dry_run():
            continue  # skip live-only benchmarks in the sandbox (never fabricate)
        measured_any = True
        print(f"    [bench] {b.id} ... ", end="", flush=True)
        t0 = time.perf_counter()
        pool = None
        try:
            if timeout_s is not None:
                # Run in a worker thread so we can bound the wall-clock time.
                # NOTE: do NOT use `with` — its __exit__ shuts down with wait=True,
                # which would block on a wedged worker and defeat the timeout. On
                # timeout we shut the pool down WITHOUT waiting so the run proceeds.
                pool = _cf.ThreadPoolExecutor(max_workers=1)
                fut = pool.submit(execute, b)
                evidence = fut.result(timeout=timeout_s)
                pool.shutdown(wait=False)
                pool = None
            else:
                evidence = execute(b)
            passed = score_benchmark(b, evidence)
            dt = time.perf_counter() - t0
            print(f"{'PASS' if passed else 'fail'} ({dt:.1f}s)", flush=True)
        except _cf.TimeoutError:
            passed = False
            print(f"TIMEOUT (>{timeout_s:.0f}s) — scored fail", flush=True)
            # Abandon the wedged worker without blocking the rest of the run.
            if pool is not None:
                pool.shutdown(wait=False)
                pool = None
        except Exception as exc:  # noqa: BLE001 — a failed run scores as a fail, never crashes
            passed = False
            dt = time.perf_counter() - t0
            print(f"error ({dt:.1f}s): {type(exc).__name__} — scored fail", flush=True)
            if pool is not None:
                pool.shutdown(wait=False)
                pool = None
        results.append((b, passed))
    if not measured_any:
        return None
    return score_domain(tuple(results))


def build_scorecard(scores: Dict[str, Optional[float]], *, tolerance: float = 0.05) -> CompetenceScorecard:
    """Assemble a scorecard + ratchet verdict from per-domain scores."""
    ratchet = CompetenceRatchet(_BASELINE_PATH)
    measured = {d: s for d, s in scores.items() if s is not None}
    verdict = ratchet.check(measured, tolerance=tolerance)
    domain_scores = tuple(
        DomainScore(d, (scores[d] if scores[d] is not None else 0.0), scores[d] is not None)
        for d in ("browser", "desktop", "research", "coding", "long_horizon")
    )
    overall = (
        sum(measured.values()) / len(measured) if measured else 0.0
    )
    return CompetenceScorecard(domain_scores=domain_scores, verdict=verdict, overall=overall)


def _build_model_router():
    """Build a ModelRouter with whatever providers are available (mirrors
    api/server.py). Returns None if no provider is available."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:  # noqa: BLE001 — dotenv is optional
        pass
    from friday.models.router import ModelRouter
    from friday.models.providers.nvidia_provider import NvidiaProvider
    from friday.models.providers.groq_provider import GroqProvider

    router = ModelRouter()
    nvidia = NvidiaProvider()
    groq = GroqProvider()
    if nvidia.available:
        router.register_provider(nvidia)
        print(f"[ok] NVIDIA: {len(nvidia.models)} models")
    if groq.available:
        router.register_provider(groq)
        print(f"[ok] Groq: {len(groq.models)} models")
    if not router.get_available_providers():
        return None
    return router


def _real_execute_factory(model_router, browser_controller=None):
    """Return an execute(benchmark) -> ExecutionEvidence that runs the goal
    through a real Operator and surfaces its evidence bundle.

    When ``browser_controller`` is supplied (see --browser), the Operator can
    perform real navigation and emit NAVIGATION evidence — required for the
    browser/desktop domains. Without it, the browserless research path is used.
    """
    from friday.operator import Operator
    from friday.verification.evidence_law import ExecutionEvidence

    def execute(benchmark):
        operator = Operator(
            model_router=model_router,
            browser_controller=browser_controller,
            # Multi-stage goals (gather -> synthesize -> save) need room for each
            # stage to run + emit its evidence; 2 iterations starves the synthesis
            # step of some benchmarks. 4 keeps runs bounded while allowing the full
            # evidence chain. This changes only the measurement harness, never the
            # acceptance criteria (required_evidence is unchanged).
            max_iterations=4,
        )
        outcome = operator.run(benchmark.goal_text)
        ev = getattr(outcome, "evidence", None)
        return ev if ev is not None else ExecutionEvidence()

    return execute


def _maybe_start_browser():
    """Start a real browser controller when --browser is passed (opt-in).

    By default uses a fresh Playwright Chromium (require_real_chrome=False) so
    live benchmark navigation of PUBLIC pages never touches the user's logged-in
    Chrome session.

    With --real-chrome, connects to the user's ALREADY-RUNNING Chrome over CDP
    (require_real_chrome=True) on CHROME_REMOTE_DEBUG_PORT (default 9222). This
    requires Chrome to be started with the debug port first
    (scripts/launch_chrome_debug.py); a CDP failure surfaces loudly rather than
    silently faking the session. Returns the started controller, or None if not
    requested or unavailable (the run then falls back to the browserless path).
    """
    if "--browser" not in sys.argv:
        return None
    try:
        from friday.actions.browser_controller import BrowserController
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] --browser requested but BrowserController import failed: {exc}")
        return None

    use_real = "--real-chrome" in sys.argv
    port = int(os.environ.get("CHROME_REMOTE_DEBUG_PORT", "9222"))
    controller = BrowserController(
        require_real_chrome=use_real,
        remote_debug_port=port,
    )
    if controller.start():
        real = " (REAL Chrome via CDP)" if controller.is_real_chrome else ""
        print(f"[ok] Browser controller started (mode={controller.connection_mode}){real}.")
        return controller
    hint = ""
    if use_real:
        hint = (
            " — start your Chrome with the debug port first: "
            "python scripts/launch_chrome_debug.py"
        )
    print(f"[warn] Browser controller failed to start: {controller.last_error}{hint}")
    return None


def main() -> int:
    """Run the capability benchmarks and print a CompetenceScorecard.

    On a real machine (FRIDAY_DRY_RUN unset) with providers available, this
    executes real goals and scores them via the Evidence Law. In the sandbox /
    dry-run, or without providers, live benchmarks are SKIPPED and no scores are
    fabricated.
    """
    print("=" * 56)
    print("  FRIDAY Capability Benchmarks — Competence Scorecard")
    print("=" * 56)

    # M23: --no-cdp forces the desktop pipeline (CDP optimization off). This is the
    # default, but the flag makes the guarantee explicit for the proof run.
    if "--no-cdp" in sys.argv:
        os.environ["FRIDAY_ENABLE_CDP"] = "0"

    if _is_dry_run():
        print("\n[dry-run] FRIDAY_DRY_RUN=1 — live benchmarks skipped, no scores fabricated.")
        print("Run on a real machine (leave FRIDAY_DRY_RUN unset) to measure competence.\n")

    router = None
    execute = None
    browser = None
    if not _is_dry_run():
        router = _build_model_router()
        if router is None:
            print("\n[warn] No model providers available (set NVIDIA_API_KEY / GROQ_API_KEY).")
            print("       Cannot execute live benchmarks; nothing will be scored.\n")
        else:
            browser = _maybe_start_browser()
            execute = _real_execute_factory(router, browser_controller=browser)

    timeout_s = _parse_timeout(default=180.0)

    # M23: the web-independence proof suite is a separate, explicitly-invoked run
    # that never perturbs the five-domain competence scorecard/ratchet.
    if "--web-independence" in sys.argv:
        rc = run_web_independence(router, timeout_s)
        if browser is not None:
            try:
                browser.stop()
            except Exception:  # noqa: BLE001
                pass
        return rc

    if execute is not None:
        print(f"\n[info] Per-benchmark timeout: {timeout_s:.0f}s. Each live benchmark runs a real")
        print("       Operator (LLM cold-start + real navigation) — expect tens of seconds each.")

    suites = all_domain_suites()
    # All domains present (None = unmeasured) so the scorecard never KeyErrors,
    # even when --domain restricts which domains actually run this session.
    scores: Dict[str, Optional[float]] = {d: None for d in suites}
    only = _parse_only_domain()
    if only:
        suites = {d: b for d, b in suites.items() if d == only}
        print(f"[info] Running ONLY domain: {only}")
    for domain, benches in suites.items():
        if execute is None:
            scores[domain] = None  # unmeasured — never fabricated
            continue
        print(f"\n[run] domain: {domain} ({len(benches)} benchmarks)", flush=True)
        scores[domain] = run_domain(domain, benches, execute, timeout_s=timeout_s)

    scorecard = build_scorecard(scores)
    print("\n" + scorecard.to_markdown())

    if execute is not None:
        measured = {d: s for d, s in scores.items() if s is not None}
        if measured:
            print("To record these as the new baseline, re-run with --record.")
            if "--record" in sys.argv:
                CompetenceRatchet(_BASELINE_PATH).record(measured)
                print(f"[ok] Recorded baseline for {len(measured)} domain(s).")

    if browser is not None:
        try:
            browser.stop()
            print("[ok] Browser controller stopped.")
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
