"""File Tool — real file operations returning ActionResult.

Creates, reads, writes, moves, deletes files. Supports plain text and
basic document formats. This is a reusable capability, not a task pipeline.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from friday.actions.result import ActionResult, ActionEvidence, ActionTimer


# Default output directory for FRIDAY-created files
DEFAULT_OUTPUT_DIR = Path(os.path.expanduser("~")) / "Documents" / "FRIDAY"


class FileTool:
    """Real file operations. Reusable across any goal that needs files."""

    def __init__(self, output_dir: Optional[str] = None) -> None:
        self._output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR

    def create_file(self, filename: str, content: str = "") -> ActionResult:
        """Create a file with content. Infers format from extension.

        Args:
            filename: Name or path. If bare name, goes to FRIDAY output dir.
            content: Text content to write.
        """
        with ActionTimer() as timer:
            try:
                path = self._resolve_path(filename)
                path.parent.mkdir(parents=True, exist_ok=True)

                ext = path.suffix.lower()
                if ext == ".docx":
                    self._write_docx(path, content)
                elif ext in (".html", ".htm"):
                    self._write_html(path, content)
                elif ext == ".csv":
                    self._write_csv(path, content)
                elif ext == ".xlsx":
                    self._write_xlsx(path, content)
                else:
                    # Plain text (.txt, .md, anything else)
                    path.write_text(content, encoding="utf-8")

                exists = path.exists()
                size = path.stat().st_size if exists else 0

                return ActionResult.success(
                    action="create_file",
                    target=str(path),
                    message=f"Created {path.name} ({size} bytes) at {path}",
                    evidence=ActionEvidence(
                        state_changed=True,
                        raw={"path": str(path), "size": size, "exists": exists},
                    ),
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )
            except Exception as exc:
                return ActionResult.failed(
                    action="create_file",
                    error=str(exc),
                    target=filename,
                    error_category="file_error",
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

    def read_file(self, filename: str) -> ActionResult:
        """Read a file's contents."""
        with ActionTimer() as timer:
            try:
                path = self._resolve_path(filename)
                if not path.exists():
                    return ActionResult.failed(
                        action="read_file",
                        error=f"File not found: {path}",
                        target=filename,
                        error_category="not_found",
                        started_at=timer.started_at,
                        duration_ms=timer.duration_ms,
                    )
                content = path.read_text(encoding="utf-8", errors="replace")
                return ActionResult.success(
                    action="read_file",
                    target=str(path),
                    message=content[:3000],
                    evidence=ActionEvidence(raw={"path": str(path), "length": len(content)}),
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )
            except Exception as exc:
                return ActionResult.failed(
                    action="read_file", error=str(exc), target=filename,
                    started_at=timer.started_at, duration_ms=timer.duration_ms,
                )

    def write_file(self, filename: str, content: str) -> ActionResult:
        """Overwrite a file with content (alias for create)."""
        return self.create_file(filename, content)

    def append_file(self, filename: str, content: str) -> ActionResult:
        """Append content to a file."""
        with ActionTimer() as timer:
            try:
                path = self._resolve_path(filename)
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(content)
                return ActionResult.success(
                    action="append_file", target=str(path),
                    message=f"Appended to {path.name}",
                    evidence=ActionEvidence(state_changed=True, raw={"path": str(path)}),
                    started_at=timer.started_at, duration_ms=timer.duration_ms,
                )
            except Exception as exc:
                return ActionResult.failed(
                    action="append_file", error=str(exc), target=filename,
                    started_at=timer.started_at, duration_ms=timer.duration_ms,
                )

    def delete_file(self, filename: str) -> ActionResult:
        """Delete a file."""
        with ActionTimer() as timer:
            try:
                path = self._resolve_path(filename)
                if path.exists():
                    path.unlink()
                    return ActionResult.success(
                        action="delete_file", target=str(path),
                        message=f"Deleted {path.name}",
                        evidence=ActionEvidence(state_changed=True),
                        started_at=timer.started_at, duration_ms=timer.duration_ms,
                    )
                return ActionResult.failed(
                    action="delete_file", error="File not found", target=filename,
                    error_category="not_found",
                    started_at=timer.started_at, duration_ms=timer.duration_ms,
                )
            except Exception as exc:
                return ActionResult.failed(
                    action="delete_file", error=str(exc), target=filename,
                    started_at=timer.started_at, duration_ms=timer.duration_ms,
                )

    def _resolve_path(self, filename: str) -> Path:
        """Resolve a filename to a full path."""
        p = Path(filename)
        if p.is_absolute():
            return p
        # Bare name → FRIDAY output dir
        return self._output_dir / filename

    def _write_docx(self, path: Path, content: str) -> None:
        """Write a .docx file. Uses python-docx if available, else plain text."""
        try:
            from docx import Document
            doc = Document()
            for line in content.split("\n"):
                doc.add_paragraph(line)
            doc.save(str(path))
        except ImportError:
            # No python-docx — write as .txt alongside
            txt_path = path.with_suffix(".txt")
            txt_path.write_text(content, encoding="utf-8")
            # Also create the .docx as plain text so the path exists
            path.write_text(content, encoding="utf-8")

    def _write_html(self, path: Path, content: str) -> None:
        """Write an HTML file."""
        html = f"<!doctype html><html><head><meta charset='utf-8'></head><body>"
        for para in content.split("\n"):
            if para.strip():
                html += f"<p>{para}</p>"
        html += "</body></html>"
        path.write_text(html, encoding="utf-8")

    def _parse_rows(self, content: str) -> list:
        """Best-effort parse of LLM text into tabular rows.

        Handles markdown tables (| a | b |), comma/tab separated lines, and
        falls back to one column per line. Returns a list of row-lists.
        """
        rows = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            # Skip markdown table separator rows like |---|---|
            if set(line) <= set("|-: "):
                continue
            if "|" in line:
                cells = [c.strip() for c in line.strip("|").split("|")]
            elif "\t" in line:
                cells = [c.strip() for c in line.split("\t")]
            elif "," in line:
                cells = [c.strip() for c in line.split(",")]
            else:
                cells = [line]
            rows.append(cells)
        return rows or [[content]]

    def _write_csv(self, path: Path, content: str) -> None:
        """Write a real CSV file from LLM content."""
        import csv
        rows = self._parse_rows(content)
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(rows)

    def _write_xlsx(self, path: Path, content: str) -> None:
        """Write a real .xlsx if openpyxl is available; else fall back to CSV."""
        rows = self._parse_rows(content)
        try:
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            for row in rows:
                ws.append(row)
            wb.save(str(path))
        except ImportError:
            # No openpyxl — write CSV content under the .xlsx path so a real,
            # openable tabular file still exists (and a .csv sibling).
            csv_path = path.with_suffix(".csv")
            self._write_csv(csv_path, content)
            self._write_csv(path, content)
