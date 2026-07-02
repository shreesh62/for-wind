"""Ch 21 — Event System: the immutable Event record.

Every occurrence inside FRIDAY is represented as an Event. Events are
frozen, signed, and causally linked via parent_id/correlation_id.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional


class FrozenDict(dict):
    """Immutable dict for use inside frozen dataclasses."""

    def __setitem__(self, *_: Any) -> None:
        raise TypeError("FrozenDict is immutable")

    def __delitem__(self, *_: Any) -> None:
        raise TypeError("FrozenDict is immutable")

    def clear(self) -> None:
        raise TypeError("FrozenDict is immutable")

    def pop(self, *_: Any) -> Any:
        raise TypeError("FrozenDict is immutable")

    def popitem(self) -> Any:
        raise TypeError("FrozenDict is immutable")

    def setdefault(self, *_: Any) -> Any:
        raise TypeError("FrozenDict is immutable")

    def update(self, *_: Any, **__: Any) -> None:
        raise TypeError("FrozenDict is immutable")

    def __hash__(self) -> int:  # type: ignore[override]
        return hash(tuple(sorted((k, repr(v)) for k, v in self.items())))


def _compute_signature(
    event_id: str, event_type: str, payload: Mapping[str, Any], parent_id: Optional[str]
) -> str:
    material = event_id + event_type + repr(sorted(payload.items())) + str(parent_id)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Event:
    """A single immutable occurrence within the cognitive system."""

    id: str
    logical_time: int
    wall_time: float
    event_type: str  # dot-namespaced, e.g. "goal.created"
    source: str  # runtime name that emitted this
    payload: FrozenDict = field(default_factory=FrozenDict)
    correlation_id: str = ""
    parent_id: Optional[str] = None
    signature: str = ""

    def verify(self) -> bool:
        """Return True if the signature matches the event contents."""
        return self.signature == _compute_signature(
            self.id, self.event_type, self.payload, self.parent_id
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "logical_time": self.logical_time,
            "wall_time": self.wall_time,
            "event_type": self.event_type,
            "source": self.source,
            "payload": dict(self.payload),
            "correlation_id": self.correlation_id,
            "parent_id": self.parent_id,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Event":
        return cls(
            id=data["id"],
            logical_time=int(data["logical_time"]),
            wall_time=float(data["wall_time"]),
            event_type=data["event_type"],
            source=data["source"],
            payload=FrozenDict(data.get("payload") or {}),
            correlation_id=data.get("correlation_id", ""),
            parent_id=data.get("parent_id"),
            signature=data.get("signature", ""),
        )


def make_event(
    event_type: str,
    source: str,
    logical_time: int,
    payload: Optional[Mapping[str, Any]] = None,
    correlation_id: str = "",
    parent_id: Optional[str] = None,
    wall_time: Optional[float] = None,
) -> Event:
    """Construct a signed, immutable Event."""
    event_id = str(uuid.uuid4())
    frozen_payload = FrozenDict(payload or {})
    return Event(
        id=event_id,
        logical_time=logical_time,
        wall_time=wall_time if wall_time is not None else time.time(),
        event_type=event_type,
        source=source,
        payload=frozen_payload,
        correlation_id=correlation_id or event_id,
        parent_id=parent_id,
        signature=_compute_signature(event_id, event_type, frozen_payload, parent_id),
    )


def verify_signature(event: Event) -> bool:
    return event.verify()
