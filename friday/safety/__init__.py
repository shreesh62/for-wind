"""Ch 35 — Safety & Permission: the constitutional boundary around cognition.

Re-exports the public safety surface: the `PermissionManager` (nine permission
levels + five trust zones), the immutable `SafetyPolicy` (hard boundaries +
confirmation rules), and the `SecretVault` (secrets by key name, never echoed).
Every risky action is gated here (Constitution Article IX).
"""

from friday.safety.permission import (
    Decision,
    PermissionLevel,
    PermissionManager,
    PermissionRequest,
    PermissionVerdict,
    TrustZone,
)
from friday.safety.action_gate import (
    ActionGate,
    GateDecision,
    classify_capability,
)
from friday.safety.policy import SafetyPolicy
from friday.safety.vault import SecretVault

__all__ = [
    "Decision",
    "PermissionLevel",
    "PermissionManager",
    "PermissionRequest",
    "PermissionVerdict",
    "TrustZone",
    "SafetyPolicy",
    "SecretVault",
    "ActionGate",
    "GateDecision",
    "classify_capability",
]
