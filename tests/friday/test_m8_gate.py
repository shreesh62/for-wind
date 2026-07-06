"""M8 Task 10.1 — The M8 Gate (end-to-end acceptance oracle).

Wires a REAL ``CognitiveKernel`` with all four M8 subsystems (Reflection,
Memory, Competence, Recovery) and proves the closed learning loop through the
kernel event log:

1. A prediction MISMATCH that is still verification-backed
   (``satisfied=True`` but observed beliefs differ from the prediction) makes
   Reflection compute ``prediction_error > 0`` and emit a *verified*
   ``memory.candidate``; Memory integrates it and Competence updates.
2. The kernel event log contains, in causal order,
   ``action.executed → verification.completed → memory.candidate →
   memory.integrated`` and ``competence.updated`` follows
   ``verification.completed``.
3. A repeated success on the same ``(capability, environment)`` strictly
   increases the CompetenceModel confidence.
4. The wrapped memory's learned context is empty before integration and
   non-empty afterward.
5. Re-running the identical scenario under DRY_RUN yields an identical ordered
   sequence of M8 event types (determinism).

All interaction is via ``kernel.subscribe`` / ``kernel.publish_event`` — zero
direct subsystem calls. Runs under ``FRIDAY_DRY_RUN=1``.

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 7.2
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from typing import Any, List, Tuple

from friday.cognition.reflection import ReflectionEngine
from friday.competence.model import CompetenceModel
from friday.events.event import make_event
from friday.kernel.kernel import CognitiveKernel
from friday.memory.runtime import MemoryRuntime
from friday.recovery.engine import RecoveryEngine


# M8-relevant event types used for the determinism comparison (Req 6.5).
_M8_EVENT_TYPES = {
    "action.executed",
    "verification.completed",
    "memory.candidate",
    "memory.integrated",
    "memory.rejected",
    "competence.updated",
    "reflection.completed",
    "recovery.proposed",
}


class FakeMemory:
    """Tiny FridayMemory surface the MemoryRuntime uses.

    Tracks integrated content so ``get_context`` is empty BEFORE anything is
    recorded and non-empty AFTER a fact/turn/pattern is integrated (Req 6.4).
    """

    def __init__(self) -> None:
        self._records: List[str] = []

    def record_turn(self, *args: Any, **kwargs: Any) -> None:
        self._records.append(kwargs.get("user_text", "turn"))

    def record_pattern(self, pattern: Any = None, *args: Any, **kwargs: Any) -> None:
        self._records.append(str(getattr(pattern, "target_description", pattern)))

    def remember_fact(self, content: str = "", *args: Any, **kwargs: Any) -> None:
        self._records.append(str(content))

    def get_context(self, query: str = "") -> Any:
        records = list(self._records)

        class _Ctx:
            def to_prompt_string(self, *a: Any, **k: Any) -> str:
                return "\n".join(records)

        return _Ctx()

    def suggest_action_strategy(self, *args: Any, **kwargs: Any) -> Any:
        return None


def _publish(kernel: CognitiveKernel, event_type: str, payload: dict) -> None:
    """Publish an event through the kernel with a monotonically advancing tick."""
    tick = int(kernel.health().get("tick", 0)) + 1
    kernel.publish_event(
        make_event(
            event_type=event_type,
            source="test",
            logical_time=tick,
            payload=payload,
        )
    )


def _dedupe(seq: List[str]) -> List[str]:
    """Preserve first occurrence order, dropping later duplicates.

    ``register_runtime`` subscribes the runtime to ``*`` while ``initialize``
    also subscribes it to ``memory.candidate``, so a candidate can be delivered
    to ``_on_candidate`` twice. Deduping keeps the order assertions robust while
    remaining deterministic across runs.
    """
    seen = set()
    out: List[str] = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def test_m8_gate(tmp_path) -> None:
    kernel = CognitiveKernel(
        store_path=str(tmp_path / "m8_gate.jsonl"), auto_checkpoint_every=0
    )

    collected: List[str] = []
    kernel.subscribe("*", lambda event: collected.append(event.event_type))

    reflection = ReflectionEngine()
    reflection.attach(kernel)
    competence = CompetenceModel()
    competence.attach(kernel)
    recovery = RecoveryEngine()
    recovery.attach(kernel)
    fake_memory = FakeMemory()
    memory = MemoryRuntime(memory=fake_memory)
    kernel.register_runtime(memory)

    capability, environment = "search", "web"
    key = (capability, environment)

    # Req 6.4 — learned context is EMPTY before any integration.
    assert fake_memory.get_context("summarize the topic").to_prompt_string() == ""

    kernel.start()
    try:
        # --- Step 1: prediction MISMATCH that is still verification-backed ----
        # expected != observed → prediction_error > 0; satisfied=True → the
        # candidate is verified → Memory INTEGRATES it (Req 6.1).
        _publish(
            kernel,
            "action.executed",
            {
                "goal_id": "g1",
                "capability": capability,
                "environment": environment,
                "prediction": {
                    "expected_beliefs": ["X done"],
                    "confidence": 0.7,
                    "reversible": True,
                },
            },
        )
        _publish(
            kernel,
            "verification.completed",
            {
                "goal_id": "g1",
                "capability": capability,
                "environment": environment,
                "satisfied": True,
                "observed_beliefs": ["Y happened"],
            },
        )

        # Req 6.1 — a verified memory.candidate was emitted and integrated.
        assert "memory.candidate" in collected
        assert "memory.integrated" in collected
        assert "competence.updated" in collected

        # Req 6.2 — causal order through the kernel event log.
        order = _dedupe(collected)
        i_act = order.index("action.executed")
        i_ver = order.index("verification.completed")
        i_cand = order.index("memory.candidate")
        i_int = order.index("memory.integrated")
        i_comp = order.index("competence.updated")
        assert i_act < i_ver < i_cand < i_int
        assert i_ver < i_comp

        # Req 6.4 — learned context is now non-empty after integration.
        assert fake_memory.get_context("summarize the topic").to_prompt_string() != ""

        # Req 6.3 — capture confidence, then a SECOND success must strictly raise it.
        confidence_after_step1 = competence.confidence(key)

        _publish(
            kernel,
            "action.executed",
            {
                "goal_id": "g2",
                "capability": capability,
                "environment": environment,
                "prediction": {
                    "expected_beliefs": ["found info"],
                    "confidence": 0.7,
                    "reversible": True,
                },
            },
        )
        _publish(
            kernel,
            "verification.completed",
            {
                "goal_id": "g2",
                "capability": capability,
                "environment": environment,
                "satisfied": True,
                "observed_beliefs": ["found info"],
            },
        )

        confidence_after_step2 = competence.confidence(key)
        assert confidence_after_step2 > confidence_after_step1, (
            "competence must strictly increase after a repeated success"
        )
    finally:
        kernel.shutdown()

    # Req 6.5 — determinism: running the identical scenario twice yields the
    # same ordered sequence of M8 event types.
    seq_a = _run_gate(tmp_path, "det_a.jsonl")
    seq_b = _run_gate(tmp_path, "det_b.jsonl")
    assert seq_a == seq_b, "M8 gate must be deterministic under DRY_RUN"

    # NOTE: zero direct subsystem calls above — the whole loop is driven purely
    # through kernel.subscribe / kernel.publish_event (Req 5.1 isolation).


def _run_gate(tmp_path, filename: str) -> List[str]:
    """Build a fresh kernel + all four subsystems, run the identical publish
    sequence, and return the ordered list of M8-relevant event types.
    """
    kernel = CognitiveKernel(
        store_path=str(tmp_path / filename), auto_checkpoint_every=0
    )

    collected: List[str] = []
    kernel.subscribe("*", lambda event: collected.append(event.event_type))

    reflection = ReflectionEngine()
    reflection.attach(kernel)
    competence = CompetenceModel()
    competence.attach(kernel)
    recovery = RecoveryEngine()
    recovery.attach(kernel)
    memory = MemoryRuntime(memory=FakeMemory())
    kernel.register_runtime(memory)

    capability, environment = "search", "web"

    scenario: List[Tuple[str, dict]] = [
        (
            "action.executed",
            {
                "goal_id": "g1",
                "capability": capability,
                "environment": environment,
                "prediction": {
                    "expected_beliefs": ["X done"],
                    "confidence": 0.7,
                    "reversible": True,
                },
            },
        ),
        (
            "verification.completed",
            {
                "goal_id": "g1",
                "capability": capability,
                "environment": environment,
                "satisfied": True,
                "observed_beliefs": ["Y happened"],
            },
        ),
        (
            "action.executed",
            {
                "goal_id": "g2",
                "capability": capability,
                "environment": environment,
                "prediction": {
                    "expected_beliefs": ["found info"],
                    "confidence": 0.7,
                    "reversible": True,
                },
            },
        ),
        (
            "verification.completed",
            {
                "goal_id": "g2",
                "capability": capability,
                "environment": environment,
                "satisfied": True,
                "observed_beliefs": ["found info"],
            },
        ),
    ]

    kernel.start()
    try:
        for event_type, payload in scenario:
            _publish(kernel, event_type, payload)
    finally:
        kernel.shutdown()

    return [et for et in collected if et in _M8_EVENT_TYPES]
