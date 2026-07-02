"""Amazon shopping automation leveraging Playwright-managed Chrome profile."""

from __future__ import annotations

import asyncio
from typing import Optional

from .playwright_manager import PlaywrightManager, PlaywrightUnavailable
from .quick_actions import AutomationResult


class AmazonSearchAutomation:
    """Automates Amazon product search using the shared Chrome profile."""

    def __init__(
        self,
        headless: bool = True,
        *,
        use_chrome_profile: bool = False,
        chrome_profile: str = "home",
        remote_debug_port: int = 9222,
        auto_launch: bool = False,
    ) -> None:
        self.manager = PlaywrightManager(
            "amazon",
            headless=headless,
            use_chrome_profile=use_chrome_profile,
            chrome_profile=chrome_profile,
            remote_debug_port=remote_debug_port,
            auto_launch=auto_launch,
        )

    async def search_async(self, query: str) -> AutomationResult:
        cleaned = self._sanitize(query)
        if not cleaned:
            return AutomationResult(False, "Please specify what to search for on Amazon.")

        async with self.manager.session() as page:
            await page.goto("https://www.amazon.in/", wait_until="domcontentloaded")

            selectors = [
                "#twotabsearchtextbox",
                "input[name='field-keywords']",
                "input[type='search']",
            ]

            target_selector: Optional[str] = None
            for selector in selectors:
                try:
                    await page.fill(selector, cleaned)
                    target_selector = selector
                    break
                except Exception:
                    continue

            if not target_selector:
                return AutomationResult(False, "Could not locate the Amazon search box.")

            try:
                await page.press(target_selector, "Enter")
            except Exception:
                # Fallback: submit form via JS if key press fails
                await page.evaluate(
                    "(selector) => {"
                    "const el = document.querySelector(selector);"
                    "if (!el) return false;"
                    "const form = el.closest('form');"
                    "if (form) { form.submit(); return true; }"
                    "el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter'}));"
                    "el.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter'}));"
                    "return true;"
                    "}",
                    target_selector,
                )

            await page.wait_for_timeout(1500)
            return AutomationResult(True, f"Searching Amazon for '{cleaned}'.", {"query": cleaned})

    def search(self, query: str) -> AutomationResult:
        try:
            return asyncio.run(self.search_async(query))
        except PlaywrightUnavailable as exc:
            return AutomationResult(False, str(exc))

    @staticmethod
    def _sanitize(query: str) -> str:
        if not query:
            return ""
        lowered = query.strip()
        tokens = [token for token in lowered.split() if token.lower() not in {"on", "amazon", "for"}]
        cleaned = " ".join(tokens).strip()
        return cleaned or lowered
