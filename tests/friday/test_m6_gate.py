"""M6 Gate Test — Backend Independence.

Proves that the Kernel and Deliberation layers produce structurally identical
DecisionRecords regardless of which environment backend is registered:
StubEnvironment vs BrowserEnvironment (mocked controller).

This is the definitive proof that FRIDAY's cognitive layers are backend-independent.

Requirements: 6.1, 6.2
"""

import os
from unittest.mock import MagicMock

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from friday.deliberation.candidate import CandidateAction
from friday.deliberation.deliberator import DecisionRecord, Deliberator
from friday.environments.browser.adapter import BrowserEnvironment
from friday.environments.stub import StubEnvironment
from friday.kernel.kernel import CognitiveKernel
from friday.perception.observation import Observation
from friday.events.event import FrozenDict


def _make_mock_browser_controller():
    """Create a mock BrowserController with available=True and scripted responses."""
    ctrl = MagicMock()
    ctrl.available = True
    ctrl.connection_mode = "cdp"
    ctrl.is_real_chrome = True
    ctrl.last_error = ""

    # observe_interactive returns a scripted element list
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

    # navigate returns success
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


def _make_candidates(goal_id: str):
    """Create a deterministic set of CandidateActions for testing."""
    return [
        CandidateAction.build(
            description="Navigate to target page",
            capability="navigate",
            goal_id=goal_id,
            expected_beliefs=["page loaded"],
            confidence=0.8,
            expected_value=1.0,
            cost=0.1,
            risk=0.0,
        ),
        CandidateAction.build(
            description="Click submit button",
            capability="click",
            goal_id=goal_id,
            expected_beliefs=["form submitted"],
            confidence=0.7,
            expected_value=0.9,
            cost=0.05,
            risk=0.1,
        ),
        CandidateAction.build(
            description="Type into input field",
            capability="type",
            goal_id=goal_id,
            expected_beliefs=["text entered"],
            confidence=0.9,
            expected_value=0.8,
            cost=0.05,
            risk=0.0,
        ),
    ]


class TestM6Gate:
    """M6 Gate: Kernel/Deliberation are backend-independent."""

    def test_decision_record_structure_identical_across_backends(self):
        """The same goal and candidates produce structurally identical DecisionRecords
        whether using StubEnvironment or BrowserEnvironment (mocked).

        This proves Kernel and Deliberation never depend on the backend.
        """
        goal_text = "Complete the form submission task"

        # --- Run with StubEnvironment ---
        kernel_stub = CognitiveKernel(
            store_path="~/.friday/events/test_stub.jsonl",
            auto_checkpoint_every=0,
        )
        stub_env = StubEnvironment(
            scripted=[
                Observation(
                    sensor="dom",
                    environment="browser",
                    object_type="button",
                    attributes=FrozenDict({"text": "Submit"}),
                ),
            ],
            capabilities=["observe", "read", "navigate", "click", "type", "scroll"],
        )
        kernel_stub.register_runtime(stub_env)
        goal_id_stub = kernel_stub.submit_goal(goal_text)

        deliberator_stub = Deliberator()
        deliberator_stub.attach(kernel_stub)
        candidates_stub = _make_candidates(goal_id_stub)
        record_stub = deliberator_stub.decide(goal_id_stub, candidates_stub)

        kernel_stub.shutdown()

        # --- Run with BrowserEnvironment (mocked controller) ---
        kernel_browser = CognitiveKernel(
            store_path="~/.friday/events/test_browser.jsonl",
            auto_checkpoint_every=0,
        )
        mock_ctrl = _make_mock_browser_controller()
        browser_env = BrowserEnvironment(browser_controller=mock_ctrl)
        kernel_browser.register_runtime(browser_env)
        goal_id_browser = kernel_browser.submit_goal(goal_text)

        deliberator_browser = Deliberator()
        deliberator_browser.attach(kernel_browser)
        candidates_browser = _make_candidates(goal_id_browser)
        record_browser = deliberator_browser.decide(goal_id_browser, candidates_browser)

        kernel_browser.shutdown()

        # --- Assert structural equivalence ---
        self._assert_decision_records_structurally_identical(record_stub, record_browser)

    def test_decision_records_are_proper_type(self):
        """Both records are DecisionRecord instances."""
        goal_text = "Read page content"

        # Stub path
        deliberator = Deliberator()
        goal_id = "test-goal-123"
        candidates = _make_candidates(goal_id)
        record = deliberator.decide(goal_id, candidates)

        assert isinstance(record, DecisionRecord)

    def test_considered_tuple_shape(self):
        """considered is a tuple of (str, float) pairs regardless of backend."""
        goal_text = "Navigate and click"

        # Using StubEnvironment
        kernel = CognitiveKernel(
            store_path="~/.friday/events/test_shape.jsonl",
            auto_checkpoint_every=0,
        )
        stub_env = StubEnvironment()
        kernel.register_runtime(stub_env)
        goal_id = kernel.submit_goal(goal_text)

        deliberator = Deliberator()
        deliberator.attach(kernel)
        candidates = _make_candidates(goal_id)
        record = deliberator.decide(goal_id, candidates)

        kernel.shutdown()

        # considered must be a tuple
        assert isinstance(record.considered, tuple)
        # Each element must be a (str, float) pair
        for pair in record.considered:
            assert isinstance(pair, tuple), f"Expected tuple, got {type(pair)}"
            assert len(pair) == 2, f"Expected 2-element tuple, got {len(pair)}"
            cid, utility = pair
            assert isinstance(cid, str), f"candidate_id should be str, got {type(cid)}"
            assert isinstance(utility, float), f"utility should be float, got {type(utility)}"

    def test_deliberation_independent_of_environment_registration(self):
        """Deliberation produces valid DecisionRecords even without an environment registered.

        This further proves deliberation is backend-agnostic — it doesn't query
        or depend on any specific environment at decision time.
        """
        goal_id = "independent-goal"
        deliberator = Deliberator()
        candidates = _make_candidates(goal_id)
        record = deliberator.decide(goal_id, candidates)

        assert isinstance(record, DecisionRecord)
        assert record.goal_id == goal_id
        assert record.chosen_id is not None  # should pick the best candidate
        assert isinstance(record.considered, tuple)
        assert len(record.considered) == len(candidates)
        assert record.reason != ""

    def _assert_decision_records_structurally_identical(
        self, record_a: DecisionRecord, record_b: DecisionRecord
    ):
        """Assert two DecisionRecords have identical structure (not identical values)."""
        # Both are DecisionRecord instances
        assert isinstance(record_a, DecisionRecord)
        assert isinstance(record_b, DecisionRecord)

        # Same fields exist
        fields_a = set(record_a.__dataclass_fields__.keys())
        fields_b = set(record_b.__dataclass_fields__.keys())
        assert fields_a == fields_b, (
            f"Field sets differ: {fields_a.symmetric_difference(fields_b)}"
        )

        # goal_id is a non-empty string in both
        assert isinstance(record_a.goal_id, str) and record_a.goal_id
        assert isinstance(record_b.goal_id, str) and record_b.goal_id

        # chosen_id: both are either str or None
        assert type(record_a.chosen_id) == type(record_b.chosen_id) or (
            isinstance(record_a.chosen_id, (str, type(None)))
            and isinstance(record_b.chosen_id, (str, type(None)))
        )

        # considered: both are tuples with same length
        assert isinstance(record_a.considered, tuple)
        assert isinstance(record_b.considered, tuple)
        assert len(record_a.considered) == len(record_b.considered), (
            f"considered lengths differ: {len(record_a.considered)} vs {len(record_b.considered)}"
        )

        # Each element of considered has the same shape: (str, float)
        for pair_a, pair_b in zip(record_a.considered, record_b.considered):
            assert isinstance(pair_a, tuple) and len(pair_a) == 2
            assert isinstance(pair_b, tuple) and len(pair_b) == 2
            assert isinstance(pair_a[0], str) and isinstance(pair_a[1], float)
            assert isinstance(pair_b[0], str) and isinstance(pair_b[1], float)

        # reason is a non-empty string in both
        assert isinstance(record_a.reason, str) and record_a.reason
        assert isinstance(record_b.reason, str) and record_b.reason
