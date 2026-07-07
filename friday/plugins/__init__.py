"""Ch 54 — plugins: adopt external capabilities through the same gates.

A plugin is just another source of ``CapabilityCandidate``s that must pass
sandbox + benchmark + permission review before install. This package touches no
protected subsystem (kernel, world, goals, safety, verification) and never
enters the ``CapabilityRegistry`` directly — candidates flow only through the
``PromotionPipeline``.
"""

from friday.plugins.manifest import LoadedPlugin, LoadFailure, PluginManifest
from friday.plugins.loader import PluginLoader
from friday.plugins.registry import PluginRegistry
from friday.plugins.sandbox import PluginSandbox

__all__ = [
    "PluginManifest",
    "LoadFailure",
    "LoadedPlugin",
    "PluginSandbox",
    "PluginLoader",
    "PluginRegistry",
]
