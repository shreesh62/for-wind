"""Ch 51 — Cognitive Identity: one continuous mind across many sessions.

Re-exports the `CognitiveIdentity` that persists identity id, preferences, goal
states, and the last checkpoint reference so the operator resumes rather than
restarts across sessions and restarts.
"""

from friday.identity.identity import CognitiveIdentity

__all__ = ["CognitiveIdentity"]
