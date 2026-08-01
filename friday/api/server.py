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
    import sys as _sys
    # Windows consoles default to cp1252 which cannot encode the ✓/⚠ chars used in
    # startup messages. Reconfigure once at app creation rather than requiring every
    # caller to do it.
    try:
        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - not all streams support reconfigure
        pass

    from dotenv import load_dotenv
    load_dotenv()

    # TD-9: migrate API keys off repeated plaintext .env reads into the vault.
    # After seeding, providers resolve credentials via the SecretVault (env
    # remains a transparent fallback for anything not seeded).
    from friday.models.credentials import seed_vault_from_env
    seeded = seed_vault_from_env(
        ("NVIDIA_API_KEY", "GROQ_API_KEY", "REMOTE_API_KEY")
    )
    if seeded:
        print(f"[✓] Vault: {seeded} secret(s) migrated from environment")

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

    # M12: opt-in kernel-backed execution. Default (flag unset) constructs the
    # bridge exactly as before. When FRIDAY_USE_KERNEL_EXECUTION=1, build a real
    # kernel + GoalExecutionRuntime (delegating to the proven Operator) and wire
    # it into the bridge. The whole block is guarded so a wiring failure falls
    # back to the legacy bridge and never prevents the server from starting.
    from friday.bridge import BridgeConfig

    kernel = None
    use_kernel = os.getenv("FRIDAY_USE_KERNEL_EXECUTION") == "1"
    if use_kernel:
        try:
            from friday.kernel.kernel import CognitiveKernel
            from friday.kernel.execution import GoalExecutionRuntime
            from friday.kernel.memory_sink import MemorySink
            from friday.operator import Operator

            kernel = CognitiveKernel()

            # M24 activation: wire the failure→recovery/competence/reflection/
            # observability loop to this kernel so requirement verdicts published by
            # the Operator (below, with kernel=kernel) actually drive recovery,
            # competence updates, reflection, and structured failure logs. Guarded:
            # a wiring failure must not prevent the server from starting.
            failure_memory = None
            # M21 (C5 / Req 6.2): the two new bounded tiers are wired opt-in in the
            # same reactive-loop try below and reused by the retrieval router. Hoist
            # them here (like `failure_memory`) so they stay in scope for the router
            # call even if it lives in a separate try block; default None means "not
            # attached" (mirrors how the loop treats absent tiers).
            capability_memory = None
            preference_memory = None
            try:
                from friday.kernel.reactive_loop import attach_reactive_loop
                from friday.memory.failure_memory import FailureMemory
                from friday.memory.capability_memory import CapabilityMemory
                from friday.memory.preference_memory import PreferenceMemory
                # Persistent failure memory (bounded) consumes the loop so past
                # failures + their recoveries inform future planning. Kept in a
                # local so the M19 Retrieval Router (below) can reuse the very same
                # bounded instance as its FAILURE-tier source.
                failure_memory = FailureMemory()
                # M21 seven-tier completion: the CAPABILITY and PREFERENCE tiers are
                # bounded (JSONFileStore, default paths under friday_data/) exactly
                # like FailureMemory above. Constructed here and reused as the
                # CAPABILITY-/PREFERENCE-tier sources by the router below.
                capability_memory = CapabilityMemory()
                preference_memory = PreferenceMemory()
                attach_reactive_loop(
                    kernel,
                    failure_memory=failure_memory,
                    capability_memory=capability_memory,
                    preference_memory=preference_memory,
                )
                print("[✓] Kernel: reactive loop active "
                      "(recovery/competence/reflection/failure-memory"
                      "/capability-memory/preference-memory)")
            except Exception as exc:  # noqa: BLE001 - loop wiring is best-effort
                print(f"[⚠] Kernel: reactive loop wiring skipped: {exc}")
                failure_memory = None
                capability_memory = None
                preference_memory = None

            # M19 (A2.7): build the Retrieval Router over FridayMemory's persistent
            # tiers, reusing the bounded FailureMemory above as the FAILURE-tier
            # source, and expose it on the kernel so planning can route retrieval
            # across tiers. Guarded so a wiring failure degrades safely (the router
            # is simply absent) without crashing bootstrap — structured logging on
            # failure rather than a silent swallow (A2.14.2 / Requirement 7.2).
            try:
                from friday.memory.controller import build_retrieval_router
                kernel.retrieval_router = build_retrieval_router(
                    friday_memory,
                    failure_memory=failure_memory,
                    capability_memory=capability_memory,
                    preference_memory=preference_memory,
                )
                print(
                    "[✓] Kernel: retrieval router active "
                    f"({kernel.retrieval_router.source_count} sources, "
                    f"tiers={[t.value for t in kernel.retrieval_router.tiers()]})"
                )
            except Exception as exc:  # noqa: BLE001 - router wiring is best-effort
                # Deliberate degradation boundary: retrieval routing is additive, so
                # any construction failure must not prevent the server from starting.
                # Log with structured context instead of swallowing silently.
                print(
                    "[⚠] Kernel: retrieval router wiring skipped "
                    f"(planning falls back to direct tier access): {exc!r}"
                )

            # M20 (A2.10): attach the three higher reflection layers (Long-Term,
            # Skill, Architectural) as pure consumers of the `reflection.completed`
            # stream emitted by the reactive loop's ReflectionEngine (wired above).
            # They only emit JSON-safe `reflection.*` proposal events — never memory
            # writes. Expose the holder on the kernel (consistent with the retrieval
            # router). Guarded so a wiring failure degrades safely (the layers are
            # simply absent) without crashing bootstrap — structured logging on
            # failure rather than a silent swallow (A2.14.2 / Requirement 7.2).
            try:
                from friday.cognition.reflection_layers import attach_reflection_layers
                kernel.reflection_layers = attach_reflection_layers(kernel)
                print(
                    "[✓] Kernel: reflection layers active "
                    "(long-term/skill/architectural proposals)"
                )
            except Exception as exc:  # noqa: BLE001 - layer wiring is best-effort
                # Deliberate degradation boundary: layered reflection is additive, so
                # any wiring failure must not prevent the server from starting. Log
                # with structured context instead of swallowing silently.
                print(
                    "[⚠] Kernel: reflection layers wiring skipped "
                    f"(higher-layer proposals disabled): {exc!r}"
                )

            # M17 (C5 / Req 5.2, 5.3): attach the SkillEvolutionPipeline as a pure
            # coordinator over signals that already flow on the bus — M20's
            # `reflection.skill` (emitted by the reflection layers wired just above)
            # and M9's `learning.validated` (emitted by a LearningEngine on the
            # reactive loop). It tracks each skill's stage and emits a single
            # deduplicated `skill.candidate` proposal once a skill carries BOTH
            # signals; it never writes memory or self-promotes. Attach it AFTER the
            # reflection layers so its `reflection.skill` source is already live.
            # Exposed on the kernel as `kernel.skill_pipeline` (consistent with the
            # retrieval router / reflection layers). Guarded so a wiring failure
            # degrades safely (the pipeline is simply absent) without crashing
            # bootstrap — structured logging on failure rather than a silent swallow
            # (A2.14.2 / Requirement 7.2).
            try:
                from friday.learning.skill_pipeline import attach_skill_pipeline
                kernel.skill_pipeline = attach_skill_pipeline(kernel)
                print(
                    "[✓] Kernel: skill evolution pipeline active "
                    "(reflection.skill + learning.validated → skill.candidate)"
                )
            except Exception as exc:  # noqa: BLE001 - pipeline wiring is best-effort
                # Deliberate degradation boundary: skill evolution is additive, so any
                # wiring failure must not prevent the server from starting. Log with
                # structured context instead of swallowing silently.
                print(
                    "[⚠] Kernel: skill evolution pipeline wiring skipped "
                    f"(skill.candidate proposals disabled): {exc!r}"
                )

            # M15 (A2.2): attach the Environment Intelligence fingerprint monitor and
            # expose it on the kernel so the executor's perception cycle can call
            # `kernel.fingerprint_monitor.observe(env_key, world_state)` to detect
            # environment/UI changes and emit `environment.*` invalidation events
            # (never silently wrong — a change makes FRIDAY re-explore). Guarded so a
            # wiring failure degrades safely (the monitor is simply absent) without
            # crashing bootstrap — structured logging on failure rather than a silent
            # swallow (A2.14.2 / Requirement 7.2).
            try:
                from friday.perception.fingerprint_monitor import attach_fingerprint_monitor
                kernel.fingerprint_monitor = attach_fingerprint_monitor(kernel)
                print(
                    "[✓] Kernel: environment fingerprint monitor active "
                    "(environment/UI change detection → capability invalidation)"
                )
            except Exception as exc:  # noqa: BLE001 - monitor wiring is best-effort
                # Deliberate degradation boundary: the fingerprint monitor is additive,
                # so any wiring failure must not prevent the server from starting. Log
                # with structured context instead of swallowing silently.
                print(
                    "[⚠] Kernel: environment fingerprint monitor wiring skipped "
                    f"(environment-change invalidation disabled): {exc!r}"
                )

            # M22 (A2.12 / C5, Req 5.2, 5.3): attach the Cognitive State Manager —
            # the capstone mind-state coordinator. It subscribes to generic signals
            # already on the bus (goal.state_changed / action.executed / goal.created
            # / observation.received / reflection.completed) to track engagement mode,
            # focus, cognitive load, and background cognition, and exposes pure query
            # reads (should_interrupt / suggested_thinking_depth) for the Event System
            # and Deliberation. It imports only friday.events + stdlib, writes no
            # memory, and its handlers never raise into the tick loop. Exposed on the
            # kernel as `kernel.cognitive_state` (consistent with the retrieval router
            # / reflection layers / skill pipeline). Guarded so a wiring failure
            # degrades safely (the manager is simply absent) without crashing
            # bootstrap — structured logging on failure rather than a silent swallow
            # (A2.14.2 / Requirement 5.2).
            try:
                from friday.cognition.state import CognitiveStateManager
                kernel.cognitive_state = CognitiveStateManager()
                kernel.cognitive_state.attach(kernel)
                print(
                    "[✓] Kernel: cognitive state manager active "
                    "(mode/focus/load/background → should_interrupt/thinking_depth)"
                )
            except Exception as exc:  # noqa: BLE001 - manager wiring is best-effort
                # Deliberate degradation boundary: the cognitive state manager is
                # additive, so any wiring failure must not prevent the server from
                # starting. Log with structured context instead of swallowing silently.
                print(
                    "[⚠] Kernel: cognitive state manager wiring skipped "
                    f"(mind-state queries disabled): {exc!r}"
                )

            # M25 (A2.15): attach the PreferenceResolver — the preference
            # resolution pipeline coordinator. It subscribes to `decision.required`
            # (emitted by the executor/deliberation when the World Model shows
            # multiple actionable options requiring user preference), queries the
            # existing Preference Memory via the Retrieval Router, evaluates
            # contextual confidence + reversibility + freshness, and either applies
            # a preference autonomously or escalates to the user. It emits
            # `decision.resolved` and `preference.*` lifecycle events. Guarded so a
            # wiring failure degrades safely (the resolver is simply absent) without
            # crashing bootstrap — structured logging on failure rather than a
            # silent swallow (A2.14.2 / Requirement 10.3).
            try:
                from friday.deliberation.preference_resolver import attach_preference_resolver
                kernel.preference_resolver = attach_preference_resolver(
                    kernel,
                    preference_memory=preference_memory,
                    retrieval_router=getattr(kernel, "retrieval_router", None),
                    cognitive_state=getattr(kernel, "cognitive_state", None),
                    failure_memory=failure_memory,
                )
                print(
                    "[✓] Kernel: preference resolver active "
                    "(decision.required → resolve → preference lifecycle events)"
                )
            except Exception as exc:  # noqa: BLE001 - resolver wiring is best-effort
                # Deliberate degradation boundary: preference resolution is additive,
                # so any wiring failure must not prevent the server from starting.
                # Log with structured context instead of swallowing silently.
                print(
                    "[⚠] Kernel: preference resolver wiring skipped "
                    f"(learned-choice resolution disabled): {exc!r}"
                )

            def _operator_factory(goal_text: str):
                # Pass the kernel so the Operator publishes verification.completed
                # verdicts into the now-wired reactive loop, and memory so the
                # Operator recalls prior context instead of restarting from zero.
                return Operator(
                    model_router=model_router,
                    max_iterations=2,
                    kernel=kernel,
                    memory=friday_memory,
                )

            runtime = GoalExecutionRuntime(
                _operator_factory,
                memory_sink=MemorySink(friday_memory),
            )
            kernel.register_runtime(runtime)
            kernel.start()
            print("[✓] Kernel: goal_execution runtime active (kernel-backed execution)")
        except Exception as exc:
            print(f"[⚠] Kernel execution wiring failed, using legacy path: {exc}")
            kernel = None
            use_kernel = False

    bridge = FridayBridge(
        automation_services=None,
        state_cache=None,
        llm_callable=None,
        model_router=model_router,
        config=BridgeConfig(
            allow_legacy_fallback=False,
            use_kernel_execution=use_kernel,
        ),
        kernel=kernel,
        memory=friday_memory,
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
