"""Ch 54 — plugin data models: manifest, load failure, loaded plugin.

A plugin is nothing more than a signed *manifest* describing the abstract
capabilities (verbs) it proposes and the permission levels it requests. It
carries no application or site names and no executable seam into a protected
subsystem — it is a pure value describing candidate capabilities that must pass
sandbox + benchmark + permission review before install.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple


@dataclass(frozen=True)
class PluginManifest:
    """Ch 54 — an externally-supplied description of proposed capabilities.

    ``capabilities`` are abstract verbs (e.g. "click", "type") — never app or
    site names (Axiom 15). ``permissions`` are requested permission levels that
    the sandbox reviews before the plugin is ever loaded.
    """

    name: str
    version: str
    author: str
    capabilities: Tuple[str, ...] = ()
    permissions: Tuple[str, ...] = ()
    signature: str = ""


@dataclass(frozen=True)
class LoadFailure:
    """Ch 54 — a manifest that was rejected before any candidate was produced."""

    manifest_name: str
    reason: str


@dataclass(frozen=True)
class LoadedPlugin:
    """Ch 54 — a successfully loaded plugin and the candidates it yielded.

    ``candidates`` are ``CapabilityCandidate``-shaped values (duck-typed to the
    M7 shape) that flow into the ``PromotionPipeline`` — never into the
    ``CapabilityRegistry`` directly.
    """

    name: str
    candidates: Tuple[Any, ...]
