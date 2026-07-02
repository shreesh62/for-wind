"""Ch 12 — SensorContract stub (fleshed out in M2)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class SensorContract(ABC):
    """A perception source producing uniform observations."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def observe(self) -> List[Dict[str, Any]]: ...
