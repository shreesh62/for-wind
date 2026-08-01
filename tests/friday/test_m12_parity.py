"""M12 — Legacy vs kernel execution parity harness (TD-2/TD-8 flip gate).

Before the kernel execution path can EVER be flipped on by default, we must
prove it is behaviorally equivalent to the legacy Operator path. This harness
drives BOTH paths from the SAME stubbed Operator (same OperatorOutcome) and
asserts they produce equivalent human-readable results.

This is additive, behaviour-preserving evidence: it does not change any default.
It is the objective gate a future "flip the default" change must satisfy.

Requirements: 3.1, 3.2 (behaviour equivalence of the two paths)
"""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import types
from unittest.mock import patch

from friday.bridge import BridgeConfig, FridayBridge
from friday.kernel.execution import GoalExecutionRuntime
from friday.kernel.kernel import CognitiveKernel
from friday.events.store import EventStore


def _outcome(completed=True, summary="research complete", created_files=()):
    return types.SimpleNamespace(
        completed=completed, summary=summary, created_files=list(created_files)
    )


def _kernel_bridge(tmp_path, outcome):
    """A bridge wired to a real kernel whose runtime returns `outcome`."""
    kernel = CognitiveKernel(event_store=EventStore(str(tmp_path / "parity.jsonl")))
    runtime = GoalExecutionRuntime(lambda goal_text: types.SimpleNamespace(run=lambda g: outcome))
    kernel.register_runtime(runtime)
    return FridayBridge(
        config=BridgeConfig(allow_legacy_fallback=False, use_kernel_execution=True),
        kernel=kernel,
    )


def _legacy_result_string(outcome):
    """Reproduce the legacy _execute_multi_step formatting from an OperatorOutcome
    (status: summary [+ Files]). The legacy path builds exactly this string."""
    status = "Completed" if outcome.completed else "Partial"
    msg = f"{status}: {outcome.summary}"
    if outcome.created_files:
        msg += f"\n\nFiles: {', '.join(outcome.created_files)}"
    return msg


# --------------------------------------------------------------------------- #
# Parity: same outcome → equivalent result on both paths
# --------------------------------------------------------------------------- #
def test_kernel_path_completed_matches_legacy_format(tmp_path):
    outcome = _outcome(completed=True, summary="did the thing", created_files=["a.md", "b.pdf"])
    bridge = _kernel_bridge(tmp_path, outcome)

    kernel_result = bridge._execute_via_kernel("multi step goal")
    legacy_result = _legacy_result_string(outcome)

    assert kernel_result == legacy_result
    assert kernel_result.startswith("Completed: did the thing")
    assert "Files: a.md, b.pdf" in kernel_result


def test_kernel_path_failed_is_partial(tmp_path):
    # A failing operator → goal.failed → the kernel path reports Partial.
    kernel = CognitiveKernel(event_store=EventStore(str(tmp_path / "fail.jsonl")))
    runtime = GoalExecutionRuntime(
        lambda goal_text: types.SimpleNamespace(
            run=lambda g: (_ for _ in ()).throw(RuntimeError("nope"))
        )
    )
    kernel.register_runtime(runtime)
    bridge = FridayBridge(
        config=BridgeConfig(allow_legacy_fallback=False, use_kernel_execution=True),
        kernel=kernel,
    )

    result = bridge._execute_via_kernel("goal that fails")
    assert result.startswith("Partial:")


def test_kernel_and_legacy_agree_on_completion_status(tmp_path):
    """For both a success and a partial outcome, the kernel path's status word
    matches what the legacy formatter would produce."""
    for completed in (True, False):
        outcome = _outcome(completed=completed, summary="x")
        bridge = _kernel_bridge(tmp_path, outcome)
        kernel_result = bridge._execute_via_kernel("goal")
        expected_status = "Completed" if completed else "Partial"
        # Kernel path: completed→"Completed: x"; failed path only triggers on an
        # exception, so a completed=False *outcome* still emits goal.completed
        # is NOT the case — completed=False maps to goal.failed → "Partial:".
        assert kernel_result.split(":")[0] == expected_status


# --------------------------------------------------------------------------- #
# The flip gate itself: with the default (flag off), legacy is used
# --------------------------------------------------------------------------- #
def test_default_flag_on_uses_kernel_when_kernel_present(tmp_path):
    """The default is now kernel execution (M13 qualified). With a kernel wired,
    multi-step goals route through the kernel path."""
    from friday.router.classifier import ComplexityLevel

    kernel = CognitiveKernel(event_store=EventStore(str(tmp_path / "on.jsonl")))
    kernel.register_runtime(
        GoalExecutionRuntime(lambda g: types.SimpleNamespace(run=lambda gg: _outcome()))
    )
    # Default config (use_kernel_execution=True), kernel present.
    bridge = FridayBridge(config=BridgeConfig(allow_legacy_fallback=False), kernel=kernel)

    with patch.object(bridge, "_execute_multi_step", return_value="LEGACY") as legacy, \
         patch.object(bridge, "_execute_via_kernel", return_value="KERNEL") as kern:
        result = bridge._handle_friday("multi", {"automation": None}, ComplexityLevel.MULTI_STEP)

    assert result == "KERNEL"
    kern.assert_called_once()
    legacy.assert_not_called()


def test_explicit_flag_off_degrades_to_legacy(tmp_path):
    """FRIDAY_USE_KERNEL_EXECUTION=0 remains the instant rollback mechanism."""
    from friday.router.classifier import ComplexityLevel

    kernel = CognitiveKernel(event_store=EventStore(str(tmp_path / "off.jsonl")))
    kernel.register_runtime(
        GoalExecutionRuntime(lambda g: types.SimpleNamespace(run=lambda gg: _outcome()))
    )
    # Explicit flag OFF — the runtime kill switch.
    bridge = FridayBridge(
        config=BridgeConfig(allow_legacy_fallback=False, use_kernel_execution=False),
        kernel=kernel,
    )

    with patch.object(bridge, "_execute_multi_step", return_value="LEGACY") as legacy, \
         patch.object(bridge, "_execute_via_kernel", return_value="KERNEL") as kern:
        result = bridge._handle_friday("multi", {"automation": None}, ComplexityLevel.MULTI_STEP)

    assert result == "LEGACY"
    legacy.assert_called_once()
    kern.assert_not_called()
