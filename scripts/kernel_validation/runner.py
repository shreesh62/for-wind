"""M13 — the dual-path validation runner (non-production; changes no defaults).

Runs each :class:`ValidationScenario` on BOTH the legacy path and the kernel
path with identical goal text, capturing a :class:`ValidationEvidence` per path.
It restores ``FRIDAY_USE_KERNEL_EXECUTION`` after each run and SKIPS
``requires_live`` scenarios under ``FRIDAY_DRY_RUN`` (never fabricating results).

This module NEVER changes a production default: the bridge/kernel are constructed
locally per run, and no global default is mutated. It is intended to be executed
manually on a real machine:

    python -m scripts.kernel_validation.runner
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Bootstrap: make the project root importable when run directly, without needing
# PYTHONPATH set (project root is three levels up from this file).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from typing import Any, Callable, List, Optional, Tuple

from scripts.kernel_validation.evidence import ValidationEvidence
from scripts.kernel_validation.faults import (
    RESULT_FAIL,
    ProbeContext,
    ProbeVerdict,
    get_probe,
)
from scripts.kernel_validation.scenarios import ValidationScenario, all_scenarios

# Importing the probes package is what registers the built-in probes, so
# get_probe(...) resolves them by the time _run_probe runs. The import lives here
# rather than in faults.py because the probe modules import faults — registering
# from faults would be a circular import.
import scripts.kernel_validation.probes  # noqa: F401,E402 - registers built-in probes


def _is_dry_run() -> bool:
    return os.environ.get("FRIDAY_DRY_RUN") == "1"


class ValidationRunner:
    """Runs scenarios on legacy and kernel paths and collects evidence.

    ``operator_factory`` is an injected callable ``(goal_text) -> operator`` used
    by the kernel path (and, in a real run, by the legacy path too). Injecting it
    keeps this tool decoupled and testable with stub operators — exactly like the
    M12 GoalExecutionRuntime.
    """

    def __init__(
        self,
        operator_factory: Callable[[str], Any],
        *,
        browser_controller: Any = None,
    ) -> None:
        self._operator_factory = operator_factory
        self._browser_controller = browser_controller

    # -- kernel path --------------------------------------------------------

    def _run_kernel(self, scenario: ValidationScenario) -> ValidationEvidence:
        from friday.events.store import EventStore
        from friday.kernel.execution import GoalExecutionRuntime
        from friday.kernel.kernel import CognitiveKernel

        seen: List[str] = []
        start = time.perf_counter()
        try:
            import tempfile

            with tempfile.TemporaryDirectory() as d:
                kernel = CognitiveKernel(event_store=EventStore(os.path.join(d, "ev.jsonl")))
                kernel.subscribe("goal.completed", lambda e: seen.append(e.event_type))
                kernel.subscribe("goal.failed", lambda e: seen.append(e.event_type))
                runtime = GoalExecutionRuntime(self._operator_factory)
                kernel.register_runtime(runtime)
                kernel.submit_goal(scenario.goal_text)
            latency = (time.perf_counter() - start) * 1000
            result = "pass" if "goal.completed" in seen else "fail"
            return ValidationEvidence(
                scenario_id=scenario.id, path="kernel", result=result,
                event_types=tuple(seen), latency_ms=latency,
            )
        except Exception as exc:  # noqa: BLE001 — a failure is recorded, not raised
            latency = (time.perf_counter() - start) * 1000
            return ValidationEvidence(
                scenario_id=scenario.id, path="kernel", result="fail",
                latency_ms=latency, error=str(exc),
            )

    # -- legacy path --------------------------------------------------------

    def _run_legacy(self, scenario: ValidationScenario) -> ValidationEvidence:
        start = time.perf_counter()
        try:
            operator = self._operator_factory(
                scenario.goal_text, requires_live=scenario.requires_live
            )
            outcome = operator.run(scenario.goal_text)
            latency = (time.perf_counter() - start) * 1000
            completed = bool(getattr(outcome, "completed", False))
            summary = str(getattr(outcome, "summary", "") or "")
            return ValidationEvidence(
                scenario_id=scenario.id, path="legacy",
                result="pass" if completed else "fail",
                output=summary, latency_ms=latency,
            )
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - start) * 1000
            return ValidationEvidence(
                scenario_id=scenario.id, path="legacy", result="fail",
                latency_ms=latency, error=str(exc),
            )

    # -- probe path ---------------------------------------------------------

    def _run_probe(
        self, scenario: ValidationScenario
    ) -> Tuple[ValidationEvidence, ValidationEvidence]:
        """Dispatch a probe-backed scenario generically through the registry.

        An unknown probe id, or an exception raised inside ``actuate``, is recorded
        as a ``fail`` verdict — never a pass, and never an escaping exception.
        """
        import shutil
        import tempfile

        start = time.perf_counter()
        probe = get_probe(scenario.probe_id)
        if probe is None:
            verdict = ProbeVerdict(
                probe_id=scenario.probe_id, result=RESULT_FAIL,
                error=f"no probe registered for id {scenario.probe_id!r}",
            )
        else:
            workdir = tempfile.mkdtemp(prefix="m13-probe-")
            try:
                context = ProbeContext(
                    scenario=scenario,
                    operator_factory=self._operator_factory,
                    browser_controller=self._browser_controller,
                    workdir=workdir,
                )
                try:
                    verdict = probe.actuate(context)
                except Exception as exc:  # noqa: BLE001 — recorded as fail, not raised
                    verdict = ProbeVerdict(
                        probe_id=scenario.probe_id, result=RESULT_FAIL,
                        error=f"{type(exc).__name__}: {exc}",
                    )
            finally:
                # The runner owns the probe workdir. ignore_errors covers a file
                # still held by a killed child on Windows; it never hides a
                # verdict, only temp-file removal.
                shutil.rmtree(workdir, ignore_errors=True)

        latency = (time.perf_counter() - start) * 1000
        probe_id = verdict.probe_id or scenario.probe_id
        kernel_ev = ValidationEvidence(
            scenario_id=scenario.id, path="kernel", result=verdict.result,
            latency_ms=latency, error=verdict.error,
            probe_id=probe_id, assertions=tuple(verdict.assertions),
        )
        legacy_ev = ValidationEvidence(
            scenario_id=scenario.id, path="legacy", result=verdict.result,
            latency_ms=latency, error=verdict.error, probe_id=probe_id,
            assertions=(
                f"no legacy-path measurement was taken: probe {probe_id!r} actuates a "
                "real fault and its verdict is path-independent; this row mirrors the "
                "kernel-path verdict so parity arithmetic claims no untaken measurement",
            ),
        )
        return legacy_ev, kernel_ev

    # -- orchestration ------------------------------------------------------

    def run_scenario(
        self, scenario: ValidationScenario
    ) -> Tuple[ValidationEvidence, ValidationEvidence]:
        """Run one scenario on both paths. Live-only scenarios are SKIPPED in
        DRY_RUN (never fabricated). Restores env defaults afterward."""
        prev_flag = os.environ.get("FRIDAY_USE_KERNEL_EXECUTION")
        try:
            if scenario.requires_live and _is_dry_run():
                skipped_k = ValidationEvidence(scenario.id, "kernel", "skipped",
                                               error="requires_live in FRIDAY_DRY_RUN")
                skipped_l = ValidationEvidence(scenario.id, "legacy", "skipped",
                                               error="requires_live in FRIDAY_DRY_RUN")
                return skipped_l, skipped_k

            if scenario.probe_id:
                return self._run_probe(scenario)

            legacy_ev = self._run_legacy(scenario)
            kernel_ev = self._run_kernel(scenario)
            return legacy_ev, kernel_ev
        finally:
            # Restore the flag exactly as it was — never leak a default change.
            if prev_flag is None:
                os.environ.pop("FRIDAY_USE_KERNEL_EXECUTION", None)
            else:
                os.environ["FRIDAY_USE_KERNEL_EXECUTION"] = prev_flag

    def run_all(self) -> List[Tuple[ValidationEvidence, ValidationEvidence]]:
        return [self.run_scenario(s) for s in all_scenarios()]


# --------------------------------------------------------------------------- #
# Real-machine driver (M13 completion). Additive: ValidationRunner's contract is
# unchanged; this only supplies a REAL Operator factory and bounded orchestration.
# --------------------------------------------------------------------------- #


def _parse_flag_value(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read ``--name value`` or ``--name=value`` from argv."""
    for i, arg in enumerate(sys.argv):
        if arg == f"--{name}" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if arg.startswith(f"--{name}="):
            return arg.split("=", 1)[1]
    return default


def _build_model_router():
    """Build a ModelRouter from available providers (mirrors the benchmark runner)."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:  # noqa: BLE001 - dotenv is optional
        pass
    from friday.models.router import ModelRouter
    from friday.models.providers.nvidia_provider import NvidiaProvider

    router = ModelRouter()
    nvidia = NvidiaProvider()
    if nvidia.available:
        router.register_provider(nvidia)
        print(f"[ok] NVIDIA: {len(nvidia.models)} models")
    if not router.get_available_providers():
        return None
    return router


def _maybe_start_browser():
    """Start a browser controller when ``--browser`` or ``--cdp`` is passed.

    ``--cdp`` connects to the user's **real Chrome** (logins, history, extensions)
    via CDP on port 9222, which is the primary use case for FRIDAY: operating the
    user's signed-in sessions. The user must have Chrome running with
    ``--remote-debugging-port=9222``.

    ``--browser`` launches a **fresh Chromium** instance (no profile, no logins) —
    useful for deterministic testing but not representative of real operation.
    """
    use_cdp = "--cdp" in sys.argv
    use_browser = "--browser" in sys.argv
    if not use_cdp and not use_browser:
        return None
    try:
        from friday.actions.browser_controller import BrowserController
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] browser requested but import failed: {exc}")
        return None
    controller = BrowserController(require_real_chrome=use_cdp)
    if controller.start():
        print(f"[ok] Browser controller started (mode={controller.connection_mode}).")
        return controller
    print(f"[warn] Browser controller failed to start: {controller.last_error}")
    return None


def _real_operator_factory(model_router, browser_controller=None):
    """Return ``factory(goal_text, scenario) -> Operator`` backed by real subsystems.

    The browser is only supplied to the Operator when the scenario actually requires
    live resources. A `requires_live=False` scenario (like file generation) getting a
    browser led the planner to select research steps it didn't need, whose Playwright
    navigations cascaded into a 900s timeout hang.
    """
    from friday.operator import Operator

    def factory(goal_text: str, *, requires_live: bool = True):
        browser = browser_controller if requires_live else None
        return Operator(
            model_router=model_router,
            browser_controller=browser,
            max_iterations=4,
        )

    return factory


def main() -> int:
    """Run the dual-path parity validation on a real machine and print the report.

    Usage:
        python -m scripts.kernel_validation.runner [--browser] [--timeout S]
                                                   [--category NAME] [--only ID,ID]

    Live scenarios are SKIPPED under FRIDAY_DRY_RUN (never fabricated). Changes no
    production default: the kernel/bridge are constructed per run and the
    ``FRIDAY_USE_KERNEL_EXECUTION`` flag is restored after every scenario.
    """
    import concurrent.futures as _cf

    # The parity report contains non-ASCII agreement marks. A Windows console
    # defaults to cp1252, which cannot encode them, so force UTF-8 on stdout
    # (errors="replace" keeps output flowing even on an exotic terminal).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - reconfigure is unavailable on some streams
        pass

    print("=" * 60)
    print("  FRIDAY M13 — Legacy vs Kernel Parity Validation")
    print("=" * 60)

    if _is_dry_run():
        print("\n[dry-run] FRIDAY_DRY_RUN=1 — live scenarios skipped, nothing fabricated.")

    router = None
    if not _is_dry_run():
        router = _build_model_router()
        if router is None:
            print("\n[warn] No model providers available (set NVIDIA_API_KEY).")
            print("       Live scenarios cannot execute; nothing will be fabricated.\n")

    browser = _maybe_start_browser() if router is not None else None
    factory = _real_operator_factory(router, browser) if router is not None else (
        lambda g, **kw: None
    )

    try:
        timeout_s = max(1.0, float(_parse_flag_value("timeout", "180") or 180))
    except ValueError:
        timeout_s = 180.0

    scenarios = list(all_scenarios())
    category = _parse_flag_value("category")
    if category:
        scenarios = [s for s in scenarios if s.category == category]
        print(f"[info] category filter: {category} ({len(scenarios)} scenarios)")
    only = _parse_flag_value("only")
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        scenarios = [s for s in scenarios if s.id in wanted]
        print(f"[info] id filter: {sorted(wanted)} ({len(scenarios)} scenarios)")

    runner = ValidationRunner(factory, browser_controller=browser)
    pairs: List[Tuple[ValidationEvidence, ValidationEvidence]] = []

    print(f"\n[info] per-scenario timeout: {timeout_s:.0f}s "
          f"({len(scenarios)} scenarios, both paths each)")

    for scenario in scenarios:
        print(f"    [scenario] {scenario.id} ... ", end="", flush=True)
        started = time.perf_counter()
        pool = None
        try:
            pool = _cf.ThreadPoolExecutor(max_workers=1)
            fut = pool.submit(runner.run_scenario, scenario)
            legacy_ev, kernel_ev = fut.result(timeout=timeout_s)
            pool.shutdown(wait=False)
            pool = None
            dt = time.perf_counter() - started
            print(f"legacy={legacy_ev.result} kernel={kernel_ev.result} ({dt:.1f}s)",
                  flush=True)
        except _cf.TimeoutError:
            dt = time.perf_counter() - started
            print(f"TIMEOUT (>{timeout_s:.0f}s) — recorded as fail", flush=True)
            legacy_ev = ValidationEvidence(
                scenario.id, "legacy", "fail", latency_ms=dt * 1000,
                error=f"timeout>{timeout_s:.0f}s")
            kernel_ev = ValidationEvidence(
                scenario.id, "kernel", "fail", latency_ms=dt * 1000,
                error=f"timeout>{timeout_s:.0f}s")
            if pool is not None:
                pool.shutdown(wait=False)
                pool = None
        except Exception as exc:  # noqa: BLE001 — a failure is recorded, not raised
            dt = time.perf_counter() - started
            print(f"error: {type(exc).__name__} — recorded as fail", flush=True)
            legacy_ev = ValidationEvidence(
                scenario.id, "legacy", "fail", latency_ms=dt * 1000, error=str(exc))
            kernel_ev = ValidationEvidence(
                scenario.id, "kernel", "fail", latency_ms=dt * 1000, error=str(exc))
            if pool is not None:
                pool.shutdown(wait=False)
                pool = None
        pairs.append((legacy_ev, kernel_ev))

    from scripts.kernel_validation.report import render_markdown

    report = render_markdown(pairs)
    print("\n" + report)

    # Persist the report so a long live run's result survives the console session.
    out_path = _parse_flag_value("out")
    if out_path:
        try:
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_text(report, encoding="utf-8")
            print(f"[ok] Parity report written to {out_path}")
        except OSError as exc:
            print(f"[warn] could not write report to {out_path}: {exc}")

    if browser is not None:
        try:
            browser.stop()
            print("[ok] Browser controller stopped.")
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":  # pragma: no cover - manual real-machine entry point
    raise SystemExit(main())
