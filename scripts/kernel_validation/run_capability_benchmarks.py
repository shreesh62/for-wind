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

from friday.benchmarks.capability.domains import all_domain_suites, CapabilityBenchmark
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


def _real_execute_factory(model_router):
    """Return an execute(benchmark) -> ExecutionEvidence that runs the goal
    through a real Operator and surfaces its evidence bundle."""
    from friday.operator import Operator
    from friday.verification.evidence_law import ExecutionEvidence

    def execute(benchmark):
        operator = Operator(model_router=model_router, max_iterations=2)
        outcome = operator.run(benchmark.goal_text)
        ev = getattr(outcome, "evidence", None)
        return ev if ev is not None else ExecutionEvidence()

    return execute


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

    if _is_dry_run():
        print("\n[dry-run] FRIDAY_DRY_RUN=1 — live benchmarks skipped, no scores fabricated.")
        print("Run on a real machine (leave FRIDAY_DRY_RUN unset) to measure competence.\n")

    router = None
    execute = None
    if not _is_dry_run():
        router = _build_model_router()
        if router is None:
            print("\n[warn] No model providers available (set NVIDIA_API_KEY / GROQ_API_KEY).")
            print("       Cannot execute live benchmarks; nothing will be scored.\n")
        else:
            execute = _real_execute_factory(router)

    timeout_s = _parse_timeout(default=180.0)
    if execute is not None:
        print(f"\n[info] Per-benchmark timeout: {timeout_s:.0f}s. Each live benchmark runs a real")
        print("       Operator (LLM cold-start + real navigation) — expect tens of seconds each.")

    suites = all_domain_suites()
    scores: Dict[str, Optional[float]] = {}
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
