"""M1 tests — EventStore append, replay, checkpoints."""

from friday.events.event import make_event
from friday.events.store import EventStore


def _store(tmp_path):
    return EventStore(str(tmp_path / "session.jsonl"))


class TestAppendReplay:
    def test_replay_returns_all_events_in_order(self, tmp_path):
        store = _store(tmp_path)
        events = [make_event("t.e", "tests", i) for i in range(1, 6)]
        for e in events:
            store.append(e)
        replayed = list(store.replay())
        assert [e.logical_time for e in replayed] == [1, 2, 3, 4, 5]
        assert replayed == events

    def test_replay_from_logical_time(self, tmp_path):
        store = _store(tmp_path)
        for i in range(1, 11):
            store.append(make_event("t.e", "tests", i))
        replayed = list(store.replay(from_logical_time=5))
        assert [e.logical_time for e in replayed] == [6, 7, 8, 9, 10]

    def test_replay_empty_store(self, tmp_path):
        assert list(_store(tmp_path).replay()) == []

    def test_replayed_events_verify(self, tmp_path):
        store = _store(tmp_path)
        store.append(make_event("t.e", "tests", 1, payload={"a": 1}))
        assert all(e.verify() for e in store.replay())


class TestCheckpoint:
    def test_checkpoint_roundtrip(self, tmp_path):
        store = _store(tmp_path)
        path = store.checkpoint({"goals": [1, 2]}, at_logical_time=5)
        state, t = store.load_checkpoint(path)
        assert state == {"goals": [1, 2]}
        assert t == 5

    def test_replay_from_checkpoint(self, tmp_path):
        store = _store(tmp_path)
        for i in range(1, 11):
            store.append(make_event("t.e", "tests", i))
        path = store.checkpoint({"n": 5}, at_logical_time=5)
        state, events = store.replay_from_checkpoint(path)
        assert state == {"n": 5}
        assert [e.logical_time for e in events] == [6, 7, 8, 9, 10]

    def test_latest_checkpoint(self, tmp_path):
        store = _store(tmp_path)
        assert store.latest_checkpoint() is None
        store.checkpoint({}, 1)
        p2 = store.checkpoint({}, 2)
        assert store.latest_checkpoint() == p2
