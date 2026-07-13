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


def web_independence_suite() -> Tuple[CapabilityBenchmark, ...]:
    """M23 — prove a browser is operated as a generic desktop app, CDP-independent.

    Domain-general goals (capability-named, never a site — Axiom 15). The TARGET
    browser (Chrome/Edge/Firefox/Brave/Electron) is a HARNESS parameter, not part
    of the goal text: the same generic goals run against each browser to prove
    that correctness is browser-invariant. Executed with the CDP optimization
    DISABLED so the desktop pipeline is the sole execution path.

    This suite is intentionally NOT part of ``all_domain_suites()`` — it is a
    separate, explicitly-invoked suite so it never perturbs the five-domain
    competence scorecard/ratchet. Scores are reported honestly (measured/
    unmeasured) and recorded only to the gitignored local baseline.
    """
    return (
        CapabilityBenchmark(
            id="web_independence.launch",
            domain="web_independence",
            goal_text="Open a web browser and confirm it is the foreground environment.",
            required_evidence=("NAVIGATION",),
            acceptance="The target browser was launched / focused (confirmed reach).",
        ),
        CapabilityBenchmark(
            id="web_independence.navigate",
            domain="web_independence",
            goal_text="Open a public information page about a given topic and read its contents.",
            required_evidence=("NAVIGATION", "GATHERED_INFO"),
            acceptance="A real navigation occurred AND real page text was read.",
        ),
        CapabilityBenchmark(
            id="web_independence.search",
            domain="web_independence",
            goal_text="Search for a topic and read a result page about it.",
            required_evidence=("GATHERED_INFO", "SOURCE_URL"),
            acceptance="Gathered info AND a source URL recorded (generated text alone fails).",
        ),
        CapabilityBenchmark(
            id="web_independence.login_flow",
            domain="web_independence",
            goal_text="Reach an account area that requires being signed in and confirm the signed-in state.",
            required_evidence=("NAVIGATION", "GATHERED_INFO"),
            acceptance="Navigation to the authenticated area AND observed signed-in page state.",
        ),
        CapabilityBenchmark(
            id="web_independence.file_upload",
            domain="web_independence",
            goal_text="Attach a local file to a page's file input and confirm it was accepted.",
            required_evidence=("NAVIGATION", "SCREENSHOT"),
            acceptance="Observed the file selected/accepted by the page (visual confirmation).",
        ),
        CapabilityBenchmark(
            id="web_independence.download_verify",
            domain="web_independence",
            goal_text="Download a file from a page and verify it exists on disk.",
            required_evidence=("FILE_ARTIFACT",),
            acceptance="A real downloaded file with byte size > 0 exists on disk.",
        ),
        CapabilityBenchmark(
            id="web_independence.multi_tab",
            domain="web_independence",
            goal_text="Open a second page in a new tab and read content from it, then return to the first.",
            required_evidence=("NAVIGATION", "GATHERED_INFO"),
            acceptance="Operated across at least two tabs and read content from another tab.",
        ),
        CapabilityBenchmark(
            id="web_independence.dynamic_interaction",
            domain="web_independence",
            goal_text="Interact with a dynamic control on a page and read the content it reveals.",
            required_evidence=("NAVIGATION", "GATHERED_INFO"),
            acceptance="A dynamic (JS-driven) update was triggered and its new content read.",
        ),
        CapabilityBenchmark(
            id="web_independence.infinite_scroll",
            domain="web_independence",
            goal_text="Scroll a long page to reveal additional content and read it.",
            required_evidence=("GATHERED_INFO", "SCREENSHOT"),
            acceptance="Content revealed only after scrolling was read (observed change).",
        ),
        CapabilityBenchmark(
            id="web_independence.unexpected_dialog",
            domain="web_independence",
            goal_text="Handle an unexpected dialog that appears and continue the task.",
            required_evidence=("NAVIGATION", "SCREENSHOT"),
            acceptance="A dialog was dismissed/accepted and the task continued (observed).",
        ),
        CapabilityBenchmark(
            id="web_independence.crash_recovery",
            domain="web_independence",
            goal_text="Recover after the browser becomes unavailable and re-establish the page.",
            required_evidence=("NAVIGATION",),
            acceptance="After a browser loss, a fresh navigation re-established the environment.",
        ),
    )


def all_domain_suites() -> Dict[str, Tuple[CapabilityBenchmark, ...]]:
    """Return every domain suite keyed by domain name.

    NOTE: ``web_independence`` (M23) is deliberately excluded — it is a separate,
    explicitly-invoked suite (see ``web_independence_suite``) so it never perturbs
    the five-domain competence scorecard/ratchet.
    """
    return {
        "browser": browser_suite(),
        "desktop": desktop_suite(),
        "research": research_suite(),
        "coding": coding_suite(),
        "long_horizon": long_horizon_suite(),
    }
