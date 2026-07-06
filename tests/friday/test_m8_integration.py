"""M8 Task 9.1 — kernel-event integration test (closed-loop causal order).

Builds a REAL ``CognitiveKernel``, registers the ``MemoryRuntime`` and attaches
the Reflection / Competence / Recovery engines, then drives one
``action.executed`` + ``verification.completed`` pair through the kernel event
bus. The test asserts that the closed learning loop happens purely via
``subscribe``/``publish_event`` (no subsystem is ever called directly) and that
the resulting kernel event stream contains, in causal order:

    verification.completed → memory.candidate → memory.integrated

and that ``competence.updated`` follows ``verification.completed``.

Runs under ``FRIDAY_DRY_RUN=1`` so no real filesystem/LLM/OS surface is touched.

Validates: Requirements 5.1, 6.2, 7.2
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from typing import Any, List

from friday.cognition.reflection import ReflectionEngine
from friday.competence.model import CompetenceModel
from friday.events.event import make_event
from friday.kernel.kernel import CognitiveKernel
from friday.memory.runtime import MemoryRuntime
from friday.recovery.engine import RecoveryEngine


class _FakeMemory:
    """Minimal FridayMemory surface used by MemoryRuntime under DRY_RUN.

    Records every integrated learning so ``get_context`` reflects what has been
    stored. Keeps the test hermetic (no disk, no real controller).
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


def test_m8_closed_loop_causal_order(tmp_path) -> None:
    # Unique store path per test so parallel/repeat runs never collide on disk.
    kernel = CognitiveKernel(
        store_path=str(tmp_path / "m8.jsonl"), auto_checkpoint_every=0
    )

    # Collector subscribed FIRST so it records every event in causal order.
    collected: List[str] = []
    kernel.subscribe("*", lambda event: collected.append(event.event_type))

    # Wire the four M8 subsystems — ALL communication is via kernel events.
    reflection = ReflectionEngine()
    reflection.attach(kernel)
    competence = CompetenceModel()
    competence.attach(kernel)
    recovery = RecoveryEngine()
    recovery.attach(kernel)
    memory = MemoryRuntime(memory=_FakeMemory())
    kernel.register_runtime(memory)

    kernel.start()
    try:
        # 1) Action carrying a prediction for goal g1 / (search, web).
        _publish(
            kernel,
            "action.executed",
            {
                "goal_id": "g1",
                "capability": "search",
                "environment": "web",
                "prediction": {
                    "expected_beliefs": ["found info"],
                    "confidence": 0.6,
                    "reversible": True,
                },
            },
        )
        # 2) Verification confirms the prediction (satisfied, observed matches).
        #    Handlers run synchronously, so once this returns the entire causal
        #    chain (candidate → integrated, competence.updated) is already logged.
        _publish(
            kernel,
            "verification.completed",
            {
                "goal_id": "g1",
                "capability": "search",
                "environment": "web",
                "satisfied": True,
                "observed_beliefs": ["found info"],
            },
        )
    finally:
        kernel.shutdown()

    # The loop must have flowed entirely through the kernel bus.
    assert "verification.completed" in collected
    assert "memory.candidate" in collected
    assert "memory.integrated" in collected
    assert "competence.updated" in collected

    # Causal order (use first-occurrence index; robust to any duplicate delivery
    # from the runtime being subscribed to both "*" and "memory.candidate").
    i_ver = collected.index("verification.completed")
    i_cand = collected.index("memory.candidate")
    i_int = collected.index("memory.integrated")
    i_comp = collected.index("competence.updated")

    assert i_ver < i_cand, "memory.candidate must follow verification.completed"
    assert i_cand < i_int, "memory.integrated must follow memory.candidate"
    assert i_ver < i_comp, "competence.updated must follow verification.completed"

    # NOTE: no subsystem method is invoked directly anywhere in this test —
    # every interaction is via kernel.subscribe / kernel.publish_event, which
    # structurally proves the Req 5.1 kernel-event isolation.
