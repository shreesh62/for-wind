"""Browser perception adapter — bridges DevTools/Playwright to FRIDAY types.

Connects the existing browser_state_tracker and devtools_bridge to the new
WorldStateBuilder by converting browser DOM state to BrowserElement objects.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from friday.perception.types import BoundingBox, BrowserElement, PerceptionSource


class BrowserPerception:
    """Adapts browser state into FRIDAY perception types.

    Bridges the existing:
    - awareness.state_cache browser summary
    - automation.devtools_bridge DOM inspection
    - automation.browser_state_tracker events

    Usage:
        perception = BrowserPerception(state_cache=awareness_controller.state_cache)
        url = perception.get_current_url()
        title = perception.get_page_title()
        elements = perception.get_visible_elements()
    """

    def __init__(self, state_cache=None) -> None:
        """Initialize with optional state cache.

        Args:
            state_cache: The existing awareness.state_cache.StateCache instance
        """
        self._state_cache = state_cache

    @property
    def available(self) -> bool:
        """Whether browser perception is available."""
        if not self._state_cache:
            return False
        try:
            summary = self._state_cache.get_browser_summary()
            return summary is not None
        except Exception:
            return False

    @property
    def connected(self) -> bool:
        """Whether we have an active browser connection."""
        return self.available

    def get_current_url(self) -> Optional[str]:
        """Get the URL of the active browser tab.

        Returns:
            URL string or None
        """
        summary = self._get_summary()
        if not summary:
            return None
        return summary.get('url') or summary.get('tab_url')

    def get_page_title(self) -> Optional[str]:
        """Get the title of the active browser tab.

        Returns:
            Title string or None
        """
        summary = self._get_summary()
        if not summary:
            return None
        return summary.get('title') or summary.get('tab_title')

    def get_visible_elements(self) -> List[BrowserElement]:
        """Get visible DOM elements from the browser state.

        Converts the DOM summary from the state cache into BrowserElement objects.

        Returns:
            List of BrowserElement objects
        """
        summary = self._get_summary()
        if not summary:
            return []

        elements: List[BrowserElement] = []

        # Extract from DOM elements list if available
        dom_elements = summary.get('elements', []) or summary.get('dom_elements', [])
        if isinstance(dom_elements, list):
            for raw in dom_elements:
                elem = self._convert_dom_element(raw)
                if elem:
                    elements.append(elem)

        # Extract from links
        links = summary.get('links', [])
        if isinstance(links, list):
            for link in links:
                if isinstance(link, str):
                    elements.append(BrowserElement(
                        tag="a",
                        text=link,
                        role="link",
                        clickable=True,
                        source=PerceptionSource.BROWSER,
                    ))
                elif isinstance(link, dict):
                    elements.append(BrowserElement(
                        tag="a",
                        text=link.get('text', ''),
                        role="link",
                        clickable=True,
                        attributes={"href": link.get('href', '')},
                        source=PerceptionSource.BROWSER,
                    ))

        # Extract from buttons
        buttons = summary.get('buttons', [])
        if isinstance(buttons, list):
            for btn in buttons:
                if isinstance(btn, str):
                    elements.append(BrowserElement(
                        tag="button",
                        text=btn,
                        role="button",
                        clickable=True,
                        source=PerceptionSource.BROWSER,
                    ))
                elif isinstance(btn, dict):
                    elements.append(BrowserElement(
                        tag="button",
                        text=btn.get('text', ''),
                        role="button",
                        clickable=True,
                        source=PerceptionSource.BROWSER,
                    ))

        # Extract from inputs
        inputs = summary.get('inputs', []) or summary.get('forms', [])
        if isinstance(inputs, list):
            for inp in inputs:
                if isinstance(inp, dict):
                    elements.append(BrowserElement(
                        tag="input",
                        text=inp.get('placeholder', '') or inp.get('label', ''),
                        role=inp.get('type', 'textbox'),
                        clickable=True,
                        attributes=inp,
                        source=PerceptionSource.BROWSER,
                    ))

        return elements

    def get_page_text(self) -> str:
        """Get the text content of the active page.

        Returns:
            Page text or empty string
        """
        summary = self._get_summary()
        if not summary:
            return ""
        return summary.get('text', '') or summary.get('page_text', '') or ''

    def get_hints(self) -> Dict[str, bool]:
        """Get browser awareness hints (login, error, consent, etc).

        Returns:
            Dict of hint flags
        """
        summary = self._get_summary()
        if not summary:
            return {}

        hints = summary.get('hints', {})
        if isinstance(hints, dict):
            return {k: bool(v) for k, v in hints.items()}
        return {}

    def _get_summary(self) -> Optional[Dict]:
        """Get current browser summary from state cache."""
        if not self._state_cache:
            return None
        try:
            summary = self._state_cache.get_browser_summary()
            if isinstance(summary, dict):
                return summary
            return None
        except Exception:
            return None

    def _convert_dom_element(self, raw) -> Optional[BrowserElement]:
        """Convert a raw DOM element dict to BrowserElement."""
        try:
            if isinstance(raw, dict):
                tag = raw.get('tag', '') or raw.get('tagName', '') or ''
                text = raw.get('text', '') or raw.get('innerText', '') or ''
                role = raw.get('role', '') or raw.get('ariaRole', '') or tag
                clickable = bool(raw.get('clickable', False))

                # Determine if clickable from tag type
                if tag.lower() in ('a', 'button', 'input', 'select', 'textarea'):
                    clickable = True

                bbox = None
                bbox_data = raw.get('bbox') or raw.get('boundingBox')
                if bbox_data and len(bbox_data) == 4:
                    bbox = BoundingBox(
                        x=int(bbox_data[0]),
                        y=int(bbox_data[1]),
                        width=int(bbox_data[2]),
                        height=int(bbox_data[3]),
                    )

                return BrowserElement(
                    tag=tag,
                    text=text,
                    role=role,
                    clickable=clickable,
                    visible=bool(raw.get('visible', True)),
                    bbox=bbox,
                    attributes={k: v for k, v in raw.items()
                               if k not in ('tag', 'text', 'role', 'clickable', 'visible', 'bbox')},
                    selector=raw.get('selector', '') or '',
                    source=PerceptionSource.BROWSER,
                )
            return None
        except Exception:
            return None
