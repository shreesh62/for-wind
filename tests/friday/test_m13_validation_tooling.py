"""M13 — tests for the kernel validation tooling (non-production).

Verifies the 5 correctness properties of the validation harness under
FRIDAY_DRY_RUN=1 with stub operators (no real I/O, no default changes, no
fabricated real-world results).

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 2.1
"""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import json
import types

from scripts.kernel_validation.evidence import ValidationEvidence
from scripts.kernel_validation.report import render_markdown, summarize
from scripts.kernel_validation.runner import ValidationRunner
from scripts.kernel_validation.scenarios import all_scenarios, categories


def _ok_factory(summary="done"):
    outcome = types.SimpleNamespace(completed=True, summary=summary, created_files=[])
    return lambda goal_text: types.SimpleNamespace(run=lambda g: outcome)


# --------------------------------------------------------------------------- #
# Scenario catalog completeness (Req 1.5)
# --------------------------------------------------------------------------- #
def test_all_18_categories_present():
    cats = set(categories())
    assert len(cats) == 18
    scenario_cats = {s.category for s in all_scenarios()}
    # Every required category is represented by at least one scenario.
    assert cats.issubset(scenario_cats)


def test_live_flags_present_on_expected_scenarios():
    by_id = {s.id: s for s in all_scenarios()}
    # Pure in-process scenarios must NOT require live.
    assert by_id["replay.event_log"].requires_live is False
    assert by_id["determinism.repeat_run"].requires_live is False
    # Real-environment scenarios must require live.
    assert by_id["browser.search_read"].requires_live is True
    assert by_id["desktop.open_app"].requires_live is True


# --------------------------------------------------------------------------- #
# Property 3 — evidence serializable
# --------------------------------------------------------------------------- #
def test_evidence_is_json_serializable():
    ev = ValidationEvidence("s", "kernel", "pass", event_types=("goal.completed",), latency_ms=1.2)
    blob = json.dumps(ev.to_dict())
    assert json.loads(blob)["scenario_id"] == "s"


# --------------------------------------------------------------------------- #
# Property 1 — runner changes no production default
# --------------------------------------------------------------------------- #
def test_runner_restores_flag_default():
    os.environ.pop("FRIDAY_USE_KERNEL_EXECUTION", None)
    runner = ValidationRunner(_ok_factory())
    # Use a non-live scenario so it actually runs in DRY_RUN.
    scenario = next(s for s in all_scenarios() if not s.requires_live)
    runner.run_scenario(scenario)
    # The flag was not left set as a global default.
    assert os.environ.get("FRIDAY_USE_KERNEL_EXECUTION") is None

    # Bridge default remains False regardless of the run.
    from friday.bridge import BridgeConfig
    assert BridgeConfig().use_kernel_execution is False


# --------------------------------------------------------------------------- #
# Property 2 — identical workload on both paths
# --------------------------------------------------------------------------- #
def test_both_paths_run_the_same_goal():
    runner = ValidationRunner(_ok_factory("same-outcome"))
    scenario = next(s for s in all_scenarios() if not s.requires_live)
    legacy, kernel = runner.run_scenario(scenario)
    assert legacy.scenario_id == kernel.scenario_id == scenario.id
    assert legacy.path == "legacy" and kernel.path == "kernel"
    # Both completed given the same successful stub outcome.
    assert legacy.result == "pass" and kernel.result == "pass"


# --------------------------------------------------------------------------- #
# Property 4 — live-only scenarios skipped safely in DRY_RUN
# --------------------------------------------------------------------------- #
def test_requires_live_scenarios_are_skipped_in_dry_run():
    assert os.environ.get("FRIDAY_DRY_RUN") == "1"
    runner = ValidationRunner(_ok_factory())
    live = next(s for s in all_scenarios() if s.requires_live)
    legacy, kernel = runner.run_scenario(live)
    assert legacy.result == "skipped"
    assert kernel.result == "skipped"


# --------------------------------------------------------------------------- #
# Property 5 — parity report deterministic
# --------------------------------------------------------------------------- #
def test_report_is_deterministic():
    pairs = [
        (ValidationEvidence("a", "legacy", "pass"), ValidationEvidence("a", "kernel", "pass")),
        (ValidationEvidence("b", "legacy", "pass"), ValidationEvidence("b", "kernel", "fail")),
        (ValidationEvidence("c", "legacy", "skipped"), ValidationEvidence("c", "kernel", "skipped")),
    ]
    assert render_markdown(pairs) == render_markdown(pairs)
    s = summarize(pairs)
    # 'a' agrees (pass/pass), 'b' disagrees, 'c' skipped (excluded from ran).
    assert s["skipped"] == 1
    assert s["ran"] == 2
    assert s["paths_agree"] == 1
