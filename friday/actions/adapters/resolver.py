"""AdapterResolver — Selects the best adapter for a target at runtime.

The resolver evaluates registered adapters in priority order (highest first)
and returns the first adapter that can handle the target AND successfully
resolves the element. On re-routing after failure, callers pass an `exclude`
list to skip previously-failed adapters.

Resolution order (Resolution_Preference):
  1. BrowserAdapter         (priority 100)
  2. DesktopAdapter         (priority 80)
  3. DesktopActionsAdapter  (priority 60)
  4. VisionAdapter          (priority 30)
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from friday.actions.adapters.base import AdapterProtocol
from friday.actions.target import Target
from friday.perception.priority import ResolvedElement
from friday.perception.world_state import WorldState


class AdapterResolver:
    """Selects the best adapter for a target based on WorldState and priority.

    Resolution order (Resolution_Preference):
      1. BrowserAdapter   (priority 100)
      2. DesktopAdapter   (priority 80)
      3. DesktopActionsAdapter (priority 60)
      4. VisionAdapter    (priority 30)

    On failure, the resolver can be asked to re-resolve excluding
    previously failed adapters.
    """

    def __init__(self, adapters: List[AdapterProtocol]) -> None:
        """Initialize with a list of adapters, sorted by priority descending.

        Args:
            adapters: List of adapters implementing AdapterProtocol.
                      Will be sorted internally by priority (highest first).
        """
        self._adapters = sorted(adapters, key=lambda a: a.priority, reverse=True)

    def resolve(
        self,
        target: Target,
        world_state: WorldState,
        exclude: Optional[List[str]] = None,
    ) -> Optional[Tuple[AdapterProtocol, ResolvedElement]]:
        """Find the best adapter + resolved element for the target.

        Iterates adapters in priority order. For each eligible adapter
        (not in the exclude set), checks if it can handle the target
        and attempts to resolve the element. Returns the first successful
        (adapter, resolved_element) pair.

        Args:
            target: What to act on (semantic description).
            world_state: Current perception snapshot.
            exclude: Adapter names to skip (for re-routing after failure).

        Returns:
            Tuple of (adapter, resolved_element) if an adapter can handle
            and resolve the target, or None if no adapter succeeds.
        """
        excluded = set(exclude or [])
        for adapter in self._adapters:
            if adapter.name in excluded:
                continue
            if adapter.can_handle(target, world_state):
                element = adapter.resolve_element(target, world_state)
                if element is not None:
                    return (adapter, element)
        return None
