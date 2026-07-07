"""Ch 54 — the plugin loader: turn a validated manifest into candidates.

The loader is the only bridge between an external plugin and FRIDAY's competence.
It refuses unsigned or sandbox-rejected manifests, and for an accepted manifest
it emits one ``CapabilityCandidate``-shaped object per declared verb. Those
candidates flow onward through the ``PromotionPipeline`` (sandbox → benchmark →
promote) — never into the ``CapabilityRegistry`` directly.

To keep the plugins package structurally independent of the exploration engine,
the candidate shape is replicated locally (``_PluginCapabilityCandidate``) rather
than imported from ``friday.environments``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Union

from friday.plugins.manifest import LoadedPlugin, LoadFailure, PluginManifest
from friday.plugins.sandbox import PluginSandbox


@dataclass(frozen=True)
class _PluginCapabilityCandidate:
    """Ch 54 — a minimal ``CapabilityCandidate``-shaped value.

    Duck-typed to the M7 ``CapabilityCandidate`` (``proposed_id``, ``affordance``,
    ``procedure``, ``evidence_count``, ``confidence``) so the ``PromotionPipeline``
    can consume it without the plugins package depending on
    ``friday.environments``.
    """

    proposed_id: str
    affordance: Optional[Any] = None
    procedure: Optional[Any] = None
    evidence_count: int = 0
    confidence: float = 0.5


class PluginLoader:
    """Ch 54 — load a validated manifest's verbs into capability candidates."""

    def __init__(self, sandbox: PluginSandbox) -> None:
        self._sandbox = sandbox

    def load(self, manifest: PluginManifest) -> Union[LoadedPlugin, LoadFailure]:
        """Produce a ``LoadedPlugin`` of candidates, or a ``LoadFailure``.

        Rejects unsigned manifests and any manifest the sandbox refuses. For an
        accepted manifest, builds one candidate per declared verb.
        """
        if not manifest.signature:
            return LoadFailure(manifest.name, "unsigned manifest")

        ok, reason = self._sandbox.validate(manifest)
        if not ok:
            return LoadFailure(manifest.name, reason)

        candidates: List[_PluginCapabilityCandidate] = []
        for verb in manifest.capabilities:
            candidates.append(
                _PluginCapabilityCandidate(
                    proposed_id=f"plugin.{manifest.name}.{verb}",
                    affordance=None,
                    procedure=None,
                    evidence_count=0,
                    confidence=0.5,
                )
            )
        return LoadedPlugin(manifest.name, tuple(candidates))
