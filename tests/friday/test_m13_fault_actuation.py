"""M13 — tests for fault actuation (the C3/C7 probe layer, non-production).

Covers the probe protocol/registry, the runner's generic dispatch, report
arithmetic honesty, and the crash probe end-to-end with a REAL subprocess, a REAL
hard kill, and a REAL persisted event log (no LLM, no network, no mocks of the
thing under test).

Validates: Requirements 1.1, 1.2, 1.3, 6.1, 6.3, 6.4, 8.1, 8.2, 8.3
"""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import dataclasses
import json
import tempfile
import types

import pytest

import scripts.kernel_validation.probes  # noqa: F401 - registers the built-ins
from scripts.kernel_validation.evidence import ValidationEvidence
from scripts.kernel_validation.faults import (
    RESULT_FAIL,
    RESULT_PASS,
    RESULT_SKIPPED,
    FaultProbe,
    ProbeContext,
    ProbeVerdict,
    get_probe,
    register_probe,
)
from scripts.kernel_validation.report import render_markdown, summarize
from scripts.kernel_validation.runner import ValidationRunner
from scripts.kernel_validation.scenarios import all_scenarios


def _ok_factory():
    outcome = types.SimpleNamespace(completed=True, summary="done", created_files=[])
    return lambda goal_text, **kw: types.SimpleNamespace(run=lambda g: outcome)


def _scenario(scenario_id: str):
    return next(s for s in all_scenarios() if s.id == scenario_id)


class _StubProbe:
    """Minimal probe used to exercise dispatch without actuating anything."""

    def __init__(self, probe_id, verdict=None, raises=None):
        self.probe_id = probe_id
        self._verdict = verdict
        self._raises = raises
        self.calls = 0

    def actuate(self, context):
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return self._verdict


# --------------------------------------------------------------------------- #
# ProbeVerdict — a pass must carry observations (Req 6.1)
# --------------------------------------------------------------------------- #
def test_verdict_json_round_trip():
    verdict = ProbeVerdict("p", RESULT_PASS, assertions=("saw x", "saw y"), error="")
    blob = json.loads(json.dumps(verdict.to_dict()))
    assert blob["probe_id"] == "p"
    assert blob["result"] == RESULT_PASS
    assert blob["assertions"] == ["saw x", "saw y"]


def test_pass_with_no_assertions_is_rejected():
    with pytest.raises(ValueError):
        ProbeVerdict("p", RESULT_PASS)


def test_fail_and_skipped_may_carry_no_assertions():
    assert ProbeVerdict("p", RESULT_FAIL, error="why").result == RESULT_FAIL
    assert ProbeVerdict("p", RESULT_SKIPPED, error="why").result == RESULT_SKIPPED


def test_invalid_result_is_rejected():
    with pytest.raises(ValueError):
        ProbeVerdict("p", "probably")


# --------------------------------------------------------------------------- #
# Registry (Req 1.1, 1.3)
# --------------------------------------------------------------------------- #
def test_register_and_lookup():
    probe = _StubProbe("test.registry_lookup", ProbeVerdict("x", RESULT_FAIL))
    register_probe(probe)
    assert get_probe("test.registry_lookup") is probe
    assert isinstance(probe, FaultProbe)


def test_unknown_probe_id_returns_none():
    assert get_probe("test.nothing_registered_here") is None


def test_registering_without_probe_id_is_rejected():
    with pytest.raises(ValueError):
        register_probe(_StubProbe("", ProbeVerdict("x", RESULT_FAIL)))


def test_builtin_probes_are_registered():
    for probe_id in (
        "crash.restart_restore",
        "browser_fail.reconnect",
        "interrupt.pause_resume",
        "human.confirm_send",
    ):
        assert get_probe(probe_id) is not None, probe_id


def test_every_probe_scenario_has_a_registered_probe():
    for scenario in all_scenarios():
        if scenario.probe_id:
            assert get_probe(scenario.probe_id) is not None, scenario.id


# --------------------------------------------------------------------------- #
# Runner dispatch (Req 1.1, 1.2, 1.3)
# --------------------------------------------------------------------------- #
def test_probe_scenario_dispatches_to_the_probe():
    probe = _StubProbe(
        "test.dispatch_hit", ProbeVerdict("test.dispatch_hit", RESULT_PASS, ("observed",))
    )
    register_probe(probe)
    scenario = dataclasses.replace(
        _scenario("file.generate_report"),
        probe_id="test.dispatch_hit",
        requires_live=False,
    )
    legacy, kernel = ValidationRunner(_ok_factory()).run_scenario(scenario)
    assert probe.calls == 1
    assert kernel.result == RESULT_PASS
    assert kernel.probe_id == "test.dispatch_hit"
    assert kernel.assertions == ("observed",)
    # The legacy row must state plainly that no legacy measurement was taken.
    assert legacy.assertions and "no legacy-path measurement" in legacy.assertions[0]


def test_non_probe_scenario_uses_the_goal_text_path():
    scenario = _scenario("file.generate_report")
    assert scenario.probe_id == ""
    legacy, kernel = ValidationRunner(_ok_factory()).run_scenario(scenario)
    assert legacy.result == "pass" and kernel.result == "pass"
    assert legacy.probe_id == "" and kernel.probe_id == ""
    assert kernel.event_types  # the real kernel lifecycle path ran


def test_unknown_probe_id_fails_and_never_passes():
    scenario = dataclasses.replace(
        _scenario("file.generate_report"),
        probe_id="test.definitely_not_registered",
        requires_live=False,
    )
    legacy, kernel = ValidationRunner(_ok_factory()).run_scenario(scenario)
    assert kernel.result == RESULT_FAIL
    assert legacy.result == RESULT_FAIL
    assert "no probe registered" in kernel.error


def test_probe_exception_is_recorded_as_fail():
    register_probe(_StubProbe("test.raises", raises=RuntimeError("kaboom")))
    scenario = dataclasses.replace(
        _scenario("file.generate_report"), probe_id="test.raises", requires_live=False
    )
    legacy, kernel = ValidationRunner(_ok_factory()).run_scenario(scenario)
    assert kernel.result == RESULT_FAIL
    assert "kaboom" in kernel.error


def test_live_probe_scenario_is_skipped_in_dry_run_without_actuating():
    assert os.environ.get("FRIDAY_DRY_RUN") == "1"
    probe = _StubProbe(
        "test.never_called", ProbeVerdict("test.never_called", RESULT_PASS, ("nope",))
    )
    register_probe(probe)
    scenario = dataclasses.replace(
        _scenario("file.generate_report"),
        probe_id="test.never_called",
        requires_live=True,
    )
    legacy, kernel = ValidationRunner(_ok_factory()).run_scenario(scenario)
    assert legacy.result == RESULT_SKIPPED and kernel.result == RESULT_SKIPPED
    assert probe.calls == 0


def test_runner_still_restores_the_execution_flag_for_probe_scenarios():
    os.environ.pop("FRIDAY_USE_KERNEL_EXECUTION", None)
    register_probe(
        _StubProbe("test.flag", ProbeVerdict("test.flag", RESULT_PASS, ("ok",)))
    )
    scenario = dataclasses.replace(
        _scenario("file.generate_report"), probe_id="test.flag", requires_live=False
    )
    ValidationRunner(_ok_factory()).run_scenario(scenario)
    assert os.environ.get("FRIDAY_USE_KERNEL_EXECUTION") is None


# --------------------------------------------------------------------------- #
# Evidence backward compatibility (Req 6.3)
# --------------------------------------------------------------------------- #
def test_evidence_to_dict_keeps_original_keys():
    ev = ValidationEvidence("s", "kernel", "pass", event_types=("goal.completed",))
    blob = ev.to_dict()
    for key in (
        "scenario_id", "path", "result", "output", "event_types", "latency_ms", "error",
    ):
        assert key in blob
    assert blob["probe_id"] == ""
    assert blob["assertions"] == []
    json.dumps(blob)  # still serializable


# --------------------------------------------------------------------------- #
# Report arithmetic honesty (Req 6.4)
# --------------------------------------------------------------------------- #
def test_skipped_is_never_counted_as_a_pass():
    pairs = [
        (ValidationEvidence("a", "legacy", "skipped"),
         ValidationEvidence("a", "kernel", "skipped")),
    ]
    s = summarize(pairs)
    assert s["skipped"] == 1
    assert s["ran"] == 0
    assert s["both_pass"] == 0
    assert s["kernel_pass"] == 0 and s["legacy_pass"] == 0
    assert s["parity_rate"] == 0.0


def test_probe_rows_do_not_inflate_the_parity_rate():
    # One real dual-path disagreement plus a mirrored probe pass. The probe pair
    # agrees by construction and must not be counted as measured agreement.
    pairs = [
        (ValidationEvidence("dual", "legacy", "pass"),
         ValidationEvidence("dual", "kernel", "fail")),
        (ValidationEvidence("probe", "legacy", "pass", probe_id="p", assertions=("x",)),
         ValidationEvidence("probe", "kernel", "pass", probe_id="p", assertions=("x",))),
    ]
    s = summarize(pairs)
    assert s["parity_measured"] == 1
    assert s["paths_agree"] == 0
    assert s["parity_rate"] == 0.0
    assert s["probe_total"] == 1 and s["probe_pass"] == 1


def test_report_renders_probe_assertions_and_reason():
    pairs = [
        (ValidationEvidence("probe", "legacy", "fail", probe_id="p"),
         ValidationEvidence("probe", "kernel", "fail", probe_id="p",
                            assertions=("observed the thing",), error="because reasons")),
    ]
    out = render_markdown(pairs)
    assert "Fault-actuation probes" in out
    assert "observed the thing" in out
    assert "because reasons" in out
    assert render_markdown(pairs) == out  # deterministic


# --------------------------------------------------------------------------- #
# Crash probe end-to-end: real subprocess, real kill, real event log (Req 2.x)
# --------------------------------------------------------------------------- #
def test_crash_probe_kills_a_real_process_and_restores_the_goal():
    probe = get_probe("crash.restart_restore")
    scenario = _scenario("crash.restart_restore")
    with tempfile.TemporaryDirectory() as workdir:
        verdict = probe.actuate(ProbeContext(scenario=scenario, workdir=workdir))
    assert verdict.result == RESULT_PASS, verdict.error
    joined = " | ".join(verdict.assertions)
    assert "killed hard with no graceful shutdown" in joined
    assert "post-restore goal id matched pre-kill id" in joined


def test_crash_probe_fails_when_no_events_are_observed(monkeypatch):
    from scripts.kernel_validation.probes import crash_restore

    # Force the poll to give up immediately: with no durable goal event there is
    # nothing to prove, and the probe must fail rather than pass.
    monkeypatch.setattr(crash_restore, "_POLL_TIMEOUT_S", 0.0)
    probe = get_probe("crash.restart_restore")
    scenario = _scenario("crash.restart_restore")
    with tempfile.TemporaryDirectory() as workdir:
        verdict = probe.actuate(ProbeContext(scenario=scenario, workdir=workdir))
    assert verdict.result == RESULT_FAIL
    assert "no goal-lifecycle events" in verdict.error


def test_probe_requires_a_workdir():
    scenario = _scenario("crash.restart_restore")
    verdict = get_probe("crash.restart_restore").actuate(
        ProbeContext(scenario=scenario, workdir="")
    )
    assert verdict.result == RESULT_FAIL
    assert "workdir" in verdict.error


# --------------------------------------------------------------------------- #
# Browser probe: absent controller must skip, never pass (Req 3.3)
# --------------------------------------------------------------------------- #
def test_browser_probe_skips_without_a_controller():
    verdict = get_probe("browser_fail.reconnect").actuate(
        ProbeContext(scenario=_scenario("browser_fail.reconnect"), browser_controller=None)
    )
    assert verdict.result == RESULT_SKIPPED
    assert verdict.result != RESULT_PASS


# --------------------------------------------------------------------------- #
# Recovery/safety probes report their gaps honestly (Req 4.3, 5.x)
# --------------------------------------------------------------------------- #
def test_interrupt_probe_actuates_a_real_suspension():
    """The kernel now exposes interrupt/resume, so the probe must actuate it.

    This test previously asserted the capability was MISSING. It is not weakened —
    it now demands the stronger outcome: a goal genuinely in flight is suspended,
    resumed, and finalized only after the resume, with no duplicated work.
    """
    with tempfile.TemporaryDirectory() as workdir:
        verdict = get_probe("interrupt.pause_resume").actuate(
            ProbeContext(scenario=_scenario("interrupt.pause_resume"), workdir=workdir)
        )
    assert verdict.result == RESULT_PASS, verdict.error
    joined = " | ".join(verdict.assertions)
    assert "genuinely in flight" in joined
    assert "suspension was honored" in joined
    assert "no duplicated work" in joined


def test_confirmation_gate_probe_proves_the_gate_is_honored():
    """The execution path must withhold an unapproved irreversible action."""
    with tempfile.TemporaryDirectory() as workdir:
        verdict = get_probe("human.confirm_send").actuate(
            ProbeContext(scenario=_scenario("human.confirm_send"), workdir=workdir)
        )
    assert verdict.result == RESULT_PASS, verdict.error
    joined = " | ".join(verdict.assertions)
    assert "withheld=True" in joined
    assert "proceeded=True" in joined


def test_confirmation_gate_probe_observes_the_real_gate():
    with tempfile.TemporaryDirectory() as workdir:
        verdict = get_probe("human.confirm_send").actuate(
            ProbeContext(scenario=_scenario("human.confirm_send"), workdir=workdir)
        )
    joined = " | ".join(verdict.assertions)
    # Whatever the verdict, these two observations must have been made against the
    # real PermissionManager: it withholds an unapproved irreversible delivery,
    # and it is not a blanket denial.
    assert "was withheld" in joined
    assert "discriminates rather than blanket-denying" in joined
    if verdict.result == RESULT_FAIL:
        assert "MISSING WIRING" in verdict.error or "permits a confident" in verdict.error
