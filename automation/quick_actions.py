"""User-facing automation actions orchestrated via Playwright."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from .playwright_manager import PlaywrightManager


@dataclass
class AutomationResult:
    success: bool
    message: str
    data: dict | None = None


class WhatsAppAutomation:
    def __init__(
        self,
        headless: bool = True,
        *,
        use_chrome_profile: bool = False,
        chrome_profile: str = "Default",
        remote_debug_port: int = 9222,
        auto_launch: bool = False,
    ) -> None:
        self.manager = PlaywrightManager(
            "whatsapp",
            headless=headless,
            use_chrome_profile=use_chrome_profile,
            chrome_profile=chrome_profile,
            remote_debug_port=remote_debug_port,
            auto_launch=auto_launch,
        )

    async def send_message_async(self, contact: str, message: str) -> AutomationResult:
        async with self.manager.session() as page:
            await page.goto("https://web.whatsapp.com/", wait_until="networkidle")
            if "Use WhatsApp on your computer" in await page.content():
                return AutomationResult(False, "Please scan the QR code for WhatsApp Web and try again.")

            await page.click("span[data-testid='chat-search']")
            await page.fill("div[contenteditable='true'][data-tab='3']", contact)
            await page.keyboard.press("Enter")
            await page.fill("div[contenteditable='true'][data-tab='10']", message)
            await page.keyboard.press("Enter")
            return AutomationResult(True, f"Message sent to {contact}.")

    def send_message(self, contact: str, message: str) -> AutomationResult:
        return asyncio.run(self.send_message_async(contact, message))


class InstagramAutomation:
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
            "instagram",
            headless=headless,
            use_chrome_profile=use_chrome_profile,
            chrome_profile=chrome_profile,
            remote_debug_port=remote_debug_port,
            auto_launch=auto_launch,
        )

    async def send_dm_async(self, username: str, message: str) -> AutomationResult:
        async with self.manager.session() as page:
            if not await self._ensure_inbox(page):
                return AutomationResult(False, "Please log in to Instagram via the automation module and try again.")

            opened = await self._open_thread(page, username)
            if not opened:
                return AutomationResult(False, f"Could not find a conversation with {username}.")

            await page.fill("textarea[placeholder='Message…']", message)
            await page.keyboard.press("Enter")
            return AutomationResult(True, f"DM sent to {username}.")

    def send_dm(self, username: str, message: str) -> AutomationResult:
        return asyncio.run(self.send_dm_async(username, message))

    async def get_inbox_async(self, limit: int = 5) -> AutomationResult:
        async with self.manager.session() as page:
            if not await self._ensure_inbox(page):
                return AutomationResult(False, "Please log in to Instagram via the automation module and try again.")

            threads_locator = page.locator("a[href^='/direct/t/']")
            await threads_locator.first.wait_for(timeout=10000)
            count = await threads_locator.count()
            entries: list[dict] = []
            for idx in range(min(count, limit)):
                item = threads_locator.nth(idx)
                raw_text = (await item.inner_text()).splitlines()
                raw_text = [line.strip() for line in raw_text if line.strip()]
                name = raw_text[0] if raw_text else "Unknown"
                preview = raw_text[1] if len(raw_text) > 1 else ""
                unread = any("·" in part or "Unread" in part for part in raw_text)
                entries.append({
                    "name": name,
                    "preview": preview,
                    "unread": unread,
                })

            return AutomationResult(True, f"Fetched {len(entries)} Instagram conversations.", {"threads": entries})

    def get_inbox(self, limit: int = 5) -> AutomationResult:
        return asyncio.run(self.get_inbox_async(limit))

    async def read_thread_async(self, username: str, limit: int = 10) -> AutomationResult:
        async with self.manager.session() as page:
            if not await self._ensure_inbox(page):
                return AutomationResult(False, "Please log in to Instagram via the automation module and try again.")

            opened = await self._open_thread(page, username)
            if not opened:
                return AutomationResult(False, f"Could not find a conversation with {username}.")

            await page.wait_for_timeout(800)
            message_nodes = page.locator("div[role='main'] div[dir='auto']")
            count = await message_nodes.count()
            start = max(0, count - limit)
            messages: list[dict] = []
            for idx in range(start, count):
                node = message_nodes.nth(idx)
                text = (await node.inner_text()).strip()
                if not text:
                    continue
                meta = await node.evaluate(
                    "(el) => el.closest('[data-testid]')?.getAttribute('data-testid') || ''"
                )
                direction = "outgoing" if meta and "outgoing" in meta else "incoming"
                messages.append({
                    "text": text,
                    "direction": direction,
                })

            return AutomationResult(True, f"Fetched {len(messages)} messages from {username}.", {"messages": messages})

    def read_thread(self, username: str, limit: int = 10) -> AutomationResult:
        return asyncio.run(self.read_thread_async(username, limit))

    async def reply_dm_async(self, username: str, message: str) -> AutomationResult:
        return await self.send_dm_async(username, message)

    def reply_dm(self, username: str, message: str) -> AutomationResult:
        return asyncio.run(self.reply_dm_async(username, message))

    async def _ensure_inbox(self, page) -> bool:
        await page.goto("https://www.instagram.com/direct/inbox/", wait_until="networkidle")
        content = await page.content()
        if "Log in" in content or "Sign up" in content:
            return False
        return True

    async def _open_thread(self, page, username: str) -> bool:
        locator = page.locator("a[href^='/direct/t/']").filter(has_text=username)
        try:
            await locator.first.click(timeout=5000)
            await page.wait_for_timeout(500)
            return True
        except Exception:
            return False


class GmailComposeTemplateAutomation:
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

    async def compose_email_async(self) -> AutomationResult:
        async with self.manager.session() as page:
            await page.goto("https://mail.google.com/mail/u/0/#inbox", wait_until="networkidle")
            content = await page.content()
            if "Sign in" in content:
                return AutomationResult(False, "Please log into Gmail in the automation browser and retry.")

            compose_selector = "div[role='button'][gh='cm']"
            await page.click(compose_selector)

            # Open recipients
            await page.fill("textarea[name='to']", "recipient@example.com")
            await page.keyboard.press("Tab")
            await page.fill("input[name='subjectbox']", "Subject template placeholder")
            await page.keyboard.press("Tab")
            await page.fill("div[aria-label='Message Body']", "Hello, this is a template message.")

            await page.wait_for_timeout(500)
            await page.keyboard.press("Escape")

            return AutomationResult(True, "Gmail compose window prepared with template.")

    def compose_email(self) -> AutomationResult:
        return asyncio.run(self.compose_email_async())


class GoogleCalendarAutomation:
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
            "google_calendar",
            headless=headless,
            use_chrome_profile=use_chrome_profile,
            chrome_profile=chrome_profile,
            remote_debug_port=remote_debug_port,
            auto_launch=auto_launch,
        )

    async def create_event_async(
        self,
        title: str,
        date_text: str | None = None,
        start_time: str | None = None,
    ) -> AutomationResult:
        async with self.manager.session() as page:
            await page.goto("https://calendar.google.com/calendar/u/0/r", wait_until="domcontentloaded", timeout=60000)
            content = await page.content()
            if "Sign in" in content:
                return AutomationResult(False, "Sign into Google Calendar in the automation browser, then retry.")

            await page.click("div[aria-label='Create']")
            await page.wait_for_timeout(800)

            await page.fill("input[aria-label='Add title']", title or "New Event")

            if date_text:
                try:
                    await page.fill("input[aria-label='Start date']", date_text)
                except Exception:
                    pass
            if start_time:
                try:
                    await page.fill("input[aria-label='Start time']", start_time)
                except Exception:
                    pass

            try:
                await page.click("button:has-text('Save')")
            except Exception:
                return AutomationResult(True, f"Drafted calendar event '{title}'. Please review in Calendar.")

            await page.wait_for_timeout(500)
            return AutomationResult(True, f"Calendar event '{title}' scheduled.")

    def create_event(self, title: str, date_text: str | None = None, start_time: str | None = None) -> AutomationResult:
        return asyncio.run(self.create_event_async(title, date_text, start_time))
