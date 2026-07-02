"""FRIDAY API Server — standalone launcher for the FRIDAY API.

This can run independently of the legacy main.py, serving the
FRIDAY API at localhost for the Tauri desktop app and mobile.

Usage:
    python -m friday.api.server

Or programmatically:
    from friday.api.server import start_server
    start_server()
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def create_app():
    """Create the FRIDAY API app with all dependencies wired."""
    from dotenv import load_dotenv
    load_dotenv()

    from friday.api.app import create_friday_api
    from friday.bridge import FridayBridge
    from friday.memory import FridayMemory
    from friday.models.router import ModelRouter
    from friday.models.providers.nvidia_provider import NvidiaProvider
    from friday.models.providers.groq_provider import GroqProvider

    # Initialize model router
    model_router = ModelRouter()
    nvidia = NvidiaProvider()
    groq = GroqProvider()
    if nvidia.available:
        model_router.register_provider(nvidia)
        print(f"[✓] NVIDIA NIM: {len(nvidia.models)} models")
    if groq.available:
        model_router.register_provider(groq)
        print(f"[✓] Groq: {len(groq.models)} models (fallback)")

    if not model_router.get_available_providers():
        print("[⚠] No model providers available. Set NVIDIA_API_KEY or GROQ_API_KEY in .env")

    # Initialize memory (with NVIDIA embeddings for semantic tier)
    embedding_provider = nvidia if nvidia.available else None
    friday_memory = FridayMemory(
        data_dir="friday_data",
        embedding_provider=embedding_provider,
    )
    stats = friday_memory.get_statistics()
    print(f"[✓] Memory: {stats['episodic']['total_episodes']} episodes, "
          f"{stats['semantic']['total_facts']} facts, "
          f"embeddings={'on' if stats['semantic']['has_embeddings'] else 'off'}")

    # Initialize Playwright browser session for FRIDAY actions
    playwright_manager = None
    try:
        from automation.playwright_manager import PlaywrightManager
        playwright_manager = PlaywrightManager(
            "friday_session",
            headless=False,
            use_chrome_profile=True,
            chrome_profile="Default",
            auto_launch=True,
        )
        # Ensure Chrome is running with debug port
        if playwright_manager.ensure_chrome_remote_debug():
            print("[✓] Browser: Chrome connected (remote debug)")
        else:
            print("[⚠] Browser: Chrome not available (actions limited)")
            playwright_manager = None
    except Exception as exc:
        print(f"[⚠] Browser: {exc}")

    # Initialize bridge with browser session available
    from friday.bridge import BridgeConfig
    bridge = FridayBridge(
        automation_services=None,
        state_cache=None,
        llm_callable=None,
        model_router=model_router,
        config=BridgeConfig(allow_legacy_fallback=False),
    )

    # Attach the playwright manager to bridge for Level 2+ tasks
    if playwright_manager:
        bridge._playwright_manager = playwright_manager

    print("[✓] Bridge: JARVIS/FRIDAY routing active")

    # Create API
    api_key = os.getenv("REMOTE_API_KEY", "")
    app = create_friday_api(
        bridge=bridge,
        memory=friday_memory,
        model_router=model_router,
        api_key=api_key,
    )
    print(f"[✓] API: ready (auth={'enabled' if api_key else 'disabled'})")

    return app


def start_server(host: str = "127.0.0.1", port: int = 8801):
    """Start the FRIDAY API server."""
    import uvicorn

    print("=" * 50)
    print("  FRIDAY API Server")
    print("=" * 50)
    print()

    app = create_app()

    print()
    print(f"[🌐] Starting at http://{host}:{port}")
    print(f"[📖] Docs at http://{host}:{port}/docs")
    print()

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    host = os.getenv("FRIDAY_HOST", "127.0.0.1")
    port = int(os.getenv("FRIDAY_PORT", "8801"))
    start_server(host=host, port=port)
