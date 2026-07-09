"""M14 — capability benchmark suites for the five domains.

Each :class:`CapabilityBenchmark` is a realistic goal with a MEASURABLE
acceptance criterion and the objective `required_evidence` (Evidence-Law artifact
kinds) that prove it. Benchmarks are domain-general: the goal text names a
capability to accomplish, never a specific application or site (Axiom 15). Real
scoring happens on a real machine; `requires_live` benchmarks are skipped under
FRIDAY_DRY_RUN.

Required-evidence values are `EvidenceKind` member NAMES (strings) so this module
stays a pure declarative catalog; the scorer resolves them against
``friday.verification.evidence_law.EvidenceKind``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class CapabilityBenchmark:
    """A measurable, evidence-scored acceptance goal for one capability domain."""

    id: str
    domain: str
    goal_text: str
    required_evidence: Tuple[str, ...]
    weight: float = 1.0
    requires_live: bool = True
    acceptance: str = ""


# --- Domain suites ---------------------------------------------------------
#
# Evidence kinds referenced (names): GATHERED_INFO, SOURCE_URL, GENERATED_CONTENT,
# FILE_ARTIFACT, NAVIGATION, DELIVERY_CONFIRMATION, SCREENSHOT.


def browser_suite() -> Tuple[CapabilityBenchmark, ...]:
    """Browser operation — measured by real navigation + real content read."""
    return (
        CapabilityBenchmark(
            id="browser.navigate_and_read",
            domain="browser",
            goal_text="Open a public information page about a given topic and read its contents.",
            required_evidence=("NAVIGATION", "GATHERED_INFO"),
            acceptance="A real navigation occurred AND real page text was read (not generated).",
        ),
        CapabilityBenchmark(
            id="browser.search_multiple_sources",
            domain="browser",
            goal_text="Search for a topic and read two independent source pages about it.",
            required_evidence=("GATHERED_INFO", "SOURCE_URL"),
            acceptance="At least one gathered-info artifact AND at least one source URL recorded.",
        ),
    )


def desktop_suite() -> Tuple[CapabilityBenchmark, ...]:
    """Desktop operation — measured by a confirmed environment reach + artifact."""
    return (
        CapabilityBenchmark(
            id="desktop.open_and_confirm",
            domain="desktop",
            goal_text="Open a local application and confirm it is the foreground environment.",
            required_evidence=("NAVIGATION",),
            acceptance="A confirmed environment reach (app launched / window focused) is recorded.",
        ),
        CapabilityBenchmark(
            id="desktop.create_local_artifact",
            domain="desktop",
            goal_text="Use a local application to produce a saved file artifact.",
            required_evidence=("FILE_ARTIFACT",),
            acceptance="A real file with byte size > 0 exists on disk.",
        ),
    )


def research_suite() -> Tuple[CapabilityBenchmark, ...]:
    """Research — measured by gathered info + cited sources, never generation alone."""
    return (
        CapabilityBenchmark(
            id="research.gather_with_sources",
            domain="research",
            goal_text="Research a current topic and gather information from credible sources.",
            required_evidence=("GATHERED_INFO", "SOURCE_URL"),
            acceptance="Real gathered info AND source URLs (generated text alone fails).",
        ),
        CapabilityBenchmark(
            id="research.produce_cited_summary",
            domain="research",
            goal_text="Produce a written summary of a topic that cites the sources it used.",
            required_evidence=("GATHERED_INFO", "SOURCE_URL", "GENERATED_CONTENT"),
            acceptance="Gathered info + sources + produced content all present.",
        ),
    )


def coding_suite() -> Tuple[CapabilityBenchmark, ...]:
    """Coding — measured by a produced code artifact on disk."""
    return (
        CapabilityBenchmark(
            id="coding.produce_source_file",
            domain="coding",
            goal_text="Write a small program to a source file that satisfies a stated requirement.",
            required_evidence=("GENERATED_CONTENT", "FILE_ARTIFACT"),
            acceptance="Generated code content AND a real source file artifact exist.",
        ),
        CapabilityBenchmark(
            id="coding.edit_existing_file",
            domain="coding",
            goal_text="Modify an existing source file to add a required behavior.",
            required_evidence=("FILE_ARTIFACT",),
            acceptance="An updated file artifact exists on disk.",
        ),
    )


def long_horizon_suite() -> Tuple[CapabilityBenchmark, ...]:
    """Long-horizon — measured by a multi-stage goal producing gathered info + artifact."""
    return (
        CapabilityBenchmark(
            id="long_horizon.research_to_document",
            domain="long_horizon",
            goal_text=(
                "Complete a multi-stage goal: research a topic, then produce and save a "
                "document summarizing it with citations."
            ),
            required_evidence=("GATHERED_INFO", "SOURCE_URL", "GENERATED_CONTENT", "FILE_ARTIFACT"),
            acceptance="End-to-end evidence chain: gather → sources → content → saved file.",
        ),
    )


def all_domain_suites() -> Dict[str, Tuple[CapabilityBenchmark, ...]]:
    """Return every domain suite keyed by domain name."""
    return {
        "browser": browser_suite(),
        "desktop": desktop_suite(),
        "research": research_suite(),
        "coding": coding_suite(),
        "long_horizon": long_horizon_suite(),
    }
