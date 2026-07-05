"""Ch 23 — EnvironmentContract stub (fleshed out in M6)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class EnvironmentContract(ABC):
    """A digital environment (browser, desktop, ...) the operator acts in."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def observe(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def health(self) -> Dict[str, Any]: ...
