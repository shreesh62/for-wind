"""Tests for per-requirement repair (M4).

Proves: the diagnoser correctly identifies WHY a requirement is unmet and
proposes a TARGETED repair (not a full re-run), and the executor's
execute_repair runs only those actions while reusing prior evidence.
"""

from __future__ import annotations

import pytest

from friday.planner.repair import (
    RepairDiagnoser,
    RepairCause,
    RepairDiagnosis,
)
from friday.verification.evidence_law import (
    ExecutionEvidence,
    RequirementKind,
)
from friday.tools.registry import ToolCapability


class TestDiagnoser:
    def test_file_unmet_with_content_only_writes_file(self):
        """If content exists but no file, repair should ONLY write the file
        — not re-gather or re-generate."""
        ev = ExecutionEvidence()
        ev.add_generated_content("A full report about X" * 20)
        d = RepairDiagnoser().diagnose("Output must be saved to a file", ev)
        assert d.cause == RepairCause.FILE_NOT_WRITTEN
        assert len(d.actions) == 1
        assert d.actions[0].capability == ToolCapability.CREATE_FILE

    def test_file_unmet_no_content_produces_then_writes(self):
        ev = ExecutionEvidence()
        d = RepairDiagnoser().diagnose("Save to a document file", ev)
        caps = [a.capability for a in d.actions]
        assert ToolCapability.GENERATE_TEXT in caps
        assert ToolCapability.CREATE_FILE in caps

    def test_produce_unmet_with_info_only_synthesizes(self):
        ev = ExecutionEvidence()
        ev.add_gathered_info("real source text " * 30, source="https://x.com")
        d = RepairDiagnoser().diagnose("A summary must be synthesized", ev)
        assert d.cause == RepairCause.NO_CONTENT
        assert len(d.actions) == 1
        assert d.actions[0].capability == ToolCapability.GENERATE_TEXT

    def test_gather_unmet_retries_research(self):
        ev = ExecutionEvidence()
        d = RepairDiagnoser().diagnose("Information must be gathered from sources", ev)
        assert d.cause == RepairCause.NO_SOURCES
        assert d.actions[0].capability == ToolCapability.SEARCH_WEB

    def test_delivery_not_repairable(self):
        ev = ExecutionEvidence()
        d = RepairDiagnoser().diagnose("The report must be emailed", ev)
        assert d.cause == RepairCause.DELIVERY_UNCONFIRMED
        assert d.repairable is False

    def test_blocked_not_repairable(self):
        ev = ExecutionEvidence()
        d = RepairDiagnoser().diagnose("Gather info", ev, blocked=True)
        assert d.cause == RepairCause.BLOCKED
        assert d.repairable is False


class TestExecuteRepair:
    def test_repair_writes_file_from_existing_content(self, tmp_path):
        """End-to-end: a FILE requirement repaired by writing existing content,
        WITHOUT re-running gather/produce."""
        from friday.executor import GoalExecutor, ExecutionResult
        from friday.actions.file_tool import FileTool
        from friday.verification.evidence_law import ExecutionEvidence, EvidenceKind
        from friday.planner.repair import RepairDiagnoser

        ev = ExecutionEvidence()
        ev.add_generated_content("Comparison report content here." * 10)

        prior = ExecutionResult(
            goal="compare X and Y and save",
            success=False, summary="", steps_executed=1, steps_skipped=0,
            final_content="Comparison report content here." * 10,
            evidence=ev,
        )

        ex = GoalExecutor(model_router=None, browser_controller=None,
                          file_tool=FileTool(output_dir=str(tmp_path)))
        diag = RepairDiagnoser().diagnose("Output must be saved to a file", ev)
        ran = ex.execute_repair(diag.actions, "compare X and Y and save", prior)

        assert ran is True
        assert len(prior.created_files) == 1
        # The file requirement is now satisfiable
        assert ev.has(EvidenceKind.FILE_ARTIFACT)
