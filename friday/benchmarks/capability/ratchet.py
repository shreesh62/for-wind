"""M14 — the competence ratchet: baselines + a must-improve regression gate.

Persists per-domain competence baselines and gates regressions: a milestone that
drops a MEASURED domain below its baseline (minus tolerance) fails the ratchet.
Unmeasured baselines never block — the first real-machine run establishes them.
The ratchet fabricates nothing: a domain is `measured` only when a real score is
recorded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class DomainScore:
    """A per-domain competence score; `measured` is False until a real run."""

    domain: str
    score: float
    measured: bool


@dataclass(frozen=True)
class RatchetVerdict:
    """Outcome of a ratchet check."""

    passed: bool
    regressions: Tuple[str, ...] = ()
    improvements: Tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class CompetenceScorecard:
    """Human-facing aggregate: per-domain scores + verdict + overall."""

    domain_scores: Tuple[DomainScore, ...]
    verdict: RatchetVerdict
    overall: float

    def to_markdown(self) -> str:
        lines = ["# Competence Scorecard", ""]
        lines.append(f"- Overall (mean of measured domains): {self.overall:.4f}")
        lines.append(f"- Ratchet: {'PASS' if self.verdict.passed else 'FAIL'}")
        if self.verdict.regressions:
            lines.append(f"- Regressions: {', '.join(self.verdict.regressions)}")
        if self.verdict.improvements:
            lines.append(f"- Improvements: {', '.join(self.verdict.improvements)}")
        lines.append("")
        lines.append("| Domain | Score | Measured |")
        lines.append("|---|---|---|")
        for ds in self.domain_scores:
            score_txt = f"{ds.score:.4f}" if ds.measured else "—"
            lines.append(f"| {ds.domain} | {score_txt} | {'yes' if ds.measured else 'no'} |")
        lines.append("")
        return "\n".join(lines)


class CompetenceRatchet:
    """Per-domain baselines + a regression gate (the must-improve mechanism)."""

    _DOMAINS = ("browser", "desktop", "research", "coding", "long_horizon")

    def __init__(self, baseline_path: str, local_path: Optional[str] = None) -> None:
        # The seed is the COMMITTED baseline (guarded pristine / all-unmeasured so
        # we never ship fabricated competence numbers). Real recorded baselines
        # persist to a local, gitignored sibling; load() overlays local over seed
        # and record() writes ONLY the local file.
        self._seed_path = Path(baseline_path)
        self._local_path = (
            Path(local_path)
            if local_path is not None
            else self._seed_path.with_name(self._seed_path.stem + ".local.json")
        )
        # Back-compat alias (some callers referenced ._path as the seed location).
        self._path = self._seed_path

    def _overlay(self, path: Path, result: Dict[str, DomainScore]) -> None:
        """Overlay per-domain scores from ``path`` onto ``result`` (in place).

        A missing/corrupt file is a no-op (fail-safe: never blocks, never raises).
        """
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — corrupt baseline never blocks / never raises
            return
        for d in self._DOMAINS:
            entry = data.get(d)
            if isinstance(entry, dict) and "score" in entry:
                try:
                    result[d] = DomainScore(
                        d, float(entry["score"]), bool(entry.get("measured", False))
                    )
                except (TypeError, ValueError):
                    continue

    def load(self) -> Dict[str, DomainScore]:
        """Load baselines: all-unmeasured defaults, then the committed seed, then
        the local recorded file overlaid on top (local wins per domain)."""
        result: Dict[str, DomainScore] = {
            d: DomainScore(d, 0.0, False) for d in self._DOMAINS
        }
        self._overlay(self._seed_path, result)
        self._overlay(self._local_path, result)
        return result

    def check(
        self, new_scores: Dict[str, float], *, tolerance: float = 0.05
    ) -> RatchetVerdict:
        """PASS iff no MEASURED domain regressed below baseline - tolerance.

        Unmeasured baselines never block (the new score establishes them).
        """
        baselines = self.load()
        regressions = []
        improvements = []
        for domain, new_score in new_scores.items():
            base = baselines.get(domain)
            if base is None or not base.measured:
                continue  # no baseline to regress against
            if new_score < base.score - tolerance:
                regressions.append(domain)
            elif new_score > base.score:
                improvements.append(domain)
        passed = not regressions
        detail = (
            "no regressions" if passed
            else f"regressed: {', '.join(sorted(regressions))}"
        )
        return RatchetVerdict(
            passed=passed,
            regressions=tuple(sorted(regressions)),
            improvements=tuple(sorted(improvements)),
            detail=detail,
        )

    def record(self, new_scores: Dict[str, float]) -> None:
        """Persist new baselines. A domain is marked measured=True only when a
        real score is supplied here; existing higher baselines are not lowered."""
        current = self.load()
        out: Dict[str, Dict] = {}
        for domain in self._DOMAINS:
            base = current.get(domain, DomainScore(domain, 0.0, False))
            if domain in new_scores:
                new_score = float(new_scores[domain])
                # Ratchet upward: never record a lower baseline than an existing
                # measured one (the gate protects the high-water mark).
                if base.measured and new_score < base.score:
                    out[domain] = {"score": base.score, "measured": True}
                else:
                    out[domain] = {"score": new_score, "measured": True}
            else:
                out[domain] = {"score": base.score, "measured": base.measured}
        # Write to the LOCAL file only — the committed seed stays pristine.
        self._local_path.parent.mkdir(parents=True, exist_ok=True)
        self._local_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
