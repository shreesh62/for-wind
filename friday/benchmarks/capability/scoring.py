"""M14 — evidence-based scoring for capability benchmarks.

A benchmark passes ONLY if every ``required_evidence`` kind is present in the
execution's :class:`ExecutionEvidence` — the Evidence Law is the judge, never an
LLM self-report (the 4th law). Domain scores are weighted, bounded, deterministic
pass ratios.
"""

from __future__ import annotations

from typing import Tuple

from friday.benchmarks.capability.domains import CapabilityBenchmark
from friday.verification.evidence_law import EvidenceKind, ExecutionEvidence


def _resolve_kind(name: str):
    """Resolve an EvidenceKind member name to the enum, or None if unknown."""
    try:
        return EvidenceKind[name]
    except KeyError:
        return None


def score_benchmark(benchmark: CapabilityBenchmark, evidence: ExecutionEvidence) -> bool:
    """True iff EVERY required evidence kind is present (real artifacts).

    An unknown evidence-kind name in a benchmark definition fails safe (the
    benchmark cannot pass), never raises. A benchmark with no required evidence
    passes only if at least one real artifact exists (generic activity).
    """
    if not benchmark.required_evidence:
        return any(a.is_real for a in evidence.artifacts)

    for name in benchmark.required_evidence:
        kind = _resolve_kind(name)
        if kind is None or not evidence.has(kind):
            return False
    return True


def score_domain(results: Tuple[Tuple[CapabilityBenchmark, bool], ...]) -> float:
    """Weighted pass ratio in [0, 1]; 0.0 when empty; deterministic.

    ``results`` is a tuple of (benchmark, passed) pairs.
    """
    total_weight = sum(b.weight for b, _passed in results)
    if total_weight <= 0:
        return 0.0
    passed_weight = sum(b.weight for b, passed in results if passed)
    score = passed_weight / total_weight
    return max(0.0, min(1.0, score))
