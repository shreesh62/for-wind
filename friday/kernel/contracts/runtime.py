"""Ch 20/52 — RuntimeContract: interface every kernel runtime must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from friday.events.event import Event


class RuntimeContract(ABC):
    """A pluggable runtime managed by the CognitiveKernel.

    Runtimes never call each other directly; all communication flows
    through kernel-published events.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def initialize(self, kernel: Any) -> None: ...

    @abstractmethod
    def tick(self, logical_time: int) -> None: ...

    @abstractmethod
    def observe(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def receive(self, event: Event) -> None: ...

    @abstractmethod
    def publish(self, event: Event) -> None: ...

    @abstractmethod
    def checkpoint(self) -> Dict[str, Any]: ...

    @abstractmethod
    def restore(self, state: Dict[str, Any]) -> None: ...

    @abstractmethod
    def shutdown(self) -> None: ...

    @abstractmethod
    def health(self) -> Dict[str, Any]: ...
