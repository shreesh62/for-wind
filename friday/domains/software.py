"""Ch 41 — software engineering domain. DEFERRED to v2 (HANDOFF Section 9); stub only.

Full software-engineering depth (edit / run / test capability composition) is
intentionally not implemented in M10. This stub keeps the domain package surface
complete and makes the deferral discoverable: constructing the domain and calling
status() yields a DeferredOutcome documenting the v2 deferral. The module owns no
durable state and names no application or site (Axiom 15).
"""

from __future__ import annotations

from typing import Any

from friday.domains.models import DeferredOutcome


class SoftwareDomain:
    """Ch 41 — software engineering domain. DEFERRED to v2 (HANDOFF Section 9); stub only."""

    DEFERRED = True

    def __init__(self, registry: Any) -> None:
        self.registry = registry

    def status(self) -> DeferredOutcome:
        """Return a DeferredOutcome documenting the v2 deferral and the verbs a future
        SWE domain would compose (edit / run / test) — no implementation."""
        return DeferredOutcome(
            domain="software",
            reason="Ch 41 full software-engineering depth is deferred to v2 (HANDOFF Section 9)",
            would_compose=("edit", "run", "test"),
            deferred=True,
        )
