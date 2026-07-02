"""Primitives — Universal Action Layer public API.

Every higher-level capability composes from these atomic primitives.
Callers describe WHAT (Target) and the layer resolves HOW (adapter selection).
All primitives are async and return ActionResult.

Usage:
    from friday.actions.primitives import init_primitives, click, type_text
    from friday.actions.target import Target

    init_primitives(browser_controller=my_controller)
    result = await click(Target(text="Submit"), world_state)
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable, List, Optional

from friday.actions.adapters.resolver import AdapterResolver
from friday.actions.adapters.browser import BrowserAdapter
from friday.actions.adapters.desktop import DesktopAdapter
from friday.actions.adapters.desktop_actions import DesktopActionsAdapter
from friday.actions.adapters.vision import VisionAdapter
from friday.actions.result import ActionResult, ActionEvidence, ActionTimer
from friday.actions.target import Target
from friday.perception.priority import ResolvedElement
from friday.perception.world_state import WorldState


# ---------------------------------------------------------------------------
# Module-level resolver
# ---------------------------------------------------------------------------

_resolver: Optional[AdapterResolver] = None


def init_primitives(browser_controller=None) -> None:
    """Initialize the primitive layer with all available adapters.

    Args:
        browser_controller: Optional BrowserController instance. If provided,
            the BrowserAdapter (priority 100) is registered.
    """
    global _resolver
    adapters = []
    if browser_controller:
        adapters.append(BrowserAdapter(browser_controller))
    adapters.append(DesktopAdapter())
    adapters.append(DesktopActionsAdapter())
    adapters.append(VisionAdapter())
    _resolver = AdapterResolver(adapters)


def get_resolver() -> Optional[AdapterResolver]:
    """Return the current resolver instance (None if not initialized)."""
    return _resolver


# ---------------------------------------------------------------------------
# Internal execution engine
# ---------------------------------------------------------------------------

async def _execute_with_fallback(
    action_name: str,
    target: Target,
    world_state: WorldState,
    execute_fn: Callable,
    timeout_ms: float,
) -> ActionResult:
    """Common execution pattern with adapter cascade and timeout.

    1. Start timer
    2. Loop: check elapsed time → resolve adapter → execute → on failure re-route
    3. Return ActionResult with timing and metadata
    """
    if _resolver is None:
        return ActionResult.failed(
            action=action_name,
            target=target.text,
            error="Primitive layer not initialized. Call init_primitives() first.",
            error_category="not_initialized",
            repair_hints=["call_init_primitives"],
        )

    timer = ActionTimer()
    timer.__enter__()
    excluded: List[str] = []
    max_attempts = len(_resolver._adapters)

    for _ in range(max_attempts):
        # Check timeout
        elapsed = (time.perf_counter() - timer._perf_start) * 1000
        if elapsed >= timeout_ms:
            timer.__exit__(None, None, None)
            return ActionResult.timeout(
                action=action_name,
                target=target.text,
                duration_ms=elapsed,
                started_at=timer.started_at,
                metadata={"adapters_attempted": list(excluded)},
            )

        # Resolve adapter
        resolution = _resolver.resolve(target, world_state, exclude=excluded)
        if resolution is None:
            timer.__exit__(None, None, None)
            return ActionResult.failed(
                action=action_name,
                target=target.text,
                error=f"No adapter can handle target: {target.text}",
                error_category="target_not_found",
                repair_hints=["re_observe", "scroll_to_element", "wait_for_element", "switch_window"],
                started_at=timer.started_at,
                duration_ms=(time.perf_counter() - timer._perf_start) * 1000,
                metadata={"adapters_attempted": list(excluded)},
            )

        adapter, element = resolution

        # Execute the action via the selected adapter
        try:
            result = await execute_fn(adapter, element)
        except Exception as exc:
            result = ActionResult.failed(
                action=action_name,
                target=target.text,
                error=str(exc),
                error_category="adapter_failed",
                repair_hints=["retry", "re_resolve_target", "try_alternative_adapter"],
            )

        if result.is_success:
            timer.__exit__(None, None, None)
            result.started_at = timer.started_at
            result.completed_at = timer.completed_at
            result.duration_ms = timer.duration_ms
            result.metadata["source"] = element.source.value
            result.metadata["adapter"] = adapter.name
            return result

        # Failed — exclude this adapter and try the next one
        excluded.append(adapter.name)

    # All adapters exhausted
    timer.__exit__(None, None, None)
    return ActionResult.failed(
        action=action_name,
        target=target.text,
        error=f"All adapters failed for target: {target.text}",
        error_category="target_not_found",
        repair_hints=["re_observe", "scroll_to_element", "wait_for_element", "switch_window"],
        started_at=timer.started_at,
        duration_ms=timer.duration_ms,
        metadata={"adapters_attempted": list(excluded)},
    )


# ===========================================================================
# POINTER PRIMITIVES
# ===========================================================================

async def click(
    target: Target,
    world_state: WorldState,
    *,
    timeout_ms: float = 10000,
) -> ActionResult:
    """Click a target element. Resolves environment automatically."""
    return await _execute_with_fallback(
        "click",
        target,
        world_state,
        lambda adapter, element: adapter.click(element),
        timeout_ms,
    )


async def double_click(
    target: Target,
    world_state: WorldState,
    *,
    timeout_ms: float = 10000,
) -> ActionResult:
    """Double-click a target element."""
    return await _execute_with_fallback(
        "double_click",
        target,
        world_state,
        lambda adapter, element: adapter.double_click(element),
        timeout_ms,
    )


async def right_click(
    target: Target,
    world_state: WorldState,
    *,
    timeout_ms: float = 10000,
) -> ActionResult:
    """Right-click (context menu) a target element."""
    return await _execute_with_fallback(
        "right_click",
        target,
        world_state,
        lambda adapter, element: adapter.right_click(element),
        timeout_ms,
    )


async def scroll(
    direction: str,
    amount: int,
    world_state: WorldState,
    *,
    target: Optional[Target] = None,
    timeout_ms: float = 5000,
) -> ActionResult:
    """Scroll in the given direction by the specified amount.

    Args:
        direction: "up", "down", "left", or "right"
        amount: Number of scroll units
        world_state: Current perception snapshot
        target: Optional element to scroll within. If None, scrolls at
                screen center.
        timeout_ms: Maximum execution time in milliseconds
    """
    # If no target provided, create a dummy target with screen-center coordinates
    if target is None:
        scroll_target = Target(text="scroll_viewport", coordinates=(960, 540))
    else:
        scroll_target = target

    return await _execute_with_fallback(
        "scroll",
        scroll_target,
        world_state,
        lambda adapter, element: adapter.scroll(direction, amount, element),
        timeout_ms,
    )


async def drag(
    source: Target,
    dest: Target,
    world_state: WorldState,
    *,
    timeout_ms: float = 15000,
) -> ActionResult:
    """Drag from source target to destination target.

    Resolves both source and destination targets, then executes the drag
    through whichever adapter handles the source.
    """
    if _resolver is None:
        return ActionResult.failed(
            action="drag",
            target=f"{source.text} -> {dest.text}",
            error="Primitive layer not initialized. Call init_primitives() first.",
            error_category="not_initialized",
            repair_hints=["call_init_primitives"],
        )

    timer = ActionTimer()
    timer.__enter__()

    # Resolve source target
    src_resolution = _resolver.resolve(source, world_state)
    if src_resolution is None:
        timer.__exit__(None, None, None)
        return ActionResult.failed(
            action="drag",
            target=source.text,
            error=f"Cannot resolve drag source: {source.text}",
            error_category="target_not_found",
            repair_hints=["re_observe", "scroll_to_element", "wait_for_element"],
            started_at=timer.started_at,
            duration_ms=timer.duration_ms,
        )

    src_adapter, src_element = src_resolution

    # Resolve destination target
    dest_resolution = _resolver.resolve(dest, world_state)
    if dest_resolution is None:
        timer.__exit__(None, None, None)
        return ActionResult.failed(
            action="drag",
            target=dest.text,
            error=f"Cannot resolve drag destination: {dest.text}",
            error_category="target_not_found",
            repair_hints=["re_observe", "scroll_to_element", "wait_for_element"],
            started_at=timer.started_at,
            duration_ms=timer.duration_ms,
        )

    _, dest_element = dest_resolution

    # Execute drag through the source adapter
    try:
        result = await src_adapter.drag(src_element, dest_element)
    except Exception as exc:
        timer.__exit__(None, None, None)
        return ActionResult.failed(
            action="drag",
            target=f"{source.text} -> {dest.text}",
            error=str(exc),
            error_category="adapter_failed",
            repair_hints=["retry", "re_resolve_target", "try_alternative_adapter"],
            started_at=timer.started_at,
            duration_ms=timer.duration_ms,
        )

    timer.__exit__(None, None, None)

    if result.is_success:
        result.started_at = timer.started_at
        result.completed_at = timer.completed_at
        result.duration_ms = timer.duration_ms
        result.metadata["source"] = src_element.source.value
        result.metadata["adapter"] = src_adapter.name

    return result


# ===========================================================================
# KEYBOARD PRIMITIVES
# ===========================================================================

async def type_text(
    text: str,
    world_state: WorldState,
    *,
    target: Optional[Target] = None,
    timeout_ms: float = 15000,
) -> ActionResult:
    """Type text into the focused element or a specified target.

    If no target is provided and no element is focused, returns FAILED
    with repair hints to establish focus first.
    """
    # Check focus: either we have a target to resolve, or something is focused
    if target is None:
        # No explicit target — require an existing focus
        has_focus = (
            world_state.focused_element is not None
            or world_state.browser_connected
        )
        if not has_focus:
            return ActionResult.failed(
                action="type_text",
                target=text[:50],
                error="No element is focused and no target specified",
                error_category="no_focus",
                repair_hints=["click_target_first", "focus_input", "tab_to_element"],
            )

        # Use a dummy target to route to the right adapter
        if world_state.browser_connected:
            type_target = Target(text="focused_input", selector="*:focus")
        else:
            type_target = Target(
                text="focused_element",
                coordinates=world_state.cursor_position or (960, 540),
            )
    else:
        type_target = target

    return await _execute_with_fallback(
        "type_text",
        type_target,
        world_state,
        lambda adapter, element: adapter.type_text(text, element),
        timeout_ms,
    )


async def press_key(
    key: str,
    world_state: WorldState,
    *,
    timeout_ms: float = 5000,
) -> ActionResult:
    """Press a single key (e.g. 'Enter', 'Tab', 'Escape').

    Requires that an element is focused or browser is connected.
    """
    # Focus check — same as type_text
    has_focus = (
        world_state.focused_element is not None
        or world_state.browser_connected
    )
    if not has_focus:
        return ActionResult.failed(
            action="press_key",
            target=key,
            error="No element is focused for key press",
            error_category="no_focus",
            repair_hints=["click_target_first", "focus_input", "tab_to_element"],
        )

    # Route to appropriate adapter
    if world_state.browser_connected:
        key_target = Target(text="focused_input", selector="*:focus")
    else:
        key_target = Target(
            text="focused_element",
            coordinates=world_state.cursor_position or (960, 540),
        )

    return await _execute_with_fallback(
        "press_key",
        key_target,
        world_state,
        lambda adapter, element: adapter.press_key(key),
        timeout_ms,
    )


async def press_hotkey(
    keys: List[str],
    world_state: WorldState,
    *,
    timeout_ms: float = 5000,
) -> ActionResult:
    """Press a key combination (e.g. ['ctrl', 's']).

    OS-level hotkeys do NOT require focus on a specific element.
    Uses DesktopActionsAdapter as the default handler.
    """
    # Hotkeys are OS-level — no focus check required.
    # Create a target that routes to DesktopActionsAdapter (no semantic hint).
    hotkey_target = Target(text="+".join(keys), coordinates=(0, 0))

    return await _execute_with_fallback(
        "press_hotkey",
        hotkey_target,
        world_state,
        lambda adapter, element: adapter.press_hotkey(keys),
        timeout_ms,
    )


# ===========================================================================
# ENVIRONMENT PRIMITIVES
# ===========================================================================

async def navigate(
    url: str,
    world_state: WorldState,
    *,
    timeout_ms: float = 30000,
) -> ActionResult:
    """Navigate the browser to a URL.

    If a CDP-connected BrowserAdapter is available, uses Playwright goto.
    Otherwise falls through the adapter cascade (desktop controller can
    navigate via the omnibox as keyboard input).
    """
    from friday.actions.target import Target as _T
    nav_target = _T(text=url, selector=url)  # selector doubles as URL hint

    async def _do_navigate(adapter, element):
        # If the adapter is a BrowserAdapter with a real controller, use navigate.
        controller = getattr(adapter, "_controller", None)
        if controller and hasattr(controller, "navigate"):
            result = controller.navigate(url)
            if result.get("ok"):
                return ActionResult.success(
                    action="navigate", target=url,
                    message=f"Navigated to {result.get('url', url)}",
                    evidence=ActionEvidence(
                        state_changed=True, url_changed=True,
                        raw={"url": result.get("url", url)},
                    ),
                )
            return ActionResult.failed(
                action="navigate", target=url,
                error=result.get("error", "navigation failed"),
                error_category="adapter_failed",
                repair_hints=["retry", "check_url"],
            )
        # Desktop fallback — type into the address bar.
        if hasattr(adapter, "type_text") and hasattr(adapter, "press_key"):
            await adapter.press_key("F6")  # focus omnibox (works in Chrome)
            import asyncio as _aio
            await _aio.sleep(0.2)
            await adapter.type_text(url, element)
            await adapter.press_key("Return")
            await _aio.sleep(2.0)
            return ActionResult.success(
                action="navigate", target=url,
                message=f"Navigated to {url} (desktop keyboard)",
                evidence=ActionEvidence(state_changed=True, url_changed=True),
            )
        return ActionResult.failed(
            action="navigate", target=url,
            error="No adapter could navigate",
            error_category="adapter_failed",
            repair_hints=["check_browser"],
        )

    return await _execute_with_fallback(
        "navigate", nav_target, world_state, _do_navigate, timeout_ms,
    )


async def switch_window(
    target: Target,
    world_state: WorldState,
    *,
    timeout_ms: float = 10000,
) -> ActionResult:
    """Bring a window matching the target to the foreground."""
    return await _execute_with_fallback(
        "switch_window",
        target,
        world_state,
        lambda adapter, element: adapter.focus_window(target),
        timeout_ms,
    )


async def observe(world_state: WorldState) -> ActionResult:
    """Observe the current environment state.

    Returns SUCCESS with a summary of the world state if perception
    sources are active, FAILED otherwise.
    """
    # Check that perception sources are active
    if not world_state.sources_used:
        return ActionResult.failed(
            action="observe",
            error="No perception sources active",
            error_category="perception_unavailable",
            repair_hints=["start_perception", "check_adapters", "restart_perception"],
        )

    # Check that we have meaningful data (semantic or OCR)
    has_semantic = len(world_state.browser_elements) > 0 or len(world_state.ui_elements) > 0
    has_ocr = len(world_state.ocr_regions) > 0

    if not has_semantic and not has_ocr:
        return ActionResult.failed(
            action="observe",
            error="Perception active but no semantic or OCR data available",
            error_category="perception_insufficient",
            repair_hints=["wait_for_page_load", "re_observe", "check_screen_visibility"],
        )

    # Build summary
    summary = world_state.to_summary()

    return ActionResult.success(
        action="observe",
        message="Environment observed successfully",
        evidence=ActionEvidence(
            state_changed=False,
            raw={"sources_used": [s.value for s in world_state.sources_used]},
        ),
        metadata={"world_state": summary},
    )


async def verify(condition: str, world_state: WorldState) -> ActionResult:
    """Verify that a condition holds in the current world state.

    Checks if the condition string is present in the perceivable text
    of the current world state.

    Args:
        condition: Text condition to verify (e.g. "Login successful")
        world_state: Current perception snapshot

    Returns:
        SUCCESS if condition is found, FAILED otherwise
    """
    if world_state.contains_text(condition):
        return ActionResult.success(
            action="verify",
            target=condition,
            message=f"Condition met: '{condition}' found in current state",
            evidence=ActionEvidence(
                state_changed=False,
                text_appeared=condition,
            ),
        )
    else:
        return ActionResult.failed(
            action="verify",
            target=condition,
            error=f"Condition not met: '{condition}' not found in current state",
            error_category="verification_failed",
            repair_hints=["wait_for_condition", "re_observe", "scroll_to_element"],
        )


async def wait_for(
    condition: str,
    world_state_fn: Callable[[], WorldState],
    *,
    timeout_ms: float = 30000,
    poll_interval_ms: float = 500,
) -> ActionResult:
    """Wait until a condition is met in the world state, polling periodically.

    Args:
        condition: Text condition to wait for
        world_state_fn: Callable that returns a fresh WorldState on each call
        timeout_ms: Maximum time to wait in milliseconds
        poll_interval_ms: Interval between polls in milliseconds

    Returns:
        SUCCESS if condition met before timeout, TIMEOUT otherwise
    """
    timer = ActionTimer()
    timer.__enter__()

    while True:
        # Get fresh world state
        current_ws = world_state_fn()

        # Check the condition
        if current_ws.contains_text(condition):
            timer.__exit__(None, None, None)
            return ActionResult.success(
                action="wait_for",
                target=condition,
                message=f"Condition met: '{condition}'",
                evidence=ActionEvidence(
                    state_changed=True,
                    text_appeared=condition,
                ),
                started_at=timer.started_at,
                duration_ms=timer.duration_ms,
            )

        # Check timeout
        elapsed = (time.perf_counter() - timer._perf_start) * 1000
        if elapsed >= timeout_ms:
            timer.__exit__(None, None, None)
            return ActionResult.timeout(
                action="wait_for",
                target=condition,
                duration_ms=elapsed,
                started_at=timer.started_at,
            )

        # Poll interval
        await asyncio.sleep(poll_interval_ms / 1000.0)


# ===========================================================================
# TOOL REGISTRY INTEGRATION
# ===========================================================================


def register_primitives(registry) -> None:
    """Register universal primitives with the Tool_Registry.

    These replace environment-specific tools as the preferred
    composable implementations for interaction capabilities.
    Priority 10 ensures they're preferred over environment-specific tools.
    """
    from friday.tools.registry import Tool, ToolCapability

    registry.register(Tool(
        name="universal.click",
        description="Click a target element (environment-agnostic)",
        capabilities=[ToolCapability.CLICK_ELEMENT],
        environment="any",
        priority=10,
        handler=click,
    ))
    registry.register(Tool(
        name="universal.type_text",
        description="Type text into focused element (environment-agnostic)",
        capabilities=[ToolCapability.TYPE_TEXT],
        environment="any",
        priority=10,
        handler=type_text,
    ))
    registry.register(Tool(
        name="universal.scroll",
        description="Scroll in any environment",
        capabilities=[ToolCapability.SCROLL],
        environment="any",
        priority=10,
        handler=scroll,
    ))
    registry.register(Tool(
        name="universal.switch_window",
        description="Switch to a window (environment-agnostic)",
        capabilities=[ToolCapability.SWITCH_WINDOW],
        environment="any",
        priority=10,
        handler=switch_window,
    ))
    registry.register(Tool(
        name="universal.verify",
        description="Verify a condition in the current environment",
        capabilities=[ToolCapability.VERIFY_RESULT],
        environment="any",
        priority=10,
        handler=verify,
    ))
    registry.register(Tool(
        name="universal.observe",
        description="Observe current environment state",
        capabilities=[ToolCapability.READ_SCREEN],
        environment="any",
        priority=10,
        handler=observe,
    ))
    registry.register(Tool(
        name="universal.navigate",
        description="Navigate the browser to a URL (environment-agnostic)",
        capabilities=[ToolCapability.NAVIGATE_URL],
        environment="any",
        priority=10,
        handler=navigate,
    ))
