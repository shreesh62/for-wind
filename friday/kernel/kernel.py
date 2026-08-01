"""Ch 20 — CognitiveKernel: the singleton authority over global state.

Pure infrastructure: no LLMs, no browser, no cognition. Owns the clock,
event bus, event store, scheduler, checkpoints, and registered runtimes.
Goals are stubs in M1 (created/tracked, never executed).
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Dict, List, Optional

from friday.events.bus import EventBus
from friday.events.event import Event, make_event
from friday.events.store import EventStore
from friday.kernel.checkpoint import CheckpointManager
from friday.kernel.clock import CognitiveClock
from friday.kernel.contracts.runtime import RuntimeContract
from friday.kernel.scheduler import CognitiveScheduler

logger = logging.getLogger(__name__)

KERNEL_SOURCE = "kernel"


class CognitiveKernel:
    """Continuously running, event-driven kernel (FAS §20.19 public API)."""

    def __init__(
        self,
        store_path: str = "~/.friday/events/session.jsonl",
        event_store: Optional[EventStore] = None,
        auto_checkpoint_every: int = 0,
        tick_min_interval: float = 0.005,
        tick_max_interval: float = 0.25,
    ) -> None:
        self._clock = CognitiveClock()
        self._bus = EventBus()
        self._store = event_store or EventStore(store_path)
        self._checkpoints = CheckpointManager(
            self._store, self._snapshot_state, auto_checkpoint_every
        )
        self._scheduler = CognitiveScheduler(
            self._tick, min_interval=tick_min_interval, max_interval=tick_max_interval
        )
        self._runtimes: Dict[str, RuntimeContract] = {}
        self._goals: Dict[str, Dict[str, Any]] = {}
        self._suspended_goals: set = set()
        self._capability_requests: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._running = False
        self._degraded_reasons: List[str] = []
        self._persist_attempts = 0

    # ------------------------------------------------------------------ API

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
        self._emit("kernel.started", {})
        self._scheduler.start()

    def shutdown(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
        self._scheduler.stop()
        for runtime in list(self._runtimes.values()):
            try:
                runtime.shutdown()
            except Exception:  # noqa: BLE001
                logger.exception("Runtime shutdown failed: %s", runtime.name)
        self._emit("kernel.shutdown", {})

    def register_runtime(self, runtime: RuntimeContract) -> None:
        with self._lock:
            self._runtimes[runtime.name] = runtime
        runtime.initialize(self)
        self._bus.subscribe("*", runtime.receive)
        self._emit("kernel.runtime_registered", {"runtime": runtime.name})

    def submit_goal(self, goal_text: str, constraints: Optional[dict] = None) -> str:
        goal_id = str(uuid.uuid4())
        with self._lock:
            self._goals[goal_id] = {
                "id": goal_id,
                "text": goal_text,
                "constraints": dict(constraints or {}),
                "state": "created",
            }
        self._emit("goal.created", {"goal_id": goal_id, "text": goal_text})
        return goal_id

    def interrupt_goal(self, goal_id: str, reason: str = "") -> bool:
        """Suspend an in-flight goal. Returns False for an unknown/terminal goal.

        Suspension is **cooperative**: it records the goal as suspended and emits
        ``goal.suspended``, and a runtime honors it at its next suspension
        checkpoint. Arbitrary in-progress work is not preempted mid-call — that
        cannot be done safely — so the granularity is the runtime's checkpoint, and
        no work is lost or repeated because the checkpoint sits between units of
        work rather than inside one.
        """
        with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None or goal.get("state") in ("completed", "failed", "abandoned"):
                return False
            if goal_id in self._suspended_goals:
                return True
            self._suspended_goals.add(goal_id)
        self._emit("goal.suspended", {"goal_id": goal_id, "reason": reason})
        return True

    def resume_goal(self, goal_id: str) -> bool:
        """Resume a suspended goal. Returns False when it was not suspended."""
        with self._lock:
            if goal_id not in self._suspended_goals:
                return False
            self._suspended_goals.discard(goal_id)
        self._emit("goal.resumed", {"goal_id": goal_id})
        return True

    def is_goal_suspended(self, goal_id: str) -> bool:
        """Whether ``goal_id`` is currently suspended (runtime checkpoint query)."""
        with self._lock:
            return goal_id in self._suspended_goals

    def submit_observation(self, observation: dict) -> None:
        self._emit("observation.received", dict(observation))

    def subscribe(self, pattern: str, handler) -> str:
        """Subscribe a handler to kernel events (fnmatch pattern)."""
        return self._bus.subscribe(pattern, handler)

    def publish_event(self, event: Event) -> None:
        """Publish an externally-constructed event through the kernel."""
        self._clock.update(event.logical_time)
        self._persist_and_route(event)

    def query_world(self) -> dict:
        logical, wall = self._clock.now()
        return {"logical_time": logical, "wall_time": wall, "runtimes": list(self._runtimes)}

    def query_goals(self) -> List[dict]:
        with self._lock:
            return [dict(g) for g in self._goals.values()]

    def request_capability(self, capability: str, params: Optional[dict] = None) -> str:
        request_id = str(uuid.uuid4())
        with self._lock:
            self._capability_requests[request_id] = {
                "id": request_id,
                "capability": capability,
                "params": dict(params or {}),
                "state": "pending",
            }
        self._emit(
            "capability.requested",
            {"request_id": request_id, "capability": capability},
        )
        return request_id

    def checkpoint(self) -> str:
        logical, _ = self._clock.now()
        path = self._checkpoints.save(logical)
        self._emit("kernel.checkpoint", {"path": path})
        return path

    def restore(self, path: str) -> None:
        state, logical_time = self._checkpoints.load(path)
        with self._lock:
            self._goals = {g["id"]: dict(g) for g in state.get("goals", [])}
            self._suspended_goals = set(state.get("suspended_goals", []))
            self._capability_requests = {
                r["id"]: dict(r) for r in state.get("capability_requests", [])
            }
            self._degraded_reasons = list(state.get("degraded_reasons", []))
        self._clock.restore(state.get("clock", {"logical": logical_time}))
        for event in self._store.replay(from_logical_time=logical_time):
            self._clock.update(event.logical_time)
            self._apply_event(event)
        for name, runtime_state in state.get("runtimes", {}).items():
            runtime = self._runtimes.get(name)
            if runtime is not None:
                runtime.restore(runtime_state)

    def health(self) -> dict:
        logical, wall = self._clock.now()
        with self._lock:
            degraded = list(self._degraded_reasons)
        if self._scheduler.tick_errors:
            degraded.append(f"tick_errors={self._scheduler.tick_errors}")
        store_lag = self._store_lag()
        if store_lag:
            degraded.append(f"event_store_lag={store_lag}")
        return {
            "status": "degraded" if degraded else "ok",
            "running": self._running,
            "tick": logical,
            "wall_time": wall,
            "runtimes": {
                name: self._safe_runtime_health(rt)
                for name, rt in self._runtimes.items()
            },
            "degraded_reasons": degraded,
            "handler_errors": self._bus.error_count,
        }

    # ------------------------------------------------------------- internal

    def _emit(self, event_type: str, payload: dict, parent_id: Optional[str] = None) -> Event:
        event = make_event(
            event_type=event_type,
            source=KERNEL_SOURCE,
            logical_time=self._clock.tick(),
            payload=payload,
            parent_id=parent_id,
        )
        self._persist_and_route(event)
        return event

    def _persist_and_route(self, event: Event) -> None:
        with self._lock:
            self._persist_attempts += 1
        try:
            self._store.append(event)
        except Exception:  # noqa: BLE001 - persistence loss degrades, never crashes
            logger.exception("EventStore append failed")
            with self._lock:
                self._degraded_reasons.append(f"store_append_failed:{event.event_type}")
        self._checkpoints.notify_event(event.logical_time)
        self._apply_event(event)
        self._bus.publish(event)

    def _apply_event(self, event: Event) -> None:
        """Rebuild kernel-owned state from an event (used live and in replay)."""
        if event.event_type == "goal.created":
            goal_id = event.payload.get("goal_id")
            if goal_id:
                with self._lock:
                    self._goals.setdefault(
                        goal_id,
                        {
                            "id": goal_id,
                            "text": event.payload.get("text", ""),
                            "constraints": {},
                            "state": "created",
                        },
                    )
            return

        # Suspension is part of kernel-owned goal state, so it is rebuilt on replay
        # too: restoring a crashed session must not lose the fact that a goal was
        # suspended (which would silently resume work the user paused).
        if event.event_type in ("goal.suspended", "goal.resumed"):
            goal_id = event.payload.get("goal_id")
            if not goal_id:
                return
            suspended = event.event_type == "goal.suspended"
            with self._lock:
                goal = self._goals.get(goal_id)
                if goal is not None:
                    goal["state"] = "suspended" if suspended else "active"
                if suspended:
                    self._suspended_goals.add(goal_id)
                else:
                    self._suspended_goals.discard(goal_id)

    def _tick(self) -> bool:
        logical = self._clock.tick()
        had_work = False
        for runtime in list(self._runtimes.values()):
            try:
                runtime.tick(logical)
                had_work = True
            except Exception:  # noqa: BLE001
                logger.exception("Runtime tick failed: %s", runtime.name)
                with self._lock:
                    self._degraded_reasons.append(f"runtime_tick_failed:{runtime.name}")
        return had_work

    def _snapshot_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "clock": self._clock.serialize(),
                "goals": [dict(g) for g in self._goals.values()],
                "suspended_goals": sorted(self._suspended_goals),
                "capability_requests": [
                    dict(r) for r in self._capability_requests.values()
                ],
                "degraded_reasons": list(self._degraded_reasons),
                "runtimes": {
                    name: self._safe_runtime_checkpoint(rt)
                    for name, rt in self._runtimes.items()
                },
            }

    def _store_lag(self) -> int:
        """Events that were emitted but never durably persisted."""
        with self._lock:
            attempts = self._persist_attempts
        try:
            persisted = self._store.append_count
        except Exception:  # noqa: BLE001
            return attempts
        return max(0, attempts - persisted)

    @staticmethod
    def _safe_runtime_health(runtime: RuntimeContract) -> Dict[str, Any]:
        try:
            return runtime.health()
        except Exception:  # noqa: BLE001
            return {"status": "error"}

    @staticmethod
    def _safe_runtime_checkpoint(runtime: RuntimeContract) -> Dict[str, Any]:
        try:
            return runtime.checkpoint()
        except Exception:  # noqa: BLE001
            return {}
