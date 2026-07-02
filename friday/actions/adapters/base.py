"""AdapterProtocol — Interface that all environment adapters must satisfy.

This uses `typing.Protocol` with `@runtime_checkable` so adapters can be
verified structurally (no inheritance required). Each adapter provides:
  - Identity (name, priority)
  - Resolution (can_handle, resolve_element)
  - Async action methods (click, type_text, scroll, etc.)

All async action methods return `ActionResult` from `friday/actions/result.py`,
preserving the existing contract (Requirement 5.1, 13.1).
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from friday.actions.result import ActionResult
from friday.actions.target import Target
from friday.perception.priority import ResolvedElement
from friday.perception.world_state import WorldState


@runtime_checkable
class AdapterProtocol(Protocol):
    """Protocol that all environment adapters must satisfy.

    Adapters are selected at runtime by the AdapterResolver based on
    their `priority` and whether they `can_handle` a given Target in
    the current WorldState.

    Priority values (higher = preferred):
        BrowserAdapter:         100
        DesktopAdapter:          80
        DesktopActionsAdapter:   60
        VisionAdapter:           30
    """

    @property
    def name(self) -> str:
        """Unique adapter identifier (e.g. 'browser', 'desktop')."""
        ...

    @property
    def priority(self) -> int:
        """Numeric priority for resolution ordering (higher = preferred)."""
        ...

    def can_handle(self, target: Target, world_state: WorldState) -> bool:
        """Return True if this adapter can act on the target given current state."""
        ...

    def resolve_element(
        self, target: Target, world_state: WorldState
    ) -> Optional[ResolvedElement]:
        """Attempt to locate the target element in this adapter's environment.

        Returns a ResolvedElement if the target can be found, or None if
        this adapter cannot resolve it.
        """
        ...

    # ------------------------------------------------------------------
    # Async action methods
    # ------------------------------------------------------------------

    async def click(self, element: ResolvedElement) -> ActionResult:
        """Execute a single click on the resolved element."""
        ...

    async def double_click(self, element: ResolvedElement) -> ActionResult:
        """Execute a double click on the resolved element."""
        ...

    async def right_click(self, element: ResolvedElement) -> ActionResult:
        """Execute a right click (context menu) on the resolved element."""
        ...

    async def type_text(
        self, text: str, element: Optional[ResolvedElement] = None
    ) -> ActionResult:
        """Type text into the focused element or specified element."""
        ...

    async def press_key(self, key: str) -> ActionResult:
        """Press a single key (e.g. 'Enter', 'Tab', 'Escape')."""
        ...

    async def press_hotkey(self, keys: List[str]) -> ActionResult:
        """Press a key combination (e.g. ['ctrl', 's'])."""
        ...

    async def scroll(
        self,
        direction: str,
        amount: int,
        element: Optional[ResolvedElement] = None,
    ) -> ActionResult:
        """Scroll in the given direction by the specified amount."""
        ...

    async def drag(
        self, source: ResolvedElement, dest: ResolvedElement
    ) -> ActionResult:
        """Drag from source element to destination element."""
        ...

    async def focus_window(self, target: Target) -> ActionResult:
        """Bring a window matching the target to the foreground."""
        ...
