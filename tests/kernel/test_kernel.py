"""M1 tests — CognitiveKernel: A1 continuous run, A3 replay, A6, A7, A8."""

import time

from hypothesis import given, settings, strategies as st

from friday.events.event import Event
from friday.events.store import EventStore
from friday.kernel.echo_runtime import EchoRuntime
from friday.kernel.kernel import CognitiveKernel


def _kernel(tmp_path, **kwargs):
    return CognitiveKernel(store_path=str(tmp_path / "session.jsonl"), **kwargs)


class TestContinuousRun:
    def test_a1_runs_continuously_until_shutdown(self, tmp_path):
        """A1: kernel.start() runs continuously; only shutdown() stops it."""
        kernel = _kernel(tmp_path)
        kernel.register_runtime(EchoRuntime())
        kernel.start()
        try:
            deadline = time.time() + 5.0
            while time.time() < deadline:
                health = kernel.health()
                assert health["status"] == "ok", health
                assert health["running"] is True
                time.sleep(0.25)
        finally:
            kernel.shutdown()
        assert kernel.health()["running"] is False

    def test_start_idempotent(self, tmp_path):
        kernel = _kernel(tmp_path)
        kernel.start()
        kernel.start()
        kernel.shutdown()
        kernel.shutdown()


class TestGoalsAndObservations:
    def test_submit_goal_tracked(self, tmp_path):
        kernel = _kernel(tmp_path)
        goal_id = kernel.submit_goal("do something", {"deadline": "soon"})
        goals = kernel.query_goals()
        assert len(goals) == 1
        assert goals[0]["id"] == goal_id
        assert goals[0]["text"] == "do something"
        assert goals[0]["state"] == "created"

    def test_capability_request_returns_id(self, tmp_path):
        kernel = _kernel(tmp_path)
        request_id = kernel.request_capability("search_web", {"q": "x"})
        assert isinstance(request_id, str) and request_id

    def test_observation_emits_event(self, tmp_path):
        kernel = _kernel(tmp_path)
        received = []
        kernel._bus.subscribe("observation.*", received.append)
        kernel.submit_observation({"sensor": "screen", "value": 1})
        assert len(received) == 1
        assert received[0].payload["sensor"] == "screen"


class TestReplayAndRestore:
    def test_a3_checkpoint_restore_replay(self, tmp_path):
        """A3: checkpoint at t, crash, restore + replay → identical state."""
        store_path = str(tmp_path / "session.jsonl")
        kernel = CognitiveKernel(store_path=store_path)
        for i in range(5):
            kernel.submit_goal(f"goal-{i}")
        checkpoint_path = kernel.checkpoint()
        for i in range(5, 10):
            kernel.submit_goal(f"goal-{i}")
        original_tick = kernel.health()["tick"]
        original_goals = sorted(g["id"] for g in kernel.query_goals())

        # Simulate crash: brand-new kernel over the same event log.
        revived = CognitiveKernel(store_path=store_path)
        revived.restore(checkpoint_path)
        assert revived.health()["tick"] >= original_tick
        assert sorted(g["id"] for g in revived.query_goals()) == original_goals

    def test_auto_checkpoint(self, tmp_path):
        kernel = _kernel(tmp_path, auto_checkpoint_every=3)
        for i in range(4):
            kernel.submit_goal(f"g{i}")
        assert kernel._checkpoints.last_checkpoint_path is not None


class TestEventInvariants:
    """A6: monotonic logical time, causal parent ordering."""

    def test_logical_time_monotonic_across_published_events(self, tmp_path):
        kernel = _kernel(tmp_path)
        seen = []
        kernel._bus.subscribe("*", lambda e: seen.append(e.logical_time))
        for i in range(20):
            kernel.submit_goal(f"g{i}")
        assert seen == sorted(seen)
        assert len(set(seen)) == len(seen)

    def test_parent_has_lower_logical_time(self, tmp_path):
        kernel = _kernel(tmp_path)
        kernel.register_runtime(EchoRuntime())
        events = {}
        kernel._bus.subscribe("*", lambda e: events.setdefault(e.id, e))
        kernel.submit_goal("g")
        from friday.events.event import make_event

        request = make_event("echo.request", "tests", kernel.health()["tick"] + 1)
        kernel.publish_event(request)
        responses = [e for e in events.values() if e.event_type == "echo.response"]
        assert responses
        for resp in responses:
            parent = events.get(resp.parent_id)
            assert parent is not None
            assert parent.logical_time < resp.logical_time


class LossyEventStore(EventStore):
    """A7 fixture: silently drops every 10th append."""

    def __init__(self, path):
        super().__init__(path)
        self._seen = 0

    def append(self, event: Event) -> None:
        self._seen += 1
        if self._seen % 10 == 0:
            return  # drop silently
        super().append(event)


class TestDegradedMode:
    def test_a7_dropped_events_degrade_but_do_not_crash(self, tmp_path):
        store = LossyEventStore(str(tmp_path / "lossy.jsonl"))
        kernel = CognitiveKernel(event_store=store)
        for i in range(20):
            kernel.submit_goal(f"g{i}")
        health = kernel.health()
        assert health["status"] == "degraded"
        assert any("event_store_lag" in r for r in health["degraded_reasons"])

    def test_raising_store_degrades_but_does_not_crash(self, tmp_path):
        class ExplodingStore(EventStore):
            def append(self, event):
                raise IOError("disk gone")

        kernel = CognitiveKernel(event_store=ExplodingStore(str(tmp_path / "x.jsonl")))
        kernel.submit_goal("g")
        health = kernel.health()
        assert health["status"] == "degraded"


class TestBenchmark:
    def test_a8_100_ticks_per_second_sustained(self, tmp_path):
        """A8: >=100 ticks/sec sustained for 5 seconds with EchoRuntime."""
        kernel = _kernel(tmp_path, tick_min_interval=0.001, tick_max_interval=0.005)
        echo = EchoRuntime()
        kernel.register_runtime(echo)
        kernel.start()
        start_ticks = echo.health()["ticks"]
        start = time.perf_counter()
        time.sleep(5.0)
        elapsed = time.perf_counter() - start
        end_ticks = echo.health()["ticks"]
        kernel.shutdown()
        rate = (end_ticks - start_ticks) / elapsed
        assert rate >= 100, f"tick rate {rate:.1f}/s below 100/s"


@settings(max_examples=25, deadline=None)
@given(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=10))
def test_property_goals_always_queryable(tmp_path_factory, goal_texts):
    tmp = tmp_path_factory.mktemp("kernel-prop")
    kernel = CognitiveKernel(store_path=str(tmp / "s.jsonl"))
    ids = [kernel.submit_goal(t) for t in goal_texts]
    goals = {g["id"]: g["text"] for g in kernel.query_goals()}
    for goal_id, text in zip(ids, goal_texts):
        assert goals[goal_id] == text
