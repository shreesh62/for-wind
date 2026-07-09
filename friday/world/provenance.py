"""Ch 9 — Belief provenance: the recorded origin and derivation of a belief.

Captures why the World Model holds a belief — the supporting and contradicting
observation IDs, the ordered derivation chain of parent beliefs (root -> immediate
parent), and a verification status. Also declares the refresh policy vocabulary a
future refresh executor will consume.

Domain-agnostic per Axiom 15: this module depends only on the standard library and
imports no belief/observation types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple


class VerificationStatus(str, Enum):
    """Whether a belief has been independently confirmed."""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"


class RefreshPolicy(str, Enum):
    """The strategy for refreshing a stale belief."""

    ON_READ = "on_read"
    ON_STALE = "on_stale"
    PERIODIC = "periodic"
    NEVER = "never"


# Maximum number of parent belief IDs retained in a derivation chain.
MAX_DERIVATION_CHAIN = 20


@dataclass
class BeliefProvenance:
    """The origin and derivation record for a single belief."""

    supporting_observations: List[str] = field(default_factory=list)
    contradicting_observations: List[str] = field(default_factory=list)
    derivation_chain: List[str] = field(default_factory=list)  # root -> immediate parent
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED


def derive_verification_status(
    supporting: List[str],
    contradicting: List[str],
    current: VerificationStatus,
) -> VerificationStatus:
    """Resolve a belief's verification status from its observation evidence.

    Reality outranks belief: contradiction with no corroboration is the strongest
    signal, so it takes precedence. When at least one supporting observation exists,
    a previously ``UNVERIFIED`` belief is promoted to ``VERIFIED`` — but we never
    silently downgrade an already ``VERIFIED`` belief here, nor override a caller's
    explicit ``CONTRADICTED`` state unless the evidence rule below re-derives it.

    Rules:
    - ``CONTRADICTED`` iff ``contradicting`` is non-empty AND ``supporting`` is empty
      (Req 3.6): a belief challenged with zero corroboration is contradicted.
    - Promote ``UNVERIFIED`` -> ``VERIFIED`` when a supporting observation exists
      (Req 3.3): independent support confirms the belief.
    - Otherwise preserve ``current`` unchanged.

    Pure and total: no side effects, never raises.
    """
    if contradicting and not supporting:
        return VerificationStatus.CONTRADICTED
    if supporting and current == VerificationStatus.UNVERIFIED:
        return VerificationStatus.VERIFIED
    return current


def build_derivation_chain(
    parent_chains_and_ids: List[Tuple[List[str], str]],
    own_id: str,
) -> List[str]:
    """Merge parent ancestor paths into a single ordered, acyclic derivation chain.

    The evidence graph is a DAG (Req 3.7): a belief can be derived from several
    parents, each carrying its own root->parent ancestor path. We flatten those
    paths — each parent's chain followed by the parent's own id — into one sequence
    that preserves root-to-immediate-parent order, then enforce the DAG invariants:

    - De-duplicate while preserving first-seen order. A repeated id is an existing
      ancestor; re-adding it would create a cycle, so the first occurrence wins.
    - Drop any occurrence of ``own_id`` (Req 3.7): a belief may never appear in its
      own ancestry (no self-reference).
    - Truncate to at most ``MAX_DERIVATION_CHAIN`` entries (Req 3.1, 3.8), keeping the
      immediate-parent-ward (tail) entries. The nearest ancestors are the most
      relevant for explanation, so when the bound is exceeded we discard the oldest
      roots rather than the recent parents, still preserving order.

    Pure and total: never raises, even on adversarial input (self-referencing ids,
    duplicate chains, or oversized ancestries).
    """
    ordered: List[str] = []
    seen = set()
    for chain, parent_id in parent_chains_and_ids:
        for belief_id in list(chain) + [parent_id]:
            if belief_id == own_id:
                # No self-reference: a belief cannot be its own ancestor.
                continue
            if belief_id in seen:
                # Already present; skipping avoids a cycle / duplicate.
                continue
            seen.add(belief_id)
            ordered.append(belief_id)
    # Keep the immediate-parent-ward tail when over the bound.
    if len(ordered) > MAX_DERIVATION_CHAIN:
        ordered = ordered[-MAX_DERIVATION_CHAIN:]
    return ordered
