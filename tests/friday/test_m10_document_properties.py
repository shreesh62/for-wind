"""M10 — Property-based tests (Hypothesis) for the DocumentDomain (Ch 40).

Realizes correctness properties 9 and 10 from the M10 design document
(``.kiro/specs/m10-domain-compositions/design.md``) as Hypothesis property
tests. Every test runs under ``FRIDAY_DRY_RUN=1`` so no real disk I/O or
external surface is ever touched.

Validates: Requirements 3.1, 3.2, 3.3
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from typing import List

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.capabilities.registry import CapabilityRegistry
from friday.domains.documents import DocumentDomain
from friday.domains.models import (
    Block,
    DocumentFormat,
    Section,
    SemanticDocument,
)
from friday.verification.evidence_law import ExecutionEvidence

# A safe alphabet (letters + numbers) so generated text is always non-empty and
# free of whitespace/markdown characters that could confuse substring checks.
_SAFE_TEXT = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=12,
)

_BLOCK = st.builds(
    Block,
    text=_SAFE_TEXT,
    style=st.sampled_from(["body", "bullet", "code"]),
)

_SECTION = st.builds(
    Section,
    heading=_SAFE_TEXT,
    blocks=st.lists(_BLOCK, min_size=0, max_size=6).map(tuple),
)

_DOCUMENT = st.builds(
    SemanticDocument,
    title=_SAFE_TEXT,
    sections=st.lists(_SECTION, min_size=0, max_size=6).map(tuple),
)


def _ordered_fragments(document: SemanticDocument) -> List[str]:
    """The title, section headings, and block texts in strict document order."""
    fragments = [document.title]
    for section in document.sections:
        fragments.append(section.heading)
        for block in section.blocks:
            fragments.append(block.text)
    return fragments


def _assert_contains_in_order(rendered: str, fragments: List[str]) -> None:
    """Every fragment is a substring, appearing in non-decreasing document order."""
    search_from = 0
    for fragment in fragments:
        index = rendered.find(fragment, search_from)
        assert index >= 0, f"fragment {fragment!r} missing from render"
        # Advance the cursor to enforce document order across the sequence.
        search_from = index + len(fragment)


# --------------------------------------------------------------------------- #
# Property 9 — Document render round-trips structure
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(document=_DOCUMENT)
def test_property_9_document_render_round_trips_structure(
    document: SemanticDocument,
) -> None:
    """Property 9: Document render round-trips structure.

    ``render(document, MARKDOWN)`` contains the title, every section heading, and
    every block text as substrings, in document order. Rendering twice yields an
    identical string. The same substring-containment holds for PLAINTEXT.

    Validates: Requirements 3.1, 3.2
    """
    domain = DocumentDomain(CapabilityRegistry())
    fragments = _ordered_fragments(document)

    markdown = domain.render(document, DocumentFormat.MARKDOWN)
    _assert_contains_in_order(markdown, fragments)

    # Deterministic: rendering twice yields identical bytes.
    assert domain.render(document, DocumentFormat.MARKDOWN) == markdown

    # Plaintext carries the same fragments (order preserved).
    plaintext = domain.render(document, DocumentFormat.PLAINTEXT)
    _assert_contains_in_order(plaintext, fragments)
    assert domain.render(document, DocumentFormat.PLAINTEXT) == plaintext


# --------------------------------------------------------------------------- #
# Property 10 — Citations reference only real gathered sources
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(
    document=_DOCUMENT,
    labels=st.lists(_SAFE_TEXT, min_size=0, max_size=6),
)
def test_property_10_citations_reference_only_real_gathered_sources(
    document: SemanticDocument, labels: List[str]
) -> None:
    """Property 10: Citations reference only real gathered sources.

    After adding K source urls to the evidence bundle, ``cite(document,
    evidence)`` returns a document with exactly K citations, each referencing one
    of the added urls. With an empty evidence bundle, zero citations are emitted.

    Validates: Requirements 3.3
    """
    domain = DocumentDomain(CapabilityRegistry())

    # Empty evidence → zero citations.
    empty_cited = domain.cite(document, ExecutionEvidence())
    assert empty_cited.citations == ()

    # Synthetic, scheme-less hosts — never a real site name, never a URL scheme.
    evidence = ExecutionEvidence()
    urls = [f"{label}.test/x" for label in labels]
    for url in urls:
        evidence.add_source_url(url)

    cited = domain.cite(document, evidence)

    # Exactly K citations, each referencing one of the added urls.
    assert len(cited.citations) == len(urls)
    added = set(urls)
    for citation in cited.citations:
        assert citation.source_url in added
