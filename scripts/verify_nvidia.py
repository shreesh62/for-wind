"""Live verification of NVIDIA NIM provider + model router.

Run: python scripts/verify_nvidia.py
Requires NVIDIA_API_KEY in .env.
"""

import asyncio
import sys
from pathlib import Path

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from friday.models.router import ModelRouter, ModelCapability
from friday.models.providers.nvidia_provider import NvidiaProvider
from friday.models.providers.groq_provider import GroqProvider


async def main():
    print("=" * 60)
    print("FRIDAY Model Router — Live Verification")
    print("=" * 60)

    # Initialize providers
    nvidia = NvidiaProvider()
    groq = GroqProvider()

    print(f"\nNVIDIA available: {nvidia.available}")
    print(f"Groq available: {groq.available}")

    router = ModelRouter()
    if nvidia.available:
        router.register_provider(nvidia)
        print(f"NVIDIA models: {len(nvidia.models)}")
    if groq.available:
        router.register_provider(groq)
        print(f"Groq models: {len(groq.models)}")

    print(f"\nAvailable providers: {router.get_available_providers()}")

    # Test 1: Reasoning task
    print("\n" + "-" * 60)
    print("TEST 1: Reasoning (should route to NVIDIA)")
    print("-" * 60)
    try:
        response = await router.complete(
            "In one sentence, what is the capital of France?",
            capability=ModelCapability.REASONING,
            max_tokens=50,
        )
        print(f"Provider used: {response.provider}")
        print(f"Model: {response.model_used}")
        print(f"Latency: {response.latency_ms:.0f}ms")
        print(f"Response: {response.text}")
    except Exception as exc:
        print(f"FAILED: {exc}")

    # Test 2: Conversation
    print("\n" + "-" * 60)
    print("TEST 2: Conversation")
    print("-" * 60)
    try:
        response = await router.complete(
            "Say hello in exactly 3 words.",
            capability=ModelCapability.CONVERSATION,
            max_tokens=20,
        )
        print(f"Provider used: {response.provider}")
        print(f"Response: {response.text}")
    except Exception as exc:
        print(f"FAILED: {exc}")

    # Usage stats
    print("\n" + "-" * 60)
    print("USAGE STATS")
    print("-" * 60)
    stats = router.get_usage_stats()
    print(f"Total requests: {stats.get('total_requests', 0)}")
    print(f"By provider: {stats.get('by_provider', {})}")
    print(f"Avg latency: {stats.get('avg_latency_ms', 0):.0f}ms")

    print("\n" + "=" * 60)
    print("Verification complete.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
