"""Confirm the router now leads with a clean model for every capability, and that
a real end-to-end completion returns non-empty content fast. Diagnostic only."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001
    pass

from friday.models.router import ModelCapability, ModelRouter
from friday.models.providers.nvidia_provider import NvidiaProvider


async def main() -> int:
    router = ModelRouter()
    nvidia = NvidiaProvider()
    if not nvidia.available:
        print(f"[warn] NVIDIA unavailable: {nvidia._last_error}")
        return 1
    router.register_provider(nvidia)

    print("Primary model per capability (highest priority):")
    for cap in (
        ModelCapability.REASONING,
        ModelCapability.CODING,
        ModelCapability.CONVERSATION,
        ModelCapability.SUMMARIZATION,
        ModelCapability.CLASSIFICATION,
    ):
        best = router._best_model_for(nvidia, cap)
        print(f"  {cap.value:15s} -> {best}")

    print("\nEnd-to-end router completions (should be non-empty, fast):")
    for cap in (ModelCapability.REASONING, ModelCapability.CODING, ModelCapability.CLASSIFICATION):
        t0 = time.perf_counter()
        resp = await router.complete(
            "In one short sentence, say hello.",
            capability=cap,
            max_tokens=64,
        )
        dt = time.perf_counter() - t0
        text = (resp.text or "").replace("\n", " ")[:70]
        print(f"  {cap.value:15s} model={resp.model_used} ({dt:.1f}s) text={text!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
