"""Playwright-driven Gmail automation helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .playwright_manager import PlaywrightManager, PlaywrightUnavailable


@dataclass
class GmailResult:
    success: bool
    message: str


class GmailAutomation:
    """Automates basic Gmail compose/send actions via Playwright."""

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
            "gmail",
            headless=headless,
            use_chrome_profile=use_chrome_profile,
            chrome_profile=chrome_profile,
            remote_debug_port=remote_debug_port,
            auto_launch=auto_launch,
        )

    async def send_email_async(self, recipient: str, subject: str, body: str) -> GmailResult:
        try:
            async with self.manager.session() as page:
                await page.goto("https://mail.google.com/mail/u/0/#inbox", wait_until="networkidle")

                if "Sign in" in await page.content():
                    return GmailResult(
                        False,
                        "Please log into Gmail in the automation browser first, then retry.",
                    )

                compose_selector = "div[role='button'][gh='cm']"
                await page.click(compose_selector)
                await page.fill("textarea[name='to']", recipient)
                await page.fill("input[name='subjectbox']", subject)
                await page.fill("div[aria-label='Message Body']", body)
                await page.click("div[role='button'][data-tooltip*='Send']")

                return GmailResult(True, f"Email queued to {recipient}.")
        except Exception as exc:  # pragma: no cover - Playwright runtime errors
            return GmailResult(False, f"Gmail automation error: {exc}")

    def send_email(self, recipient: str, subject: str, body: str) -> GmailResult:
        try:
            return asyncio.run(self.send_email_async(recipient, subject, body))
        except PlaywrightUnavailable as exc:
            return GmailResult(False, str(exc))
        except RuntimeError:
            # If event loop already running (e.g., inside async context), reuse loop
            return GmailResult(False, "Gmail automation cannot run inside existing event loop right now.")
