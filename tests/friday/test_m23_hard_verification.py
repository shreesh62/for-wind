"""M23 — hard, non-fabricable verification (Evidence Law strengthening).

Feature: m23-browser-generic-desktop-environment

Weak verification let junk through: acting on an unfilled template placeholder
("<<topic>>", "<<extracted URL>>") and recording a non-URL "source". These tests
lock in the hardened Evidence Law:
  - structured placeholder tokens are never real evidence (and are never acted on),
  - source URLs must be concrete URLs (http/https/file), never bare hosts,
  - navigation/source details that are placeholders are rejected,
  - natural-language queries are NOT over-flagged as placeholders.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.verification.evidence_law import (
    EvidenceArtifact,
    EvidenceKind,
    ExecutionEvidence,
    looks_like_placeholder,
)


def test_placeholder_detection_positive_and_negative():
    for p in ("<<topic>>", "<<extracted URL>>", "<extracted URL>", "{{query}}",
              "[topic]", "{topic}", "<url>", "extracted url", "the url of the page"):
        assert looks_like_placeholder(p) is True, p
    # Natural language and real identifiers must NOT be flagged (no false positives).
    for real in ("https://en.wikipedia.org/wiki/Automation", "clicked:Login",
                 "launched:chrome", "given topic", "research a topic about jazz",
                 "Automation is the use of technology"):
        assert looks_like_placeholder(real) is False, real


def test_source_url_must_be_real_url():
    assert EvidenceArtifact(kind=EvidenceKind.SOURCE_URL,
                            detail="https://example.com/x").is_real is True
    assert EvidenceArtifact(kind=EvidenceKind.SOURCE_URL,
                            detail="file:///tmp/page.html").is_real is True
    # Bare host / description / placeholder are NOT valid sources.
    assert EvidenceArtifact(kind=EvidenceKind.SOURCE_URL,
                            detail="host.example/x").is_real is False
    assert EvidenceArtifact(kind=EvidenceKind.SOURCE_URL,
                            detail="a public information page").is_real is False
    assert EvidenceArtifact(kind=EvidenceKind.SOURCE_URL,
                            detail="<<extracted URL>>").is_real is False


def test_navigation_rejects_placeholder():
    assert EvidenceArtifact(kind=EvidenceKind.NAVIGATION,
                            detail="https://site/page").is_real is True
    assert EvidenceArtifact(kind=EvidenceKind.NAVIGATION,
                            detail="launched:notepad").is_real is True
    assert EvidenceArtifact(kind=EvidenceKind.NAVIGATION,
                            detail="launched:<<extracted URL>>").is_real is False


def test_gathered_and_generated_need_only_nonempty():
    # Substance is enforced at the action layer (placeholder targets never produce
    # evidence); real text of any length counts here.
    assert EvidenceArtifact(kind=EvidenceKind.GATHERED_INFO, detail="x", value=9).is_real is True
    assert EvidenceArtifact(kind=EvidenceKind.GENERATED_CONTENT, detail="x", value=20).is_real is True


def test_of_kind_excludes_placeholder_and_nonurl_sources():
    ev = ExecutionEvidence()
    ev.add(EvidenceArtifact(kind=EvidenceKind.SOURCE_URL, detail="<<extracted URL>>"))
    ev.add(EvidenceArtifact(kind=EvidenceKind.SOURCE_URL, detail="host.example/x"))
    ev.add(EvidenceArtifact(kind=EvidenceKind.SOURCE_URL, detail="https://real.example/p"))
    reals = ev.of_kind(EvidenceKind.SOURCE_URL)
    assert len(reals) == 1 and reals[0].detail == "https://real.example/p"


@settings(max_examples=100)
@given(token=st.sampled_from(["<<topic>>", "<extracted url>", "{{q}}", "[x]",
                              "<url>", "the url of the result"]))
def test_placeholder_url_or_nav_never_real(token):
    # Feature: m23-browser-generic-desktop-environment:
    # a placeholder is never real evidence for a URL or navigation artifact.
    assert EvidenceArtifact(kind=EvidenceKind.SOURCE_URL, detail=token).is_real is False
    assert EvidenceArtifact(kind=EvidenceKind.NAVIGATION, detail=token).is_real is False
