"""Per-requirement repair — diagnose WHY a requirement is unmet and fix only it.

Before M4, the operator either re-ran the WHOLE plan or accepted partial
success. That wastes work (re-doing satisfied requirements) and rarely helps.

This module diagnoses each UNMET requirement against the execution evidence
and proposes a TARGETED repair: a small plan that addresses only that one
requirement, choosing a different approach than what already failed.

It is requirement-centric, not workflow-centric:
- GATHER unmet + no sources read  -> diagnose "no real sources" -> retry search
  with a different engine / open more links
- FILE unmet + content exists     -> diagnose "file not written" -> just write
  the file from existing content (don't re-gather)
- PRODUCE unmet + info gathered    -> diagnose "not synthesized" -> generate from
  gathered info
- NAVIGATE/DELIVER unmet           -> diagnose access/confirmation gap

The diagnosis drives a minimal repair plan so the operator fixes the gap
without redoing everything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from friday.verification.evidence_law import (
    EvidenceKind,
    ExecutionEvidence,
    RequirementKind,
    classify_requirement,
)
from friday.tools.registry import ToolCapability


class RepairCause(str, Enum):
    """Why a requirement is unmet (diagnosed from evidence)."""

    NO_SOURCES = "no_sources"             # gather: nothing was read
    NO_CONTENT = "no_content"             # produce: nothing synthesized
    FILE_NOT_WRITTEN = "file_not_written" # file: content exists but no file
    NOT_NAVIGATED = "not_navigated"       # navigate: never reached
    DELIVERY_UNCONFIRMED = "delivery_unconfirmed"  # deliver: no confirmation
    BLOCKED = "blocked"                   # captcha/verification wall
    UNKNOWN = "unknown"


@dataclass
class RepairAction:
    """A targeted action to repair one requirement."""

    capability: ToolCapability
    target: str
    description: str


@dataclass
class RepairDiagnosis:
    """Diagnosis + targeted repair plan for a single unmet requirement."""

    requirement: str
    kind: RequirementKind
    cause: RepairCause
    actions: List[RepairAction] = field(default_factory=list)
    repairable: bool = True
    note: str = ""


class RepairDiagnoser:
    """Diagnoses unmet requirements and proposes minimal, targeted repairs."""

    def diagnose(
        self,
        requirement_description: str,
        evidence: ExecutionEvidence,
        *,
        blocked: bool = False,
    ) -> RepairDiagnosis:
        kind = classify_requirement(requirement_description)

        if blocked:
            return RepairDiagnosis(
                requirement=requirement_description, kind=kind,
                cause=RepairCause.BLOCKED, repairable=False,
                note="Blocked by captcha/verification — needs human or session change",
            )

        has_info = evidence.has(EvidenceKind.GATHERED_INFO)
        has_content = evidence.has(EvidenceKind.GENERATED_CONTENT)
        has_file = evidence.has(EvidenceKind.FILE_ARTIFACT)
        has_nav = evidence.has(EvidenceKind.NAVIGATION)

        if kind == RequirementKind.GATHER:
            # Nothing real was gathered → try searching/reading again.
            return RepairDiagnosis(
                requirement=requirement_description, kind=kind,
                cause=RepairCause.NO_SOURCES,
                actions=[
                    RepairAction(ToolCapability.SEARCH_WEB, requirement_description,
                                 "Retry research: search + open + read real sources"),
                    RepairAction(ToolCapability.EXTRACT_WEB_CONTENT, "results",
                                 "Extract content from opened pages"),
                ],
                note="No real sources were read; retry gathering",
            )

        if kind == RequirementKind.PRODUCE:
            if has_info:
                # Info exists but wasn't synthesized → just generate.
                return RepairDiagnosis(
                    requirement=requirement_description, kind=kind,
                    cause=RepairCause.NO_CONTENT,
                    actions=[RepairAction(ToolCapability.GENERATE_TEXT,
                                          requirement_description,
                                          "Synthesize content from gathered info")],
                    note="Gathered info present; synthesize it",
                )
            # No info to synthesize from → gather first, then produce.
            return RepairDiagnosis(
                requirement=requirement_description, kind=kind,
                cause=RepairCause.NO_CONTENT,
                actions=[
                    RepairAction(ToolCapability.SEARCH_WEB, requirement_description,
                                 "Gather info to synthesize from"),
                    RepairAction(ToolCapability.GENERATE_TEXT, requirement_description,
                                 "Synthesize content"),
                ],
                note="No content and no info; gather then synthesize",
            )

        if kind == RequirementKind.FILE:
            if has_content or has_info:
                # We have material — just write the file (don't re-gather!).
                return RepairDiagnosis(
                    requirement=requirement_description, kind=kind,
                    cause=RepairCause.FILE_NOT_WRITTEN,
                    actions=[RepairAction(ToolCapability.CREATE_FILE,
                                          requirement_description,
                                          "Write existing content to a file")],
                    note="Content exists; only the file write is missing",
                )
            # No content to write → produce first, then write.
            return RepairDiagnosis(
                requirement=requirement_description, kind=kind,
                cause=RepairCause.FILE_NOT_WRITTEN,
                actions=[
                    RepairAction(ToolCapability.GENERATE_TEXT, requirement_description,
                                 "Produce content for the file"),
                    RepairAction(ToolCapability.CREATE_FILE, requirement_description,
                                 "Write the file"),
                ],
                note="No content yet; produce then write",
            )

        if kind == RequirementKind.NAVIGATE:
            return RepairDiagnosis(
                requirement=requirement_description, kind=kind,
                cause=RepairCause.NOT_NAVIGATED,
                actions=[RepairAction(ToolCapability.NAVIGATE_URL,
                                      requirement_description,
                                      "Navigate to the required destination")],
                note="Navigation not confirmed; retry",
            )

        if kind == RequirementKind.DELIVER:
            return RepairDiagnosis(
                requirement=requirement_description, kind=kind,
                cause=RepairCause.DELIVERY_UNCONFIRMED, repairable=False,
                note="Delivery is safety-gated; needs verified interaction",
            )

        return RepairDiagnosis(
            requirement=requirement_description, kind=kind,
            cause=RepairCause.UNKNOWN, repairable=False,
            note="No targeted repair available",
        )
