"""Ch 54 — the plugin sandbox: reject manifests that reach protected subsystems.

Ch 54.5 hard boundary — a plugin may never touch the kernel, world model, goal
graph, safety engine, or verification engine. The sandbox inspects a manifest's
requested permissions and rejects any that name a protected subsystem before the
loader ever produces a single candidate.
"""

from __future__ import annotations

from typing import Tuple

from friday.plugins.manifest import PluginManifest


class PluginSandbox:
    """Ch 54.5 — validate a manifest declares no forbidden protected access."""

    PROTECTED: Tuple[str, ...] = ("kernel", "world", "goals", "safety", "verification")

    def validate(self, manifest: PluginManifest) -> Tuple[bool, str]:
        """Return ``(ok, reason)``.

        Rejects any manifest whose permission strings reference a protected
        subsystem (case-insensitive substring match). Otherwise ``(True, "")``.
        """
        for permission in manifest.permissions:
            lowered = permission.lower()
            for name in self.PROTECTED:
                if name in lowered:
                    return (False, f"requests protected subsystem: {name}")
        return (True, "")
