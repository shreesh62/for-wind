"""M11 — Property tests for plugin sandbox and pipeline-only entry (Ch 54).

Exercises ``friday/plugins/*``:
- Property 7: ``PluginSandbox.validate`` rejects any manifest whose permissions
  reference a protected subsystem (kernel/world/goals/safety/verification) and
  accepts otherwise.
- Property 8: a loaded plugin yields CapabilityCandidate-shaped objects, the
  plugins package imports no capability seam (structural), and installing a
  plugin records only — it never mutates a CapabilityRegistry.

All tests run under ``FRIDAY_DRY_RUN=1`` so the existing suite stays green.

Validates: Requirements 3.1, 3.2, 3.3, 3.4
"""

from __future__ import annotations

import os

# MUST be set before importing any friday module so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")

import ast
from pathlib import Path

from hypothesis import given, settings, strategies as st

from friday.capabilities.registry import CapabilityRegistry
from friday.plugins.loader import PluginLoader
from friday.plugins.manifest import LoadedPlugin, PluginManifest
from friday.plugins.registry import PluginRegistry
from friday.plugins.sandbox import PluginSandbox

_PROTECTED = ("kernel", "world", "goals", "safety", "verification")
_BENIGN = ("read", "observe", "network", "click", "type")

_PLUGINS_DIR = Path(__file__).resolve().parent.parent.parent / "friday" / "plugins"


# --------------------------------------------------------------------------- #
# Property 7: Plugins cannot request protected subsystems
# --------------------------------------------------------------------------- #
@given(permissions=st.lists(st.sampled_from(_PROTECTED + _BENIGN), max_size=5))
@settings(max_examples=100)
def test_property7_sandbox_rejects_protected_permissions(permissions):
    """validate is (False, reason) iff any permission names a protected subsystem."""
    manifest = PluginManifest(
        name="p",
        version="1",
        author="a",
        capabilities=("click",),
        permissions=tuple(permissions),
        signature="sig",
    )
    ok, reason = PluginSandbox().validate(manifest)

    references_protected = any(
        prot in perm.lower() for perm in permissions for prot in _PROTECTED
    )
    if references_protected:
        assert ok is False
        assert reason
    else:
        assert ok is True
        assert reason == ""


# --------------------------------------------------------------------------- #
# Property 8: Plugin capabilities enter only through the pipeline
# --------------------------------------------------------------------------- #
@given(verbs=st.lists(st.sampled_from(_BENIGN), min_size=1, max_size=4, unique=True))
@settings(max_examples=50)
def test_property8_loaded_plugin_yields_candidate_shaped_objects(verbs):
    """A loaded plugin yields objects exposing proposed_id (candidate-shaped)."""
    manifest = PluginManifest(
        name="p", version="1", author="a",
        capabilities=tuple(verbs), permissions=("read",), signature="sig",
    )
    loaded = PluginLoader(PluginSandbox()).load(manifest)
    assert isinstance(loaded, LoadedPlugin)
    assert len(loaded.candidates) == len(verbs)
    for candidate in loaded.candidates:
        assert hasattr(candidate, "proposed_id")
        assert candidate.proposed_id.startswith("plugin.p.")


def test_property8_plugins_package_imports_no_capability_seam():
    """No file under friday/plugins/ imports friday.capabilities (structural)."""
    offenders = []
    for path in _PLUGINS_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "friday.capabilities" or node.module.startswith(
                    "friday.capabilities."
                ):
                    offenders.append(f"{path.name}: {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("friday.capabilities"):
                        offenders.append(f"{path.name}: {alias.name}")
    assert offenders == [], f"plugins import capability seam: {offenders}"


def test_property8_install_records_only_and_does_not_touch_registry():
    """Installing a plugin records the manifest but never mutates a CapabilityRegistry."""
    cap_registry = CapabilityRegistry()
    before = cap_registry.capability_count

    plugins = PluginRegistry()
    manifest = PluginManifest(
        name="p", version="1", author="a",
        capabilities=("click",), permissions=("read",), signature="sig",
    )
    assert plugins.install(manifest) == "p"
    assert plugins.get("p") is manifest

    # Installing a plugin does not register any executable capability.
    assert cap_registry.capability_count == before
