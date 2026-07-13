"""M23 — web-independence benchmark suite definition tests.

Feature: m23-browser-generic-desktop-environment

Validates the proof-suite DEFINITIONS (not a live run): the 11 required
capabilities are present, every required_evidence name resolves to a real
EvidenceKind, goals are domain-general (no site names, no browser names —
Axiom 15), and the suite is NOT wired into the competence scorecard.
"""

from friday.benchmarks.capability.domains import (
    all_domain_suites,
    web_independence_suite,
)
from friday.verification.evidence_law import EvidenceKind


_EXPECTED_CAPABILITIES = {
    "launch", "navigate", "search", "login_flow", "file_upload",
    "download_verify", "multi_tab", "dynamic_interaction", "infinite_scroll",
    "unexpected_dialog", "crash_recovery",
}

# URL-ish substrings that would betray a site-specific goal (Axiom 15 violation).
_FORBIDDEN_SUBSTRINGS = ("http", "www", ".com", ".org")
# Whole-word site/browser names (word-boundary matched so "arc" != "search").
_FORBIDDEN_WORDS = (
    "google", "gmail", "youtube", "instagram", "facebook", "amazon", "twitter",
    "chrome", "edge", "firefox", "brave", "arc", "electron",
)


def test_suite_covers_the_eleven_capabilities():
    # Validates: Requirements 8.3
    suite = web_independence_suite()
    caps = {b.id.split(".", 1)[1] for b in suite}
    assert caps == _EXPECTED_CAPABILITIES
    assert len(suite) == 11
    assert all(b.domain == "web_independence" for b in suite)


def test_required_evidence_names_are_valid():
    # Validates: Requirements 8.4 (Evidence-Law scored, not self-report)
    valid = {k.name for k in EvidenceKind}
    for b in web_independence_suite():
        assert b.required_evidence, f"{b.id} has no required_evidence"
        for name in b.required_evidence:
            assert name in valid, f"{b.id}: '{name}' is not an EvidenceKind"


def test_goals_are_domain_general():
    # Validates: Requirements 8.5 (goal names a capability, never a site/browser)
    import re

    for b in web_independence_suite():
        g = b.goal_text.lower()
        for tok in _FORBIDDEN_SUBSTRINGS:
            assert tok not in g, f"{b.id} goal names '{tok}': {b.goal_text!r}"
        for word in _FORBIDDEN_WORDS:
            assert not re.search(rf"\b{re.escape(word)}\b", g), \
                f"{b.id} goal names '{word}': {b.goal_text!r}"
        assert b.acceptance, f"{b.id} missing acceptance criterion"


def test_web_independence_excluded_from_competence_scorecard():
    # Proof suite must not perturb the five-domain scorecard/ratchet.
    assert "web_independence" not in all_domain_suites()
