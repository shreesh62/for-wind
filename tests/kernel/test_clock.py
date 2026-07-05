"""M1 tests — CognitiveClock monotonicity and Lamport merge."""

import threading

from hypothesis import given, strategies as st

from friday.kernel.clock import CognitiveClock


def test_tick_monotonic():
    clock = CognitiveClock()
    values = [clock.tick() for _ in range(100)]
    assert values == sorted(values)
    assert len(set(values)) == 100


def test_lamport_merge():
    clock = CognitiveClock(initial=5)
    assert clock.update(10) == 11
    assert clock.update(3) == 12


def test_serialize_restore():
    clock = CognitiveClock()
    for _ in range(7):
        clock.tick()
    state = clock.serialize()
    fresh = CognitiveClock()
    fresh.restore(state)
    assert fresh.now()[0] == 7


def test_concurrent_ticks_unique():
    clock = CognitiveClock()
    results = []
    lock = threading.Lock()

    def worker():
        for _ in range(100):
            v = clock.tick()
            with lock:
                results.append(v)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(results)) == 800


@given(st.lists(st.integers(min_value=0, max_value=10**6), max_size=50))
def test_property_update_always_advances(received_times):
    clock = CognitiveClock()
    last = clock.now()[0]
    for r in received_times:
        new = clock.update(r)
        assert new > last
        assert new > r
        last = new
