"""Ch 37 — research depth as a pure capability composition (no durable state).

`ResearchDomain` composes the existing `research(...)` capability
(`friday/capabilities/research.py`) with three pure, deterministic layers:

- source **credibility ranking** by an authority *class* heuristic (host suffix
  class — never a literal site name, Axiom 15),
- lightweight **claim extraction** + **contradiction detection** over gathered
  text, and
- **hypothesis scoring** as a bounded support ratio.

The domain owns no durable cross-call state: its only attributes are the
`CapabilityRegistry` and an optional browser/tool controller threaded straight
through to the underlying capability. Every method is a pure function of its
inputs — identical gathered evidence yields an identical `ResearchFinding`. All
artifacts flow into the caller-owned `ExecutionEvidence`; the domain stores
nothing.
"""

from __future__ import annotations

from typing import Any, List, Tuple

from friday.capabilities.research import research
from friday.domains.models import (
    Claim,
    Contradiction,
    HypothesisScore,
    RankedSource,
    ResearchFinding,
)
from friday.verification.evidence_law import ExecutionEvidence

# Authority-class heuristic (host *suffix* classes, never literal site names).
_PRIMARY_CREDIBILITY = 0.9
_REFERENCE_CREDIBILITY = 0.7
_GENERAL_CREDIBILITY = 0.4

# Host suffixes that denote an authority class. These are generic top-level
# categories, not application or site identities (Axiom 15).
_PRIMARY_SUFFIXES = (".gov", ".edu")
_REFERENCE_SUFFIX = ".org"
_ACADEMIC_INFIX = ".ac."

# Lightweight negation tokens for polarity detection (best-effort, not NLP).
_NEGATION_TOKENS = ("not", "no", "never", "cannot", "false")

_SUBJECT_WORD_LIMIT = 6
_PATH_SEPARATOR = "/"


class ResearchDomain:
    """Ch 37 — research depth as a pure capability composition (no durable state)."""

    def __init__(self, registry: Any, browser_controller: Any = None) -> None:
        # The ONLY instance attributes. No mutable cross-call state is owned.
        self.registry = registry
        self.browser_controller = browser_controller

    # -- Primary composition -------------------------------------------------

    def investigate(
        self,
        query: str,
        evidence: ExecutionEvidence,
        *,
        hypotheses: Tuple[str, ...] = (),
        max_sources: int = 3,
    ) -> ResearchFinding:
        """Gather via `research(...)`, then rank sources, score hypotheses, and
        detect contradictions — purely over the gathered evidence.

        Degrades gracefully (no raise) to a blocked finding when no browser /
        research capability is available.
        """
        controller = self.browser_controller
        if not controller or not getattr(controller, "available", False):
            return ResearchFinding(
                query=query,
                sources_read=0,
                blocked=True,
                error="No research capability available",
            )

        res = research(query, controller, evidence, max_sources=max_sources)

        ranked_sources = self.rank_sources(tuple(res.source_urls))
        claims = self._extract_claims(res.gathered_text)
        contradictions = self.detect_contradictions(claims)
        scored = self.score_hypotheses(tuple(hypotheses), claims)

        return ResearchFinding(
            query=query,
            sources_read=res.sources_read,
            ranked_sources=ranked_sources,
            hypotheses=scored,
            contradictions=contradictions,
            blocked=res.blocked,
            error=res.error,
        )

    # -- Pure cores ----------------------------------------------------------

    def rank_sources(self, source_urls: Tuple[str, ...]) -> Tuple[RankedSource, ...]:
        """Score/sort sources by an authority-*class* heuristic (host suffix
        class, never a literal site name). Stable total order: descending
        credibility, then url ascending.
        """
        ranked: List[RankedSource] = []
        for url in source_urls:
            authority_class, credibility = self._classify_host(self._host_of(url))
            ranked.append(
                RankedSource(url=url, authority_class=authority_class, credibility=credibility)
            )
        ranked.sort(key=lambda r: (-r.credibility, r.url))
        return tuple(ranked)

    def detect_contradictions(
        self, claims: Tuple[Claim, ...]
    ) -> Tuple[Contradiction, ...]:
        """Report a contradiction iff two claims share a subject with opposing
        polarity. Symmetric in input order, deduplicated, sorted by subject.
        """
        positives_by_subject: dict = {}
        negatives_by_subject: dict = {}
        for claim in claims:
            bucket = positives_by_subject if claim.polarity else negatives_by_subject
            bucket.setdefault(claim.subject, []).append(claim.source_url)

        seen = set()
        found: List[Contradiction] = []
        for subject in positives_by_subject:
            if subject not in negatives_by_subject:
                continue
            for pos_source in positives_by_subject[subject]:
                for neg_source in negatives_by_subject[subject]:
                    key = (subject, pos_source, neg_source)
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append(
                        Contradiction(
                            subject=subject,
                            positive_source=pos_source,
                            negative_source=neg_source,
                        )
                    )
        found.sort(key=lambda c: (c.subject, c.positive_source, c.negative_source))
        return tuple(found)

    def score_hypotheses(
        self, hypotheses: Tuple[str, ...], claims: Tuple[Claim, ...]
    ) -> Tuple[HypothesisScore, ...]:
        """Support score in [0, 1] per hypothesis = supporting / total relevant
        claims (0 when no relevant claims). One score per hypothesis, in input
        order.
        """
        scores: List[HypothesisScore] = []
        for hypothesis in hypotheses:
            hypothesis_lower = hypothesis.lower()
            total = 0
            supporting = 0
            for claim in claims:
                subject_lower = claim.subject.lower()
                relevant = subject_lower in hypothesis_lower or hypothesis_lower in subject_lower
                if not relevant:
                    continue
                total += 1
                if claim.polarity is True:
                    supporting += 1
            support = supporting / total if total else 0.0
            scores.append(
                HypothesisScore(
                    hypothesis=hypothesis,
                    support=support,
                    supporting=supporting,
                    total=total,
                )
            )
        return tuple(scores)

    def _extract_claims(self, text: str) -> Tuple[Claim, ...]:
        """Lightweight deterministic claim extraction (not NLP): one claim per
        non-empty line, subject = first few words lowercased, polarity = False
        when a negation token is present.
        """
        claims: List[Claim] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            words = stripped.split()
            subject = " ".join(words[:_SUBJECT_WORD_LIMIT]).lower().strip()
            lowered_words = [w.strip(".,;:!?").lower() for w in words]
            polarity = not any(token in lowered_words for token in _NEGATION_TOKENS)
            claims.append(Claim(subject=subject, polarity=polarity, source_url=""))
        return tuple(claims)

    # -- Host parsing helpers (generic, no scheme/site literals) -------------

    @staticmethod
    def _host_of(url: str) -> str:
        """Parse the host generically from a url's path segments (Axiom 15: no
        scheme or site literals). Skips empty and scheme-like segments (those
        ending with a colon) and returns the first dotted segment.
        """
        segments = url.split(_PATH_SEPARATOR)
        for segment in segments:
            if not segment or segment.endswith(":"):
                continue
            if "." in segment:
                return segment.lower()
        # Fallback: first non-empty, non-scheme segment.
        for segment in segments:
            if segment and not segment.endswith(":"):
                return segment.lower()
        return ""

    @staticmethod
    def _classify_host(host: str) -> Tuple[str, float]:
        """Map a host to (authority_class, credibility) by suffix class only."""
        if host.endswith(_PRIMARY_SUFFIXES):
            return "primary", _PRIMARY_CREDIBILITY
        if host.endswith(_REFERENCE_SUFFIX) or _ACADEMIC_INFIX in host:
            return "reference", _REFERENCE_CREDIBILITY
        return "general", _GENERAL_CREDIBILITY
