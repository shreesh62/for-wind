"""Ch 9 — WorldObject and Relationship: the object graph inside the World Model."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class WorldObject:
    """A thing the operator believes exists (window, button, file, ...)."""

    object_type: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    attributes: Dict[str, Any] = field(default_factory=dict)
    belief_ids: List[str] = field(default_factory=list)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


@dataclass
class Relationship:
    """A typed edge between two WorldObjects (contains, overlaps, owns, ...)."""

    source_id: str
    target_id: str
    relation: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    confidence: float = 1.0
