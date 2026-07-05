"""M1 tests — EventBus pattern matching, thread safety, handler isolation."""

import threading

from friday.events.bus import EventBus
from friday.events.event import make_event


def _event(event_type, t=1):
    return make_event(event_type, "tests", t)


class TestSubscription:
    def test_exact_match(self):
        bus = EventBus()
        received = []
        bus.subscribe("goal.created", received.append)
        bus.publish(_event("goal.created"))
        assert len(received) == 1

    def test_wildcard_match(self):
        bus = EventBus()
        received = []
        bus.subscribe("goal.*", received.append)
        bus.publish(_event("goal.created"))
        bus.publish(_event("goal.completed"))
        bus.publish(_event("observation.received"))
        assert len(received) == 2

    def test_star_matches_everything(self):
        bus = EventBus()
        received = []
        bus.subscribe("*", received.append)
        bus.publish(_event("anything.at.all"))
        assert len(received) == 1

    def test_unsubscribe(self):
        bus = EventBus()
        received = []
        sub = bus.subscribe("goal.*", received.append)
        assert bus.unsubscribe(sub)
        bus.publish(_event("goal.created"))
        assert received == []
        assert not bus.unsubscribe(sub)


class TestHandlerIsolation:
    def test_failing_handler_does_not_break_others(self):
        bus = EventBus()
        received = []

        def bad_handler(event):
            raise RuntimeError("boom")

        bus.subscribe("*", bad_handler)
        bus.subscribe("*", received.append)
        delivered = bus.publish(_event("x.y"))
        assert len(received) == 1
        assert delivered == 1
        assert bus.error_count == 1


class TestThreadSafety:
    def test_concurrent_publish_and_subscribe(self):
        bus = EventBus()
        received = []
        lock = threading.Lock()

        def handler(event):
            with lock:
                received.append(event)

        bus.subscribe("load.*", handler)

        def publish_many():
            for i in range(50):
                bus.publish(_event("load.test", t=i))

        threads = [threading.Thread(target=publish_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(received) == 200
