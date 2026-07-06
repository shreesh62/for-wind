"""Ch 25 — DemonstrationRecorder: watch a user, extract PRINCIPLES not coordinates.

A demonstration is a stream of raw events. Each event names an interaction
(``capability`` or ``type``) and describes *where* it happened. The recorder's
job is to distill each event into a **coordinate-free** :class:`Principle`: a
semantic ``target_descriptor`` such as "primary button" or "element near the
top-right region" — never a raw pixel coordinate.

This matters because coordinates do not generalize: a learned procedure must
survive a re-scaled or re-positioned interface. By describing *what* was acted
on (semantics, relative region) rather than *where* (pixels), replay can
re-resolve the same target on a different layout.

CRITICAL (Axiom 15): extraction is generic. No app identity, no hardcoded UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from friday.environments.unknown.object_graph import Principle


@dataclass
class DemonstrationRecording:
    """Ch 25 — the raw events captured during a single demonstration."""

    events: List[dict] = field(default_factory=list)


class DemonstrationRecorder:
    """Ch 25 — records raw demonstration events for principle extraction."""

    def __init__(self) -> None:
        self._events: List[dict] = []
        self._recording = False

    def start(self) -> None:
        """Begin a fresh recording, discarding any previous buffer."""
        self._events = []
        self._recording = True

    def record_event(self, raw: dict) -> None:
        """Append a single raw event (ignored unless a recording is active)."""
        if self._recording:
            self._events.append(dict(raw))

    def stop(self) -> DemonstrationRecording:
        """End the recording and return the captured events."""
        self._recording = False
        return DemonstrationRecording(events=list(self._events))


def extract_principles(recording: DemonstrationRecording) -> List[Principle]:
    """Convert raw demonstration events into coordinate-free :class:`Principle`s.

    Each event is expected to name an interaction (``capability`` or ``type``)
    and, ideally, carry a semantic context describing the target region
    (``target``, ``context``, ``region``, ``descriptor``, or ``label``). The
    resulting ``target_descriptor`` is guaranteed non-empty and to contain no
    raw pixel coordinate. If an event only carries coordinates, a descriptor is
    synthesized from the *relative* region (e.g. "element near top-right
    region") WITHOUT embedding the pixel numbers.
    """
    principles: List[Principle] = []
    for index, event in enumerate(recording.events):
        capability = _capability_of(event)
        descriptor = _descriptor_of(event)
        value = event.get("value") or event.get("text")
        principles.append(
            Principle(
                step_index=index,
                capability=capability,
                target_descriptor=descriptor,
                value=str(value) if value is not None else None,
            )
        )
    return principles


# --- helpers ---------------------------------------------------------------

# Semantic keys, in priority order, that already describe a target region.
_DESCRIPTOR_KEYS = ("target_descriptor", "descriptor", "target", "context", "region", "label")


def _capability_of(event: dict) -> str:
    """Extract the abstract verb from a raw event."""
    cap = event.get("capability") or event.get("type") or event.get("action")
    return str(cap) if cap else "observe"


def _descriptor_of(event: dict) -> str:
    """Return a non-empty, coordinate-free target descriptor for an event."""
    for key in _DESCRIPTOR_KEYS:
        val = event.get(key)
        if val:
            text = str(val).strip()
            if text:
                return text
    # No semantic hint given — synthesize one from relative position, WITHOUT
    # embedding any pixel numbers.
    region = _relative_region(event)
    if region:
        return f"element near {region} region"
    return "element in the interface"


def _relative_region(event: dict) -> Optional[str]:
    """Derive a coarse relative-region phrase from coordinates, if present.

    The pixel numbers themselves are never returned — only a qualitative region
    label (e.g. "top-right"). Coordinates may be given as ``x``/``y`` or as an
    ``(x, y)`` / bbox tuple under ``coordinates`` / ``bbox``, optionally with
    ``width``/``height`` (or a screen size) to normalize against.
    """
    x, y = _coords_of(event)
    if x is None or y is None:
        return None

    width = _num(event.get("width")) or _num(event.get("screen_width")) or 1920.0
    height = _num(event.get("height")) or _num(event.get("screen_height")) or 1080.0
    if width <= 0:
        width = 1920.0
    if height <= 0:
        height = 1080.0

    fx = x / width
    fy = y / height

    vertical = "top" if fy < 0.34 else ("bottom" if fy > 0.66 else "middle")
    horizontal = "left" if fx < 0.34 else ("right" if fx > 0.66 else "center")

    if vertical == "middle" and horizontal == "center":
        return "center"
    if vertical == "middle":
        return horizontal
    if horizontal == "center":
        return vertical
    return f"{vertical}-{horizontal}"


def _coords_of(event: dict):
    """Extract (x, y) from an event's coordinate fields, or (None, None)."""
    if "x" in event and "y" in event:
        return _num(event.get("x")), _num(event.get("y"))
    for key in ("coordinates", "bbox", "position", "point"):
        raw = event.get(key)
        if raw is None:
            continue
        try:
            seq = list(raw)
        except TypeError:
            continue
        if len(seq) >= 2:
            return _num(seq[0]), _num(seq[1])
    return None, None


def _num(value) -> Optional[float]:
    """Best-effort numeric coercion; None on failure."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
