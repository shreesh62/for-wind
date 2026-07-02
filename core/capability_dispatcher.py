"""Capability dispatcher mapping intents to concrete handlers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple
from urllib.parse import quote_plus

from capabilities import CapabilityRegistry
from automation.services import AutomationServices
from core.telemetry import TelemetryLogger
from services.news_service import fetch_headlines

_APP_LAUNCH_PATTERN = re.compile(r"(?:open|launch|start|play|run)\s+(?P<app>[\w\s]+)$", re.IGNORECASE)
_WEBSITE_PATTERN = re.compile(
    r"(?:open|launch|start|play|go to|navigate to|visit|take me to|head to|browse to)\s+(?P<site>.+)",
    re.IGNORECASE,
)


@dataclass
class DispatchContext:
    """Arguments passed to capability handlers."""

    command: str
    normalized: str


class CapabilityDispatcher:
    """Routes matched capabilities to their execution handlers."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        weather_handler: Callable[[str], str],
        distance_handler: Callable[[str, str], str],
        automation_services: Optional[AutomationServices] = None,
        telemetry: Optional[TelemetryLogger] = None,
    ) -> None:
        self.registry = registry
        self.weather_handler = weather_handler
        self.distance_handler = distance_handler
        self.automation = automation_services or AutomationServices()
        self.telemetry = telemetry
        self.last_tool_trace: list[str] = []
        self.handlers: Dict[str, Callable[[DispatchContext], Optional[str]]] = {
            "qa_general": self._handle_qa_general,
            "self_describe": self._handle_self_describe,
            "weather_check": self._handle_weather,
            "maps_distance": self._handle_maps_distance,
            "maps_travel_time": self._handle_maps_travel_time,
            "whatsapp_message": self._handle_whatsapp_message,
            "instagram_dm": self._handle_instagram_dm,
            "amazon_shopping": self._handle_amazon_shopping,
            "browser_summarize": self._handle_browser_summary,
            "desktop_screenshot": self._handle_desktop_screenshot,
            "desktop_focus": self._handle_desktop_focus,
            "desktop_type": self._handle_desktop_type,
            "news_brief": self._handle_news_brief,
            "app_launch": self._handle_app_launch,
            "web_navigate": self._handle_web_navigate,
            "youtube_search": self._handle_youtube_search,
        }

    def _trace(self, message: str) -> None:
        if not message:
            return
        self.last_tool_trace.append(message.replace("\n", " ")[:300])

    def _trace_automation_result(self, action: str, result) -> None:
        try:
            success = getattr(result, "success", None)
            msg = getattr(result, "message", "")
        except Exception:
            success = None
            msg = ""
        self._trace(f"{action}: success={success} message={(msg or '')[:220]}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def dispatch(self, capability_key: Optional[str], command: str, normalized: str) -> Optional[str]:
        self.last_tool_trace = []
        if not capability_key:
            self._trace("capability_dispatch: key=None")
            return self._fallback_response(normalized)

        if not self.registry.is_available(capability_key):
            self._trace(f"capability_gate: {capability_key} allowed=False")
            return self.registry.explain_unavailable(capability_key)
        handler = self.handlers.get(capability_key)
        if not handler:
            self._trace(f"capability_dispatch: {capability_key} handler=None")
            return self._fallback_response(normalized)

        context = DispatchContext(command=command, normalized=normalized)
        if self.telemetry:
            self.telemetry.log("capability_invoked", {"capability": capability_key})
        self._trace(f"capability_dispatch: {capability_key} allowed=True")
        result = handler(context)
        self._trace(f"capability_result: {capability_key} chars={len(result or '')}")
        if self.telemetry:
            self.telemetry.log(
                "capability_completed",
                {
                    "capability": capability_key,
                    "response_length": len(result or ""),
                },
            )
        return result

    def register_handler(
        self,
        capability_key: str,
        handler: Callable[[DispatchContext], Optional[str]],
    ) -> None:
        """Register or override a handler for a capability."""

        self.handlers[capability_key] = handler

    def unregister_handler(self, capability_key: str) -> None:
        """Remove a previously registered capability handler."""

        self.handlers.pop(capability_key, None)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------
    def _handle_self_describe(self, _: DispatchContext) -> str:
        return self.registry.describe_capabilities()

    def _handle_qa_general(self, _: DispatchContext) -> Optional[str]:
        return None

    def _handle_weather(self, ctx: DispatchContext) -> str:
        match = re.search(r"(?:weather|temperature|forecast)(?: in)? ([\w\s,]+)", ctx.normalized)
        city = match.group(1).strip() if match else "Thane"
        city = city.title()
        self._trace(f"weather_check: city={city}")
        return self.weather_handler(city)

    def _handle_maps_distance(self, ctx: DispatchContext) -> str:
        start, end = self._extract_locations(ctx)
        if not start or not end:
            return "Please tell me origin and destination, for example: 'from Thane to Pune'."
        self._trace(f"maps_distance: origin={start} destination={end}")
        return self.distance_handler(start, end)

    def _handle_maps_travel_time(self, ctx: DispatchContext) -> str:
        start, end = self._extract_locations(ctx)
        if not start or not end:
            return "Please tell me origin and destination, for example: 'from Thane to Pune'."
        self._trace(f"maps_travel_time: origin={start} destination={end}")
        return self.distance_handler(start, end)

    def _handle_whatsapp_message(self, ctx: DispatchContext) -> Optional[str]:
        contact, message = self._extract_contact_and_message(ctx.normalized, platform="whatsapp")
        if not contact or not message:
            return "Please specify the WhatsApp contact and message, for example: 'send a WhatsApp message to Riya saying I’m on my way.'"
        result = self.automation.send_whatsapp(contact, message)
        self._trace_automation_result("send_whatsapp", result)
        return result.message

    def _handle_instagram_dm(self, ctx: DispatchContext) -> Optional[str]:
        contact, message = self._extract_contact_and_message(ctx.normalized, platform="instagram")
        if not contact or not message:
            return "Please specify the Instagram username and message, for example: 'send an Instagram DM to @riya saying good luck.'"
        result = self.automation.send_instagram_dm(contact, message)
        self._trace_automation_result("send_instagram_dm", result)
        return result.message

    def _handle_amazon_shopping(self, ctx: DispatchContext) -> Optional[str]:
        cleaned = ctx.command.strip()
        result = self.automation.search_amazon(cleaned)
        self._trace_automation_result("search_amazon", result)
        return result.message

    def _handle_browser_summary(self, _: DispatchContext) -> Optional[str]:
        response = self.automation.describe_active_tab()
        self._trace_automation_result("describe_active_tab", response)
        return response.message

    def _handle_desktop_screenshot(self, _: DispatchContext) -> Optional[str]:
        response = self.automation.take_screenshot()
        self._trace_automation_result("take_screenshot", response)
        return response.message

    def _handle_desktop_focus(self, ctx: DispatchContext) -> Optional[str]:
        target = self._extract_focus_target(ctx.normalized or ctx.command)
        if not target:
            return "Please tell me which window to focus."
        title, exe = target
        response = self.automation.focus_window(title=title, exe=exe)
        self._trace_automation_result("focus_window", response)
        return response.message

    def _handle_desktop_type(self, ctx: DispatchContext) -> Optional[str]:
        text = self._extract_type_payload(ctx.command)
        if not text:
            text = self._extract_type_payload(ctx.normalized)
        if not text:
            return "Please specify the text you want me to type."
        response = self.automation.type_text(text)
        self._trace_automation_result("type_text", response)
        return response.message

    def _handle_news_brief(self, ctx: DispatchContext) -> Optional[str]:
        topic = self._extract_topic(ctx.command)
        self._trace(f"news_brief: topic={topic}")
        return fetch_headlines(topic)

    def _handle_app_launch(self, ctx: DispatchContext) -> Optional[str]:
        app = self._extract_app_name(ctx.normalized or ctx.command)
        if not app:
            return "Please tell me which application to open."
        response = self.automation.launch_application(app)
        self._trace_automation_result("launch_application", response)
        return response.message

    def _handle_web_navigate(self, ctx: DispatchContext) -> Optional[str]:
        site, browser = self._extract_site_and_browser(ctx.normalized or ctx.command)
        if not site:
            return "Please tell me which website to open."
        response = self.automation.open_website(site, browser=browser)
        self._trace_automation_result("open_website", response)
        return response.message

    def _handle_youtube_search(self, ctx: DispatchContext) -> Optional[str]:
        command = (ctx.command or "").strip()
        lowered = command.lower().strip()
        norm = (ctx.normalized or "").strip().lower()

        query: str | None = None
        patterns = [
            r"search(?: for)?\s+(?P<q>.+?)\s+on\s+youtube",
            r"youtube\s+search\s+(?P<q>.+)",
            r"search\s+youtube\s+(?:for\s+)?(?P<q>.+)",
            r"(?:play|put on|open)\s+(?P<q>.+?)\s+(?:on\s+)?youtube",
        ]
        for pattern in patterns:
            match = re.search(pattern, lowered, re.IGNORECASE) or re.search(pattern, norm, re.IGNORECASE)
            if match:
                query = (match.group("q") or "").strip().strip("\"'")
                break

        if not query:
            return "Tell me what you want me to search for on YouTube."

        wants_play = bool(re.search(r"\b(play|put on)\b", lowered))
        if wants_play:
            result = self.automation.youtube_search_and_click_first(query)
            self._trace_automation_result("youtube_search_and_click_first", result)
            return result.message

        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        response = self.automation.open_website(url, browser="chrome")
        self._trace_automation_result("open_website", response)
        if response.success:
            self._trace(f"youtube_search: success=True query={query}")
            return f"Searching YouTube for '{query}'."
        self._trace(f"youtube_search: success=False query={query}")
        return response.message

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_locations(ctx: DispatchContext) -> tuple[Optional[str], Optional[str]]:
        patterns = [
            r"from (.+?) to (.+)",
            r"(?:between|from) (.+?) (?:and|to) (.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, ctx.normalized)
            if match:
                start, end = match.groups()
                return start.strip(), end.strip()
        return None, None

    @staticmethod
    def _extract_contact_and_message(text: str, platform: str) -> tuple[Optional[str], Optional[str]]:
        raw = (text or "").strip()
        if not raw:
            return None, None

        p = (platform or "").strip().lower()
        platform_word = "whatsapp" if p == "whatsapp" else "instagram"

        patterns = [
            rf"(?:send|text|message)\s+(?:a\s+)?{platform_word}\s+(?:message\s+)?to\s+(?P<contact>.+?)(?:\s+(?:saying|that|with)\s+|\s*:\s*)(?P<msg>.+)$",
            rf"(?:send|text|message)\s+(?P<contact>.+?)\s+on\s+{platform_word}(?:\s+(?:saying|that|with)\s+|\s*:\s*)(?P<msg>.+)$",
            rf"\b{platform_word}\b\s+(?:to\s+)?(?P<contact>.+?)(?:\s+(?:saying|that|with)\s+|\s*:\s*)(?P<msg>.+)$",
        ]
        if platform_word == "instagram":
            patterns.insert(
                0,
                r"(?:dm|message)\s+(?P<contact>@?[^\s]+)(?:\s+(?:saying|that|with)\s+|\s*:\s*)(?P<msg>.+)$",
            )

        for pat in patterns:
            m = re.search(pat, raw, flags=re.IGNORECASE)
            if not m:
                continue
            contact = (m.groupdict().get("contact") or "").strip().strip("'\"")
            msg = (m.groupdict().get("msg") or "").strip().strip("'\"")
            if contact and msg:
                return contact, msg
        return None, None

    @staticmethod
    def _extract_focus_target(command: str) -> Optional[tuple[Optional[str], Optional[str]]]:
        lowered = command.lower()
        match = re.search(r"(?:focus|switch to|bring up|activate)\s+(?:the\s+)?(.+)$", lowered)
        if not match:
            return None
        target = match.group(1).strip().strip(".?!")
        if target in {"window", "app", "application"}:
            return None
        if target.endswith(".exe"):
            return None, target
        return target.title(), None

    @staticmethod
    def _extract_type_payload(command: str) -> Optional[str]:
        match = re.search(r"(?:type|enter)\s+(?:out\s+)?(?:'([^']+)'|\"([^\"]+)\"|(.+))", command, re.IGNORECASE)
        if not match:
            return None
        groups = match.groups()
        for group in groups:
            if group:
                return group.strip()
        return None

    @staticmethod
    def _extract_topic(command: str) -> Optional[str]:
        match = re.search(r"(?:news|headlines|updates)(?: about| on)?\s+(.+)", command, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return command.strip() or None

    @staticmethod
    def _extract_app_name(command: str) -> Optional[str]:
        match = _APP_LAUNCH_PATTERN.search(command)
        if not match:
            return None
        app = (match.group("app") or "").strip()
        if not app:
            return None
        lowered = app.lower()
        if lowered.startswith("the "):
            app = app[4:]
        return app.strip()

    @staticmethod
    def _extract_site_and_browser(command: str) -> Tuple[Optional[str], Optional[str]]:
        match = _WEBSITE_PATTERN.search(command)
        if not match:
            return None, None

        site = (match.group("site") or "").strip()
        if not site:
            return None, None

        lowered = site.lower()
        if lowered in {"spotify", "netflix", "youtube"}:
            return None, None

        browser = None
        for keyword in ("in chrome", "on chrome", "in edge", "on edge", "in browser"):
            if keyword in lowered:
                site = site.replace(keyword.replace("in ", "").strip(), "")
                site = site.replace(keyword, "").strip()
                if "chrome" in keyword:
                    browser = "chrome"
                elif "edge" in keyword:
                    browser = "edge"
                else:
                    browser = None
                break

        return site.strip() or None, browser


    def _fallback_response(self, user_text: str) -> str:
        request = user_text.strip()
        if request:
            return (
                f"I don't have that functionality yet for '{request}'. "
                "Would you like me to simulate it in conversation instead?"
            )
        return "I don't have that functionality yet. Would you like me to simulate it in conversation instead?"
