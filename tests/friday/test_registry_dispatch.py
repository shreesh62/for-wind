"""Registry-backed dispatch in the executor.

The planner selects tools from the ToolRegistry, but the executor only knew its
own hardcoded capability table. A capability with no built-in handler fell through
to a "Executed: <description>" message — reporting work that never happened. These
tests pin that a registered tool's handler is actually invoked, that built-ins keep
precedence, and that handler failures are reported rather than swallowed.
"""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import pytest

from friday.executor import ExecutionContext, GoalExecutor
from friday.safety.action_gate import ActionGate
from friday.tools.registry import Tool, ToolCapability, ToolRegistry


def _step(capability, target="t"):
    class _S:
        pass

    s = _S()
    s.capability = capability
    s.target = target
    s.description = f"step {capability}"
    s.can_skip = False
    return s


def _executor(registry=None):
    # Approve everything so these tests isolate dispatch, not the permission gate.
    return GoalExecutor(
        registry=registry, permission_gate=ActionGate(approval_fn=lambda p: True)
    )


class _Outcome:
    def __init__(self, ok=True, message="did the thing", error=""):
        self.is_success = ok
        self.message = message
        self.error = error


# A capability with no built-in handler in _dispatch_table.
_UNHANDLED = ToolCapability.CHECK_PROCESS


def test_unhandled_capability_without_registry_keeps_old_fallback():
    ctx = ExecutionContext(goal="g")
    out = _executor()._execute_step(_step(_UNHANDLED), ctx)
    assert out.startswith("Executed:")


def test_registered_handler_is_invoked_for_an_unhandled_capability():
    calls = []
    registry = ToolRegistry()
    registry.register(Tool(
        name="custom.check",
        description="check a process",
        capabilities=[_UNHANDLED],
        handler=lambda params: calls.append(params) or _Outcome(message="checked"),
    ))

    ctx = ExecutionContext(goal="my goal")
    out = _executor(registry)._execute_step(_step(_UNHANDLED, "notepad"), ctx)

    assert calls, "the registered handler must actually be called"
    assert calls[0]["target"] == "notepad"
    assert calls[0]["goal"] == "my goal"
    assert "custom.check" in out and "checked" in out


def test_async_handler_is_supported():
    async def _handler(params):
        return _Outcome(message="async done")

    registry = ToolRegistry()
    registry.register(Tool(
        name="custom.async",
        description="async tool",
        capabilities=[_UNHANDLED],
        handler=_handler,
    ))

    ctx = ExecutionContext(goal="g")
    out = _executor(registry)._execute_step(_step(_UNHANDLED), ctx)
    assert "async done" in out


def test_handler_failure_is_reported_not_swallowed():
    def _handler(params):
        raise RuntimeError("tool exploded")

    registry = ToolRegistry()
    registry.register(Tool(
        name="custom.broken",
        description="broken tool",
        capabilities=[_UNHANDLED],
        handler=_handler,
    ))

    ctx = ExecutionContext(goal="g")
    out = _executor(registry)._execute_step(_step(_UNHANDLED), ctx)
    assert "custom.broken" in out
    assert "tool exploded" in out


def test_unsuccessful_outcome_is_reported_as_such():
    registry = ToolRegistry()
    registry.register(Tool(
        name="custom.failing",
        description="failing tool",
        capabilities=[_UNHANDLED],
        handler=lambda params: _Outcome(ok=False, error="no such process"),
    ))

    ctx = ExecutionContext(goal="g")
    out = _executor(registry)._execute_step(_step(_UNHANDLED), ctx)
    assert "did not succeed" in out
    assert "no such process" in out


def test_handlerless_registered_tool_does_not_claim_success():
    """A metadata-only tool must not be reported as having run."""
    registry = ToolRegistry()
    registry.register(Tool(
        name="custom.metadata_only",
        description="no handler",
        capabilities=[_UNHANDLED],
    ))

    ctx = ExecutionContext(goal="g")
    out = _executor(registry)._execute_step(_step(_UNHANDLED), ctx)
    assert "custom.metadata_only" not in out
    assert out.startswith("Executed:")


def test_builtin_handlers_keep_precedence_over_the_registry():
    """Registry dispatch must not silently reroute a proven built-in path."""
    calls = []
    registry = ToolRegistry()
    registry.register(Tool(
        name="custom.generate",
        description="would hijack generation",
        capabilities=[ToolCapability.GENERATE_TEXT],
        handler=lambda params: calls.append(params) or _Outcome(),
    ))

    ctx = ExecutionContext(goal="g")
    out = _executor(registry)._execute_step(_step(ToolCapability.GENERATE_TEXT), ctx)
    assert not calls, "a built-in capability must keep using its built-in handler"
    assert "Generated" in out


def test_registry_lookup_failure_is_reported():
    class _BrokenRegistry:
        def find_tools(self, capability, **kwargs):
            raise RuntimeError("registry corrupt")

    ctx = ExecutionContext(goal="g")
    out = _executor(_BrokenRegistry())._execute_step(_step(_UNHANDLED), ctx)
    assert "Registry lookup failed" in out


def test_the_operator_gives_its_executor_the_planner_registry():
    """The planner and executor must agree on the tool set."""
    from friday.operator import Operator

    operator = Operator(model_router=None, max_iterations=1)
    assert operator._executor._registry is operator._registry


def test_registry_dispatch_still_respects_the_permission_gate():
    """A registry tool must not become a way around the gate."""
    calls = []
    registry = ToolRegistry()
    registry.register(Tool(
        name="custom.risky",
        description="risky",
        capabilities=[ToolCapability.UPLOAD_FILE],
        handler=lambda params: calls.append(params) or _Outcome(),
    ))

    # Default gate: no approval handler, so an irreversible capability is withheld.
    executor = GoalExecutor(registry=registry)
    ctx = ExecutionContext(goal="g")
    out = executor._execute_step(_step(ToolCapability.UPLOAD_FILE), ctx)
    assert "WITHHELD" in out
    assert not calls, "a withheld step must never reach the tool handler"
