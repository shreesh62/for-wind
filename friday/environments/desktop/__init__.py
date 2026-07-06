"""Ch 30 — Desktop Runtime package: the Windows desktop as a uniform environment.

Exports the real :class:`DesktopEnvironment` (in ``runtime.py``) which implements
the same ``EnvironmentContract`` + ``EnvironmentRuntime`` as M6's
``BrowserEnvironment``, so the Kernel can register/tick/checkpoint it
identically. The M6 placeholder implementation has been removed.

FAS Ch 30 — every digital environment is interchangeable at the contract boundary.
"""

from __future__ import annotations

from friday.environments.desktop.runtime import DesktopEnvironment

__all__ = ["DesktopEnvironment"]
