"""M9 — Unit tests for the Generalizer (task 1.6).

Validates ``friday/learning/generalization.py`` (Ch 15.6/15.9 transfer learning):
- ``generalize`` lifts a discovered pattern into a principle whose ``applicability`` is
  strictly *broader* than the single source ``(capability, environment)`` context while
  preserving provenance (source signature + aggregate support).
- ``merge`` folds extra supporting evidence so ``confidence`` is monotonically
  non-decreasing in accumulated support, widens (never narrows) applicability, and keeps
  provenance.
- No literal application/site name appears in any ``statement``/``applicability``
  (Axiom 15).

Runs under ``FRIDAY_DRY_RUN=1`` so no real disk I/O or external surface is touched.

_Requirements: 1.4, 1.5, 5.4, 7.2_
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from friday.learning.generalization import Generalizer
from friday.learning.models import DiscoveredPattern


def _pattern(
    *,
    capability: str = "cap",
    environment: str = "env",
    support: int = 3,
    signature: str | None = None,
) -> DiscoveredPattern:
    return DiscoveredPattern(
        signature=signature or f"{capability}\x00{environment}\x00outcome",
        capability=capability,
        environment=environment,
        support=support,
        mean_prediction_error=0.1,
    )


# A conservative sample of literal app/site names that MUST NOT appear (Axiom 15).
_FORBIDDEN_LITERALS = (
    "chrome", "firefox", "safari", "edge", "google", "gmail", "youtube",
    "facebook", "twitter", "amazon", "outlook", "slack", "notion", "github",
    "http://", "https://", ".com", ".org", ".net",
)


def _assert_no_literal_names(principle) -> None:
    haystack = " ".join(
        (principle.statement, *principle.applicability, *principle.source_signatures)
    ).lower()
    for literal in _FORBIDDEN_LITERALS:
        assert literal not in haystack, f"forbidden literal {literal!r} leaked"


# --------------------------------------------------------------------------- #
# generalize: broader applicability + preserved provenance
# --------------------------------------------------------------------------- #
def test_generalize_applicability_is_broader_than_source_context() -> None:
    pattern = _pattern(capability="cap", environment="env", support=4)
    principle = Generalizer().generalize(pattern)

    # The source context is a single (capability, environment) point. The principle must
    # apply beyond that single environment: it carries the capability class plus a wildcard
    # scope spanning the whole environment class.
    assert principle.applicability == ("cap", "cap::*")
    # Strictly broader: more than one scope token, and none is the literal source environment.
    assert len(principle.applicability) > 1
    assert pattern.environment not in principle.applicability


def test_generalize_preserves_provenance() -> None:
    pattern = _pattern(support=5)
    principle = Generalizer().generalize(pattern)

    assert principle.source_signatures == (pattern.signature,)
    assert principle.support == pattern.support
    assert isinstance(principle.applicability, tuple)
    assert isinstance(principle.source_signatures, tuple)


def test_generalize_confidence_in_unit_interval_and_increases_with_support() -> None:
    low = Generalizer().generalize(_pattern(support=3))
    high = Generalizer().generalize(_pattern(support=30))
    assert 0.0 <= low.confidence <= 1.0
    assert 0.0 <= high.confidence <= 1.0
    assert high.confidence > low.confidence


def test_generalize_no_literal_app_or_site_name() -> None:
    _assert_no_literal_names(Generalizer().generalize(_pattern()))


# --------------------------------------------------------------------------- #
# merge: monotonic confidence + widened applicability + preserved provenance
# --------------------------------------------------------------------------- #
def test_merge_confidence_monotonically_non_decreasing_in_support() -> None:
    gen = Generalizer()
    principle = gen.generalize(_pattern(capability="cap", environment="env-a", support=3))

    confidence_trace = [principle.confidence]
    support_trace = [principle.support]
    # Fold in a sequence of additional corroborating patterns; confidence must never drop.
    for i in range(5):
        principle = gen.merge(
            principle,
            _pattern(
                capability="cap",
                environment=f"env-{i}",
                support=2,
                signature=f"cap\x00env-{i}\x00outcome",
            ),
        )
        support_trace.append(principle.support)
        confidence_trace.append(principle.confidence)

    # Support strictly grows; confidence is monotonically non-decreasing and bounded.
    for prev, curr in zip(support_trace, support_trace[1:]):
        assert curr > prev
    for prev, curr in zip(confidence_trace, confidence_trace[1:]):
        assert curr >= prev
    assert all(0.0 <= c <= 1.0 for c in confidence_trace)


def test_merge_widens_applicability_and_preserves_provenance() -> None:
    gen = Generalizer()
    principle = gen.generalize(_pattern(capability="cap-a", environment="env", support=3))
    before = set(principle.applicability)

    other = _pattern(
        capability="cap-b",
        environment="env",
        support=4,
        signature="cap-b\x00env\x00outcome",
    )
    merged = gen.merge(principle, other)

    # Applicability only grows (superset) and gains the new capability class.
    assert before.issubset(set(merged.applicability))
    assert "cap-b" in merged.applicability
    # Provenance accumulates both source signatures and aggregate support.
    assert set(merged.source_signatures) == {
        principle.source_signatures[0],
        other.signature,
    }
    assert merged.support == principle.support + other.support
    # Identity is preserved across the merge.
    assert merged.id == principle.id


def test_merge_no_literal_app_or_site_name() -> None:
    gen = Generalizer()
    principle = gen.generalize(_pattern(capability="cap-a", environment="env"))
    merged = gen.merge(
        principle,
        _pattern(capability="cap-b", environment="env2", signature="cap-b\x00env2\x00o"),
    )
    _assert_no_literal_names(merged)


def test_merge_same_pattern_twice_does_not_duplicate_provenance() -> None:
    gen = Generalizer()
    principle = gen.generalize(_pattern(support=3))
    same = _pattern(support=3)  # identical signature
    merged = gen.merge(principle, same)
    # Signature already present -> provenance not duplicated, but support still accumulates.
    assert merged.source_signatures == principle.source_signatures
    assert merged.support == principle.support + same.support
