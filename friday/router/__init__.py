"""Request Router — classifies intent and routes to JARVIS or FRIDAY mode.

JARVIS = Assistant Mode (fast, conversational, no agent loop)
FRIDAY = Agent Mode (perception, planning, execution, verification)

Complexity Levels:
- Level 0: Simple questions → JARVIS → Response (no planning, no verification)
- Level 1: Simple actions → FRIDAY → Action → Verify → Done
- Level 2: Multi-step tasks → FRIDAY → Mini Plan → Execute → Verify
- Level 3: Complex goals → FRIDAY → Full Agent Loop (Observe Plan Act Verify Repair)

Principle: Default to JARVIS. Use FRIDAY only when execution is required.
"""

from friday.router.classifier import RequestClassifier, ComplexityLevel, RequestMode
from friday.router.request_router import RequestRouter

__all__ = [
    "RequestClassifier",
    "ComplexityLevel",
    "RequestMode",
    "RequestRouter",
]
