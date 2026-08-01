"""FRIDAY observability (M24) — logging as a consumer of the event system.

Rather than scattered ``print()`` calls, observability subscribes to kernel events
and emits structured log records. This keeps a single source of truth (the append-only
event store) and makes logs replay-compatible.
"""

from friday.observability.failure_log import FailureLogSubscriber

__all__ = ["FailureLogSubscriber"]
