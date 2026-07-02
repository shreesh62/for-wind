"""Ch 12 — SensorContract: the uniform interface every sensor implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, List, Optional

from friday.perception.observation import Observation


class SensorContract(ABC):
    """A perception source producing uniform Observations."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def environment(self) -> str: ...

    @abstractmethod
    def observe(self) -> List[Observation]: ...

    def subscribe(self, handler: Callable[[Observation], None]) -> None:
        """Optional push-mode; default sensors are poll-only."""
        raise NotImplementedError(f"{self.name} does not support subscriptions")

    def query(self, object_type: Optional[str] = None) -> List[Observation]:
        observations = self.observe()
        if object_type is None:
            return observations
        return [o for o in observations if o.object_type == object_type]


class ScreenSensor(SensorContract):
    """Wraps the existing ScreenCapture as a SensorContract (no rewrite)."""

    def __init__(self, capture=None) -> None:
        if capture is None:
            from friday.perception.screen import ScreenCapture

            capture = ScreenCapture()
        self._capture = capture

    @property
    def name(self) -> str:
        return "screen"

    @property
    def environment(self) -> str:
        return "desktop"

    def observe(self) -> List[Observation]:
        from friday.events.event import FrozenDict

        shot = self._capture.grab()
        if shot is None:
            return []
        width = getattr(shot, "width", None)
        height = getattr(shot, "height", None)
        return [
            Observation(
                sensor=self.name,
                environment=self.environment,
                object_type="screenshot",
                attributes=FrozenDict(
                    {"width": width, "height": height, "name": "primary_display"}
                ),
                confidence=1.0,
                bbox=(0, 0, width or 0, height or 0),
            )
        ]
