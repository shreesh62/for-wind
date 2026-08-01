"""M13 — the fault probe protocol, verdict value, and probe registry.

A **fault probe** actuates a real fault (process kill, browser death, interrupt)
or attempts a gated irreversible action, and returns a :class:`ProbeVerdict`
whose ``assertions`` are the concrete observations that justify the result. The
runner dispatches through :class:`FaultProbe` only — there is no per-scenario
branching anywhere (Axiom 15).

Nothing here is application- or site-specific, and no failure is swallowed: an
unusable probe returns ``fail``/``skipped`` with a reason instead of a pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Protocol, Tuple, runtime_checkable

RESULT_PASS = "pass"
RESULT_FAIL = "fail"
RESULT_SKIPPED = "skipped"

_RESULTS: Tuple[str, ...] = (RESULT_PASS, RESULT_FAIL, RESULT_SKIPPED)


@dataclass(frozen=True)
class ProbeVerdict:
    """The outcome of one fault actuation, with its audit trail."""

    probe_id: str
    result: str                      # "pass" | "fail" | "skipped"
    assertions: Tuple[str, ...] = ()  # ordered human-readable observations
    error: str = ""

    def __post_init__(self) -> None:
        if self.result not in _RESULTS:
            raise ValueError(
                f"invalid probe result {self.result!r}; expected one of {_RESULTS}"
            )
        if self.result == RESULT_PASS and not self.assertions:
            raise ValueError(
                f"probe {self.probe_id!r} returned pass with no assertions; "
                "a pass with no observations is not evidence"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "result": self.result,
            "assertions": list(self.assertions),
            "error": self.error,
        }


@dataclass(frozen=True)
class ProbeContext:
    """What a probe may need, without coupling probes to the runner.

    ``scenario`` is the :class:`~scripts.kernel_validation.scenarios.ValidationScenario`
    being actuated, ``operator_factory`` is the injected ``(goal_text) -> operator``
    callable, ``browser_controller`` is a live controller when one exists, and
    ``workdir`` is a temporary directory owned (and cleaned up) by the runner.
    """

    scenario: Any
    operator_factory: Optional[Callable[[str], Any]] = None
    browser_controller: Any = None
    workdir: str = ""


@runtime_checkable
class FaultProbe(Protocol):
    """The single protocol every fault probe conforms to."""

    probe_id: str

    def actuate(self, context: ProbeContext) -> ProbeVerdict:
        """Actuate the fault and return a verdict derived from observed state."""
        ...


_REGISTRY: Dict[str, FaultProbe] = {}


def register_probe(probe: FaultProbe) -> None:
    """Register ``probe`` under its ``probe_id``.

    Raises ``ValueError`` on a missing id or a duplicate registration — a silently
    shadowed probe would make a verdict untraceable.
    """
    probe_id = getattr(probe, "probe_id", "")
    if not probe_id:
        raise ValueError("probe must expose a non-empty probe_id")
    existing = _REGISTRY.get(probe_id)
    if existing is not None and existing is not probe:
        raise ValueError(f"probe id {probe_id!r} is already registered")
    _REGISTRY[probe_id] = probe


def get_probe(probe_id: str) -> Optional[FaultProbe]:
    """Return the registered probe for ``probe_id``, or ``None`` if unknown."""
    return _REGISTRY.get(probe_id)
