"""Browser session — real Playwright interaction for FRIDAY agent mode.

Wraps the existing PlaywrightManager to provide high-level browser
operations that return ActionResult. Uses the user's real Chrome profile
(persistent login state for Instagram, WhatsApp, Gmail, etc).

Follows ADR-014: DOM-first. All element finding uses Playwright selectors
and page.query_selector, not screenshots.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from friday.actions.result import ActionResult, ActionEvidence, ActionTimer


class BrowserSession:
    """Real browser interaction via Playwright returning ActionResult.

    Connects to the user's Chrome profile (persistent logins).
    All operations are DOM-first (ADR-014).

    Usage:
        session = BrowserSession()
        result = await session.navigate("https://instagram.com/direct/inbox")
        result = await session.get_page_text()
        result = await session.click("Messages")
    """

    def __init__(self, playwright_manager=None) -> None:
        """Initialize with an existing PlaywrightManager or create one.

        Args:
            playwright_manager: Existing PlaywrightManager instance.
                If None, creates one on first use.
        """
        self._pw_manager = playwright_manager
        self._initialized = False

    def _get_manager(self):
        """Lazily initialize PlaywrightManager, ensuring Chrome debug port."""
        if self._pw_manager is None:
            try:
                from automation.playwright_manager import PlaywrightManager
                self._pw_manager = PlaywrightManager(
                    "friday_browser",
                    headless=False,
                    use_chrome_profile=True,
                    chrome_profile="Default",
                    auto_launch=True,
                )
                # Ensure Chrome is running with remote debugging
                self._pw_manager.ensure_chrome_remote_debug()
                self._initialized = True
            except Exception as exc:
                raise RuntimeError(f"Cannot initialize Playwright: {exc}")
        return self._pw_manager

    @property
    def available(self) -> bool:
        """Whether Playwright browser session is available."""
        try:
            self._get_manager()
            return True
        except Exception:
            return False

    async def navigate(self, url: str) -> ActionResult:
        """Navigate to a URL using Playwright (DOM-based, not address bar).

        Args:
            url: Target URL

        Returns:
            ActionResult with URL change evidence
        """
        with ActionTimer() as timer:
            try:
                manager = self._get_manager()
                async with manager.session() as page:
                    before_url = page.url
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    after_url = page.url

                    return ActionResult.success(
                        action="navigate",
                        target=url,
                        message=f"Navigated to {after_url}",
                        evidence=ActionEvidence(
                            before_hash=before_url[:16] if before_url else "",
                            after_hash=after_url[:16] if after_url else "",
                            url_changed=before_url != after_url,
                            state_changed=True,
                            raw={"before_url": before_url, "after_url": after_url},
                        ),
                        started_at=timer.started_at,
                        duration_ms=timer.duration_ms,
                    )
            except Exception as exc:
                return ActionResult.failed(
                    action="navigate",
                    error=str(exc),
                    target=url,
                    error_category="navigation_error",
                    repair_hints=["check_url", "check_browser_open", "retry"],
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

    async def click(self, text: str, selector: Optional[str] = None) -> ActionResult:
        """Click an element by text or selector (DOM-first).

        Args:
            text: Visible text of the element to click
            selector: Optional CSS/XPath selector (preferred if known)

        Returns:
            ActionResult
        """
        with ActionTimer() as timer:
            try:
                manager = self._get_manager()
                async with manager.session() as page:
                    before_url = page.url

                    if selector:
                        await page.click(selector, timeout=10000)
                    else:
                        # DOM-first: find by text content
                        element = page.get_by_text(text, exact=False).first
                        await element.click(timeout=10000)

                    # Brief wait for state to settle
                    await page.wait_for_timeout(500)
                    after_url = page.url

                    return ActionResult.success(
                        action="click",
                        target=text,
                        message=f"Clicked '{text}'",
                        evidence=ActionEvidence(
                            state_changed=True,
                            url_changed=before_url != after_url,
                            raw={"before_url": before_url, "after_url": after_url},
                        ),
                        started_at=timer.started_at,
                        duration_ms=timer.duration_ms,
                    )
            except Exception as exc:
                return ActionResult.failed(
                    action="click",
                    error=str(exc),
                    target=text,
                    error_category="click_error",
                    repair_hints=["scroll_to_element", "wait_for_element", "try_selector"],
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

    async def type_text(self, text: str, selector: Optional[str] = None, field_label: str = "") -> ActionResult:
        """Type text into an input field (DOM-targeted).

        Args:
            text: Text to type
            selector: CSS selector for the input (preferred)
            field_label: Visible label/placeholder text for the field
        """
        with ActionTimer() as timer:
            try:
                manager = self._get_manager()
                async with manager.session() as page:
                    if selector:
                        await page.fill(selector, text, timeout=10000)
                    elif field_label:
                        await page.get_by_placeholder(field_label).fill(text, timeout=10000)
                    else:
                        # Type into currently focused element
                        await page.keyboard.type(text)

                    return ActionResult.success(
                        action="type",
                        target=field_label or selector or "input",
                        message=f"Typed text into {field_label or 'field'}",
                        evidence=ActionEvidence(
                            state_changed=True,
                            text_appeared=text[:50],
                        ),
                        started_at=timer.started_at,
                        duration_ms=timer.duration_ms,
                    )
            except Exception as exc:
                return ActionResult.failed(
                    action="type",
                    error=str(exc),
                    target=field_label or "input",
                    error_category="type_error",
                    repair_hints=["click_field_first", "check_selector"],
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

    async def get_page_text(self) -> ActionResult:
        """Extract the visible text content of the current page (DOM-first).

        Returns:
            ActionResult with the page text in the message field
        """
        with ActionTimer() as timer:
            try:
                manager = self._get_manager()
                async with manager.session() as page:
                    # Get all visible text content via DOM
                    text = await page.inner_text("body")
                    url = page.url
                    title = await page.title()

                    # Truncate for response
                    truncated = text[:3000] if text else ""

                    return ActionResult.success(
                        action="read_page",
                        target=url,
                        message=truncated,
                        evidence=ActionEvidence(
                            state_changed=False,
                            raw={"url": url, "title": title, "text_length": len(text)},
                        ),
                        started_at=timer.started_at,
                        duration_ms=timer.duration_ms,
                    )
            except Exception as exc:
                return ActionResult.failed(
                    action="read_page",
                    error=str(exc),
                    target="current page",
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

    async def get_links(self, limit: int = 20) -> ActionResult:
        """Get all clickable links on the page (DOM extraction).

        Returns:
            ActionResult with links in metadata
        """
        with ActionTimer() as timer:
            try:
                manager = self._get_manager()
                async with manager.session() as page:
                    links = await page.eval_on_selector_all(
                        "a[href]",
                        """(elements) => elements.slice(0, 50).map(el => ({
                            text: el.innerText.trim().substring(0, 100),
                            href: el.href
                        })).filter(l => l.text.length > 0)"""
                    )

                    return ActionResult.success(
                        action="get_links",
                        target="page links",
                        message=f"Found {len(links)} links",
                        evidence=ActionEvidence(raw={"links": links[:limit]}),
                        started_at=timer.started_at,
                        duration_ms=timer.duration_ms,
                        metadata={"links": links[:limit]},
                    )
            except Exception as exc:
                return ActionResult.failed(
                    action="get_links",
                    error=str(exc),
                    target="page links",
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

    async def wait_for_text(self, text: str, timeout_ms: int = 10000) -> ActionResult:
        """Wait for specific text to appear on the page.

        Useful for verifying navigation/action completed.
        """
        with ActionTimer() as timer:
            try:
                manager = self._get_manager()
                async with manager.session() as page:
                    await page.get_by_text(text, exact=False).first.wait_for(
                        state="visible", timeout=timeout_ms
                    )
                    return ActionResult.success(
                        action="wait_for_text",
                        target=text,
                        message=f"Text '{text}' appeared",
                        evidence=ActionEvidence(
                            state_changed=True,
                            text_appeared=text,
                        ),
                        started_at=timer.started_at,
                        duration_ms=timer.duration_ms,
                    )
            except Exception as exc:
                return ActionResult.timeout(
                    action="wait_for_text",
                    target=text,
                    duration_ms=timer.duration_ms,
                )

    async def get_current_url(self) -> str:
        """Get the current page URL."""
        try:
            manager = self._get_manager()
            async with manager.session() as page:
                return page.url
        except Exception:
            return ""

    async def screenshot_base64(self) -> Optional[str]:
        """Take a screenshot and return as base64 (for vision analysis if needed)."""
        try:
            import base64
            manager = self._get_manager()
            async with manager.session() as page:
                data = await page.screenshot(type="jpeg", quality=70)
                return base64.b64encode(data).decode("ascii")
        except Exception:
            return None
