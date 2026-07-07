"""Ch 40 — semantic document model, multi-format export, citations (pure composition).

A ``DocumentDomain`` is a pure composition leaf (HANDOFF Section 12/13, Axiom
15): it renders a caller-owned :class:`SemanticDocument` value deterministically
to text, then delegates persistence to whatever ``create_file``-verb capability
the registry exposes. It names no application, site, or URL scheme literal, and
owns no durable cross-call state — the only instance attribute is the registry.
Citations are linked strictly to real ``SOURCE_URL`` evidence (Evidence Law
provenance); a citation is never invented without backing evidence.
"""

from __future__ import annotations

import html
from typing import Any

from friday.capabilities.registry import CapabilityRegistry
from friday.domains.models import (
    Citation,
    DocumentFormat,
    ExportOutcome,
    SemanticDocument,
)
from friday.verification.evidence_law import EvidenceKind, ExecutionEvidence


class DocumentDomain:
    """Ch 40 — semantic document model, multi-format export, citations (pure composition)."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        # The registry is the ONLY instance attribute; the domain owns no other
        # mutable state and nothing durable survives a call.
        self.registry = registry

    # -- Rendering -----------------------------------------------------------

    def render(self, document: SemanticDocument, fmt: DocumentFormat) -> str:
        """Pure, deterministic render of the semantic model to text.

        Same ``document`` + ``fmt`` always yields an identical string containing
        the title and every section heading and block text in document order.
        MARKDOWN / HTML / PLAINTEXT render directly; DOCX / PDF return the
        MARKDOWN string (the ``create_file`` capability handles binary
        formatting on export).
        """
        if fmt is DocumentFormat.HTML:
            return self._render_html(document)
        if fmt is DocumentFormat.PLAINTEXT:
            return self._render_plaintext(document)
        # MARKDOWN, and DOCX/PDF which defer binary formatting to create_file.
        return self._render_markdown(document)

    def _render_markdown(self, document: SemanticDocument) -> str:
        parts = [f"# {document.title}\n\n"]
        for section in document.sections:
            parts.append(f"## {section.heading}\n\n")
            for block in section.blocks:
                if block.style == "bullet":
                    parts.append(f"- {block.text}\n")
                elif block.style == "code":
                    parts.append(f"```\n{block.text}\n```\n\n")
                else:  # "body" and any other style
                    parts.append(f"{block.text}\n\n")
        if document.citations:
            parts.append("## References\n\n")
            for citation in document.citations:
                parts.append(f"{citation.marker} {citation.source_url}\n")
        return "".join(parts)

    def _render_plaintext(self, document: SemanticDocument) -> str:
        parts = [document.title]
        for section in document.sections:
            parts.append(section.heading)
            for block in section.blocks:
                parts.append(block.text)
        if document.citations:
            for citation in document.citations:
                parts.append(f"{citation.marker} {citation.source_url}")
        return "\n\n".join(parts)

    def _render_html(self, document: SemanticDocument) -> str:
        parts = [
            "<!doctype html><html><head><meta charset='utf-8'><title>",
            html.escape(document.title),
            "</title></head><body>",
            f"<h1>{html.escape(document.title)}</h1>",
        ]
        for section in document.sections:
            parts.append(f"<h2>{html.escape(section.heading)}</h2>")
            for block in section.blocks:
                text = html.escape(block.text)
                if block.style == "bullet":
                    parts.append(f"<li>{text}</li>")
                elif block.style == "code":
                    parts.append(f"<pre><code>{text}</code></pre>")
                else:  # "body" and any other style
                    parts.append(f"<p>{text}</p>")
        if document.citations:
            parts.append("<ol>")
            for citation in document.citations:
                parts.append(
                    f"<li>{html.escape(citation.marker)} "
                    f"{html.escape(citation.source_url)}</li>"
                )
            parts.append("</ol>")
        parts.append("</body></html>")
        return "".join(parts)

    # -- Export --------------------------------------------------------------

    async def export(
        self,
        document: SemanticDocument,
        filename: str,
        fmt: DocumentFormat,
        evidence: ExecutionEvidence,
        world: Any = None,
    ) -> ExportOutcome:
        """Render then persist via a ``create_file``-verb capability from the registry.

        Returns a failed ``ExportOutcome`` (never raises) when no capability
        matches. On success records a ``FILE_ARTIFACT`` and ``GENERATED_CONTENT``
        artifact; on failure records neither (Evidence Law — no file artifact
        unless a real file exists).
        """
        caps = self.registry.find_for("create_file")
        if not caps:
            return ExportOutcome(
                filename, fmt, success=False, error="no create_file capability"
            )

        content = self.render(document, fmt)
        result = await caps[0].execute(
            {"filename": filename, "content": content}, world
        )

        if getattr(result, "is_success", False):
            raw = getattr(getattr(result, "evidence", None), "raw", None) or {}
            size = raw.get("size")
            if size is None:
                size = len(content.encode("utf-8"))
            path = raw.get("path", filename)
            evidence.add_file(path, size)
            evidence.add_generated_content(content)
            return ExportOutcome(filename, fmt, bytes_written=size, success=True)

        return ExportOutcome(
            filename,
            fmt,
            success=False,
            error=getattr(result, "error", "export failed") or "export failed",
        )

    # -- Citations -----------------------------------------------------------

    def cite(
        self, document: SemanticDocument, evidence: ExecutionEvidence
    ) -> SemanticDocument:
        """Return a NEW document whose citations reference real ``SOURCE_URL`` evidence.

        Builds one ``Citation`` per real ``SOURCE_URL`` artifact, in order,
        linking produced content back to gathered sources. Never emits a
        citation without a backing ``SOURCE_URL`` artifact (Evidence Law).
        """
        sources = evidence.of_kind(EvidenceKind.SOURCE_URL)
        citations = tuple(
            Citation(marker=f"[{i + 1}]", source_url=art.detail)
            for i, art in enumerate(sources)
        )
        return SemanticDocument(
            title=document.title,
            sections=document.sections,
            citations=citations,
        )
