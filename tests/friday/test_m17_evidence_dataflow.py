"""Property + example tests for M17 — Evidence Law + executor data flow.

Feature: m17-long-horizon-synthesis

Exercises the pure `EvidenceVerifier` over in-memory `ExecutionEvidence`, plus
the deterministic executor data flow (`model_router=None`) and the source-URL
citation path (fake router capturing the prompt). No live network/model calls.

Properties covered: P6. Example tests cover Requirements 4.1-4.4.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.verification.evidence_law import (
    EvidenceKind,
    EvidenceVerifier,
    ExecutionEvidence,
    RequirementKind,
    classify_requirement,
)

PRODUCE_DESC = "A written summary must be synthesized and composed"
GATHER_DESC = "Relevant information must be gathered"


# --------------------------------------------------------------------------
# Property 6: Evidence Law enforces PRODUCE via GENERATED_CONTENT only
# --------------------------------------------------------------------------
# Feature: m17-long-horizon-synthesis, Property 6: Evidence Law enforces PRODUCE via GENERATED_CONTENT only
@settings(max_examples=100)
@given(present=st.booleans(), text=st.text(max_size=200))
def test_p6_produce_satisfied_iff_generated_content_present(present, text):
    """Validates: Requirements 3.3, 3.4, 6.3"""
    # Sanity: fixed descriptions classify as intended.
    assert classify_requirement(PRODUCE_DESC) == RequirementKind.PRODUCE
    assert classify_requirement(GATHER_DESC) == RequirementKind.GATHER

    ev = ExecutionEvidence()
    content = "SYNTHESIZED SUMMARY " + text  # always non-empty / non-whitespace
    if present:
        ev.add_generated_content(content)

    verifier = EvidenceVerifier()
    produce = verifier.verify_one(PRODUCE_DESC, ev)
    gather = verifier.verify_one(GATHER_DESC, ev)

    # (a) PRODUCE satisfied iff a GENERATED_CONTENT artifact is present.
    assert produce.satisfied == present
    # (b) a GENERATED_CONTENT artifact NEVER satisfies a GATHER requirement.
    assert gather.satisfied is False


# --------------------------------------------------------------------------
# Example: executor gather -> generate -> create_file data flow (no router)
# --------------------------------------------------------------------------
def test_generate_then_create_file_flow(tmp_path):
    """Validates: Requirements 4.1, 4.2, 4.3"""
    from friday.executor import GoalExecutor, ExecutionContext
    from friday.actions.file_tool import FileTool
    from friday.tools.registry import ToolCapability

    ex = GoalExecutor(model_router=None, file_tool=FileTool(output_dir=str(tmp_path)))
    ctx = ExecutionContext(goal="research jazz and save a document summarizing it")
    ctx.add_info("Jazz originated in New Orleans in the late 19th century.")

    # Synthesize: content derives from the gathered info (no-router path).
    ex._dispatch_generate("summarize the topic", ToolCapability.GENERATE_TEXT, ctx)
    assert ctx.generated_content
    assert ctx.generated_content == ctx.combined_info
    assert ctx.evidence.of_kind(EvidenceKind.GENERATED_CONTENT)

    # Save: the file receives the synthesized content, and a FILE_ARTIFACT is recorded.
    ex._dispatch_create_file("output.txt", ToolCapability.CREATE_FILE, ctx)
    assert ctx.created_files
    written = Path(ctx.created_files[-1]).read_text(encoding="utf-8")
    assert written == ctx.generated_content
    assert ctx.evidence.of_kind(EvidenceKind.FILE_ARTIFACT)


def test_create_file_prefers_generated_over_raw_gathered(tmp_path):
    """Validates: Requirements 4.2 — saved file is the synthesized document, not a raw dump."""
    from friday.executor import GoalExecutor, ExecutionContext
    from friday.actions.file_tool import FileTool
    from friday.tools.registry import ToolCapability

    ex = GoalExecutor(model_router=None, file_tool=FileTool(output_dir=str(tmp_path)))
    ctx = ExecutionContext(goal="save a report to output.txt")
    ctx.add_info("RAW GATHERED DUMP — should not be written to the file")
    ctx.generated_content = "SYNTHESIZED DISTINCT DOCUMENT"

    ex._dispatch_create_file("output.txt", ToolCapability.CREATE_FILE, ctx)
    written = Path(ctx.created_files[-1]).read_text(encoding="utf-8")
    assert written == "SYNTHESIZED DISTINCT DOCUMENT"
    assert "RAW GATHERED DUMP" not in written


# --------------------------------------------------------------------------
# Example: source URLs are cited in the synthesis prompt (Req 4.4)
# --------------------------------------------------------------------------
def test_generate_includes_source_urls_in_prompt():
    """Validates: Requirements 4.4 — cited summary, verified via a fake router (no live call)."""
    from friday.executor import GoalExecutor, ExecutionContext

    captured = {}

    class FakeRouter:
        async def complete(self, prompt, **kwargs):
            captured["prompt"] = prompt
            from friday.models.router import ModelResponse
            return ModelResponse(
                text="synthesized cited summary", model_used="m", provider="p",
            )

    ex = GoalExecutor(model_router=FakeRouter())
    ctx = ExecutionContext(goal="research jazz and produce a cited summary")
    ctx.add_info("Jazz facts gathered from sources.")
    ctx.evidence.add_source_url("https://example.com/jazz-history")
    ctx.evidence.add_source_url("https://example.org/new-orleans")

    result = ex._generate("summarize with citations", ctx)

    assert result == "synthesized cited summary"
    assert "prompt" in captured
    assert "https://example.com/jazz-history" in captured["prompt"]
    assert "https://example.org/new-orleans" in captured["prompt"]
