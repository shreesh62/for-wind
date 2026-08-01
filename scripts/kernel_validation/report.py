"""M13 — parity report generator (legacy vs kernel, deterministic).

Consumes the (legacy, kernel) :class:`ValidationEvidence` pairs from the runner
and produces a deterministic Markdown parity report plus a machine-readable
summary comparing the two paths across behavior, correctness, reliability,
performance, recovery quality, and determinism.

Two counting rules keep the numbers honest:

* **Skipped is never a pass.** Skipped pairs are excluded from the agreement
  denominator (they would trivially "agree") and never counted as passes.
* **Probe-backed scenarios are excluded from the parity arithmetic.** A fault
  probe actuates a real fault and its verdict is path-independent, so the runner
  mirrors that one verdict onto both rows. Counting those as "paths agree" would
  inflate parity with an agreement nobody measured. They are reported separately,
  with their assertions, as actuation evidence.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from scripts.kernel_validation.evidence import ValidationEvidence

Pair = Tuple[ValidationEvidence, ValidationEvidence]


def _is_probe(pair: Pair) -> bool:
    legacy, kernel = pair
    return bool(legacy.probe_id or kernel.probe_id)


def summarize(pairs: List[Pair]) -> Dict[str, Any]:
    """Deterministic machine-readable summary of a validation run."""
    total = len(pairs)
    skipped = sum(1 for legacy, _k in pairs if legacy.result == "skipped")
    ran = total - skipped

    parity_pairs = [p for p in pairs if not _is_probe(p)]
    probe_pairs = [p for p in pairs if _is_probe(p)]

    both_pass = sum(
        1 for legacy, kernel in pairs
        if legacy.result == "pass" and kernel.result == "pass"
    )
    # Agreement is measured only over scenarios that actually RAN and that were
    # measured on BOTH paths. Skipped pairs trivially agree; probe-backed pairs
    # mirror a single path-independent verdict. Either would inflate parity.
    agree = sum(
        1 for legacy, kernel in parity_pairs
        if legacy.result != "skipped" and legacy.result == kernel.result
    )
    parity_ran = sum(
        1 for legacy, _k in parity_pairs if legacy.result != "skipped"
    )
    kernel_pass = sum(1 for _l, kernel in pairs if kernel.result == "pass")
    legacy_pass = sum(1 for legacy, _k in pairs if legacy.result == "pass")

    return {
        "total": total,
        "ran": ran,
        "skipped": skipped,
        "both_pass": both_pass,
        "paths_agree": agree,
        "parity_measured": parity_ran,
        "kernel_pass": kernel_pass,
        "legacy_pass": legacy_pass,
        "parity_rate": round(agree / parity_ran, 4) if parity_ran else 0.0,
        "probe_total": len(probe_pairs),
        "probe_pass": sum(1 for _l, k in probe_pairs if k.result == "pass"),
        "probe_fail": sum(1 for _l, k in probe_pairs if k.result == "fail"),
        "probe_skipped": sum(1 for _l, k in probe_pairs if k.result == "skipped"),
    }


def render_markdown(pairs: List[Pair]) -> str:
    """Deterministic Markdown parity report for identical inputs."""
    s = summarize(pairs)
    lines: List[str] = []
    lines.append("# Kernel vs Legacy — Parity Report")
    lines.append("")
    lines.append(f"- Scenarios total: {s['total']}")
    lines.append(f"- Ran: {s['ran']}  |  Skipped (requires_live in DRY_RUN): {s['skipped']}")
    lines.append(f"- Legacy pass: {s['legacy_pass']}  |  Kernel pass: {s['kernel_pass']}")
    lines.append(
        f"- Paths agree: {s['paths_agree']}/{s['parity_measured']} dual-path scenarios"
        f"  |  Parity rate: {s['parity_rate']}"
    )
    if s["probe_total"]:
        lines.append(
            f"- Fault-actuation probes: {s['probe_total']} "
            f"(pass {s['probe_pass']} | fail {s['probe_fail']} | "
            f"skipped {s['probe_skipped']}) — excluded from the parity rate because a "
            "probe verdict is path-independent, not a two-path measurement"
        )
    lines.append("")

    lines.append("## Dual-path scenarios (goal text on both paths)")
    lines.append("")
    lines.append("| Scenario | Legacy | Kernel | Agree | Kernel latency (ms) |")
    lines.append("|---|---|---|---|---|")
    for legacy, kernel in pairs:
        if _is_probe((legacy, kernel)):
            continue
        agree = "✓" if legacy.result == kernel.result else "✗"
        lines.append(
            f"| {legacy.scenario_id} | {legacy.result} | {kernel.result} | {agree} "
            f"| {kernel.latency_ms:.1f} |"
        )
    lines.append("")

    # A failed scenario is only actionable with its reason. Without this a report
    # showing "fail" forced the reader to guess whether the cause was the kernel,
    # the legacy path, or the environment.
    failures = [
        (legacy, kernel) for legacy, kernel in pairs
        if not _is_probe((legacy, kernel))
        and (legacy.result == "fail" or kernel.result == "fail")
    ]
    if failures:
        lines.append("### Failure detail")
        lines.append("")
        for legacy, kernel in failures:
            lines.append(f"- **{legacy.scenario_id}**")
            for ev in (legacy, kernel):
                if ev.result != "fail":
                    continue
                reason = ev.error or ev.output or "(no reason recorded)"
                lines.append(f"  - {ev.path}: {str(reason)[:400]}")
        lines.append("")

    probe_pairs = [p for p in pairs if _is_probe(p)]
    if probe_pairs:
        lines.append("## Fault-actuation probes (real fault / real gate)")
        lines.append("")
        lines.append("| Scenario | Probe | Verdict | Latency (ms) |")
        lines.append("|---|---|---|---|")
        for _legacy, kernel in probe_pairs:
            lines.append(
                f"| {kernel.scenario_id} | {kernel.probe_id} | {kernel.result} "
                f"| {kernel.latency_ms:.1f} |"
            )
        lines.append("")
        for _legacy, kernel in probe_pairs:
            lines.append(f"### {kernel.scenario_id} — {kernel.result}")
            lines.append("")
            if kernel.assertions:
                for assertion in kernel.assertions:
                    lines.append(f"- {assertion}")
            else:
                lines.append("- (no assertions recorded)")
            if kernel.error:
                lines.append("")
                lines.append(f"**Reason:** {kernel.error}")
            lines.append("")

    return "\n".join(lines)
