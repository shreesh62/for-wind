"""Ch 16 — CapabilityContract stub (fleshed out in M7)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class CapabilityContract(ABC):
    """A reusable, composable unit of competence."""

    @property
    @abstractmethod
    def id(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Any: ...
