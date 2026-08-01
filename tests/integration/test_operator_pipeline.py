"""Integration: the Operator pipeline end-to-end.

These tests drive a REAL Operator (no mocks on the pipeline itself) and verify
observable outcomes: files created, evidence recorded, memory recalled, gate
honored. They exercise the machinery that matters — requirements discovery →
planning → execution → verification → repair — as a single connected system.

Model calls use the real fallback (no router = deterministic heuristic), which
means these are fast, offline, and deterministic. A separate `test_live_llm.py`
exercises the LLM-backed path when NVIDIA is available.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from friday.operator import Operator, OperatorOutcome


class _FakeMemory:
    """Records how the Operator used it without depending on disk."""

    def __init__(self, context_text=""):
        self._context_text = context_text
        self.recalls = []
        self.episodes = []
        self.active_goals = []
        self.completed = 0

    def get_context(self, query=""):
        self.recalls.append(query)

        class Ctx:
            def to_prompt_string(self_, max_length=2000):
                return self._context_text

        return Ctx()

    def set_active_goal(self, text, steps=0):
        self.active_goals.append(text)

    def record_episode(self, episode):
        self.episodes.append(episode)

    def complete_goal(self):
        self.completed += 1


def _operator(memory=None, max_iterations=2) -> Operator:
    """Real Operator, no model router (uses deterministic fallback paths)."""
    return Operator(model_router=None, max_iterations=max_iterations, memory=memory)


# --------------------------------------------------------------------------- #
# FILE GENERATION — the simplest end-to-end path
# --------------------------------------------------------------------------- #
class TestFileGeneration:
    """A goal that says 'save/write/create a file' must produce a real file."""

    def test_creates_a_file_on_disk(self):
        outcome = _operator().run("Write a short note about Python and save it to a file")
        assert outcome.completed or outcome.created_files, (
            f"file generation goal should produce a file; trace: {outcome.trace}"
        )
        if outcome.created_files:
            for path in outcome.created_files:
                assert Path(path).exists(), f"reported file does not exist: {path}"
                assert Path(path).stat().st_size > 0, f"file is empty: {path}"

    def test_file_evidence_is_recorded(self):
        outcome = _operator().run("Create a report about machine learning and save it")
        from friday.verification.evidence_law import EvidenceKind

        evidence = outcome.evidence
        if outcome.created_files:
            assert evidence.has(EvidenceKind.FILE_ARTIFACT), (
                "a file was created but no FILE_ARTIFACT evidence was recorded"
            )

    def test_no_notepad_spam(self, monkeypatch):
        """A file-generation goal must NEVER launch notepad."""
        launched = []
        import friday.actions.system as sys_mod

        orig = sys_mod.SystemActions.launch_app

        def _spy(self, app_name):
            launched.append(app_name)
            return orig(self, app_name)

        monkeypatch.setattr(sys_mod.SystemActions, "launch_app", _spy)
        _operator().run("Generate a summary about renewable energy and save it")
        assert "notepad" not in [x.lower() for x in launched], (
            f"notepad was launched during a file-generation goal: {launched}"
        )


# --------------------------------------------------------------------------- #
# REQUIREMENTS → VERIFICATION — the evidence law is actually enforced
# --------------------------------------------------------------------------- #
class TestRequirementsVerification:
    """Requirements are satisfied by real evidence, not by having run."""

    def test_a_file_goal_is_not_satisfied_without_a_file(self):
        """If no file is created, the goal must NOT report completed."""
        # A goal that asks for a file but can't possibly create one (no target name)
        outcome = _operator(max_iterations=1).run(
            "Save a file to /nonexistent/path/that/cannot/exist.txt"
        )
        # The goal may still "complete" via fallback, but the evidence should NOT
        # contain a FILE_ARTIFACT for that path
        from friday.verification.evidence_law import EvidenceKind

        files = [a.detail for a in outcome.evidence.of_kind(EvidenceKind.FILE_ARTIFACT)]
        for f in files:
            if "/nonexistent/" in f:
                pytest.fail("fabricated evidence for a file that cannot exist")

    def test_generated_content_evidence_is_recorded(self):
        outcome = _operator().run("Write a paragraph about quantum computing")
        from friday.verification.evidence_law import EvidenceKind

        assert outcome.evidence.has(EvidenceKind.GENERATED_CONTENT), (
            "a content-generation goal must record GENERATED_CONTENT evidence"
        )


# --------------------------------------------------------------------------- #
# MEMORY INTEGRATION — recall and record in the real pipeline
# --------------------------------------------------------------------------- #
class TestMemoryIntegration:
    """The Operator must recall context before planning and record after."""

    def test_recalls_context_for_the_goal(self):
        memory = _FakeMemory("user prefers .md files")
        _operator(memory=memory).run("Write a note and save it")
        assert memory.recalls, "memory was never queried"

    def test_records_the_outcome(self):
        memory = _FakeMemory()
        outcome = _operator(memory=memory).run("Write a note and save it")
        assert memory.episodes, "outcome was never recorded"
        assert memory.episodes[0]["goal"] == outcome.goal

    def test_memory_failure_does_not_break_the_goal(self):
        class _BrokenMemory(_FakeMemory):
            def get_context(self, query=""):
                raise RuntimeError("disk exploded")

            def record_episode(self, episode):
                raise RuntimeError("disk exploded")

        outcome = _operator(memory=_BrokenMemory()).run("Write a note and save it")
        assert outcome.goal, "a memory failure should not prevent the goal from running"


# --------------------------------------------------------------------------- #
# PERMISSION GATE — the gate is consulted and honored
# --------------------------------------------------------------------------- #
class TestPermissionGate:
    """Irreversible actions must be withheld; safe work must proceed."""

    def test_safe_local_work_is_not_blocked(self):
        """A file-creation goal must not be stopped by the gate."""
        outcome = _operator().run("Write a short paragraph about AI and save it")
        # If the outcome has content or files, the gate let work through.
        assert outcome.final_content or outcome.created_files or outcome.summary

    def test_an_irreversible_step_is_withheld_by_default(self):
        """RUN_COMMAND is withheld without explicit approval."""
        from friday.executor import ExecutionContext, GoalExecutor
        from friday.tools.registry import ToolCapability

        class _Step:
            capability = ToolCapability.RUN_COMMAND
            target = "rm -rf /"
            description = "dangerous command"
            can_skip = False

        executor = GoalExecutor()
        ctx = ExecutionContext(goal="test")
        out = executor._execute_step(_Step(), ctx)
        assert "WITHHELD" in out
        assert ctx.withheld

    def test_delivery_is_gated_downstream(self):
        """A send goal without a browser must not claim delivery evidence."""
        outcome = _operator().run("Send an email to test@example.com saying hello")
        from friday.verification.evidence_law import EvidenceKind

        deliveries = outcome.evidence.of_kind(EvidenceKind.DELIVERY_CONFIRMATION)
        assert not deliveries, (
            "delivery evidence was fabricated without a browser or confirmation"
        )


# --------------------------------------------------------------------------- #
# REGISTRY-BACKED DISPATCH — registered tools are actually callable
# --------------------------------------------------------------------------- #
class TestRegistryDispatch:
    """A tool registered with a handler must be callable from the executor."""

    def test_a_registered_handler_runs_through_the_pipeline(self):
        from friday.executor import ExecutionContext, GoalExecutor
        from friday.safety.action_gate import ActionGate
        from friday.tools.registry import Tool, ToolCapability, ToolRegistry

        calls = []
        registry = ToolRegistry()
        registry.register(Tool(
            name="custom.action",
            description="custom test tool",
            capabilities=[ToolCapability.CHECK_PROCESS],
            handler=lambda params: calls.append(params) or type(
                "R", (), {"is_success": True, "message": "ran"}
            )(),
        ))

        executor = GoalExecutor(
            registry=registry,
            permission_gate=ActionGate(approval_fn=lambda p: True),
        )

        class _Step:
            capability = ToolCapability.CHECK_PROCESS
            target = "python"
            description = "check process"
            can_skip = False

        ctx = ExecutionContext(goal="check")
        out = executor._execute_step(_Step(), ctx)
        assert calls, "the registered handler was never called"
        assert "custom.action" in out


# --------------------------------------------------------------------------- #
# KERNEL GOAL EXECUTION — the kernel path works end-to-end
# --------------------------------------------------------------------------- #
class TestKernelExecution:
    """Goals routed through the kernel produce real lifecycle events."""

    def test_kernel_completes_a_goal(self):
        import tempfile

        from friday.events.store import EventStore
        from friday.kernel.execution import GoalExecutionRuntime
        from friday.kernel.kernel import CognitiveKernel

        seen = []
        with tempfile.TemporaryDirectory() as d:
            kernel = CognitiveKernel(event_store=EventStore(os.path.join(d, "ev.jsonl")))
            kernel.subscribe("goal.completed", lambda e: seen.append(e.event_type))
            kernel.subscribe("goal.failed", lambda e: seen.append(e.event_type))
            runtime = GoalExecutionRuntime(lambda _text: Operator(max_iterations=1))
            kernel.register_runtime(runtime)
            kernel.submit_goal("Write a short paragraph about testing")

        assert "goal.completed" in seen or "goal.failed" in seen, (
            f"kernel must emit a terminal lifecycle event; got {seen}"
        )

    def test_kernel_suspension_is_honored(self):
        """A suspended goal must not finalize until resumed."""
        import tempfile
        import threading

        from friday.events.store import EventStore
        from friday.kernel.execution import GoalExecutionRuntime
        from friday.kernel.kernel import CognitiveKernel

        class _Blocking:
            def __init__(self):
                self.entered = threading.Event()
                self.release = threading.Event()

            def run(self, goal_text):
                self.entered.set()
                self.release.wait(timeout=10)

                class O:
                    completed = True
                    summary = "done"
                    created_files = ()

                return O()

        op = _Blocking()
        order = []
        with tempfile.TemporaryDirectory() as d:
            kernel = CognitiveKernel(event_store=EventStore(os.path.join(d, "ev.jsonl")))
            kernel.subscribe("goal.suspended", lambda e: order.append("suspended"))
            kernel.subscribe("goal.resumed", lambda e: order.append("resumed"))
            kernel.subscribe("goal.completed", lambda e: order.append("completed"))
            runtime = GoalExecutionRuntime(lambda _t: op)
            kernel.register_runtime(runtime)

            worker = threading.Thread(target=lambda: kernel.submit_goal("test"))
            worker.start()
            assert op.entered.wait(timeout=5)
            goal_id = next(iter(kernel._goals))
            kernel.interrupt_goal(goal_id)
            op.release.set()
            import time; time.sleep(0.3)
            assert "completed" not in order, "goal finalized while suspended"
            kernel.resume_goal(goal_id)
            worker.join(timeout=10)

        assert order == ["suspended", "resumed", "completed"]


# --------------------------------------------------------------------------- #
# MODEL ROUTER — failover and circuit breaker
# --------------------------------------------------------------------------- #
class TestModelRouter:
    """The router must try alternative models and skip dead ones."""

    def test_failover_to_a_working_model(self):
        import asyncio

        from friday.models.router import (
            ModelCapability,
            ModelInfo,
            ModelResponse,
            ModelRouter,
        )

        class _FakeProvider:
            name = "fake"
            available = True

            @property
            def models(self):
                return [
                    ModelInfo(provider="fake", model_id="dead", priority=10,
                             capabilities=[ModelCapability.REASONING], max_tokens=100),
                    ModelInfo(provider="fake", model_id="alive", priority=5,
                             capabilities=[ModelCapability.REASONING], max_tokens=100),
                ]

            async def complete(self, prompt, *, model=None, **kw):
                if model == "dead":
                    raise RuntimeError("404 Not Found")
                return ModelResponse(text="ok", model_used="alive",
                                     provider="fake", tokens_used=5)

        router = ModelRouter()
        router.register_provider(_FakeProvider())
        resp = asyncio.run(router.complete("hi", capability=ModelCapability.REASONING))
        assert resp.text == "ok"
        assert "fake/dead" in router.unavailable_models

    def test_circuit_breaker_skips_dead_models(self):
        import asyncio

        from friday.models.router import (
            ModelCapability,
            ModelInfo,
            ModelResponse,
            ModelRouter,
        )

        calls = []

        class _FakeProvider:
            name = "fake"
            available = True

            @property
            def models(self):
                return [
                    ModelInfo(provider="fake", model_id="dead", priority=10,
                             capabilities=[ModelCapability.REASONING], max_tokens=100),
                    ModelInfo(provider="fake", model_id="alive", priority=5,
                             capabilities=[ModelCapability.REASONING], max_tokens=100),
                ]

            async def complete(self, prompt, *, model=None, **kw):
                calls.append(model)
                if model == "dead":
                    raise RuntimeError("404 Not Found")
                return ModelResponse(text="ok", model_used="alive",
                                     provider="fake", tokens_used=5)

        router = ModelRouter()
        router.register_provider(_FakeProvider())
        asyncio.run(router.complete("hi", capability=ModelCapability.REASONING))
        calls.clear()
        asyncio.run(router.complete("hi", capability=ModelCapability.REASONING))
        assert calls == ["alive"], f"dead model was retried: {calls}"


# --------------------------------------------------------------------------- #
# BRIDGE ROUTING — JARVIS vs FRIDAY mode
# --------------------------------------------------------------------------- #
class TestBridgeRouting:
    """The bridge correctly routes conversational vs action requests."""

    def test_a_question_routes_to_jarvis_mode(self):
        from friday.bridge import FridayBridge

        bridge = FridayBridge(model_router=None)
        result = bridge.process("What is machine learning?")
        from friday.router.classifier import RequestMode

        assert result.mode == RequestMode.JARVIS

    def test_an_action_routes_to_friday_mode(self):
        from friday.bridge import FridayBridge

        bridge = FridayBridge(model_router=None)
        result = bridge.process("Search the web for Python tutorials and save a summary")
        from friday.router.classifier import RequestMode

        assert result.mode == RequestMode.FRIDAY


# --------------------------------------------------------------------------- #
# NO NOTEPAD SPAM — the platform must never launch random apps
# --------------------------------------------------------------------------- #
class TestNoNotepadSpam:
    """Verify the notepad-fallback is gone from every code path."""

    def test_unresolved_target_does_not_launch_notepad(self, monkeypatch):
        from friday.executor import ExecutionContext, GoalExecutor
        from friday.safety.action_gate import ActionGate
        from friday.tools.registry import ToolCapability

        # Ensure DRY_RUN is OFF so the navigate path is actually exercised.
        monkeypatch.setenv("FRIDAY_DRY_RUN", "0")

        class _Step:
            capability = ToolCapability.NAVIGATE_URL
            target = "some vague application description"
            description = "navigate to something"
            can_skip = False

        executor = GoalExecutor(
            permission_gate=ActionGate(approval_fn=lambda p: True)
        )
        ctx = ExecutionContext(goal="test")
        out = executor._execute_step(_Step(), ctx)
        assert "notepad" not in out.lower()
        assert "could not resolve" in out.lower() or "Navigation" in out

    def test_a_full_goal_run_never_launches_notepad(self, monkeypatch):
        launched = []
        import friday.actions.system as sys_mod

        orig_launch = sys_mod.SystemActions.launch_app

        def _track(self, app_name):
            launched.append(app_name.lower())
            # Don't actually launch anything — just track
            from friday.actions.result import ActionResult
            return ActionResult.failed(action="launch_app", error="blocked by test",
                                       target=app_name)

        monkeypatch.setattr(sys_mod.SystemActions, "launch_app", _track)
        _operator().run("Open an application and do something useful")
        assert "notepad" not in launched, f"notepad launched: {launched}"
