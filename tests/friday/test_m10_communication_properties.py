"""M10 — Property-based tests (Hypothesis) for the CommunicationDomain (Ch 39).

Realizes correctness properties 7 and 8 from the M10 design document
(``.kiro/specs/m10-domain-compositions/design.md``) as Hypothesis property
tests. Every test runs under ``FRIDAY_DRY_RUN=1`` so no real disk I/O or
external surface is ever touched.

Validates: Requirements 2.2, 2.3, 2.4
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from typing import List, Tuple

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.capabilities.registry import CapabilityRegistry
from friday.domains.communication import CommunicationDomain
from friday.domains.models import Conversation
from friday.verification.evidence_law import ExecutionEvidence

# A safe alphabet (letters + numbers) so generated text is always non-empty and
# whitespace-free — avoids the Evidence Law's ``.strip()`` no-op filtering.
_SAFE_TEXT = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=12,
)


# --------------------------------------------------------------------------- #
# Property 7 — Delivery requires real confirmation evidence
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(generated=_SAFE_TEXT, confirmation=_SAFE_TEXT)
def test_property_7_delivery_requires_real_confirmation_evidence(
    generated: str, confirmation: str
) -> None:
    """Property 7: Delivery requires real confirmation evidence.

    ``CommunicationDomain.verify_delivery(evidence)`` is True iff the bundle
    carries a real ``DELIVERY_CONFIRMATION`` artifact. A bundle containing only
    generated content is never confirmed; adding a real delivery confirmation
    flips it to True.

    Validates: Requirements 2.2, 2.3
    """
    domain = CommunicationDomain(CapabilityRegistry())
    evidence = ExecutionEvidence()

    # Generated content alone can NEVER satisfy a delivery demand (Evidence Law).
    evidence.add_generated_content(generated)
    assert domain.verify_delivery(evidence) is False

    # A real DELIVERY_CONFIRMATION artifact flips verification to True.
    evidence.add_delivery_confirmation(confirmation)
    assert domain.verify_delivery(evidence) is True


# --------------------------------------------------------------------------- #
# Property 8 — Conversation memory is immutable and append-only
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(
    turns=st.lists(
        st.tuples(_SAFE_TEXT, _SAFE_TEXT),
        min_size=0,
        max_size=6,
    )
)
def test_property_8_conversation_memory_is_immutable_and_append_only(
    turns: List[Tuple[str, str]],
) -> None:
    """Property 8: Conversation memory is immutable and append-only.

    Starting from an empty ``Conversation`` and appending N random turns via
    ``append_turn`` yields a conversation whose turns equal the accumulated list,
    with each ``logical_index`` strictly increasing (0..N-1). Every intermediate
    conversation object is unchanged — its ``len(turns)`` stays exactly what it
    was at the moment it was created.

    Validates: Requirements 2.4
    """
    domain = CommunicationDomain(CapabilityRegistry())

    conversation = Conversation()
    # Snapshot each intermediate object alongside the length it had at creation.
    snapshots: List[Tuple[Conversation, int]] = [(conversation, len(conversation.turns))]
    accumulated: List[Tuple[str, str]] = []

    for speaker, text in turns:
        conversation = domain.append_turn(conversation, speaker, text)
        accumulated.append((speaker, text))
        snapshots.append((conversation, len(conversation.turns)))

    # The final conversation's turns equal the accumulated (speaker, text) list.
    assert len(conversation.turns) == len(accumulated)
    for turn, (speaker, text) in zip(conversation.turns, accumulated):
        assert turn.speaker == speaker
        assert turn.text == text

    # logical_index is strictly increasing 0..N-1.
    indices = [turn.logical_index for turn in conversation.turns]
    assert indices == list(range(len(accumulated)))

    # Every intermediate object is unchanged — its length is frozen at creation.
    for snapshot, expected_len in snapshots:
        assert len(snapshot.turns) == expected_len
