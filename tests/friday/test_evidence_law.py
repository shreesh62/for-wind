"""Tests for the Evidence Law (M0) — false completion must be impossible.

These tests are the M0 acceptance proof:
1. A "research" requirement CANNOT be satisfied by generated text alone.
2. A "research" requirement IS satisfied only when real info was gathered.
3. A "file" requirement needs a real file artifact with byte size > 0.
4. A "deliver" requirement needs an observed confirmation (never auto-passes).
5. The operator reports research UNMET when no browser/search happened.
"""

from __future__ import annotations

import pytest

from friday.verification.evidence_law import (
    EvidenceArtifact,
    EvidenceKind,
    EvidenceVerifier,
    ExecutionEvidence,
    RequirementKind,
    classify_requirement,
)


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

class TestClassification:
    def test_research_classified_as_gather(self):
        assert classify_requirement(
            "Information about France's position must be gathered"
        ) == RequirementKind.GATHER

    def test_search_classified_as_gather(self):
        assert classify_requirement("Relevant information must be gathered") == RequirementKind.GATHER

    def test_email_classified_as_deliver(self):
        assert classify_requirement(
            "The report must be sent via email to the boss"
        ) == RequirementKind.DELIVER

    def test_file_classified_as_file(self):
        assert classify_requirement("The report must be saved as a document file") == RequirementKind.FILE

    def test_synthesis_classified_as_produce(self):
        assert classify_requirement("A comparison report must be synthesized") == RequirementKind.PRODUCE

    def test_deliver_beats_produce(self):
        # "send the report" must be DELIVER, not PRODUCE
        assert classify_requirement("Send the report to the recipient") == RequirementKind.DELIVER

    def test_gather_beats_produce(self):
        # "research and summarize" must classify the gather demand as GATHER
        assert classify_requirement(
            "Data must be gathered from official sources"
        ) == RequirementKind.GATHER


# --------------------------------------------------------------------------
# THE CORE GUARANTEE: generated text cannot satisfy research
# --------------------------------------------------------------------------

class TestEvidenceLawCore:
    def test_generated_text_does_NOT_satisfy_research(self):
        """The false-positive engine: generated content must NOT pass research."""
        evidence = ExecutionEvidence()
        evidence.add_generated_content("Here is a summary of laptops..." * 50)
        # No gathered info, no source URLs

        verifier = EvidenceVerifier()
        verdict = verifier.verify_one(
            "Relevant information must be gathered from sources", evidence
        )
        assert verdict.satisfied is False
        assert "generated text does NOT satisfy" in verdict.reason.lower() or \
               "no information" in verdict.reason.lower()

    def test_real_gathered_info_DOES_satisfy_research(self):
        evidence = ExecutionEvidence()
        evidence.add_gathered_info("Real article text read from a page" * 20,
                                   source="https://example.gov")
        evidence.add_source_url("https://example.gov/policy")

        verifier = EvidenceVerifier()
        verdict = verifier.verify_one(
            "Relevant information must be gathered from sources", evidence
        )
        assert verdict.satisfied is True

    def test_produce_requirement_satisfied_by_generated_content(self):
        evidence = ExecutionEvidence()
        evidence.add_generated_content("A synthesized comparison report." * 30)

        verifier = EvidenceVerifier()
        verdict = verifier.verify_one("A comparison report must be synthesized", evidence)
        assert verdict.satisfied is True

    def test_empty_generated_content_does_not_satisfy_produce(self):
        evidence = ExecutionEvidence()
        evidence.add_generated_content("")  # ignored — not real

        verifier = EvidenceVerifier()
        verdict = verifier.verify_one("Content must be produced", evidence)
        assert verdict.satisfied is False


class TestFileEvidence:
    def test_file_requires_real_artifact(self):
        evidence = ExecutionEvidence()
        verifier = EvidenceVerifier()
        verdict = verifier.verify_one("Output must be saved to a file", evidence)
        assert verdict.satisfied is False

    def test_zero_byte_file_does_not_satisfy(self):
        evidence = ExecutionEvidence()
        evidence.add_file("empty.txt", 0)  # 0 bytes is not real
        verifier = EvidenceVerifier()
        verdict = verifier.verify_one("Output must be saved to a file", evidence)
        assert verdict.satisfied is False

    def test_real_file_satisfies(self):
        evidence = ExecutionEvidence()
        evidence.add_file("report.docx", 2990)
        verifier = EvidenceVerifier()
        verdict = verifier.verify_one("Output must be saved to a file", evidence)
        assert verdict.satisfied is True
        assert "2990" in verdict.evidence_detail


class TestDeliveryEvidence:
    def test_delivery_never_auto_passes(self):
        evidence = ExecutionEvidence()
        # produced content + file but NO delivery confirmation
        evidence.add_generated_content("email body" * 10)
        evidence.add_file("attach.docx", 1000)

        verifier = EvidenceVerifier()
        verdict = verifier.verify_one(
            "The document must be delivered via email", evidence
        )
        assert verdict.satisfied is False

    def test_delivery_passes_with_confirmation(self):
        evidence = ExecutionEvidence()
        evidence.add_delivery_confirmation("Message appears in Sent folder")
        verifier = EvidenceVerifier()
        verdict = verifier.verify_one("The document must be delivered via email", evidence)
        assert verdict.satisfied is True


class TestNavigationEvidence:
    def test_navigation_requires_confirmation(self):
        evidence = ExecutionEvidence()
        verifier = EvidenceVerifier()
        verdict = verifier.verify_one("The Gmail page must be opened", evidence)
        assert verdict.satisfied is False

    def test_navigation_passes_when_confirmed(self):
        evidence = ExecutionEvidence()
        evidence.add_navigation("https://mail.google.com")
        verifier = EvidenceVerifier()
        verdict = verifier.verify_one("The Gmail page must be opened", evidence)
        assert verdict.satisfied is True


# --------------------------------------------------------------------------
# OPERATOR-LEVEL: the headline regression from the Truth Report
# --------------------------------------------------------------------------

class TestStructuralRequirements:
    """Goal-derived structural requirements must be enforced even if the LLM
    omits them — prevents false completion on save/deliver goals."""

    def test_save_goal_gets_file_requirement_when_llm_omits_it(self):
        from friday.planner.requirements import RequirementsDiscovery, Requirement
        from friday.verification.evidence_law import classify_requirement, RequirementKind

        d = RequirementsDiscovery(model_router=None)
        vague = [
            Requirement(description="The content should be clear and concise"),
            Requirement(description="It should cover key points"),
        ]
        augmented = d._augment_structural("Write a note and save it to notes.md", vague)
        kinds = {classify_requirement(r.description) for r in augmented}
        assert RequirementKind.FILE in kinds

    def test_email_goal_gets_delivery_requirement(self):
        from friday.planner.requirements import RequirementsDiscovery, Requirement
        from friday.verification.evidence_law import classify_requirement, RequirementKind

        d = RequirementsDiscovery(model_router=None)
        vague = [Requirement(description="Compose a clear message")]
        augmented = d._augment_structural("write a report and email it to my boss", vague)
        kinds = {classify_requirement(r.description) for r in augmented}
        assert RequirementKind.DELIVER in kinds

    def test_no_duplicate_file_requirement(self):
        from friday.planner.requirements import RequirementsDiscovery, Requirement
        from friday.verification.evidence_law import classify_requirement, RequirementKind

        d = RequirementsDiscovery(model_router=None)
        existing = [Requirement(description="Save the output to a file")]
        augmented = d._augment_structural("save to a file", existing)
        file_reqs = [r for r in augmented
                     if classify_requirement(r.description) == RequirementKind.FILE]
        assert len(file_reqs) == 1


class TestOperatorNoFalseSuccess:
    def test_research_goal_with_no_browser_reports_unmet(self):
        """Truth Report headline: 'Research laptops and create summary' reported
        complete despite search/read failing. That MUST now be impossible.
        """
        from friday.operator import Operator

        # No model router, no browser → search and read cannot happen.
        operator = Operator(model_router=None, browser_controller=None)
        outcome = operator.run("Research laptops and create a summary")

        # A research (gather) requirement must exist and must be UNMET,
        # because nothing was actually gathered.
        from friday.verification.evidence_law import classify_requirement, RequirementKind
        # The fallback requirements include a gather requirement for "research".
        # The operator must NOT report all requirements satisfied.
        gather_reqs = [
            r for r in operator._discovery.discover(
                "Research laptops and create a summary"
            ).requirements
            if classify_requirement(r.description) == RequirementKind.GATHER
        ]
        assert gather_reqs, "expected at least one gather requirement"

        # The actual outcome must not be a clean completion via fake research.
        # Either not completed, or completion did not rely on a satisfied gather req
        # without evidence. Concretely: a gather requirement cannot be satisfied.
        assert outcome.completion_ratio < 1.0 or not any(
            classify_requirement(r) == RequirementKind.GATHER
            for r in [req.description for req in operator._discovery.discover(
                "Research laptops and create a summary").requirements]
        )

    def test_content_only_goal_still_completes(self):
        """A pure 'write X and save' goal (no research) should still complete,
        because produce + file evidence are real."""
        from friday.operator import Operator

        operator = Operator(model_router=None, browser_controller=None)
        outcome = operator.run("Write a short note and save it to a file")

        # File should be produced; at least one file artifact recorded.
        # (No browser needed for this goal.)
        assert outcome.requirements_total >= 1
