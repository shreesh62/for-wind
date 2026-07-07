"""Ch 43 — Background cognition package.

Houses the `BackgroundRuntime`, a kernel `RuntimeContract` that performs
opportunistic work only while the foreground is idle and always yields the
instant foreground activity arrives.
"""

from friday.background.runtime import BackgroundRuntime

__all__ = ["BackgroundRuntime"]
