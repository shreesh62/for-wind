"""M24 (activation) — wire the failure→recovery/competence/reflection/observability
loop to a kernel in ONE reusable place.

M24 built the missing ``verification.completed`` producer; this helper attaches the
consumers so the loop is LIVE end-to-end. Any bootstrap (API server, tests, future
entrypoints) calls ``attach_reactive_loop(kernel)`` to get the identical wired loop,
rather than each duplicating the subscription dance (no duplicate systems).

The loop also attaches the M9 ``LearningEngine`` (the producer of ``learning.validated``),
so verified experience flowing through ReflectionEngine now yields real learning events —
making the M9→M17 skill-evolution chain complete in production (previously there was no
production producer of ``learning.validated``).

The M21 ``CapabilityMemory`` and ``PreferenceMemory`` tiers can also be attached opt-in
(exactly like ``failure_memory``): supply an instance to wire it, or leave it ``None`` so
nothing is attached and hermetic runs write no disk files.

Imports are function-local so importing this module never creates a package import
cycle and never pulls the heavy subsystems until wiring is actually requested.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ReactiveLoop:
    """The attached reactive-loop components (held so callers can inspect them)."""

    recovery: Any
    competence: Any
    reflection: Any
    failure_log: Optional[Any]
    failure_memory: Optional[Any] = None
    learning: Optional[Any] = None
    capability_memory: Optional[Any] = None
    preference_memory: Optional[Any] = None


def attach_reactive_loop(
    kernel: Any,
    *,
    recovery_engine: Any = None,
    competence_model: Any = None,
    reflection_engine: Any = None,
    failure_log: Any = None,
    failure_memory: Any = None,
    learning_engine: Any = None,
    capability_memory: Any = None,
    preference_memory: Any = None,
    enable_logging: bool = True,
) -> ReactiveLoop:
    """Attach recovery + competence + reflection (+ observability) to ``kernel``.

    Each component subscribes to ``verification.completed`` (and recovery/reflection
    also to their inputs), so publishing a verdict now drives the full loop:
    failure → recovery.proposed, competence.updated, reflection/memory candidates,
    and structured failure logs. The M9 ``LearningEngine`` is also attached: it
    consumes ``reflection.completed`` and produces ``learning.validated`` (plus
    ``learning.rejected``/``memory.candidate``/``learning.pattern_discovered``), so
    verified experience yields real learning events and the M9→M17 skill-evolution
    chain completes in production. All components isolate their own exceptions and
    never raise into the kernel tick loop.

    Passing an existing component reuses it (e.g. a shared ``CompetenceModel`` used
    for gating elsewhere) instead of constructing a fresh one.

    The opt-in ``capability_memory`` / ``preference_memory`` (M21 seven-tier memory)
    are attached only when supplied (like ``failure_memory``); default ``None`` means
    they are not attached, so hermetic runs never write memory files unbidden.
    """
    from friday.recovery.engine import RecoveryEngine
    from friday.competence.model import CompetenceModel
    from friday.cognition.reflection import ReflectionEngine
    from friday.observability.failure_log import FailureLogSubscriber
    from friday.learning.engine import LearningEngine

    recovery = recovery_engine if recovery_engine is not None else RecoveryEngine()
    competence = competence_model if competence_model is not None else CompetenceModel()
    reflection = reflection_engine if reflection_engine is not None else ReflectionEngine()
    learning = learning_engine if learning_engine is not None else LearningEngine()

    # Order matters: failure memory subscribes FIRST so it records the failure
    # before recovery (attached next) publishes the nested `recovery.proposed` that
    # annotates that record. Failure memory is opt-in (it persists to disk): attach
    # only when a caller supplies one, so hermetic tests never write files unbidden.
    if failure_memory is not None:
        failure_memory.attach(kernel)

    # Capability/Preference memory tiers (M21 slice 2) are opt-in the same way:
    # both persist to disk, so attach only when a caller supplies one (default
    # None → not attached, so hermetic tests write no disk files). CapabilityMemory
    # subscribes to `competence.updated` (published later by the CompetenceModel
    # attached below); the bus routes by event type, so subscription order here does
    # not affect correctness. PreferenceMemory subscribes to nothing today but stores
    # the kernel handle on attach.
    if capability_memory is not None:
        capability_memory.attach(kernel)
    if preference_memory is not None:
        preference_memory.attach(kernel)

    recovery.attach(kernel)
    competence.attach(kernel)
    reflection.attach(kernel)
    # The LearningEngine consumes `reflection.completed` (emitted by ReflectionEngine)
    # and produces `learning.validated`, so attach it AFTER reflection for a sensible
    # logical order (the bus routes by event type regardless). It isolates its own
    # exceptions in every handler and never raises into the tick loop.
    learning.attach(kernel)

    flog: Optional[Any] = None
    if enable_logging:
        flog = failure_log if failure_log is not None else FailureLogSubscriber()
        flog.attach(kernel)

    return ReactiveLoop(
        recovery=recovery,
        competence=competence,
        reflection=reflection,
        failure_log=flog,
        failure_memory=failure_memory,
        learning=learning,
        capability_memory=capability_memory,
        preference_memory=preference_memory,
    )
