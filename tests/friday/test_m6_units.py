"""M6 Unit Tests — Environment Contracts, Verification Engine, Evidence Repository.

Comprehensive unit tests covering the M6 milestone components:

- Task 1.3: EnvironmentContract + EnvironmentRuntime core types
- Task 2.2: StubEnvironment
- Task 4.2: BrowserEnvironment adapter (mocked BrowserController)
- Task 5.2: EvidenceRepository
- Task 6.2: UnifiedVerificationEngine

All tests run under FRIDAY_DRY_RUN=1 — no real browser or I/O.
"""

import dataclasses
import json
import os
from unittest.mock import MagicMock

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import pytest

from friday.actions.result import ActionResult, ActionStatus
from friday.environments.browser.adapter import BrowserEnvironment
from friday.environments.contract import (
    Action,
    EnvironmentContract,
    ObjectQuery,
)
from friday.environments.runtime import EnvironmentRuntime
from friday.environments.stub import StubEnvironment
from friday.events.event import FrozenDict
from friday.goals.goal import Goal
from friday.kernel.contracts.environment import (
    EnvironmentContract as KernelEnvironmentStub,
)
from friday.perception.observation import Observation
from friday.verification.engine import (
    GoalVerificationResult,
    UnifiedVerificationEngine,
)
from friday.verification.evidence_law import (
    EvidenceArtifact,
    EvidenceKind,
    EvidenceVerifier,
    ExecutionEvidence,
    RequirementVerdict,
    RequirementKind,
)
from friday.verification.evidence_repo import EvidenceRecord, EvidenceRepository
from friday.verification.verifier import VerificationResult, VerificationVerdict
from friday.world.objects import WorldObject


# ======================================================================
# Shared helpers
# ======================================================================


def _make_mock_browser_controller(available: bool = True):
    """Create a mock BrowserController with scripted method returns.

    Mirrors the pattern used in test_m6_gate.py.
    """
    ctrl = MagicMock()
    ctrl.available = available
    ctrl.connection_mode = "cdp"
    ctrl.is_real_chrome = True
    ctrl.last_error = ""

    ctrl.observe_interactive.return_value = {
        "ok": True,
        "elements": [
            {
                "role": "button",
                "text": "Submit",
                "editable": False,
                "selector": "button#submit",
                "index": 0,
                "in_view": True,
            },
            {
                "role": "textbox",
                "text": "",
                "editable": True,
                "selector": "input#name",
                "index": 1,
                "in_view": True,
            },
        ],
    }

    ctrl.navigate.return_value = {"ok": True, "url_before": "", "url_after": ""}
    ctrl.click.return_value = {"ok": True, "changed": True}
    ctrl.click_index.return_value = {"ok": True, "changed": True}
    ctrl.type_text.return_value = {"ok": True, "changed": True}
    ctrl.fill_index.return_value = {"ok": True, "changed": True}
    ctrl.scroll.return_value = {"ok": True, "scrolled": True}
    ctrl.press.return_value = {"ok": True}
    ctrl.read_text.return_value = "page content"
    ctrl.upload_file.return_value = {"ok": True}
    ctrl.download_file.return_value = {"ok": True}
    ctrl.stop.return_value = None
    return ctrl


def _scripted_observations():
    """A deterministic set of scripted Observations for the stub."""
    return [
        Observation(
            sensor="dom",
            environment="browser",
            object_type="button",
            attributes=FrozenDict({"text": "Submit"}),
        ),
        Observation(
            sensor="dom",
            environment="browser",
            object_type="textbox",
            attributes=FrozenDict({"text": "email field"}),
        ),
        Observation(
            sensor="dom",
            environment="browser",
            object_type="link",
            attributes=FrozenDict({"text": "Home"}),
        ),
    ]


# ======================================================================
# TASK 1.3 — EnvironmentContract and EnvironmentRuntime
# ======================================================================


class TestEnvironmentContractTypes:
    """Task 1.3 — core types: Action, ObjectQuery, contract inheritance, runtime."""

    def test_action_is_frozen_dataclass_with_correct_fields(self):
        assert dataclasses.is_dataclass(Action)
        field_names = {f.name for f in dataclasses.fields(Action)}
        assert field_names == {"capability", "target", "params"}

        action = Action(capability="click")
        assert action.capability == "click"
        assert action.target is None
        assert action.params == {}

        # Frozen: mutation must raise
        with pytest.raises(dataclasses.FrozenInstanceError):
            action.capability = "type"  # type: ignore[misc]

    def test_object_query_is_frozen_dataclass_with_correct_fields(self):
        assert dataclasses.is_dataclass(ObjectQuery)
        field_names = {f.name for f in dataclasses.fields(ObjectQuery)}
        assert field_names == {"object_type", "text_contains", "editable_only", "limit"}

        query = ObjectQuery()
        assert query.object_type is None
        assert query.text_contains is None
        assert query.editable_only is False
        assert query.limit == 60

        # Frozen: mutation must raise
        with pytest.raises(dataclasses.FrozenInstanceError):
            query.object_type = "button"  # type: ignore[misc]

    def test_environment_contract_subclasses_kernel_stub(self):
        assert issubclass(EnvironmentContract, KernelEnvironmentStub)

    def test_environment_runtime_checkpoint_restore_round_trip(self):
        # StubEnvironment is an EnvironmentRuntime; exercise the runtime lifecycle.
        env = StubEnvironment()
        assert isinstance(env, EnvironmentRuntime)

        env.pause()
        state = env.checkpoint()

        # Round-trip: restore into a fresh instance
        fresh = StubEnvironment()
        fresh.restore(state)
        assert fresh._paused is True

        # Resume then checkpoint again reflects the change
        env.resume()
        state2 = env.checkpoint()
        fresh.restore(state2)
        assert fresh._paused is False

    def test_environment_runtime_checkpoint_is_json_serializable(self):
        env = StubEnvironment()
        env.pause()
        blob = json.dumps(env.checkpoint())
        # Round-trips through JSON with primitives only
        restored = json.loads(blob)
        assert restored["paused"] is True
        assert "name" in restored


# ======================================================================
# TASK 2.2 — StubEnvironment
# ======================================================================


class TestStubEnvironment:
    """Task 2.2 — StubEnvironment conformance."""

    def test_contract_methods_return_correct_types(self):
        env = StubEnvironment(
            scripted=_scripted_observations(),
            capabilities=["observe", "click", "type"],
        )
        assert env.name == "stub.testenv"
        assert isinstance(env.observe(), list)
        assert all(isinstance(o, Observation) for o in env.observe())
        assert isinstance(env.query_capabilities(), list)
        assert isinstance(env.health(), dict)
        assert isinstance(env.query_objects(ObjectQuery()), list)

        result = env.interact(Action(capability="click"))
        assert isinstance(result, ActionResult)

        verify = env.verify(None)
        assert isinstance(verify, VerificationResult)
        assert verify.verdict == VerificationVerdict.VERIFIED

    def test_interact_never_raises_for_any_valid_capability(self):
        caps = ["observe", "read", "navigate", "click", "type", "scroll", "press",
                "upload", "download"]
        env = StubEnvironment(capabilities=caps)
        for cap in caps:
            result = env.interact(Action(capability=cap))
            assert isinstance(result, ActionResult)
            assert result.status == ActionStatus.SUCCESS

    def test_observe_returns_scripted_observations_with_correct_fields(self):
        scripted = _scripted_observations()
        env = StubEnvironment(scripted=scripted)
        observed = env.observe()
        assert len(observed) == len(scripted)
        first = observed[0]
        assert first.environment == "browser"
        assert first.object_type == "button"
        assert first.attributes.get("text") == "Submit"

    def test_query_objects_filters_by_object_type(self):
        env = StubEnvironment(scripted=_scripted_observations())
        results = env.query_objects(ObjectQuery(object_type="button"))
        assert len(results) == 1
        assert all(isinstance(r, WorldObject) for r in results)
        assert results[0].object_type == "button"

    def test_pause_resume_shutdown_flags(self):
        env = StubEnvironment()
        assert env._paused is False

        env.pause()
        assert env._paused is True
        assert env.health()["paused"] is True

        env.resume()
        assert env._paused is False

        assert env._shut_down is False
        env.shutdown()
        assert env._shut_down is True
        assert env.health()["shut_down"] is True


# ======================================================================
# TASK 4.2 — BrowserEnvironment (mocked BrowserController)
# ======================================================================


class TestBrowserEnvironment:
    """Task 4.2 — BrowserEnvironment adapter with mocked controller."""

    def test_navigate_routes_to_controller_navigate(self):
        ctrl = _make_mock_browser_controller()
        env = BrowserEnvironment(browser_controller=ctrl)
        env.interact(Action(capability="navigate", params={"url": "example"}))
        ctrl.navigate.assert_called_once_with("example")

    def test_click_index_routes_to_controller_click_index(self):
        ctrl = _make_mock_browser_controller()
        env = BrowserEnvironment(browser_controller=ctrl)
        elements = [{"role": "button", "index": 0}]
        env.interact(Action(capability="click", params={"index": 0, "elements": elements}))
        ctrl.click_index.assert_called_once_with(0, elements)

    def test_type_index_routes_to_controller_fill_index(self):
        ctrl = _make_mock_browser_controller()
        env = BrowserEnvironment(browser_controller=ctrl)
        elements = [{"role": "textbox", "index": 1}]
        env.interact(
            Action(capability="type", params={"index": 1, "value": "hi", "elements": elements})
        )
        ctrl.fill_index.assert_called_once_with(1, "hi", elements)

    def test_scroll_routes_to_controller_scroll(self):
        ctrl = _make_mock_browser_controller()
        env = BrowserEnvironment(browser_controller=ctrl)
        env.interact(Action(capability="scroll", params={"direction": "up", "amount": 100}))
        ctrl.scroll.assert_called_once_with(direction="up", amount=100)

    def test_press_routes_to_controller_press(self):
        ctrl = _make_mock_browser_controller()
        env = BrowserEnvironment(browser_controller=ctrl)
        env.interact(Action(capability="press", params={"key": "Enter"}))
        ctrl.press.assert_called_once_with("Enter")

    def test_read_routes_to_controller_read_text(self):
        ctrl = _make_mock_browser_controller()
        env = BrowserEnvironment(browser_controller=ctrl)
        result = env.interact(Action(capability="read", params={"max_chars": 500}))
        ctrl.read_text.assert_called_once_with(max_chars=500)
        assert result.status == ActionStatus.SUCCESS

    def test_observe_maps_dicts_to_observation_objects(self):
        ctrl = _make_mock_browser_controller()
        env = BrowserEnvironment(browser_controller=ctrl)
        observations = env.observe()
        assert len(observations) == 2
        assert all(isinstance(o, Observation) for o in observations)
        assert observations[0].environment == "browser"
        assert observations[0].object_type == "button"
        assert observations[0].attributes.get("text") == "Submit"
        assert observations[1].object_type == "textbox"

    def test_interact_returns_blocked_when_controller_unavailable(self):
        ctrl = _make_mock_browser_controller(available=False)
        env = BrowserEnvironment(browser_controller=ctrl)
        result = env.interact(Action(capability="navigate", params={"url": "x"}))
        assert result.status == ActionStatus.BLOCKED

    def test_interact_returns_failed_for_unknown_capability(self):
        ctrl = _make_mock_browser_controller()
        env = BrowserEnvironment(browser_controller=ctrl)
        result = env.interact(Action(capability="frobnicate"))
        assert result.status == ActionStatus.FAILED

    def test_query_objects_filters_by_object_type(self):
        ctrl = _make_mock_browser_controller()
        env = BrowserEnvironment(browser_controller=ctrl)
        env.observe()  # populate the snapshot cache
        results = env.query_objects(ObjectQuery(object_type="textbox"))
        assert len(results) == 1
        assert results[0].object_type == "textbox"
        assert all(isinstance(r, WorldObject) for r in results)

    def test_health_returns_correct_shape(self):
        ctrl = _make_mock_browser_controller()
        env = BrowserEnvironment(browser_controller=ctrl)
        health = env.health()
        assert set(health.keys()) == {
            "status", "available", "connection_mode", "is_real_chrome", "last_error"
        }
        assert health["status"] == "ok"
        assert health["available"] is True
        assert health["connection_mode"] == "cdp"
        assert health["is_real_chrome"] is True

    def test_checkpoint_is_json_serializable(self):
        ctrl = _make_mock_browser_controller()
        env = BrowserEnvironment(browser_controller=ctrl)
        blob = json.dumps(env.checkpoint())
        restored = json.loads(blob)
        assert restored["name"] == "browser.chrome.dedicated"
        assert restored["available"] is True


# ======================================================================
# TASK 5.2 — EvidenceRepository
# ======================================================================


class TestEvidenceRepository:
    """Task 5.2 — signed, indexed, append-only evidence store."""

    def _gathered_artifact(self, detail="some real text", value=100, source="http-source"):
        return EvidenceArtifact(
            kind=EvidenceKind.GATHERED_INFO,
            detail=detail,
            value=value,
            source=source,
        )

    def test_add_artifact_query_round_trips(self):
        repo = EvidenceRepository()
        artifact = self._gathered_artifact()
        record_id = repo.add_artifact("goal-1", artifact, requirement="research X")
        assert isinstance(record_id, str)

        results = repo.query(goal_id="goal-1")
        assert len(results) == 1
        assert results[0].record_id == record_id
        assert results[0].artifact.kind == EvidenceKind.GATHERED_INFO

    def test_signature_validates_on_read(self):
        repo = EvidenceRepository()
        repo.add_artifact("goal-1", self._gathered_artifact())
        assert repo.verify_integrity() is True

    def test_tampering_is_detected(self):
        repo = EvidenceRepository()
        repo.add_artifact("goal-1", self._gathered_artifact())
        assert repo.verify_integrity() is True

        # Mutate a frozen record in place to simulate tampering
        record = repo._records[0]
        object.__setattr__(record, "goal_id", "tampered-goal")
        assert repo.verify_integrity() is False

    def test_query_filters_by_goal_id_and_kind_and_both(self):
        repo = EvidenceRepository()
        repo.add_artifact("goal-A", self._gathered_artifact(detail="a-gather"))
        repo.add_artifact(
            "goal-A",
            EvidenceArtifact(kind=EvidenceKind.FILE_ARTIFACT, detail="a.txt", value=10),
        )
        repo.add_artifact("goal-B", self._gathered_artifact(detail="b-gather"))

        # By goal_id
        assert len(repo.query(goal_id="goal-A")) == 2
        assert len(repo.query(goal_id="goal-B")) == 1

        # By kind
        assert len(repo.query(kind=EvidenceKind.GATHERED_INFO)) == 2
        assert len(repo.query(kind=EvidenceKind.FILE_ARTIFACT)) == 1

        # By both (AND logic)
        both = repo.query(goal_id="goal-A", kind=EvidenceKind.GATHERED_INFO)
        assert len(both) == 1
        assert both[0].goal_id == "goal-A"
        assert both[0].artifact.kind == EvidenceKind.GATHERED_INFO

    def test_for_goal_reconstructs_execution_evidence(self):
        repo = EvidenceRepository()
        repo.add_artifact("goal-1", self._gathered_artifact(detail="read text", value=50))
        repo.add_artifact(
            "goal-1",
            EvidenceArtifact(kind=EvidenceKind.NAVIGATION, detail="opened-page"),
        )

        evidence = repo.for_goal("goal-1")
        assert isinstance(evidence, ExecutionEvidence)
        assert evidence.has(EvidenceKind.GATHERED_INFO)
        assert evidence.has(EvidenceKind.NAVIGATION)

    def test_add_verdict_stores_verdict_record(self):
        repo = EvidenceRepository()
        verdict = RequirementVerdict(
            description="research topic X",
            kind=RequirementKind.GATHER,
            satisfied=True,
            evidence_detail="2 real reads",
        )
        record_id = repo.add_verdict("goal-1", verdict)
        assert isinstance(record_id, str)

        results = repo.query(goal_id="goal-1")
        assert len(results) == 1
        assert results[0].verdict_satisfied is True
        assert results[0].requirement == "research topic X"


# ======================================================================
# TASK 6.2 — UnifiedVerificationEngine
# ======================================================================


class TestUnifiedVerificationEngine:
    """Task 6.2 — merged artifact-based + diff-based verification."""

    def _produce_evidence(self):
        ev = ExecutionEvidence()
        ev.add_generated_content("This is a produced summary report of some length.")
        return ev

    def _gather_and_produce_evidence(self):
        ev = ExecutionEvidence()
        ev.add_gathered_info("real information read from a source page", source="http-x")
        ev.add_generated_content("A synthesized report body with content.")
        return ev

    def test_verify_requirement_matches_evidence_verifier(self):
        engine = UnifiedVerificationEngine()
        verifier = EvidenceVerifier()
        req = "write a summary report"
        evidence = self._produce_evidence()

        result = engine.verify_requirement(req, evidence)
        expected = verifier.verify_one(req, evidence)

        assert (result.verdict == VerificationVerdict.VERIFIED) == expected.satisfied

    def test_verify_goal_all_satisfied(self):
        engine = UnifiedVerificationEngine()
        goal = Goal(
            text="produce and research",
            constraints={
                "requirements": [
                    "write a summary report",
                    "research information about the topic",
                ]
            },
        )
        evidence = self._gather_and_produce_evidence()
        result = engine.verify_goal(goal, evidence)
        assert isinstance(result, GoalVerificationResult)
        assert result.satisfied is True
        assert all(v.satisfied for v in result.requirement_verdicts)

    def test_verify_goal_one_unmet_not_satisfied(self):
        engine = UnifiedVerificationEngine()
        goal = Goal(
            text="produce and deliver",
            constraints={
                "requirements": [
                    "write a summary report",
                    "send the email to the recipient",  # DELIVER — no confirmation
                ]
            },
        )
        evidence = self._produce_evidence()
        result = engine.verify_goal(goal, evidence)
        assert result.satisfied is False

    def test_verify_goal_zero_requirements_not_satisfied(self):
        engine = UnifiedVerificationEngine()
        goal = Goal(text="empty goal", constraints={"requirements": []})
        result = engine.verify_goal(goal, ExecutionEvidence())
        assert result.satisfied is False

    def test_verify_action_uses_artifact_presence(self):
        engine = UnifiedVerificationEngine()

        # With a real artifact → VERIFIED
        ev_real = ExecutionEvidence()
        ev_real.add_file("out.txt", 42)
        result = engine.verify_action("click", None, None, ev_real)
        assert result.verdict == VerificationVerdict.VERIFIED

        # No artifacts → UNVERIFIED
        result_empty = engine.verify_action("click", None, None, ExecutionEvidence())
        assert result_empty.verdict == VerificationVerdict.UNVERIFIED

    def test_gather_requirement_with_only_generated_content_is_unmet(self):
        engine = UnifiedVerificationEngine()
        evidence = self._produce_evidence()  # only GENERATED_CONTENT
        result = engine.verify_requirement("research information about the topic", evidence)
        assert result.verdict == VerificationVerdict.UNVERIFIED

    def test_deliver_requirement_with_only_generated_content_is_unmet(self):
        engine = UnifiedVerificationEngine()
        evidence = self._produce_evidence()  # only GENERATED_CONTENT
        result = engine.verify_requirement("send the email to the recipient", evidence)
        assert result.verdict == VerificationVerdict.UNVERIFIED

    def test_engine_persists_verdicts_to_repository(self):
        repo = EvidenceRepository()
        engine = UnifiedVerificationEngine(repo=repo)
        goal = Goal(
            text="produce report",
            constraints={"requirements": ["write a summary report"]},
        )
        evidence = self._produce_evidence()
        engine.verify_goal(goal, evidence)

        stored = repo.query(goal_id=goal.id)
        assert len(stored) >= 1
        assert any(r.verdict_satisfied is True for r in stored)
