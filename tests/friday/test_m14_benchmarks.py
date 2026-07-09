"""M14 — tests for capability benchmarks + competence ratchet.

Verifies the 6 correctness properties under FRIDAY_DRY_RUN=1 using stub evidence.
No real competence numbers are asserted — real scores come only from a
real-machine run.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 3.3
"""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import ast
import json
from pathlib import Path

from friday.benchmarks.capability.domains import (
    CapabilityBenchmark,
    all_domain_suites,
)
from friday.benchmarks.capability.ratchet import CompetenceRatchet
from friday.benchmarks.capability.scoring import score_benchmark, score_domain
from friday.verification.evidence_law import ExecutionEvidence

_DOMAINS_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "friday" / "benchmarks" / "capability" / "domains.py"
)
_BANNED = ("gmail", "instagram", "whatsapp", "twitter", "facebook", "youtube")
_URL_SCHEMES = ("http://", "https://", "file://")


def _evidence_with(*builders):
    ev = ExecutionEvidence()
    for b in builders:
        b(ev)
    return ev


# --------------------------------------------------------------------------- #
# Property 5 — all five domains covered
# --------------------------------------------------------------------------- #
def test_all_five_domains_present():
    suites = all_domain_suites()
    assert set(suites) == {"browser", "desktop", "research", "coding", "long_horizon"}
    for domain, benches in suites.items():
        assert benches, f"{domain} has no benchmarks"
        for b in benches:
            assert b.acceptance, f"{b.id} lacks a measurable acceptance criterion"
            assert b.required_evidence, f"{b.id} lacks required evidence"


# --------------------------------------------------------------------------- #
# Property 6 — no app/site names or URL schemes in benchmark definitions
# --------------------------------------------------------------------------- #
def test_no_app_site_names_in_definitions():
    source = _DOMAINS_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    # Scan string literals (excluding docstrings) for banned names.
    doc_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(
                node.body[0].value, ast.Constant
            ) and isinstance(node.body[0].value.value, str):
                doc_ids.add(id(node.body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_ids:
            low = node.value.lower()
            for banned in _BANNED:
                assert banned not in low, f"banned name {banned!r} in benchmark defs"
            for scheme in _URL_SCHEMES:
                assert scheme not in low, f"url scheme {scheme!r} in benchmark defs"


# --------------------------------------------------------------------------- #
# Property 1 — evidence is the judge, never self-report
# --------------------------------------------------------------------------- #
def test_benchmark_passes_only_with_required_evidence():
    bench = CapabilityBenchmark(
        id="t", domain="research", goal_text="research a topic",
        required_evidence=("GATHERED_INFO", "SOURCE_URL"),
    )
    # Only generated content → FAIL (generation never satisfies a gather benchmark).
    only_generated = _evidence_with(lambda e: e.add_generated_content("a summary"))
    assert score_benchmark(bench, only_generated) is False

    # Gathered info but no source URL → still FAIL (missing a required kind).
    partial = _evidence_with(lambda e: e.add_gathered_info("real text", source="s"))
    # add_gathered_info with a source also records nothing for SOURCE_URL kind here:
    assert score_benchmark(bench, partial) is False

    # Both required kinds present → PASS.
    full = _evidence_with(
        lambda e: e.add_gathered_info("real text", source="s"),
        lambda e: e.add_source_url("host.example/x"),
    )
    assert score_benchmark(bench, full) is True


def test_unknown_evidence_kind_fails_safe():
    bench = CapabilityBenchmark(
        id="t", domain="x", goal_text="g", required_evidence=("NOT_A_REAL_KIND",),
    )
    full = _evidence_with(lambda e: e.add_generated_content("stuff"))
    assert score_benchmark(bench, full) is False


# --------------------------------------------------------------------------- #
# Property 2 — domain score is a bounded weighted ratio
# --------------------------------------------------------------------------- #
def test_domain_score_bounded_and_weighted():
    b1 = CapabilityBenchmark("a", "d", "g", ("GENERATED_CONTENT",), weight=1.0)
    b2 = CapabilityBenchmark("b", "d", "g", ("GENERATED_CONTENT",), weight=3.0)
    # b1 pass, b2 fail → 1/(1+3) = 0.25
    assert score_domain(((b1, True), (b2, False))) == 0.25
    assert score_domain(((b1, True), (b2, True))) == 1.0
    assert score_domain(((b1, False), (b2, False))) == 0.0
    assert score_domain(()) == 0.0


# --------------------------------------------------------------------------- #
# Property 3 — ratchet blocks regressions, allows improvements
# --------------------------------------------------------------------------- #
def test_ratchet_blocks_regression_allows_improvement(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({
        "browser": {"score": 0.8, "measured": True},
        "research": {"score": 0.5, "measured": True},
    }), encoding="utf-8")
    ratchet = CompetenceRatchet(str(path))

    # Regression on browser (0.8 → 0.6, tolerance 0.05) → FAIL.
    v = ratchet.check({"browser": 0.6, "research": 0.9})
    assert v.passed is False
    assert "browser" in v.regressions
    assert "research" in v.improvements

    # Hold/improve everywhere → PASS.
    v2 = ratchet.check({"browser": 0.8, "research": 0.7})
    assert v2.passed is True
    assert v2.regressions == ()


def test_ratchet_within_tolerance_passes(tmp_path):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"coding": {"score": 0.70, "measured": True}}), encoding="utf-8")
    ratchet = CompetenceRatchet(str(path))
    # 0.70 → 0.66 is within the 0.05 tolerance → PASS.
    assert ratchet.check({"coding": 0.66}).passed is True


# --------------------------------------------------------------------------- #
# Property 4 — ratchet never fabricates baselines
# --------------------------------------------------------------------------- #
def test_unmeasured_baseline_never_blocks(tmp_path):
    path = tmp_path / "baseline.json"  # does not exist → all unmeasured
    ratchet = CompetenceRatchet(str(path))
    loaded = ratchet.load()
    assert all(not ds.measured for ds in loaded.values())
    # A low score against an unmeasured baseline must NOT block.
    assert ratchet.check({"browser": 0.01}).passed is True


def test_record_marks_only_supplied_domains_measured(tmp_path):
    path = tmp_path / "baseline.json"
    ratchet = CompetenceRatchet(str(path))
    ratchet.record({"research": 0.6})
    loaded = ratchet.load()
    assert loaded["research"].measured is True
    assert loaded["research"].score == 0.6
    # Unsupplied domains remain unmeasured (not fabricated).
    assert loaded["browser"].measured is False


def test_record_ratchets_upward_only(tmp_path):
    path = tmp_path / "baseline.json"
    ratchet = CompetenceRatchet(str(path))
    ratchet.record({"coding": 0.7})
    ratchet.record({"coding": 0.5})  # attempt to lower
    loaded = ratchet.load()
    # High-water mark preserved.
    assert loaded["coding"].score == 0.7


def test_seeded_baseline_is_all_unmeasured():
    seeded = (
        Path(__file__).resolve().parent.parent.parent
        / "friday" / "benchmarks" / "capability" / "baseline.json"
    )
    data = json.loads(seeded.read_text(encoding="utf-8"))
    assert all(entry["measured"] is False for entry in data.values())
