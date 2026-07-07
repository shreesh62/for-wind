"""Ch 54 — the plugin registry: track installed manifests by name.

The registry records *which* plugins are installed. It deliberately does not
touch the ``CapabilityRegistry`` — installing a plugin never registers or
promotes a capability. Candidates flow only through the ``PromotionPipeline``,
a property enforced structurally by this module importing no capability seam.
"""

from __future__ import annotations

from typing import Dict, Optional

from friday.plugins.manifest import PluginManifest


class PluginRegistry:
    """Ch 54 — record installed plugin manifests (never a capability seam)."""

    def __init__(self) -> None:
        self._manifests: Dict[str, PluginManifest] = {}

    def install(self, manifest: PluginManifest) -> str:
        """Record a manifest by name and return the name. Records only."""
        self._manifests[manifest.name] = manifest
        return manifest.name

    def uninstall(self, name: str) -> None:
        """Forget an installed plugin by name (no-op if absent)."""
        self._manifests.pop(name, None)

    def get(self, name: str) -> Optional[PluginManifest]:
        """Return the installed manifest for ``name``, or ``None``."""
        return self._manifests.get(name)
