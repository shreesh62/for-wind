"""M10 — End-to-end integration test (research → document → dry-run deliver).

Exercises the M10 domains composing capabilities through a REAL
``CapabilityRegistry`` seeded with stub capabilities, and confirms the Evidence
Law artifacts (``SOURCE_URL`` / ``FILE_ARTIFACT`` / ``DELIVERY_CONFIRMATION``)
line up end-to-end. The stubs are ``BaseCapability`` subclasses discovered by
abstract verb only (no hardcoded app/site name, Axiom 15); no real disk or
network I/O ever happens under ``FRIDAY_DRY_RUN=1``.

Requirements: 1.1, 2.2, 3.2, 3.3
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import asyncio
from typing import Any, Dict, List, Optional

from friday.actions.result import ActionEvidence, ActionResult
from friday.capabilities.contracts import BaseCapability
from friday.capabilities.registry import CapabilityRegistry
from friday.domains.communication import CommunicationDomain
from friday.domains.documents import DocumentDomain
from friday.domains.models import (
    Block,
    DeliveryStatus,
    DocumentFormat,
    Section,
    SemanticDocument,
)
from friday.kernel.contracts.capability import Condition, WorldStateDelta
from friday.verification.evidence_law import EvidenceKind, ExecutionEvidence


# --------------------------------------------------------------------------- #
# Stub capabilities — BaseCapability subclasses discovered by abstract verb.
# --------------------------------------------------------------------------- #
class StubCreateFileCapability(BaseCapability):
    """A ``create_file``-verb stub that writes nothing to real disk (DRY_RUN).

    Returns a successful ``ActionResult`` whose evidence carries the synthetic
    path and byte size so ``DocumentDomain.export`` can record a real
    ``FILE_ARTIFACT`` without touching the filesystem.
    """

    @property
    def id(self) -> str:
        return "stub.create_file"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def verbs(self) -> List[str]:
        return ["create_file"]

    def preconditions(self) -> List[Condition]:
        return []

    def expected_outcome(self) -> WorldStateDelta:
        return WorldStateDelta()

    async def execute(self, params: Dict[str, Any], world: Any) -> ActionResult:
        # DRY_RUN honoured: no real file is written; size is computed from bytes.
        content = params.get("content", "")
        size = len(content.encode("utf-8"))
        return ActionResult.success(
            action="create_file",
            target=params["filename"],
            message="written",
            evidence=ActionEvidence(
                state_changed=True,
                raw={"path": params["filename"], "size": size},
            ),
        )

    def verify(self, result: ActionResult, world: Any) -> bool:
        return result.is_success

    def recover(self, failure: ActionResult) -> Optional[BaseCapability]:
        return None


class StubDeliverCapability(BaseCapability):
    """A ``deliver``-verb stub that records a (dry-run) send.

    Returns a successful ``ActionResult``; the observed sent-state confirmation
    is added to the evidence bundle by the test flow (representing a real
    observed confirmation) so the Evidence Law stays honest — generated text
    alone never confirms delivery.
    """

    @property
    def id(self) -> str:
        return "stub.deliver"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def verbs(self) -> List[str]:
        return ["deliver"]

    def preconditions(self) -> List[Condition]:
        return []

    def expected_outcome(self) -> WorldStateDelta:
        return WorldStateDelta()

    async def execute(self, params: Dict[str, Any], world: Any) -> ActionResult:
        return ActionResult.success(
            action="deliver",
            target=params["recipient"],
            message="sent",
        )

    def verify(self, result: ActionResult, world: Any) -> bool:
        return result.is_success

    def recover(self, failure: ActionResult) -> Optional[BaseCapability]:
        return None


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def _build_document() -> SemanticDocument:
    """A small semantic document: a title + one section + a couple of blocks."""
    return SemanticDocument(
        title="Research Report",
        sections=(
            Section(
                heading="Findings",
                blocks=(
                    Block(text="The first observed finding."),
                    Block(text="A supporting detail.", style="bullet"),
                ),
            ),
        ),
    )


# --------------------------------------------------------------------------- #
# End-to-end flow.
# --------------------------------------------------------------------------- #
def test_research_document_deliver_end_to_end() -> None:
    """Gather → cite → export → deliver, with the Evidence Law lining up."""

    async def _flow() -> None:
        # 1. Real registry seeded with both stub capabilities.
        registry = CapabilityRegistry()
        registry.register(StubCreateFileCapability())
        registry.register(StubDeliverCapability())

        # 2. Simulate gathered research on the evidence bundle.
        evidence = ExecutionEvidence()
        evidence.add_source_url("alpha.gov/a")
        evidence.add_source_url("beta.org/b")
        evidence.add_gathered_info("some gathered text", source="alpha.gov/a")

        # 3. Build a semantic document and cite it against the gathered sources.
        doc = _build_document()
        cited_doc = DocumentDomain(registry).cite(doc, evidence)
        assert len(cited_doc.citations) == 2
        cited_urls = {c.source_url for c in cited_doc.citations}
        assert cited_urls == {"alpha.gov/a", "beta.org/b"}

        # 4. Export the cited document via the create_file stub.
        export_outcome = await DocumentDomain(registry).export(
            cited_doc, "report.md", DocumentFormat.MARKDOWN, evidence
        )
        assert export_outcome.success is True
        assert export_outcome.bytes_written > 0
        assert evidence.has(EvidenceKind.FILE_ARTIFACT)
        assert evidence.has(EvidenceKind.GENERATED_CONTENT)

        # 5. Deliver: record the real observed sent-state, then deliver.
        evidence.add_delivery_confirmation("observed sent")
        delivery_outcome = await CommunicationDomain(registry).deliver(
            "recipient-id", "the report is ready", evidence
        )
        assert delivery_outcome.confirmed is True
        assert delivery_outcome.capability_id == "stub.deliver"

        # 6. Evidence Law artifacts line up end-to-end.
        assert evidence.has(EvidenceKind.SOURCE_URL) is True
        assert evidence.has(EvidenceKind.FILE_ARTIFACT) is True
        assert evidence.has(EvidenceKind.DELIVERY_CONFIRMATION) is True

    asyncio.run(_flow())


def test_export_unavailable_without_capability() -> None:
    """With no ``create_file`` capability, export fails and records no file."""

    async def _flow() -> None:
        registry = CapabilityRegistry()  # empty
        evidence = ExecutionEvidence()

        outcome = await DocumentDomain(registry).export(
            _build_document(), "report.md", DocumentFormat.MARKDOWN, evidence
        )

        assert outcome.success is False
        assert evidence.has(EvidenceKind.FILE_ARTIFACT) is False

    asyncio.run(_flow())


def test_deliver_unavailable_without_capability() -> None:
    """With no ``deliver`` capability, delivery degrades to UNAVAILABLE."""

    async def _flow() -> None:
        registry = CapabilityRegistry()  # empty
        evidence = ExecutionEvidence()

        outcome = await CommunicationDomain(registry).deliver(
            "recipient-id", "the report is ready", evidence
        )

        assert outcome.status is DeliveryStatus.UNAVAILABLE

    asyncio.run(_flow())
