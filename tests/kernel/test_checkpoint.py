"""M1 tests — CheckpointManager save/load/auto-checkpoint."""

from friday.events.store import EventStore
from friday.kernel.checkpoint import CheckpointManager


def _manager(tmp_path, auto_every=0, state=None):
    store = EventStore(str(tmp_path / "s.jsonl"))
    return CheckpointManager(
        store, lambda: dict(state or {"k": "v"}), auto_checkpoint_every=auto_every
    )


def test_save_and_load(tmp_path):
    mgr = _manager(tmp_path, state={"goals": [1]})
    path = mgr.save(at_logical_time=9)
    assert mgr.last_checkpoint_path == path
    state, t = mgr.load(path)
    assert state == {"goals": [1]}
    assert t == 9


def test_auto_checkpoint_threshold(tmp_path):
    mgr = _manager(tmp_path, auto_every=3)
    assert mgr.notify_event(1) is None
    assert mgr.notify_event(2) is None
    path = mgr.notify_event(3)
    assert path is not None
    assert mgr.notify_event(4) is None


def test_no_auto_checkpoint_when_disabled(tmp_path):
    mgr = _manager(tmp_path, auto_every=0)
    for i in range(10):
        assert mgr.notify_event(i) is None
