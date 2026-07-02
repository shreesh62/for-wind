"""Model layer — provider abstraction and intelligent routing.

Architecture: API-native, no vendor lock-in.
All model calls go through the router. Providers can be added
without modifying agent logic.

Providers:
- Groq (primary reasoning)
- NVIDIA NIM (free endpoints: vision, coding, summarization)
- Future: local models, additional APIs

Features:
- Task classification → model selection
- Automatic failover
- Rate limit handling
- Usage analytics
"""

from friday.models.router import ModelRouter, ModelCapability

__all__ = ["ModelRouter", "ModelCapability"]
