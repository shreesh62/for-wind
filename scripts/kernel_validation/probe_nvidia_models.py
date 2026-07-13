"""Ad-hoc latency probe: which NVIDIA NIM models actually answer right now?

Sends a tiny prompt to each candidate model with a short per-model timeout and
prints latency + a snippet of the response (or the failure). Diagnostic only —
records nothing, changes no defaults.

Usage (real machine, from repo root):
    python scripts/kernel_validation/probe_nvidia_models.py
"""

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

from friday.models.providers.nvidia_provider import NvidiaConfig, NvidiaProvider

# The models the router actually uses for the general reasoning/coding/prose path.
CANDIDATES = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "mistralai/mistral-medium-3.5-128b",
    "qwen/qwen3.5-397b-a17b",
    "nvidia/nemotron-mini-4b-instruct",
]

PER_MODEL_TIMEOUT = 25.0


async def probe_one(provider: NvidiaProvider, model: str) -> None:
    print(f"  [probe] {model} ... ", end="", flush=True)
    t0 = time.perf_counter()
    try:
        resp = await asyncio.wait_for(
            provider.complete(
                "Reply with exactly: OK",
                model=model,
                max_tokens=16,
                temperature=0.0,
            ),
            timeout=PER_MODEL_TIMEOUT,
        )
        dt = time.perf_counter() - t0
        snippet = (resp.text or "").replace("\n", " ")[:60]
        status = "OK" if snippet.strip() else "EMPTY-CONTENT"
        print(f"{status} ({dt:.1f}s) tokens={resp.tokens_used} text={snippet!r}", flush=True)
    except asyncio.TimeoutError:
        dt = time.perf_counter() - t0
        print(f"TIMEOUT (>{PER_MODEL_TIMEOUT:.0f}s)", flush=True)
    except Exception as exc:  # noqa: BLE001
        dt = time.perf_counter() - t0
        print(f"ERROR ({dt:.1f}s): {type(exc).__name__}: {str(exc)[:120]}", flush=True)


async def main() -> int:
    # Short client timeout so a wedged call fails fast instead of 60s x 2 retries.
    provider = NvidiaProvider(NvidiaConfig(timeout=20.0, max_retries=1))
    if not provider.available:
        print(f"[warn] NVIDIA provider unavailable: {provider._last_error}")
        return 1
    print(f"[ok] NVIDIA provider available. Probing {len(CANDIDATES)} models "
          f"(per-model timeout {PER_MODEL_TIMEOUT:.0f}s)\n")
    for model in CANDIDATES:
        await probe_one(provider, model)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
