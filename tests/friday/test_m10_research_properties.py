"""M10 — Property-based tests (Hypothesis) for the research domain pure cores.

Realizes correctness properties 3–6 from the M10 design document
(``.kiro/specs/m10-domain-compositions/design.md``) as Hypothesis property
tests over ``ResearchDomain`` (`friday/domains/research.py`). Every method under
test is a pure function of its inputs, so ``ResearchDomain(None)`` (no browser)
is sufficient — no capability wiring is exercised.

All tests run under ``FRIDAY_DRY_RUN=1`` so the existing suite stays green and no
real disk I/O or external surface is ever touched.

Validates: Requirements 1.2, 1.3, 1.4
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import string
from typing import List, Tuple

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.domains.models import Claim
from friday.domains.research import ResearchDomain


# --------------------------------------------------------------------------- #
# Shared generators — synthetic, site-agnostic (Axiom 15). No real site names.
# --------------------------------------------------------------------------- #
_HOST_ALPHABET = string.ascii_lowercase
_SUFFIXES = (".gov", ".edu", ".org", ".com", ".net")
_SUBJECTS = ("alpha", "beta", "gamma", "delta")


def _domain() -> ResearchDomain:
    """A ResearchDomain with no browser — only its pure cores are exercised."""
    return ResearchDomain(None)


_host_labels = st.text(alphabet=_HOST_ALPHABET, min_size=1, max_size=6)


@st.composite
def _url(draw) -> str:
    """A synthetic URL: a random host label joined with a chosen suffix and path."""
    label = draw(_host_labels)
    suffix = draw(st.sampled_from(_SUFFIXES))
    path = draw(st.text(alphabet=_HOST_ALPHABET + "/", max_size=8))
    return f"{label}{suffix}/{path}" if path else f"{label}{suffix}"


_urls = st.lists(_url(), max_size=8)

_claims = st.lists(
    st.builds(
        Claim,
        subject=st.sampled_from(_SUBJECTS),
        polarity=st.booleans(),
        source_url=st.text(alphabet=_HOST_ALPHABET, min_size=1, max_size=4),
    ),
    max_size=8,
)

_hypotheses = st.lists(
    st.sampled_from(_SUBJECTS + ("alpha beta", "unrelated")),
    max_size=6,
)


# --------------------------------------------------------------------------- #
# Property 3 — Research findings are deterministic in gathered evidence
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(urls=_urls, claims=_claims, hypotheses=_hypotheses)
def test_property_3_research_findings_are_deterministic(
    urls: List[str], claims: List[Claim], hypotheses: List[str]
) -> None:
    """Property 3: Research findings are deterministic in gathered evidence.

    ``rank_sources``, ``detect_contradictions`` and ``score_hypotheses`` are pure
    functions: calling each twice with identical inputs yields identical,
    stably-ordered outputs.

    Validates: Requirements 1.2, 1.3, 1.4
    """
    domain = _domain()
    urls_t = tuple(urls)
    claims_t = tuple(claims)
    hyps_t = tuple(hypotheses)

    assert domain.rank_sources(urls_t) == domain.rank_sources(urls_t)
    assert domain.detect_contradictions(claims_t) == domain.detect_contradictions(claims_t)
    assert domain.score_hypotheses(hyps_t, claims_t) == domain.score_hypotheses(hyps_t, claims_t)


# --------------------------------------------------------------------------- #
# Property 4 — Credibility scores are bounded and authority-ordered
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(urls=_urls)
def test_property_4_credibility_bounded_and_ordered(urls: List[str]) -> None:
    """Property 4: Credibility scores are bounded and authority-ordered.

    Every ranked source's credibility lies in [0, 1] and the returned tuple is
    sorted by descending credibility (a stable total order).

    Validates: Requirements 1.2
    """
    ranked = _domain().rank_sources(tuple(urls))

    for source in ranked:
        assert 0.0 <= source.credibility <= 1.0

    credibilities = [s.credibility for s in ranked]
    assert credibilities == sorted(credibilities, reverse=True)


@settings(max_examples=200, deadline=None)
@given(label=_host_labels, path=st.text(alphabet=_HOST_ALPHABET, max_size=6))
def test_property_4_authority_class_outranks_general(label: str, path: str) -> None:
    """Property 4 (authority ordering): a primary-authority host (.gov/.edu)
    outranks (>=) a general host (.com) of the same path shape.

    Validates: Requirements 1.2
    """
    domain = _domain()
    tail = f"/{path}" if path else ""

    gov_cred = domain.rank_sources((f"{label}.gov{tail}",))[0].credibility
    edu_cred = domain.rank_sources((f"{label}.edu{tail}",))[0].credibility
    com_cred = domain.rank_sources((f"{label}.com{tail}",))[0].credibility

    assert gov_cred >= com_cred
    assert edu_cred >= com_cred


# --------------------------------------------------------------------------- #
# Property 5 — Contradiction detection is symmetric and subject-scoped
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(claims=_claims)
def test_property_5_contradiction_symmetric_and_subject_scoped(
    claims: List[Claim],
) -> None:
    """Property 5: Contradiction detection is symmetric and subject-scoped.

    A contradiction is reported iff two claims share a subject with opposing
    polarity; reversing the input order yields the same set of contradictions.

    Validates: Requirements 1.3
    """
    domain = _domain()
    claims_t = tuple(claims)

    forward = domain.detect_contradictions(claims_t)
    backward = domain.detect_contradictions(tuple(reversed(claims_t)))

    # Symmetric in input order (as sets).
    assert set(forward) == set(backward)

    # Subject-scoped: exactly the subjects carrying BOTH polarities are reported.
    positive_subjects = {c.subject for c in claims_t if c.polarity}
    negative_subjects = {c.subject for c in claims_t if not c.polarity}
    expected_subjects = positive_subjects & negative_subjects

    assert {c.subject for c in forward} == expected_subjects


# --------------------------------------------------------------------------- #
# Property 6 — Hypothesis support is a bounded ratio
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(hypotheses=_hypotheses, claims=_claims)
def test_property_6_hypothesis_support_is_bounded_ratio(
    hypotheses: List[str], claims: List[Claim]
) -> None:
    """Property 6: Hypothesis support is a bounded ratio.

    Each hypothesis score's support equals ``supporting / total`` (0 when
    ``total == 0``), lies in [0, 1], and satisfies ``0 <= supporting <= total``.

    Validates: Requirements 1.4
    """
    scores = _domain().score_hypotheses(tuple(hypotheses), tuple(claims))

    for score in scores:
        assert 0 <= score.supporting <= score.total
        assert 0.0 <= score.support <= 1.0
        if score.total == 0:
            assert score.support == 0.0
        else:
            assert score.support == score.supporting / score.total
