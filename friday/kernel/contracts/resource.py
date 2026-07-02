"""Ch 45-48 — ResourceContract stub (fleshed out in M4)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class ResourceContract(ABC):
    """A finite resource (LLM budget, browser session, mouse, ...)."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def health(self) -> Dict[str, Any]: ...
