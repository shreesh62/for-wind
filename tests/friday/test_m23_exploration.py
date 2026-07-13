"""M23 — Exploration-on-low-confidence property tests.

Feature: m23-browser-generic-desktop-environment

Property 10: when the resolver cannot resolve a target above a confidence
threshold, the executor invokes the generic ExplorationEngine (Observe →
hypothesize → risk-ordered SAFE experiment → verify → update World Model)
instead of a blind action — and it does so through the abstract
EnvironmentContract surface only, with no application-specific heuristics
(Axiom 15). When no exploration path is wired, the executor still never guesses:
it fails cleanly.

These tests drive the REAL ExplorationEngine (AffordanceInferrer +
SafeExperimentPlanner + CapabilityRegistry) over a generic fake environment that
has NO application identity, proving the mechanism is environment-agnostic.
"""

from __future__ import annotations

import asyncio

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.actions.result import ActionResult, ActionStatus
from friday.capabilities.registry import CapabilityRegistry
from friday.environments.contract import Action
from friday.environments.unknown.affordances import AffordanceInferrer
from friday.environments.unknown.exploration import ExplorationEngine
from friday.environments.unknown.experiment import SafeExperimentPlanner
from friday.events.event import FrozenDict
from friday.executor import ExecutionContext, GoalExecutor
from friday.perception.observation import Observation


# --------------------------------------------------------------------------- #
# Generic fakes — NO application identity anywhere (Axiom 15).
# --------------------------------------------------------------------------- #


class _FakeEnvironment:
    """A minimal environment exposing only the abstract observe/interact surface.

    It knows nothing about browsers/apps/sites. It emits a fixed set of generic
    Observations and records every interaction so a test can assert that only
    SAFE (confidence/risk-permitted) experiments were run — never a blind action.
    """

    def __init__(self, observations):
        self._observations = list(observations)
        self.interactions: list[Action] = []

    def observe(self):
        return list(self._observations)

    def interact(self, action: Action) -> ActionResult:
        self.interactions.append(action)
        return ActionResult.success(action=action.capability, message="ok")


def _obs(object_type: str, name: str, confidence: float = 1.0) -> Observation:
    return Observation(
        sensor="uia",
        environment="desktop",
        object_type=object_type,
        attributes=FrozenDict({"name": name}),
        confidence=confidence,
        bbox=(1, 2, 3, 4),
    )


def _real_engine(max_experiments: int = 20) -> ExplorationEngine:
    return ExplorationEngine(
        inferrer=AffordanceInferrer(),
        planner=SafeExperimentPlanner(),
        registry=CapabilityRegistry(),
        max_experiments=max_experiments,
    )


def _executor(engine=None, environment=None) -> GoalExecutor:
    provider = (lambda: environment) if environment is not None else None
    return GoalExecutor(exploration_engine=engine, environment_provider=provider)


# --------------------------------------------------------------------------- #
# Property 10
# --------------------------------------------------------------------------- #


def test_p10_exploration_triggered_instead_of_blind_action():
    # Feature: m23-browser-generic-desktop-environment, Property 10:
    # an unresolved target triggers exploration (observe + >=1 safe experiment),
    # never a blind action. Validates: Requirements 6.1, 6.2
    env = _FakeEnvironment([_obs("button", "Save"), _obs("textbox", "Query")])
    ex = _executor(engine=_real_engine(), environment=env)
    ctx = ExecutionContext(goal="do something")

    note = ex._explore_on_low_confidence("Save", ctx)

    assert note is not None
    assert "Explored" in note
    # The engine observed and ran at least one SAFE experiment (observe-risk is
    # always permitted) — it did not perform a blind click.
    assert len(env.interactions) >= 1
    # Every interaction that ran is a safe, low-risk probe — never a raw "click"
    # on an unconfirmed node (button click needs confidence >= 0.5; fresh nodes
    # start well below that, so it must be gated out).
    assert all(a.capability != "click" for a in env.interactions)
    assert any("[explore]" in line for line in ctx.step_log)


def test_p10_no_exploration_path_means_clean_failure_not_guess():
    # Feature: m23-browser-generic-desktop-environment, Property 10:
    # with no engine/provider wired, exploration returns None so the caller fails
    # cleanly — the executor NEVER guesses. Validates: Requirements 6.1
    ctx = ExecutionContext(goal="g")
    assert _executor()._explore_on_low_confidence("X", ctx) is None
    # engine present but no environment provider -> still None (no blind action).
    assert _executor(engine=_real_engine())._explore_on_low_confidence("X", ctx) is None


def test_p10_high_risk_experiment_is_gated_out():
    # Feature: m23-browser-generic-desktop-environment, Property 10:
    # a destructive-labelled node's high-risk click is NEVER run at low confidence
    # (safe-experiment gating). Validates: Requirements 6.2, 6.3
    env = _FakeEnvironment([_obs("button", "Delete account")])
    ex = _executor(engine=_real_engine(), environment=env)
    note = ex._explore_on_low_confidence("Delete account", ExecutionContext(goal="g"))
    assert note is not None
    # DELETE-risk needs confidence >= 0.9; a fresh node never reaches it, so the
    # destructive click is gated out — only observe/hover safe probes may run.
    assert all(a.capability not in ("click", "type") for a in env.interactions)


def test_p10_exploration_never_raises_on_broken_provider():
    # Feature: m23-browser-generic-desktop-environment, Property 10:
    # a provider/engine failure degrades gracefully, never crashing the step and
    # never turning into a blind action. Validates: Requirements 6.1
    def _boom():
        raise RuntimeError("provider exploded")

    ex = GoalExecutor(exploration_engine=_real_engine(), environment_provider=_boom)
    # Broken provider -> None (caller fails cleanly).
    assert ex._explore_on_low_confidence("X", ExecutionContext(goal="g")) is None

    class _BrokenEngine:
        def explore(self, environment):
            raise RuntimeError("engine exploded")

    env = _FakeEnvironment([_obs("button", "OK")])
    ex2 = _executor(engine=_BrokenEngine(), environment=env)
    note = ex2._explore_on_low_confidence("OK", ExecutionContext(goal="g"))
    assert note is not None and "failed" in note.lower()


@settings(max_examples=100)
@given(
    label=st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != ""),
    otype=st.sampled_from(["button", "textbox", "link", "unknown", "menuitem"]),
)
def test_p10_environment_agnostic(label, otype):
    # Feature: m23-browser-generic-desktop-environment, Property 10:
    # exploration is environment-agnostic — for ANY object label/type (any "app"),
    # the same generic path triggers and returns a note through the abstract
    # contract only. No app/site/browser branching. Validates: Requirements 6.3, 6.4
    env = _FakeEnvironment([_obs(otype, label)])
    ex = _executor(engine=_real_engine(), environment=env)
    note = ex._explore_on_low_confidence(label, ExecutionContext(goal="g"))
    assert note is not None
    assert "Explored" in note


def test_p10_execute_click_routes_to_exploration(monkeypatch):
    # Feature: m23-browser-generic-desktop-environment, Property 10:
    # _execute_click, on a target_not_found resolution, routes to exploration
    # rather than reporting a bare failure. Validates: Requirements 6.1, 6.2
    monkeypatch.setenv("FRIDAY_DRY_RUN", "1")  # skip real screen capture in WS build

    from friday.actions import primitives as P

    async def _fake_click(target, ws, **kwargs):
        return ActionResult.failed(
            action="click",
            target=getattr(target, "text", ""),
            error="No adapter can handle target",
            error_category="target_not_found",
        )

    monkeypatch.setattr(P, "get_resolver", lambda: object())
    monkeypatch.setattr(P, "click", _fake_click)

    env = _FakeEnvironment([_obs("button", "Save")])
    ex = _executor(engine=_real_engine(), environment=env)
    out = ex._execute_click("Nonexistent Target", ExecutionContext(goal="g"))
    assert "Explored" in out
    assert len(env.interactions) >= 1


def test_p10_execute_click_target_not_found_without_engine_reports_failure(monkeypatch):
    # Feature: m23-browser-generic-desktop-environment, Property 10:
    # with no exploration wired, a target_not_found click reports a clean failure
    # (no blind action). Validates: Requirements 6.1
    monkeypatch.setenv("FRIDAY_DRY_RUN", "1")

    from friday.actions import primitives as P

    async def _fake_click(target, ws, **kwargs):
        return ActionResult.failed(
            action="click", target="x",
            error="No adapter can handle target",
            error_category="target_not_found",
        )

    monkeypatch.setattr(P, "get_resolver", lambda: object())
    monkeypatch.setattr(P, "click", _fake_click)

    ex = _executor()  # no engine, no provider
    out = ex._execute_click("Nonexistent", ExecutionContext(goal="g"))
    assert out.startswith("Click failed")
