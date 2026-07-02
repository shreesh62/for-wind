"""Evidence collection — builds ActionEvidence from WorldState diffs.

Compares before/after WorldState snapshots to determine what changed
and whether the change matches what was expected for a given action.
"""

from __future__ import annotations

from typing import Optional

from friday.actions.result import ActionEvidence
from friday.perception.world_state import WorldState


def collect_evidence(before: WorldState, after: WorldState) -> ActionEvidence:
    """Build ActionEvidence by comparing two WorldState snapshots.

    Args:
        before: WorldState captured before the action
        after: WorldState captured after the action

    Returns:
        ActionEvidence with all detected changes
    """
    diff = after.diff_from(before)

    # Detect text that appeared
    text_appeared = _find_new_text(before, after)
    text_disappeared = _find_removed_text(before, after)

    # Detect new elements
    element_appeared = _find_new_element(before, after)

    return ActionEvidence(
        before_hash=before.state_hash,
        after_hash=after.state_hash,
        state_changed=diff.get("hash_changed", False),
        window_changed=diff.get("window_changed", False),
        url_changed=diff.get("url_changed", False),
        focus_changed=diff.get("focus_changed", False),
        text_appeared=text_appeared,
        text_disappeared=text_disappeared,
        element_appeared=element_appeared,
        screenshot_changed=diff.get("screenshot_changed", False),
        raw={
            "before_window": before.active_window.title if before.active_window else None,
            "after_window": after.active_window.title if after.active_window else None,
            "before_url": before.browser_url,
            "after_url": after.browser_url,
            "before_elements": len(before.ui_elements),
            "after_elements": len(after.ui_elements),
        },
    )


def _find_new_text(before: WorldState, after: WorldState) -> Optional[str]:
    """Find significant text that appeared in the after state."""
    before_text = set(_extract_text_fragments(before))
    after_text = set(_extract_text_fragments(after))

    new_texts = after_text - before_text
    if not new_texts:
        return None

    # Return the longest new text fragment (most informative)
    return max(new_texts, key=len)


def _find_removed_text(before: WorldState, after: WorldState) -> Optional[str]:
    """Find significant text that disappeared from the before state."""
    before_text = set(_extract_text_fragments(before))
    after_text = set(_extract_text_fragments(after))

    removed_texts = before_text - after_text
    if not removed_texts:
        return None

    return max(removed_texts, key=len)


def _find_new_element(before: WorldState, after: WorldState) -> Optional[str]:
    """Find a UI element that appeared after the action."""
    before_elements = {e.text.lower() for e in before.ui_elements if e.text}
    after_elements = {e.text.lower() for e in after.ui_elements if e.text}

    new_elements = after_elements - before_elements
    if new_elements:
        return max(new_elements, key=len)

    # Check browser elements too
    before_browser = {e.text.lower() for e in before.browser_elements if e.text}
    after_browser = {e.text.lower() for e in after.browser_elements if e.text}

    new_browser = after_browser - before_browser
    if new_browser:
        return max(new_browser, key=len)

    return None


def _extract_text_fragments(state: WorldState) -> list:
    """Extract all meaningful text fragments from a WorldState."""
    fragments = []

    for elem in state.ui_elements:
        if elem.text and len(elem.text.strip()) > 2:
            fragments.append(elem.text.strip())

    for region in state.ocr_regions:
        if region.text and len(region.text.strip()) > 2:
            fragments.append(region.text.strip())

    for elem in state.browser_elements:
        if elem.text and len(elem.text.strip()) > 2:
            fragments.append(elem.text.strip())

    return fragments
