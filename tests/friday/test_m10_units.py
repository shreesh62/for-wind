"""M10 — Unit tests for the domain data models (`friday/domains/models.py`).

Verifies the frozen value-object contracts from the M10 design (Data Models):
immutability, credibility/support clamping to [0, 1], tuple-typed collection
fields, `ResearchFinding.success` semantics, `Conversation.with_turn`
append-only copy behaviour, and `DeliveryOutcome.confirmed` status mapping.

All tests run under ``FRIDAY_DRY_RUN=1`` so the existing suite stays green and no
real disk I/O or external surface is ever touched.

Validates: Requirements 1.4, 2.4, 3.1, 5.4
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import dataclasses

import pytest

from friday.domains.models import (
    Block,
    Citation,
    Claim,
    Contradiction,
    Conversation,
    DeferredOutcome,
    DeliveryOutcome,
    DeliveryStatus,
    DocumentFormat,
    ExportOutcome,
    HypothesisScore,
    RankedSource,
    ResearchFinding,
    Section,
    SemanticDocument,
    Turn,
)


# --------------------------------------------------------------------------- #
# Immutability — every model is a frozen dataclass.
# --------------------------------------------------------------------------- #
def _sample_instances() -> list:
    """One representative instance of every domain data model."""
    return [
        RankedSource(url="label.gov/x", authority_class="primary", credibility=0.9),
        Claim(subject="topic", polarity=True, source_url="label.gov/x"),
        Contradiction(subject="topic", positive_source="a", negative_source="b"),
        HypothesisScore(hypothesis="h", support=0.5, supporting=1, total=2),
        ResearchFinding(query="q", sources_read=1),
        Turn(speaker="user", text="hi", logical_index=0),
        Conversation(),
        DeliveryOutcome(recipient="r", status=DeliveryStatus.CONFIRMED),
        Citation(marker="[1]", source_url="label.gov/x"),
        Block(text="body text"),
        Section(heading="H"),
        SemanticDocument(title="T"),
        ExportOutcome(filename="f.md", fmt=DocumentFormat.MARKDOWN),
        DeferredOutcome(domain="software", reason="deferred to v2"),
    ]


@pytest.mark.parametrize("instance", _sample_instances())
def test_all_models_are_frozen(instance) -> None:
    """Setting any attribute on any model raises FrozenInstanceError."""
    field_name = dataclasses.fields(instance)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, field_name, "mutated")


# --------------------------------------------------------------------------- #
# Credibility clamping — RankedSource clamps to [0, 1].
# --------------------------------------------------------------------------- #
def test_ranked_source_credibility_clamps_high() -> None:
    assert RankedSource(url="u", authority_class="primary", credibility=2.0).credibility == 1.0


def test_ranked_source_credibility_clamps_low() -> None:
    assert RankedSource(url="u", authority_class="general", credibility=-1.0).credibility == 0.0


def test_ranked_source_credibility_passthrough_in_range() -> None:
    assert RankedSource(url="u", authority_class="reference", credibility=0.7).credibility == 0.7


# --------------------------------------------------------------------------- #
# Support clamping — HypothesisScore clamps to [0, 1].
# --------------------------------------------------------------------------- #
def test_hypothesis_score_support_clamps_high() -> None:
    assert HypothesisScore(hypothesis="h", support=5.0, supporting=1, total=1).support == 1.0


def test_hypothesis_score_support_clamps_low() -> None:
    assert HypothesisScore(hypothesis="h", support=-3.0, supporting=0, total=1).support == 0.0


def test_hypothesis_score_support_passthrough_in_range() -> None:
    assert HypothesisScore(hypothesis="h", support=0.25, supporting=1, total=4).support == 0.25


# --------------------------------------------------------------------------- #
# ResearchFinding.success — True only when sources_read > 0 and not blocked.
# --------------------------------------------------------------------------- #
def test_research_finding_success_true() -> None:
    assert ResearchFinding(query="q", sources_read=2, blocked=False).success is True


def test_research_finding_success_false_when_no_sources() -> None:
    assert ResearchFinding(query="q", sources_read=0, blocked=False).success is False


def test_research_finding_success_false_when_blocked() -> None:
    assert ResearchFinding(query="q", sources_read=2, blocked=True).success is False


# --------------------------------------------------------------------------- #
# Conversation.with_turn — append-only immutable copy.
# --------------------------------------------------------------------------- #
def test_with_turn_returns_new_object_leaving_original_unchanged() -> None:
    original = Conversation()
    updated = original.with_turn("user", "hello")

    # A NEW object is returned; the original keeps fewer turns.
    assert updated is not original
    assert len(original.turns) == 0
    assert len(updated.turns) == 1


def test_with_turn_logical_index_equals_old_length() -> None:
    convo = Conversation().with_turn("user", "one")
    old_length = len(convo.turns)

    convo2 = convo.with_turn("assistant", "two")
    new_turn = convo2.turns[-1]

    assert new_turn.logical_index == old_length
    # Indices are strictly increasing across appends.
    assert [t.logical_index for t in convo2.turns] == [0, 1]


# --------------------------------------------------------------------------- #
# DeliveryOutcome.confirmed — CONFIRMED True, others False.
# --------------------------------------------------------------------------- #
def test_delivery_outcome_confirmed_true() -> None:
    assert DeliveryOutcome(recipient="r", status=DeliveryStatus.CONFIRMED).confirmed is True


def test_delivery_outcome_failed_not_confirmed() -> None:
    assert DeliveryOutcome(recipient="r", status=DeliveryStatus.FAILED).confirmed is False


def test_delivery_outcome_unavailable_not_confirmed() -> None:
    assert DeliveryOutcome(recipient="r", status=DeliveryStatus.UNAVAILABLE).confirmed is False


# --------------------------------------------------------------------------- #
# Tuple-typed collection fields default to (and remain) tuples.
# --------------------------------------------------------------------------- #
def test_tuple_fields_are_tuples() -> None:
    finding = ResearchFinding(query="q", sources_read=1)
    assert isinstance(finding.ranked_sources, tuple)
    assert isinstance(finding.hypotheses, tuple)
    assert isinstance(finding.contradictions, tuple)

    assert isinstance(Conversation().turns, tuple)

    document = SemanticDocument(title="T")
    assert isinstance(document.sections, tuple)
    assert isinstance(document.citations, tuple)

    assert isinstance(Section(heading="H").blocks, tuple)
    assert isinstance(DeferredOutcome(domain="d", reason="r").would_compose, tuple)
