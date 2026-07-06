"""Ch 28 — Competence package: evidence-only competence modelling.

Re-exports the public surface of the CompetenceModel (Ch 28): the model itself,
its graph node, the ``(capability, environment)`` key type, and the per-risk
confidence gate.
"""

from __future__ import annotations

from friday.competence.model import CompetenceKey, CompetenceModel, CompetenceNode

# Ch 28.11 — the per-risk confidence gate lives on the model; surface it at the
# package level for convenient import.
RISK_CONFIDENCE_GATE = CompetenceModel.RISK_CONFIDENCE_GATE

__all__ = [
    "CompetenceModel",
    "CompetenceNode",
    "CompetenceKey",
    "RISK_CONFIDENCE_GATE",
]
