"""Ch 15.6/15.9 — generalization: lift a specific pattern into a transferable principle.

``PatternDiscovery`` proves that a lesson *recurred* in one concrete
``(capability, environment)`` context; the :class:`Generalizer` performs the Ch 15.6/15.9
transfer step, lifting that specific, verified pattern into a reusable
:class:`Principle` whose ``applicability`` is *broader* than the single source context —
it covers the capability across the whole environment class, not just the one environment
the evidence came from. ``merge`` then folds additional corroborating evidence from other
contexts into an existing principle, widening its applicability and raising confidence.

Two invariants make the transfer safe:

* **Provenance is preserved.** Every principle records the ``source_signatures`` and the
  aggregate ``support`` it was lifted from, so a generalization can always be traced back
  to the verified repetitions that justify it (Ch 15.9).
* **Confidence is monotonically non-decreasing in accumulated support.** More corroboration
  can only raise (or hold) confidence — never lower it — via the bounded, saturating map
  ``1 - 1 / (1 + support)`` into ``[0, 1]``.

Isolation (Property 1 / Req 5.2): this module holds only pure generalization logic over the
plain data models in :mod:`friday.learning.models`. It MUST NOT import
``friday.memory.controller``, ``friday.memory.runtime``, or any ``friday.competence``
module, and MUST NOT reference ``FridayMemory``/``MemoryStore``. Applicability is expressed
purely by capability/environment *class* — no literal application name, site name, or URL
appears here (Axiom 15).
"""

from __future__ import annotations

import hashlib
from typing import Tuple

from friday.learning.models import DiscoveredPattern, Principle

# Suffix marking a capability generalized across every environment of its class. Because it
# is a wildcard (not a literal environment identifier) it strictly broadens a single
# concrete (capability, environment) source context (Axiom 15 — no literal names).
_ENV_WILDCARD = "::*"


def _confidence(support: int) -> float:
    """Bounded, saturating confidence in ``[0, 1]``, monotonically increasing in support.

    Uses ``1 - 1 / (1 + support)``: more accumulated corroboration can only raise (or hold)
    confidence and never lower it, and the value saturates toward — but never exceeds — 1.0.
    """

    return 1.0 - 1.0 / (1.0 + max(0, support))


def _scope_tokens(capability: str) -> Tuple[str, ...]:
    """Applicability tokens for one capability class.

    Yields the capability class itself plus a wildcard scope
    (``"<capability>::*"``) denoting "this capability across *any* environment of its
    class" — strictly broader than a single concrete environment, and free of any literal
    app/site name (Axiom 15).
    """

    return (capability, f"{capability}{_ENV_WILDCARD}")


def _principle_id(signature: str) -> str:
    """Stable, deterministic principle id derived from the source pattern signature."""

    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:12]
    return f"principle-{digest}"


class Generalizer:
    """Ch 15.6/15.9 — lift a specific pattern into a transferable principle."""

    def generalize(self, pattern: DiscoveredPattern) -> Principle:
        """Produce a context-lifted :class:`Principle` from a discovered pattern.

        The specific source context — a single ``(capability, environment)`` point — is
        abstracted into a broader ``applicability`` scope covering the capability across its
        whole environment class. Provenance (the source signature + aggregate support) is
        preserved, and the initial confidence is derived monotonically from support. NEVER
        hardcodes app/site names (Axiom 15): scope is expressed by capability/environment
        class, not literal identifiers.
        """

        applicability = _scope_tokens(pattern.capability)
        statement = (
            f"Capability '{pattern.capability}' reliably yields its verified outcome "
            f"across environments of the same class."
        )
        return Principle(
            id=_principle_id(pattern.signature),
            statement=statement,
            applicability=applicability,
            source_signatures=(pattern.signature,),
            support=pattern.support,
            confidence=_confidence(pattern.support),
        )

    def merge(self, principle: Principle, other: DiscoveredPattern) -> Principle:
        """Fold additional supporting evidence from another context into a principle.

        Accumulates ``other``'s support, records its signature as further provenance, widens
        (never narrows) the applicability to include ``other``'s capability class, and
        re-derives confidence from the accumulated support so it is monotonically
        non-decreasing in corroboration. The principle's identity (``id``) is preserved.
        """

        # Widen applicability: ordered union so it can only grow (never narrow).
        applicability = list(principle.applicability)
        for token in _scope_tokens(other.capability):
            if token not in applicability:
                applicability.append(token)

        # Preserve provenance: append the new source signature if not already present.
        source_signatures = principle.source_signatures
        if other.signature not in source_signatures:
            source_signatures = source_signatures + (other.signature,)

        accumulated_support = principle.support + other.support
        return Principle(
            id=principle.id,
            statement=principle.statement,
            applicability=tuple(applicability),
            source_signatures=source_signatures,
            support=accumulated_support,
            confidence=_confidence(accumulated_support),
        )
