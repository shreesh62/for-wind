"""Bridge — connects the new friday/ architecture to the existing runtime.

This is the integration layer that allows the existing main.py and
AssistantOrchestrator to use the new FRIDAY architecture without
requiring a full rewrite.

The bridge:
1. Wraps existing AutomationServices with FridayEngine (verified actions)
2. Wraps existing groq_llm/LLM with ModelRouter (NVIDIA-first)
3. Routes via RequestRouter (JARVIS vs FRIDAY mode)
4. Preserves ALLOW_LEGACY_FALLBACK=1 behavior

Usage in main.py:
    from friday.bridge import FridayBridge

    bridge = FridayBridge(
        automation_services=automation_services,
        state_cache=awareness_controller.state_cache,
        llm_callable=query_groq,  # legacy fallback
    )

    # Replace orchestrator.process_command with:
    result = bridge.process(command, wake_word=detected_wake_word)
"""

from __future__ import annotations

import os
import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from friday.core import FridayEngine, EngineConfig
from friday.router.classifier import ComplexityLevel, RequestMode
from friday.router.request_router import RequestRouter, RouteResult
from friday.models.router import ModelCapability, ModelRouter
from friday.actions.result import ActionResult


@dataclass
class BridgeConfig:
    """Configuration for the bridge layer."""

    allow_legacy_fallback: bool = True
    use_nvidia_primary: bool = True
    verify_actions: bool = True
    allow_unverified: bool = False
    # M12: opt-in kernel-backed execution for multi-step goals. Default False
    # preserves the exact legacy Operator path (pure superset, reversible).
    use_kernel_execution: bool = False


@dataclass
class BridgeResult:
    """Unified result from the bridge, regardless of mode."""

    response: str
    mode: RequestMode
    complexity: ComplexityLevel
    handled: bool = True
    action_result: Optional[ActionResult] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class FridayBridge:
    """Bridges new friday/ architecture to existing Jarvis runtime.

    Integrates:
    - RequestRouter (JARVIS/FRIDAY mode classification)
    - FridayEngine (perception + verification for actions)
    - ModelRouter (NVIDIA-first inference)
    - Legacy fallback (existing AutomationServices + groq_llm)
    """

    def __init__(
        self,
        automation_services=None,
        state_cache=None,
        llm_callable: Optional[Callable] = None,
        model_router: Optional[ModelRouter] = None,
        config: Optional[BridgeConfig] = None,
        kernel: Optional[Any] = None,
    ) -> None:
        self._config = config or BridgeConfig(
            allow_legacy_fallback=os.getenv("ALLOW_LEGACY_FALLBACK", "1") == "1",
        )
        self._automation = automation_services
        self._state_cache = state_cache
        self._llm_callable = llm_callable
        self._model_router = model_router
        # M12: optional kernel collaborator. When present AND
        # config.use_kernel_execution is True, multi-step goals run through the
        # kernel's GoalExecutionRuntime; otherwise the legacy path is used.
        self._kernel = kernel

        # Initialize FRIDAY engine
        engine_config = EngineConfig(
            verify_all_actions=self._config.verify_actions,
            allow_unverified_success=self._config.allow_unverified,
        )
        self._engine = FridayEngine(state_cache=state_cache, config=engine_config)

        # Initialize request router
        self._router = RequestRouter(
            jarvis_handler=self._handle_jarvis,
            friday_handler=self._handle_friday,
        )

    @property
    def engine(self) -> FridayEngine:
        """Access the FRIDAY engine directly."""
        return self._engine

    @property
    def router(self) -> RequestRouter:
        """Access the request router."""
        return self._router

    def process(
        self,
        command: str,
        wake_word: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> BridgeResult:
        """Process a user command through the full JARVIS/FRIDAY pipeline.

        This is the main entry point that replaces orchestrator.process_command().

        Args:
            command: User's command text
            wake_word: Detected wake word ("jarvis" or "friday")
            context: Optional context (memory, state)

        Returns:
            BridgeResult with response and action data
        """
        ctx = context or {}
        ctx["automation"] = self._automation
        ctx["state_cache"] = self._state_cache

        route_result = self._router.route(command, wake_word=wake_word, context=ctx)

        return BridgeResult(
            response=route_result.response,
            mode=route_result.mode,
            complexity=route_result.complexity,
            handled=bool(route_result.response),
            action_result=route_result.action_result,
            metadata={
                "classification": {
                    "mode": route_result.mode.value,
                    "complexity": int(route_result.complexity),
                    "reasoning": route_result.classification.reasoning if route_result.classification else "",
                },
            },
        )

    def _handle_jarvis(self, text: str, context: Dict) -> str:
        """JARVIS mode handler — fast conversational response.

        Uses the model router (NVIDIA-first) for LLM calls.
        Prefers fast models for low latency. Falls back to legacy groq_llm.
        """
        # Try model router first (NVIDIA-primary)
        if self._model_router:
            try:
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    # Already in an async context — use thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(
                            asyncio.run,
                            self._model_router.complete(
                                text,
                                capability=ModelCapability.CONVERSATION,
                                max_tokens=512,
                                system_prompt=(
                                    "You are JARVIS, an intelligent AI assistant created by Shreesh. "
                                    "Be concise, helpful, and conversational. "
                                    "Do not perform actions — only discuss, explain, and advise."
                                ),
                            )
                        )
                        response = future.result(timeout=45)
                except RuntimeError:
                    # No running loop — safe to use asyncio.run
                    response = asyncio.run(
                        self._model_router.complete(
                            text,
                            capability=ModelCapability.CONVERSATION,
                            max_tokens=512,
                            system_prompt=(
                                "You are JARVIS, an intelligent AI assistant created by Shreesh. "
                                "Be concise, helpful, and conversational. "
                                "Do not perform actions — only discuss, explain, and advise."
                            ),
                        )
                    )
                return response.text
            except Exception:
                pass

        # Legacy fallback
        if self._llm_callable:
            try:
                return self._llm_callable(text)
            except Exception as exc:
                return f"I encountered an error: {exc}"

        return "I'm ready to help, but no language model is configured."

    def _handle_friday(
        self, text: str, context: Dict, complexity: ComplexityLevel
    ) -> Any:
        """FRIDAY mode handler — agent execution with verification.

        Routes based on complexity:
        - Level 1: Direct action via engine
        - Level 2: Mini plan via existing planner
        - Level 3: Full cognitive loop
        """
        automation = context.get("automation")

        # M12: opt-in kernel-backed execution for multi-step / complex goals.
        # Default (flag off or no kernel) keeps the exact legacy Operator path.
        kernel_execution = (
            getattr(self._config, "use_kernel_execution", False)
            and self._kernel is not None
        )

        if complexity == ComplexityLevel.SIMPLE_ACTION:
            return self._execute_simple_action(text, automation)
        elif complexity == ComplexityLevel.MULTI_STEP:
            if kernel_execution:
                return self._execute_via_kernel(text)
            return self._execute_multi_step(text, automation)
        elif complexity == ComplexityLevel.COMPLEX_GOAL:
            if kernel_execution:
                return self._execute_via_kernel(text)
            return self._execute_complex_goal(text, automation)

        # Fallback
        return self._execute_simple_action(text, automation)

    def _execute_via_kernel(self, text: str) -> str:
        """M12: run a multi-step goal through the kernel's GoalExecutionRuntime.

        Submits the goal, awaits the ``goal.completed`` / ``goal.failed``
        lifecycle event, and formats the same style of human-readable string the
        legacy path returns. Falls back to the legacy Operator path when no
        kernel is wired (never raises, never returns None).
        """
        if self._kernel is None:
            return self._execute_multi_step(text, None)

        outcome_holder: Dict[str, Any] = {}

        def _capture(event) -> None:
            payload = getattr(event, "payload", None) or {}
            if not outcome_holder:
                outcome_holder.update(
                    {"event_type": getattr(event, "event_type", ""), "payload": dict(payload)}
                )

        try:
            self._kernel.subscribe("goal.completed", _capture)
            self._kernel.subscribe("goal.failed", _capture)
            self._kernel.submit_goal(text)
        except Exception as exc:  # noqa: BLE001 — degrade to the legacy path on any wiring error
            return self._execute_multi_step(text, None)

        if not outcome_holder:
            # The runtime executes synchronously on goal.created in-process; if
            # no lifecycle event was captured, fall back to the legacy path.
            return self._execute_multi_step(text, None)

        payload = outcome_holder.get("payload", {})
        if outcome_holder.get("event_type") == "goal.completed":
            summary = payload.get("summary", "") or "Done."
            msg = f"Completed: {summary}"
            files = payload.get("created_files") or []
            if files:
                msg += f"\n\nFiles: {', '.join(files)}"
            return msg
        return f"Partial: {payload.get('error', 'goal did not complete')}"

    def _execute_simple_action(self, text: str, automation) -> Any:
        """Level 1: Single action with verification.

        Uses SystemActions (our new action layer) which doesn't require
        legacy AutomationServices. Falls back to legacy only for complex actions.
        """
        # Use FridayEngine for verified execution with SystemActions
        def action_fn():
            return self._dispatch_to_automation(text, automation)

        result = self._engine.execute_verified(
            action_fn=action_fn,
            action_type=self._infer_action_type(text),
            target=text,
        )

        if result.is_success:
            return result.message or "Done."
        elif result.needs_repair:
            # Try legacy fallback if repair fails
            if self._config.allow_legacy_fallback and automation:
                return self._legacy_execute(text, automation)
            return f"Action needs repair: {result.error}"
        else:
            return f"Action failed: {result.error}"

    def _execute_multi_step(self, text: str, automation) -> str:
        """Level 2-3: Closed-loop General Operator (ADR-021).

        Requirements Discovery → Plan → Execute → Verify → Replan.
        No workflows. Reasons about what must be true, then composes
        capabilities and self-corrects until requirements are met.
        """
        from friday.operator import Operator
        from friday.actions.browser_strategy import resolve_browser_strategy, BrowserMode

        # Decide HOW to operate the browser for THIS goal (goal-aware).
        strategy = resolve_browser_strategy(goal_text=text)

        controller = None
        if strategy.uses_cdp:
            controller = self._get_browser_controller(strategy=strategy)
            # If CDP control was wanted but unavailable AND the goal needs the
            # user's session, fall back to desktop control of the open Chrome.
            if controller is None and strategy.needs_user_session:
                strategy = strategy.__class__(
                    mode=BrowserMode.DESKTOP_CONTROL,
                    reason="CDP unavailable — switching to desktop control of "
                           "the visible Chrome to use your logged-in session",
                    needs_user_session=True,
                    profile_display_name=strategy.profile_display_name,
                )

        # DESKTOP_CONTROL: operate the already-open Chrome like a human
        # (focus window + keyboard + screen OCR), using the user's real session.
        if strategy.uses_desktop:
            try:
                from friday.actions.desktop_chrome import DesktopChromeController
                dctrl = DesktopChromeController()
                if dctrl.available and dctrl.start():
                    controller = dctrl
            except Exception as exc:
                self._last_browser_error = str(exc)

        operator = Operator(
            model_router=self._model_router,
            browser_controller=controller,
            max_iterations=2,
            browser_strategy=strategy,
        )
        outcome = operator.run(text)

        status = "Completed" if outcome.completed else "Partial"
        msg = f"{status}: {outcome.summary}"
        if strategy.uses_desktop:
            msg += f"\n\n(Operated Chrome via desktop control: {strategy.reason})"
        if outcome.created_files:
            msg += f"\n\nFiles: {', '.join(outcome.created_files)}"
        return msg

    def _get_browser_controller(self, strategy=None):
        """Get or lazily create a persistent browser controller.

        M2: prefer the user's REAL Chrome. If FRIDAY_REQUIRE_REAL_CHROME is set,
        we first ensure Chrome is running with the CDP debug port (launching it
        on the user's profile if needed) and refuse to silently fall back to a
        fresh Chromium that lacks the user's logins.
        """
        if getattr(self, '_browser_controller', None) is not None:
            if self._browser_controller.available:
                return self._browser_controller

        try:
            import os
            from friday.actions.browser_controller import BrowserController

            port = int(os.getenv("CHROME_REMOTE_DEBUG_PORT", "9222"))
            require_real = os.getenv("FRIDAY_REQUIRE_REAL_CHROME", "0") == "1"

            if require_real:
                # Make sure the real-Chrome CDP session exists before connecting.
                # The profile is resolved per-device from config (never hardcoded).
                from friday.actions.chrome_launcher import ensure_chrome_debug
                from friday.config.browser_config import resolve_browser_choice
                choice = resolve_browser_choice(use_dedicated_if_unset=True)
                launch = ensure_chrome_debug(
                    port=port,
                    user_data_dir=choice.user_data_dir,
                    profile_directory=choice.profile_directory,
                )
                if not launch.ok:
                    # Honest failure — do not fake a session.
                    self._last_browser_error = launch.error
                    return None

            controller = BrowserController(
                chrome_user_data_dir=os.getenv("JARVIS_CHROME_USER_DATA_DIR"),
                remote_debug_port=port,
                require_real_chrome=require_real,
            )
            if controller.start():
                self._browser_controller = controller
                return controller
        except Exception as exc:
            self._last_browser_error = str(exc)
        return None

    def _target_to_url(self, target: str) -> Optional[str]:
        """Resolve a target to a URL ONLY if it is already a URL/host (Axiom 15).

        No hardcoded site map: a bare app/site word resolves to ``None`` so the
        environment is discovered generically rather than looked up by
        application name (FAS Ch 39/Ch 63).
        """
        from friday.actions.url_resolve import resolve_target_url

        return resolve_target_url(target)

    def _execute_complex_goal(self, text: str, automation) -> str:
        """Level 3: Full cognitive agent loop — same operator planner as Level 2.

        Per ADR-020: No distinction between Level 2 and 3 in terms of planning.
        Both use the OperatorPlanner. Level 3 just has more steps.
        """
        return self._execute_multi_step(text, automation)

    def _legacy_execute(self, text: str, automation) -> str:
        """Fallback to legacy automation planner."""
        if automation:
            try:
                from automation.planner import AutomationPlanner
                planner = AutomationPlanner(automation)
                return planner.execute(text)
            except Exception:
                pass

        if self._llm_callable:
            return self._llm_callable(text)

        return "Could not execute command."

    def _dispatch_to_automation(self, text: str, automation) -> str:
        """Dispatch a simple action to system actions or browser session."""
        from friday.actions.system import SystemActions

        text_lower = text.lower().strip()
        sys_actions = SystemActions()

        # Open/launch app or navigate to URL
        if "open" in text_lower or "launch" in text_lower or "go to" in text_lower:
            # Check if target is a known URL/site
            url = self._target_to_url(text_lower)
            if url:
                # Use webbrowser (opens in default browser, always works)
                import webbrowser
                webbrowser.open(url)
                return f"Opened {url}"

            # Extract app name from known apps
            for app in ["chrome", "spotify", "notepad", "terminal", "explorer",
                        "edge", "firefox", "calculator", "vscode", "settings", "paint"]:
                if app in text_lower:
                    result = sys_actions.launch_app(app)
                    return result.message if result.is_success else f"Failed: {result.error}"

        # Screenshot
        if "screenshot" in text_lower:
            if automation and hasattr(automation, 'take_screenshot'):
                try:
                    return automation.take_screenshot()
                except Exception:
                    pass

        # Focus window
        if "focus" in text_lower or "switch to" in text_lower:
            target = text_lower.replace("focus", "").replace("switch to", "").strip()
            result = sys_actions.focus_window(target)
            return result.message if result.is_success else f"Failed: {result.error}"

        # Generic: try existing automation execute
        if automation and hasattr(automation, 'execute'):
            return automation.execute(text)

        return f"Executed: {text}"

    def _infer_action_type(self, text: str) -> str:
        """Infer the action type from command text."""
        text_lower = text.lower()
        if "open" in text_lower or "launch" in text_lower:
            return "open_app"
        if "click" in text_lower:
            return "click"
        if "type" in text_lower or "enter" in text_lower:
            return "type"
        if "scroll" in text_lower:
            return "scroll"
        if "focus" in text_lower or "switch" in text_lower:
            return "focus"
        if "search" in text_lower or "navigate" in text_lower:
            return "navigate"
        if "screenshot" in text_lower:
            return "screenshot"
        return "generic"
