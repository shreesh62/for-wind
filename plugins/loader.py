"""Plugin loading infrastructure for Jarvis."""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterable, Optional

from capabilities import CapabilityRegistry
from core.capability_dispatcher import CapabilityDispatcher, DispatchContext


@dataclass
class PluginContext:
    """Objects exposed to plugin modules for registration."""

    registry: CapabilityRegistry
    dispatcher: CapabilityDispatcher


class PluginLoadError(RuntimeError):
    pass


class PluginLoader:
    """Discovers plugin manifests and registers their capabilities."""

    def __init__(self, plugins_dir: Path) -> None:
        self.plugins_dir = plugins_dir

    def discover(self) -> Iterable[Path]:
        if not self.plugins_dir.exists():
            return []
        return sorted(
            [path for path in self.plugins_dir.iterdir() if (path / "manifest.json").exists()]
        )

    def _load_manifest(self, manifest_path: Path) -> Dict[str, Any]:
        try:
            with manifest_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise PluginLoadError(f"Failed to read manifest: {manifest_path}: {exc}") from exc

        if not isinstance(data, dict):
            raise PluginLoadError(f"Invalid manifest structure in {manifest_path}")
        return data

    def _load_module(self, module_path: Path) -> ModuleType:
        spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"Cannot create spec for {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_path.stem] = module
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
        return module

    def load_plugins(self, context: PluginContext) -> None:
        for plugin_dir in self.discover():
            manifest_path = plugin_dir / "manifest.json"
            module_path = plugin_dir / "module.py"

            manifest = self._load_manifest(manifest_path)
            module = self._load_module(module_path) if module_path.exists() else None

            capabilities = manifest.get("capabilities", [])
            for capability in capabilities:
                self._register_capability(context, capability, module)

    def _register_capability(
        self,
        context: PluginContext,
        capability_def: Dict[str, Any],
        module: Optional[ModuleType],
    ) -> None:
        key = capability_def.get("key")
        if not key:
            raise PluginLoadError("Capability definition missing 'key'")

        definition = capability_def.get("definition", {})
        context.registry.register_dynamic_capability(key, definition)

        handler_name = capability_def.get("handler")
        if module and handler_name and hasattr(module, handler_name):
            handler_func = getattr(module, handler_name)
            if callable(handler_func):
                context.dispatcher.register_handler(
                    key,
                    lambda ctx, func=handler_func: func(context=ctx, capability=definition),
                )
        else:
            # If no handler supplied, capability remains informational only
            pass
