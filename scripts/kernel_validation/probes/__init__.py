"""M13 — built-in fault probes.

Each probe module registers itself with the ``faults`` registry at import time, so
importing this package is what makes ``get_probe(...)`` resolve the built-ins.
The runner imports this package once; it never references a probe class directly.
"""

from __future__ import annotations

from scripts.kernel_validation.probes import browser_kill  # noqa: F401 - registers
from scripts.kernel_validation.probes import confirmation_gate  # noqa: F401 - registers
from scripts.kernel_validation.probes import crash_restore  # noqa: F401 - registers
from scripts.kernel_validation.probes import interrupt_resume  # noqa: F401 - registers
from scripts.kernel_validation.probes import replay_checkpoint  # noqa: F401 - registers

__all__ = [
    "browser_kill",
    "confirmation_gate",
    "crash_restore",
    "interrupt_resume",
    "replay_checkpoint",
]
