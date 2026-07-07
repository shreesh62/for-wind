"""M13 — parity report generator (legacy vs kernel, deterministic).

Consumes the (legacy, kernel) :class:`ValidationEvidence` pairs from the runner
and produces a deterministic Markdown parity report plus a machine-readable
summary comparing the two paths across behavior, correctness, reliability,
performance, recovery quality, and determinism.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from scripts.kernel_validation.evidence import ValidationEvidence


def summarize(
    pairs: List[Tuple[ValidationEvidence, ValidationEvidence]]
) -> Dict[str, Any]:
    """Deterministic machine-readable summary of a validation run."""
    total = len(pairs)
    skipped = sum(1 for legacy, _k in pairs if legacy.result == "skipped")
    ran = total - skipped
    both_pass = sum(
        1 for legacy, kernel in pairs
        if legacy.result == "pass" and kernel.result == "pass"
    )
    # Agreement is measured only over scenarios that actually RAN (skipped pairs
    # trivially "agree" and would inflate the parity number).
    agree = sum(
        1 for legacy, kernel in pairs
        if legacy.result != "skipped" and legacy.result == kernel.result
    )
    kernel_pass = sum(1 for _l, kernel in pairs if kernel.result == "pass")
    legacy_pass = sum(1 for legacy, _k in pairs if legacy.result == "pass")
    return {
        "total": total,
        "ran": ran,
        "skipped": skipped,
        "both_pass": both_pass,
        "paths_agree": agree,
        "kernel_pass": kernel_pass,
        "legacy_pass": legacy_pass,
        "parity_rate": round(agree / ran, 4) if ran else 0.0,
    }


def render_markdown(
    pairs: List[Tuple[ValidationEvidence, ValidationEvidence]]
) -> str:
    """Deterministic Markdown parity report for identical inputs."""
    s = summarize(pairs)
    lines: List[str] = []
    lines.append("# Kernel vs Legacy — Parity Report")
    lines.append("")
    lines.append(f"- Scenarios total: {s['total']}")
    lines.append(f"- Ran: {s['ran']}  |  Skipped (requires_live in DRY_RUN): {s['skipped']}")
    lines.append(f"- Legacy pass: {s['legacy_pass']}  |  Kernel pass: {s['kernel_pass']}")
    lines.append(f"- Paths agree: {s['paths_agree']}/{s['ran']}  |  Parity rate: {s['parity_rate']}")
    lines.append("")
    lines.append("| Scenario | Legacy | Kernel | Agree | Kernel latency (ms) |")
    lines.append("|---|---|---|---|---|")
    for legacy, kernel in pairs:
        agree = "✓" if legacy.result == kernel.result else "✗"
        lines.append(
            f"| {legacy.scenario_id} | {legacy.result} | {kernel.result} | {agree} "
            f"| {kernel.latency_ms:.1f} |"
        )
    lines.append("")
    return "\n".join(lines)
