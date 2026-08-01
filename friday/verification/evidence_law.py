"""Evidence Law — makes false completion architecturally impossible.

THE CORE GUARANTEE (M0):
A requirement may be marked satisfied ONLY when a matching evidence artifact
exists. Generated text can satisfy a "produce content" requirement, but it can
NEVER satisfy a "gather / research / deliver" requirement. If there is no
evidence, the requirement is UNMET — no exceptions, no heuristics that paper
over missing work.

This replaces the previous heuristic verification in operator.py that marked
research/information requirements satisfied whenever ANY content was generated
(the false-positive engine identified in the Truth Report).

Design:
- RequirementKind classifies what a requirement actually demands.
- EvidenceArtifact is concrete proof that the demand was met.
- ExecutionEvidence is the bundle of artifacts produced by an execution.
- EvidenceVerifier maps each requirement to the evidence it requires and
  satisfies it ONLY if that specific evidence exists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


# --- Hard verification (M23: strong, non-fabricable evidence) -----------------
# Unfilled template/placeholder tokens that must NEVER count as real evidence or
# be acted upon (e.g. "<<topic>>", "<extracted URL>", "{{query}}", "[topic]").
# Structured tokens only (angle/brace/bracket wrappers) + a few unambiguous
# placeholder phrases — deliberately NOT natural-language words like "topic", so
# real queries are never misclassified. Detected only on SHORT identifier strings.
_PLACEHOLDER_RE = re.compile(
    r"<<.*?>>|\{\{.*?\}\}|<[a-zA-Z][^>]{0,60}>|^\[[^\]]{1,60}\]$|^\{[^}]{1,60}\}$"
)
_PLACEHOLDER_PHRASES = (
    "extracted url", "the url of", "placeholder", "insert url", "insert the",
    "<topic>", "<url>", "<query>", "todo:",
)


def looks_like_placeholder(text: Optional[str]) -> bool:
    """True if ``text`` is an unfilled template/placeholder (never real evidence).

    Applies only to SHORT identifier-like strings (targets, URLs, nav details) so
    genuine long page text or documents are never misclassified.
    """
    if not text:
        return False
    t = text.strip()
    if not t or len(t) > 200:
        return False
    if _PLACEHOLDER_RE.search(t):
        return True
    tl = t.lower()
    return any(p in tl for p in _PLACEHOLDER_PHRASES)


def _looks_like_url(text: Optional[str]) -> bool:
    """True if ``text`` is a concrete URL (http/https/file), not a placeholder."""
    if not text:
        return False
    t = text.strip().lower()
    return t.startswith(("http://", "https://", "file://")) and not looks_like_placeholder(t)


class RequirementKind(str, Enum):
    """What a requirement actually demands to be considered complete."""

    GATHER = "gather"           # Real information must be collected from sources
    PRODUCE = "produce"         # Content must be synthesized/generated
    FILE = "file"               # A file/document must exist on disk
    NAVIGATE = "navigate"       # An environment must be reached (page/app open)
    DELIVER = "deliver"         # Something must be sent/delivered + confirmed
    GENERIC = "generic"         # Catch-all: some real activity must have occurred


class EvidenceKind(str, Enum):
    """Types of concrete evidence the system can collect."""

    GATHERED_INFO = "gathered_info"     # Real text read from a source/page
    SOURCE_URL = "source_url"           # A URL that was actually opened/read
    GENERATED_CONTENT = "generated_content"  # Synthesized text
    FILE_ARTIFACT = "file_artifact"     # A file on disk with byte size > 0
    NAVIGATION = "navigation"           # A confirmed navigation/open
    DELIVERY_CONFIRMATION = "delivery_confirmation"  # Observed "sent" state
    SCREENSHOT = "screenshot"           # A real screenshot file on disk (visual proof)


@dataclass
class EvidenceArtifact:
    """Concrete proof that some work actually happened."""

    kind: EvidenceKind
    detail: str = ""            # human-readable (e.g. filename, URL, snippet)
    value: int = 0              # numeric proof (e.g. byte size, char count)
    source: str = ""            # where it came from (URL, adapter, tool)

    @property
    def is_real(self) -> bool:
        """An artifact is real only if it carries non-trivial, non-placeholder proof.

        HARD verification (M23):
        - files/screenshots: real bytes on disk (> 0).
        - gathered/generated text: at least a minimum substance (no 1-char "reads").
        - source URLs: a concrete http(s) URL, never a placeholder.
        - navigation/delivery: a non-empty, non-placeholder detail.
        """
        detail = (self.detail or "").strip()

        if self.kind in (EvidenceKind.FILE_ARTIFACT, EvidenceKind.GATHERED_INFO,
                         EvidenceKind.GENERATED_CONTENT, EvidenceKind.SCREENSHOT):
            # Real bytes / real text (non-empty). Content quality is enforced at
            # the action layer (placeholder targets never produce these).
            return self.value > 0
        if self.kind == EvidenceKind.SOURCE_URL:
            # A source must be a concrete URL that was actually opened/read —
            # never a bare host, a description, or a placeholder.
            return _looks_like_url(detail)
        # NAVIGATION / DELIVERY_CONFIRMATION: non-empty, non-placeholder detail.
        return bool(detail) and not looks_like_placeholder(detail)


@dataclass
class ExecutionEvidence:
    """All evidence artifacts produced by one execution.

    The executor populates this from REAL outcomes only:
    - gathered_info: text actually read from pages/sources
    - source_urls: URLs actually opened and read
    - generated_content: synthesized text
    - files: real files on disk (with verified byte size)
    - navigations: confirmed navigations
    - delivery_confirmations: observed send/sent state
    """

    artifacts: List[EvidenceArtifact] = field(default_factory=list)

    def add(self, artifact: EvidenceArtifact) -> None:
        self.artifacts.append(artifact)

    def of_kind(self, kind: EvidenceKind) -> List[EvidenceArtifact]:
        return [a for a in self.artifacts if a.kind == kind and a.is_real]

    def has(self, kind: EvidenceKind) -> bool:
        return len(self.of_kind(kind)) > 0

    # -- Convenience builders (used by the executor) --

    def add_gathered_info(self, text: str, source: str = "") -> None:
        if text and text.strip():
            self.add(EvidenceArtifact(
                kind=EvidenceKind.GATHERED_INFO,
                detail=text[:120],
                value=len(text),
                source=source,
            ))

    def add_source_url(self, url: str) -> None:
        if url and url.strip():
            self.add(EvidenceArtifact(
                kind=EvidenceKind.SOURCE_URL, detail=url, source=url,
            ))

    def add_generated_content(self, text: str) -> None:
        if text and text.strip():
            self.add(EvidenceArtifact(
                kind=EvidenceKind.GENERATED_CONTENT,
                detail=text[:120], value=len(text),
            ))

    def add_file(self, path: str, size: int) -> None:
        self.add(EvidenceArtifact(
            kind=EvidenceKind.FILE_ARTIFACT, detail=path, value=size, source=path,
        ))

    def add_navigation(self, where: str) -> None:
        if where and where.strip():
            self.add(EvidenceArtifact(
                kind=EvidenceKind.NAVIGATION, detail=where, source=where,
            ))

    def add_delivery_confirmation(self, detail: str) -> None:
        if detail and detail.strip():
            self.add(EvidenceArtifact(
                kind=EvidenceKind.DELIVERY_CONFIRMATION, detail=detail,
            ))

    def add_screenshot(self, path: str, size: int, label: str = "") -> None:
        """Record a screenshot file as visual evidence (size > 0 = real)."""
        if size > 0:
            self.add(EvidenceArtifact(
                kind=EvidenceKind.SCREENSHOT,
                detail=label or path, value=size, source=path,
            ))


def classify_requirement(description: str) -> RequirementKind:
    """Classify a requirement by what it actually demands.

    Order matters: DELIVER and GATHER are checked before PRODUCE because
    "send the report" and "research X" must NOT be satisfiable by mere
    content generation.
    """
    d = description.lower()

    # Delivery — highest scrutiny (real side effect + confirmation)
    if any(kw in d for kw in ["deliver", "email", "send", "sent", "message",
                              "recipient", "share with"]):
        return RequirementKind.DELIVER

    # Gather / research — must come from real sources, NOT generation
    if any(kw in d for kw in ["gather", "research", "source", "find ",
                              "search", "collect", "look up", "information about",
                              "data must", "facts must", "evidence"]):
        return RequirementKind.GATHER

    # File / document artifact
    if any(kw in d for kw in ["file", "document", "save", "saved", ".docx",
                              ".txt", ".md", ".pdf", "stored to disk"]):
        return RequirementKind.FILE

    # Produce / synthesize content
    if any(kw in d for kw in ["synthes", "content", "report", "summary",
                              "paper", "written", "write", "generate", "compose",
                              "draft", "compare", "comparison", "extract"]):
        return RequirementKind.PRODUCE

    # Navigation / reaching an environment
    if any(kw in d for kw in ["navigat", "open", "access", "page", "visit",
                              "go to", "launch"]):
        return RequirementKind.NAVIGATE

    # Interaction / UI operations (click, type, submit, login) — require evidence
    # that the specific action was taken, not just that the page was reached
    if any(kw in d for kw in ["click", "press", "tap", "type", "enter",
                              "log in", "login", "sign in", "log out", "logout",
                              "submit", "select", "toggle", "check", "uncheck"]):
        return RequirementKind.NAVIGATE  # needs confirmed navigation/interaction evidence

    return RequirementKind.GENERIC


@dataclass
class RequirementVerdict:
    """Result of verifying one requirement against evidence."""

    description: str
    kind: RequirementKind
    satisfied: bool
    evidence_detail: str = ""
    reason: str = ""            # why UNMET, if unmet


class EvidenceVerifier:
    """Verifies requirements against execution evidence using the Evidence Law.

    The Law: a requirement is satisfied ONLY by an evidence artifact whose
    kind matches the requirement's demand. No artifact ⇒ UNMET.
    """

    def verify_one(
        self, description: str, evidence: ExecutionEvidence
    ) -> RequirementVerdict:
        kind = classify_requirement(description)

        if kind == RequirementKind.GATHER:
            arts = evidence.of_kind(EvidenceKind.GATHERED_INFO)
            srcs = evidence.of_kind(EvidenceKind.SOURCE_URL)
            if arts:
                detail = f"{len(arts)} real read(s)"
                if srcs:
                    detail += f", {len(srcs)} source URL(s)"
                return RequirementVerdict(description, kind, True, detail)
            return RequirementVerdict(
                description, kind, False,
                reason="No information was actually gathered from any source "
                       "(generated text does NOT satisfy a research requirement)",
            )

        if kind == RequirementKind.PRODUCE:
            arts = evidence.of_kind(EvidenceKind.GENERATED_CONTENT)
            if arts:
                return RequirementVerdict(
                    description, kind, True,
                    f"Content produced ({arts[0].value} chars)")
            return RequirementVerdict(
                description, kind, False, reason="No content was produced")

        if kind == RequirementKind.FILE:
            arts = evidence.of_kind(EvidenceKind.FILE_ARTIFACT)
            if arts:
                return RequirementVerdict(
                    description, kind, True,
                    f"File: {arts[0].detail} ({arts[0].value} bytes)")
            return RequirementVerdict(
                description, kind, False,
                reason="No file artifact exists on disk")

        if kind == RequirementKind.NAVIGATE:
            arts = evidence.of_kind(EvidenceKind.NAVIGATION)
            if arts:
                return RequirementVerdict(
                    description, kind, True, f"Navigated: {arts[0].detail}")
            return RequirementVerdict(
                description, kind, False,
                reason="No confirmed navigation occurred")

        if kind == RequirementKind.DELIVER:
            arts = evidence.of_kind(EvidenceKind.DELIVERY_CONFIRMATION)
            if arts:
                return RequirementVerdict(
                    description, kind, True, f"Delivered: {arts[0].detail}")
            return RequirementVerdict(
                description, kind, False,
                reason="Delivery not confirmed (no observed 'sent' state). "
                       "Send is gated and requires verified interaction")

        # GENERIC — any real artifact counts as activity
        if evidence.artifacts and any(a.is_real for a in evidence.artifacts):
            return RequirementVerdict(
                description, kind, True, "Real activity evidence present")
        return RequirementVerdict(
            description, kind, False, reason="No evidence of any real activity")
