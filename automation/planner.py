"""High-level automation planner that maps natural-language commands to actions."""

from __future__ import annotations

import re
import time
from typing import Iterable, Optional, Tuple
from urllib.parse import quote_plus

from automation.services import AutomationServices, AutomationResponse
from capabilities import CapabilityRegistry
from awareness.snapshot import redact_snapshot_for_prompt

try:  # Optional awareness dependency
    from awareness.state_cache import StateCache
except ImportError:  # pragma: no cover
    StateCache = None  # type: ignore

_SCREEN_INTENT_KEYWORDS: Iterable[str] = (
    "what's on screen",
    "what is on screen",
    "what's on the screen",
    "what is on the screen",
    "what's in the screen",
    "what is in the screen",
    "what do you see",
    "what can you see",
    "describe my screen",
    "describe the screen",
    "what is visible",
    "in the screen",
    "in screen",
    "on the screen",
    "on screen",
    "current window",
    "which window",
    "what window",
    "what is open",
)

_SCREEN_INTENT_PATTERN = re.compile(
    r"(?:what(?:'s| is)|describe|summarize|show|tell me).*?(?:on|in)?\s*(?:the\s*)?screen",
    re.IGNORECASE,
)

_BROWSER_INTENT_PATTERN = re.compile(
    r"(?:what|describe|summarize|tell me).*?(?:browser|tab|chrome|web page|webpage)",
    re.IGNORECASE,
)

_SCREENSHOT_KEYWORDS: Iterable[str] = (
    "screenshot",
    "screen shot",
    "capture screen",
    "grab screen",
    "screen capture",
    "take a screenshot",
    "take screenshot",
)

_LAUNCH_PATTERN = re.compile(
    r"(?:open|launch|start|play)\s+(?P<app>[\w\s]+)$",
    re.IGNORECASE,
)

_WEBSITE_PATTERN = re.compile(
    r"(?:open|launch|start|play|go to|navigate to|visit)\s+(?P<site>.+)",
    re.IGNORECASE,
)

_FOCUS_PATTERN = re.compile(
    r"(?:focus|switch to|bring up|activate)\s+(?:the\s+)?(?P<target>.+?)(?:\s+window)?$",
    re.IGNORECASE,
)

_TYPE_PATTERN = re.compile(
    r"(?:type|enter|write|input)\s+(?P<text>\"[^\"]+\"|'[^']+'|.+)",
    re.IGNORECASE,
)

_CHAIN_SPLIT_PATTERN = re.compile(
    r"\s*(?:,|;)?\s*(?:and\s+)?then\s+",
    re.IGNORECASE,
)

_DURATION_TOKEN_PATTERN = re.compile(
    r"^(?:\d+(?:\.\d+)?|one|two|three|four|five)$",
    re.IGNORECASE,
)

_WAIT_PATTERN = re.compile(
    r"^\s*wait(?:\s+(?:a\s+bit|and))?(?:\s+(?P<n>\d+(?:\.\d+)?|one|two|three|four|five))?\s*(?:seconds|secs|s)?\s*$",
    re.IGNORECASE,
)

_WAIT_PREFIX_PATTERN = re.compile(
    r"^\s*wait(?:\s+(?:a\s+bit|and))?(?:\s+(?P<n>\d+(?:\.\d+)?|one|two|three|four|five))?\s*(?:seconds|secs|s)?\s*(?:and\s+)?(?P<rest>.+)$",
    re.IGNORECASE,
)

_CLICK_COORD_PATTERN = re.compile(
    r"\bclick(?:\s+at)?\s+(?P<x>\d+)\s*[,:\s]\s*(?P<y>\d+)\b",
    re.IGNORECASE,
)

_DOUBLE_CLICK_COORD_PATTERN = re.compile(
    r"\bdouble\s+click(?:\s+at)?\s+(?P<x>\d+)\s*[,:\s]\s*(?P<y>\d+)\b",
    re.IGNORECASE,
)

_SCROLL_PATTERN = re.compile(
    r"\bscroll\s+(?P<dir>up|down)\s+(?:by\s+)?(?P<n>\d+)\s*(?:px|pixels|lines)?\b",
    re.IGNORECASE,
)

_SCROLL_PATTERN_ALT = re.compile(
    r"\bscroll\s+(?P<n>\d+)\s*(?:px|pixels|lines)?\s+(?P<dir>up|down)\b",
    re.IGNORECASE,
)

_CLICK_ELEMENT_PATTERN = re.compile(
    r"\bclick\s+element\s+(?P<name>\"[^\"]+\"|'[^']+'|.+)$",
    re.IGNORECASE,
)

_CLICK_TEXT_PATTERN = re.compile(
    r"\bclick\s+text\s+(?P<phrase>\"[^\"]+\"|'[^']+'|.+)$",
    re.IGNORECASE,
)

_WHAT_FOCUSED_PATTERN = re.compile(
    r"\b(what\s+is\s+(focused|selected|focus)|what\s+is\s+the\s+focus|what's\s+(focused|selected)|what\s+has\s+focus|what\s+am\s+i\s+focused\s+on|what\s+is\s+in\s+focus)\b",
    re.IGNORECASE,
)

_OCR_SCREEN_PATTERN = re.compile(
    r"\b(?:ocr|read|scan)\s+(?:the\s+)?screen\b",
    re.IGNORECASE,
)

_REGION_PATTERN = re.compile(
    r"(?P<action>(?:screenshot|capture|ocr|read))\s+(?:region\s+)?(?P<x>\d+)\s+(?P<y>\d+)\s+(?P<w>\d+)\s+(?P<h>\d+)",
    re.IGNORECASE,
)

_RELOAD_PATTERN = re.compile(
    r"\b(reload|refresh)\b(?:\s+(?:the\s+)?)?(?:page|tab|browser|site)?$",
    re.IGNORECASE,
)

_AMAZON_ACTION_KEYWORDS: Iterable[str] = (
    "buy",
    "search",
    "find",
    "order",
    "look",
)

_WHATSAPP_KEYWORDS: Iterable[str] = (
    "whatsapp",
    "message",
)

_WHATSAPP_PATTERN = re.compile(
    r"(?:send|message|text)\s+(?:a\s+)?(?:whatsapp\s+)?(?:message\s+)?to\s+(?P<contact>.+?)(?:\s+(?:saying|that|with|says)\s+(?P<message>.+))?$",
    re.IGNORECASE,
)


class AutomationPlanner:
    """Determines and executes UI/browser automation tasks."""

    def __init__(
        self,
        automation: AutomationServices,
        *,
        awareness_state: "StateCache | None" = None,
        registry: CapabilityRegistry | None = None,
        use_cognitive_loop: bool = False,
    ) -> None:
        self.automation = automation
        self.awareness_state = awareness_state
        self.last_tool_trace: list[str] = []
        self.registry = registry
        self._last_scroll_direction: str | None = None
        self._last_scroll_amount: int | None = None
        self._current_command: str | None = None
        self._last_verified_command: str | None = None
        self._last_verified_action: str | None = None
        self._last_verified_at: float | None = None
        self._pending_website: tuple[str, str | None] | None = None
        self._last_website: tuple[str, str | None] | None = None
        self._last_verified_scroll_direction: str | None = None
        self._last_verified_scroll_amount: int | None = None
        self.use_cognitive_loop = use_cognitive_loop
        self._cognitive_loop = None
        if use_cognitive_loop and awareness_state:
            try:
                from .cognitive_loop import CognitiveLoop
                self._cognitive_loop = CognitiveLoop(automation, awareness_state)
            except Exception:
                self._cognitive_loop = None

    def execute_cognitive(self, command: str) -> Optional[str]:
        """Execute a command using the cognitive control loop.
        
        This is the new perception-driven execution path that replaces
        static keyword routing with a closed-loop autonomous system.
        """
        if not self._cognitive_loop:
            raise RuntimeError("Cognitive loop is not initialized")
        
        result = self._cognitive_loop.execute_goal(command)
        self.last_tool_trace = ["cognitive_loop: executed"]
        return result

    def repeat_last_verified(self, *, snapshot: dict | None = None) -> Optional[str]:
        cmd = (self._last_verified_command or "").strip()
        if not cmd:
            return "I don't have a verified previous action to repeat yet."
        prefix = f"repeat_last_verified: command={cmd}"
        msg = self.execute(cmd, snapshot=snapshot, _chain_depth=1)
        trace = list(getattr(self, "last_tool_trace", []) or [])
        self.last_tool_trace = [prefix, *trace]
        return msg

    def open_last_website(self, *, snapshot: dict | None = None) -> Optional[str]:
        if not self._last_website:
            return "I don't know which website you mean yet. Tell me the site to open."
        target, browser = self._last_website
        self.last_tool_trace = [f"open_last_website: target={target} browser={browser}"]
        return self._handle_website(target, browser)

    def cancel_context(self) -> str:
        self._pending_website = None
        self._current_command = None
        return "Okay. Cancelled."

    def undo_last_verified(self, *, snapshot: dict | None = None) -> Optional[str]:
        action = (self._last_verified_action or "").strip()
        if not action:
            return "I don't have a verified previous action to undo yet."

        if action == "desktop_scroll":
            if not (self._last_verified_scroll_direction and isinstance(self._last_verified_scroll_amount, int)):
                return "I can't safely undo the last scroll yet."
            amt = int(self._last_verified_scroll_amount)
            undo_amt = abs(amt) if self._last_verified_scroll_direction == "down" else -abs(amt)
            self.last_tool_trace = [f"undo_last_verified: action=desktop_scroll amount={undo_amt}"]
            result = self.automation.scroll(int(undo_amt))
            return self._finalize_result("undo_scroll", result)

        if action == "type_text":
            if not hasattr(self.automation, "press_hotkey"):
                return "Undo for typing isn't available yet on this setup."
            self.last_tool_trace = ["undo_last_verified: action=type_text hotkey=ctrl+z"]
            result = self.automation.press_hotkey("ctrl", "z")
            return self._finalize_result("undo_type_text", result)

        return "I can't safely undo that action yet."

    def _gate(self, capability_key: str) -> Optional[str]:
        """Return an error message if the capability is unavailable; otherwise None."""

        if not self.registry or not capability_key:
            return None
        allowed = False
        try:
            allowed = bool(self.registry.is_available(capability_key))
        except Exception:
            allowed = False

        self.last_tool_trace.append(f"capability_gate: {capability_key} allowed={allowed}")
        if allowed:
            return None
        try:
            return self.registry.explain_unavailable(capability_key)
        except Exception:
            return "That capability isn’t enabled yet."

    @staticmethod
    def _looks_like_failure_message(message: str) -> bool:
        low = (message or "").lower()
        return any(
            token in low
            for token in (
                "failed",
                "couldn't",
                "error",
                "unavailable",
                "unable",
                "cancel",
                "cancelled",
                "canceled",
                "not configured",
                "not installed",
                "no active",
                "missing",
            )
        )

    def _record_tool_result(self, action: str, result: AutomationResponse) -> None:
        safe_msg = (result.message or "").replace("\n", " ")
        ver = getattr(result, "verification", None)
        ver_ok = None
        try:
            if isinstance(ver, dict):
                ver_ok = bool(ver.get("ok"))
        except Exception:
            ver_ok = None
        ver_part = "" if ver_ok is None else f" verified={ver_ok}"
        self.last_tool_trace.append(
            f"{action}: success={result.success}{ver_part} message={safe_msg[:240]}"
        )

    def _finalize_result(self, action: str, result: AutomationResponse) -> str:
        self._record_tool_result(action, result)
        ver = getattr(result, "verification", None)
        verified_ok = False
        try:
            if isinstance(ver, dict):
                verified_ok = bool(ver.get("ok"))
        except Exception:
            verified_ok = False

        if action == "open_website":
            # Record the last requested website even when we cannot verify navigation.
            # This enables follow-ups like "open it again" after a best-effort open.
            if result.success and self._pending_website:
                self._last_website = self._pending_website
            self._pending_website = None

        if action == "desktop_scroll" and verified_ok:
            try:
                if self._last_scroll_direction and isinstance(self._last_scroll_amount, int):
                    self._last_verified_scroll_direction = self._last_scroll_direction
                    self._last_verified_scroll_amount = int(self._last_scroll_amount)
            except Exception:
                pass

        if verified_ok and not str(action).startswith("undo_"):
            try:
                cmd = (self._current_command or "").strip()
                if cmd:
                    self._last_verified_command = cmd
                    self._last_verified_action = action
                    self._last_verified_at = time.time()
            except Exception:
                pass

        if result.success:
            if verified_ok:
                return self._with_recovery(result.message)
            details = ""
            try:
                if isinstance(ver, dict):
                    reason = ver.get("reason")
                    method = ver.get("method")
                    if isinstance(reason, str) and reason.strip():
                        details = reason.strip()
                    elif isinstance(method, str) and method.strip():
                        details = f"verification method: {method.strip()}"
            except Exception:
                details = ""
            msg = (result.message or "").strip()
            parts = [f"I attempted {action} but could not confirm success."]
            if details:
                parts.append(details)
            if msg:
                parts.append(msg)
            return self._with_recovery(" ".join(parts))
        if self._looks_like_failure_message(result.message):
            return self._with_recovery(result.message)
        return self._with_recovery(f"I tried but failed: {result.message}")

    def execute(
        self,
        command: str,
        *,
        snapshot: dict | None = None,
        _chain_depth: int = 0,
    ) -> Optional[str]:
        self.last_tool_trace = []
        raw_command = command
        command = self._normalize_command(command)
        command_lower = command.lower().strip()
        self._current_command = command
        if not command_lower:
            return None

        if re.fullmatch(r"(?:cancel|stop|never\s+mind|forget\s+it)", command_lower, flags=re.IGNORECASE):
            return self.cancel_context()

        if re.fullmatch(r"(?:undo|undo\s+that|go\s+back|reverse\s+that)", command_lower, flags=re.IGNORECASE):
            return self.undo_last_verified(snapshot=snapshot)

        if snapshot is None and self.awareness_state is not None:
            try:
                snapshot = self.awareness_state.get_snapshot()
            except Exception:
                snapshot = None

        if _chain_depth <= 0:
            chained = self._split_chained_commands(command)
            if chained:
                trace: list[str] = []
                messages: list[str] = []
                current_snapshot = self._ensure_uia_snapshot(snapshot)
                i = 0
                while i < len(chained):
                    part = chained[i]
                    part = self._clean_chain_part(part)

                    if i > 0 and self._is_duration_token(part) and (i + 1) < len(chained):
                        nxt = self._clean_chain_part(chained[i + 1])
                        if self._looks_like_explicit_command(nxt) or (nxt or "").lower().startswith("click "):
                            seconds = self._parse_wait_seconds(part)
                            try:
                                time.sleep(seconds)
                            except Exception:
                                pass
                            trace.append(f"wait: seconds={seconds}")
                            current_snapshot = self._refresh_snapshot(current_snapshot, min_timestamp=time.time())
                            i += 1
                            continue

                    if part.strip().lower() == "wait" and (i + 1) < len(chained):
                        nxt = self._clean_chain_part(chained[i + 1])
                        if re.fullmatch(r"\d+(?:\.\d+)?|one|two|three|four|five", (nxt or "").strip().lower()):
                            seconds = self._parse_wait_seconds(nxt)
                            try:
                                time.sleep(seconds)
                            except Exception:
                                pass
                            trace.append(f"wait: seconds={seconds}")
                            current_snapshot = self._refresh_snapshot(current_snapshot, min_timestamp=time.time())
                            i += 2
                            continue

                    if self._is_wait_step(part):
                        seconds = self._parse_wait_seconds(part)
                        try:
                            time.sleep(seconds)
                        except Exception:
                            pass
                        trace.append(f"wait: seconds={seconds}")
                        current_snapshot = self._refresh_snapshot(current_snapshot, min_timestamp=time.time())
                        i += 1
                        continue

                    wait_prefix = self._parse_wait_prefix(part)
                    if wait_prefix:
                        seconds, rest = wait_prefix
                        try:
                            time.sleep(seconds)
                        except Exception:
                            pass
                        trace.append(f"wait: seconds={seconds}")
                        current_snapshot = self._refresh_snapshot(current_snapshot, min_timestamp=time.time())
                        if rest:
                            part = rest
                        else:
                            i += 1
                            continue
                    subcmd = part
                    if i > 0:
                        subcmd = self._inherit_leading_verb(chained[0], part)
                    step_started = time.time()
                    msg = self.execute(subcmd, snapshot=current_snapshot, _chain_depth=_chain_depth + 1)
                    trace.extend(self.last_tool_trace)
                    if msg is None:
                        self.last_tool_trace = trace
                        return None
                    messages.append(msg)
                    if self._looks_like_failure_message(msg):
                        self.last_tool_trace = trace
                        return msg

                    current_snapshot = self._refresh_snapshot(current_snapshot, min_timestamp=step_started)
                    i += 1
                self.last_tool_trace = trace
                return " Then ".join(messages)

        if self._matches_amazon(command_lower):
            blocked = self._gate("amazon_shopping")
            if blocked:
                return blocked
            response = self.automation.search_amazon(raw_command)
            return self._finalize_result("search_amazon", response)

        if self._matches_whatsapp(command_lower):
            blocked = self._gate("whatsapp_message")
            if blocked:
                return blocked
            response = self._handle_whatsapp(raw_command)
            if response:
                return response

        if self._matches_screen_intent(command_lower):
            return self._describe_screen(self._ensure_uia_snapshot(snapshot))

        if _WHAT_FOCUSED_PATTERN.search(command):
            return self._what_is_focused(self._ensure_uia_snapshot(snapshot))

        m_scroll = _SCROLL_PATTERN.search(command)
        if m_scroll:
            blocked = self._gate("desktop_scroll")
            if blocked:
                return blocked
            return self._handle_scroll(m_scroll.group("dir"), m_scroll.group("n"), snapshot)

        m_scroll_alt = _SCROLL_PATTERN_ALT.search(command)
        if m_scroll_alt:
            blocked = self._gate("desktop_scroll")
            if blocked:
                return blocked
            return self._handle_scroll(m_scroll_alt.group("dir"), m_scroll_alt.group("n"), snapshot)

        if re.search(r"\b(scroll\s+more|scroll\s+again|keep\s+scrolling|keep\s+going)\b", command_lower):
            blocked = self._gate("desktop_scroll")
            if blocked:
                return blocked
            if not self._last_scroll_direction:
                return "Tell me which direction to scroll (up/down)."
            amt = self._last_scroll_amount if isinstance(self._last_scroll_amount, int) else 350
            return self._handle_scroll(self._last_scroll_direction, str(abs(int(amt))), snapshot)

        m_dc = _DOUBLE_CLICK_COORD_PATTERN.search(command)
        if m_dc:
            blocked = self._gate("desktop_click")
            if blocked:
                return blocked
            return self._handle_double_click(m_dc.group("x"), m_dc.group("y"), snapshot)

        m_click = _CLICK_COORD_PATTERN.search(command)
        if m_click:
            blocked = self._gate("desktop_click")
            if blocked:
                return blocked
            return self._handle_click(m_click.group("x"), m_click.group("y"), snapshot)

        m_click_el = _CLICK_ELEMENT_PATTERN.search(command)
        if m_click_el:
            blocked = self._gate("desktop_click")
            if blocked:
                return blocked
            return self._handle_click_element(m_click_el.group("name"), snapshot)

        m_click_txt = _CLICK_TEXT_PATTERN.search(command)
        if m_click_txt:
            blocked = self._gate("desktop_click")
            if blocked:
                return blocked
            return self._handle_click_text(m_click_txt.group("phrase"), snapshot)

        if command_lower.startswith("click ") and "youtube" not in command_lower and "yt" not in command_lower:
            blocked = self._gate("desktop_click")
            if blocked:
                return blocked
            remainder = command.strip()[len("click ") :].strip()
            if remainder and not any(ch.isdigit() for ch in remainder):
                return self._handle_click_element(remainder, snapshot)

        if self._matches_screenshot(command_lower):
            blocked = self._gate("desktop_screenshot")
            if blocked:
                return blocked
            return self._handle_screenshot()

        if _OCR_SCREEN_PATTERN.search(command):
            blocked = self._gate("desktop_ocr")
            if blocked:
                return blocked
            return self._handle_ocr_screen()

        # Region-based actions: screenshot/ocr
        m_region = _REGION_PATTERN.search(command)
        if m_region:
            action = (m_region.group("action") or "").lower()
            x, y, w, h = m_region.group("x"), m_region.group("y"), m_region.group("w"), m_region.group("h")
            if action in {"screenshot", "capture"}:
                blocked = self._gate("desktop_screenshot")
                if blocked:
                    return blocked
                return self._handle_screenshot_region(x, y, w, h)
            if action in {"ocr", "read"}:
                blocked = self._gate("desktop_ocr")
                if blocked:
                    return blocked
                return self._handle_ocr_region(x, y, w, h)

        # Reload / refresh active tab
        if _RELOAD_PATTERN.search(command):
            blocked = self._gate("web_navigate")
            if blocked:
                return blocked
            result = self.automation.reload_active_tab()
            return self._finalize_result("reload_active_tab", result)

        focus_target = self._extract_focus_target(command)
        if focus_target:
            blocked = self._gate("desktop_focus")
            if blocked:
                return blocked
            return self._handle_focus(*focus_target)
        if self._wants_focus(command_lower):
            return "Please tell me which window to focus."

        type_text = self._extract_type_text(command)
        if type_text:
            blocked = self._gate("desktop_type")
            if blocked:
                return blocked
            return self._handle_type_text(type_text)

        if self._matches_browser_summary(command_lower):
            blocked = self._gate("browser_summarize")
            if blocked:
                return blocked
            return self._handle_browser_summary()

        # Specialized: YouTube search (+ optional click-first)
        yt_search = self._extract_youtube_search(command)
        if yt_search:
            blocked = self._gate("youtube_search")
            if blocked:
                return blocked
            query, browser, click_first = yt_search
            if click_first:
                result = self.automation.youtube_search_and_click_first(query)
                return self._finalize_result("youtube_search_and_click_first", result)
            url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
            response = self.automation.open_website(url, browser=browser)
            self._record_tool_result("open_website", response)
            if response.success:
                return self._with_recovery(f"Searching YouTube for '{query}'.")
            if self._looks_like_failure_message(response.message):
                return self._with_recovery(response.message)
            return self._with_recovery(f"I tried but failed: {response.message}")

        # Open YouTube and click the first video
        if re.search(r"\bopen\s+(?:youtube|yt).*\b(click|play)\b.*\b(first)\b.*\b(video|one|result)\b", command, flags=re.IGNORECASE):
            blocked = self._gate("youtube_search")
            if blocked:
                return blocked
            result = self.automation.youtube_open_and_click_first()
            return self._finalize_result("youtube_open_and_click_first", result)

        m_n = re.search(
            r"(?:search|find|look up)\s+(?P<q>.+?)\s+(?:on|in)\s+(?:youtube|yt).*(?:click|play)\s+(?:on\s+)?(?:the\s+)?(?P<ord>(first|second|third|\d+(?:st|nd|rd|th)?))\s+(?:video|result|one)",
            command,
            flags=re.IGNORECASE,
        )
        if m_n:
            blocked = self._gate("youtube_search")
            if blocked:
                return blocked
            q = (m_n.group("q") or "").strip()
            ord_text = (m_n.group("ord") or "").lower()
            index = 1
            if ord_text.isdigit():
                index = int(ord_text)
            else:
                mapping = {"first": 1, "second": 2, "third": 3}
                index = mapping.get(ord_text, index)
            result = self.automation.youtube_search_and_click_n(q, max(index, 1))
            return self._finalize_result("youtube_search_and_click_n", result)

        if re.search(r"\bopen\s+(?:youtube|yt)\s+and\b", command, flags=re.IGNORECASE):
            blocked = self._gate("youtube_search")
            if blocked:
                return blocked
            return self._handle_website("https://www.youtube.com/", None)

        if re.search(r"\b(next\s+(video|track)|skip)\b", command_lower):
            blocked = self._gate("youtube_search")
            if blocked:
                return blocked
            result = self.automation.youtube_next_video()
            return self._finalize_result("youtube_next_video", result)
        if re.search(r"\b(prev(ious)?\s+(video|track)|go back)\b", command_lower):
            blocked = self._gate("youtube_search")
            if blocked:
                return blocked
            result = self.automation.youtube_prev_video()
            return self._finalize_result("youtube_prev_video", result)
        if re.search(r"\b(pause|resume|play)\b.*\b(video|youtube)?\b", command_lower):
            blocked = self._gate("youtube_search")
            if blocked:
                return blocked
            result = self.automation.youtube_toggle_pause()
            return self._finalize_result("youtube_toggle_pause", result)

        m_fwd = re.search(r"\b(fast\s+forward|forward|seek\s+forward|most\s+forward)\b(?:\s+(?P<sec>\d+)\s*(seconds|secs|s)?)?", command_lower)
        if m_fwd:
            blocked = self._gate("youtube_search")
            if blocked:
                return blocked
            sec = m_fwd.group("sec")
            seconds = int(sec) if sec and sec.isdigit() else 10
            result = self.automation.youtube_forward(seconds)
            return self._finalize_result("youtube_forward", result)
        m_back = re.search(r"\b(rewind|back|seek\s+back)\b(?:\s+(?P<sec>\d+)\s*(seconds|secs|s)?)?", command_lower)
        if m_back:
            blocked = self._gate("youtube_search")
            if blocked:
                return blocked
            sec = m_back.group("sec")
            seconds = int(sec) if sec and sec.isdigit() else 10
            result = self.automation.youtube_rewind(seconds)
            return self._finalize_result("youtube_rewind", result)

        site_request = self._extract_website(command)
        if site_request:
            site, browser = site_request
            normalized = site.lower()
            # Prefer app launch for known app keywords
            if normalized in {
                "spotify",
                "alarm",
                "clock",
                "notepad",
                "calculator",
                "calc",
                "chrome",
                "google chrome",
                "edge",
                "microsoft edge",
                "terminal",
                "cmd",
                "command prompt",
                "explorer",
            }:
                blocked = self._gate("app_launch")
                if blocked:
                    return blocked
                return self._handle_app_launch(site)

            blocked = self._gate("web_navigate")
            if blocked:
                return blocked
            return self._handle_website(site, browser)

        app_name = self._extract_app_name(command)
        if app_name:
            blocked = self._gate("app_launch")
            if blocked:
                return blocked
            return self._handle_app_launch(app_name)

        return None

    # ------------------------------------------------------------------
    # Individual task handlers
    # ------------------------------------------------------------------
    def _handle_amazon(self, command: str) -> Optional[str]:
        result: AutomationResponse = self.automation.search_amazon(command)
        return self._finalize_result("search_amazon", result)

    def _handle_whatsapp(self, command: str) -> Optional[str]:
        contact, message = self._extract_contact_message(command)
        if not contact or not message:
            return "Please specify who to message and what to say on WhatsApp."

        result = self.automation.send_whatsapp(contact, message)
        return self._finalize_result("send_whatsapp", result)

    def _handle_browser_summary(self) -> Optional[str]:
        response = self.automation.describe_active_tab()
        return self._finalize_result("describe_active_tab", response)

    def _handle_app_launch(self, app_name: str) -> Optional[str]:
        response = self.automation.launch_application(app_name)
        return self._finalize_result("launch_application", response)

    def _handle_website(self, target: str, browser: Optional[str]) -> Optional[str]:
        self._pending_website = (target, browser)
        response = self.automation.open_website(target, browser=browser)
        return self._finalize_result("open_website", response)

    def _handle_screenshot(self) -> Optional[str]:
        response = self.automation.take_screenshot()
        return self._finalize_result("take_screenshot", response)

    def _handle_screenshot_region(self, x: int, y: int, w: int, h: int) -> Optional[str]:
        try:
            xi, yi, wi, hi = int(x), int(y), int(w), int(h)
        except Exception:
            return "Invalid region parameters."
        response = self.automation.take_screenshot_region(xi, yi, wi, hi)
        return self._finalize_result("take_screenshot_region", response)

    def _handle_ocr_region(self, x: int, y: int, w: int, h: int) -> Optional[str]:
        try:
            xi, yi, wi, hi = int(x), int(y), int(w), int(h)
        except Exception:
            return "Invalid region parameters."
        response = self.automation.ocr_region(xi, yi, wi, hi)
        return self._finalize_result("ocr_region", response)

    def _handle_ocr_screen(self) -> Optional[str]:
        response = self.automation.ocr_screen()
        return self._finalize_result("ocr_screen", response)

    def _handle_type_text(self, text: str) -> Optional[str]:
        response = self.automation.type_text(text)
        return self._finalize_result("type_text", response)

    def _handle_focus(self, title: Optional[str], exe: Optional[str]) -> Optional[str]:
        response = self.automation.focus_window(title=title, exe=exe)
        return self._finalize_result("focus_window", response)

    @staticmethod
    def _strip_quotes(text: str) -> str:
        t = (text or "").strip()
        if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
            t = t[1:-1]
        return t.strip()

    @staticmethod
    def _split_chained_commands(command: str) -> list[str]:
        parts = [p.strip() for p in _CHAIN_SPLIT_PATTERN.split(command or "") if p and p.strip()]
        if len(parts) > 1:
            return parts
        lowered = (command or "").strip().lower()
        if "youtube" in lowered or " yt" in lowered:
            return []
        if re.search(
            r"\b(click|double\s+click|scroll|type|enter|write|input|ocr|read|screenshot|capture|reload|refresh|focus|switch\s+to|bring\s+up|activate|open|launch|start|play)\b.*\band\b.*\b(click|double\s+click|scroll|type|enter|write|input|ocr|read|screenshot|capture|reload|refresh|focus|switch\s+to|bring\s+up|activate|open|launch|start|play)\b",
            lowered,
        ):
            and_parts = [p.strip() for p in re.split(r"\s*(?:,|;)?\s+and\s+", command or "") if p and p.strip()]
            return and_parts if len(and_parts) > 1 else []
        return []

    @staticmethod
    def _is_duration_token(text: str) -> bool:
        return bool(_DURATION_TOKEN_PATTERN.match((text or "").strip()))

    @staticmethod
    def _normalize_command(command: str) -> str:
        text = (command or "").strip()
        if not text:
            return ""

        parts = re.split(r'(\"[^\"]*\"|\'[^\']*\')', text)
        out: list[str] = []
        for i, seg in enumerate(parts):
            if not seg:
                continue
            if i % 2 == 1:
                out.append(seg)
                continue

            s = seg
            s = re.sub(r"^\s*(?:hey\s+)?jarvis\b\s*[:,]?\s*", "", s, flags=re.IGNORECASE)
            s = re.sub(
                r"^\s*(?:please|plz|can\s+you|could\s+you|would\s+you|will\s+you|kindly)\b\s*", "", s, flags=re.IGNORECASE
            )
            s = re.sub(r"\bdouble\s+tap\b", "double click", s, flags=re.IGNORECASE)
            s = re.sub(r"\b(double\s+)?press\b", lambda m: "double click" if m.group(1) else "click", s, flags=re.IGNORECASE)
            s = re.sub(r"\btap\b", "click", s, flags=re.IGNORECASE)
            s = re.sub(r"\bclick\s+on\b", "click", s, flags=re.IGNORECASE)
            s = re.sub(r"\bopen\s+up\b", "open", s, flags=re.IGNORECASE)
            s = re.sub(r"\b(go|head)\s+(?:to|on|onto|over\s+to)\b", "open", s, flags=re.IGNORECASE)
            s = re.sub(r"\b(?:take|bring)\s+me\s+to\b", "open", s, flags=re.IGNORECASE)
            s = re.sub(r"\bnavigate\s+(?:me\s+)?to\b", "open", s, flags=re.IGNORECASE)
            s = re.sub(r"\bswitch\s+over\s+to\b", "switch to", s, flags=re.IGNORECASE)
            s = re.sub(r"\bpage\s+down\b", "scroll down 350", s, flags=re.IGNORECASE)
            s = re.sub(r"\bpage\s+up\b", "scroll up 350", s, flags=re.IGNORECASE)
            s = re.sub(
                r"\bscroll\s+(up|down)\s+(?:a\s+bit|a\s+little|little|slightly)\b",
                r"scroll \1 250",
                s,
                flags=re.IGNORECASE,
            )
            s = re.sub(
                r"\bscroll\s+(up|down)\s+(?:a\s+lot|a\s+ton|lots|much)\b",
                r"scroll \1 900",
                s,
                flags=re.IGNORECASE,
            )
            s = re.sub(r"\bscroll\s+(up|down)\b(?!\s+(?:by\s+)?\d)", r"scroll \1 350", s, flags=re.IGNORECASE)
            s = re.sub(r"^\s*(?:select|choose)\s+", "click ", s, flags=re.IGNORECASE)
            s = re.sub(r"\bwait\s+for\b", "wait", s, flags=re.IGNORECASE)
            s = re.sub(r"\bwait\s+(a|one)\s+second\b", "wait 1", s, flags=re.IGNORECASE)
            s = re.sub(r"\bwait\s+one\b", "wait 1", s, flags=re.IGNORECASE)
            s = re.sub(r"\bwait\s+a\s+moment\b", "wait", s, flags=re.IGNORECASE)
            s = re.sub(r"\s+", " ", s).strip()
            out.append(s)

        normalized = " ".join([o for o in out if o]).strip()
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    @staticmethod
    def _clean_chain_part(text: str) -> str:
        t = (text or "").strip()
        t = re.sub(r"\bthen\b\s*$", "", t, flags=re.IGNORECASE).strip()
        return t

    @staticmethod
    def _parse_wait_prefix(text: str) -> tuple[float, str | None] | None:
        m = _WAIT_PREFIX_PATTERN.match(text or "")
        if not m:
            return None
        n = m.group("n")
        rest = (m.group("rest") or "").strip() or None
        seconds = AutomationPlanner._parse_wait_seconds(n or "", default_seconds=0.9)
        return seconds, rest

    @staticmethod
    def _is_wait_step(text: str) -> bool:
        return bool(_WAIT_PATTERN.match(text or ""))

    @staticmethod
    def _parse_wait_seconds(text: str, *, default_seconds: float = 0.9) -> float:
        raw = (text or "").strip().lower()
        mapping = {
            "one": 1.0,
            "two": 2.0,
            "three": 3.0,
            "four": 4.0,
            "five": 5.0,
        }
        if raw in mapping:
            return mapping[raw]

        m = _WAIT_PATTERN.match(text or "")
        if m:
            n = m.group("n")
            if not n:
                return default_seconds
            raw = (n or "").strip().lower()
            if raw in mapping:
                return mapping[raw]
            try:
                return max(0.0, float(n))
            except Exception:
                return default_seconds
        try:
            return max(0.0, float(raw))
        except Exception:
            return default_seconds

    def _ensure_uia_snapshot(self, snapshot: dict | None) -> dict | None:
        if self.awareness_state is None:
            return snapshot
        if self._snapshot_has_clickable_uia(snapshot):
            return snapshot
        try:
            latest = self.awareness_state.get_snapshot()
            if self._snapshot_has_clickable_uia(latest):
                return latest
        except Exception:
            pass
        return self._refresh_snapshot(snapshot, min_timestamp=time.time(), timeout_s=5.0, require_uia=True)

    @staticmethod
    def _snapshot_has_clickable_uia(snapshot: dict | None) -> bool:
        if not isinstance(snapshot, dict):
            return False
        uia = snapshot.get("uia") if isinstance(snapshot.get("uia"), dict) else {}
        elements = uia.get("elements") if isinstance(uia.get("elements"), list) else []
        for el in elements:
            if not isinstance(el, dict):
                continue
            rect = el.get("bounding_rect")
            name = el.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            if not (
                isinstance(rect, (list, tuple))
                and len(rect) == 4
                and all(isinstance(v, (int, float)) for v in rect)
                and float(rect[2]) > float(rect[0])
                and float(rect[3]) > float(rect[1])
            ):
                continue
            return True
        return False

    def _refresh_snapshot(
        self,
        previous: dict | None,
        *,
        timeout_s: float = 2.2,
        interval_s: float = 0.15,
        min_timestamp: float | None = None,
        require_uia: bool = False,
    ) -> dict | None:
        if self.awareness_state is None:
            return previous

        deadline = time.time() + timeout_s
        latest = previous
        while time.time() < deadline:
            try:
                latest = self.awareness_state.get_snapshot()
            except Exception:
                return previous
            if not isinstance(latest, dict):
                return previous

            if require_uia and not self._snapshot_has_clickable_uia(latest):
                try:
                    time.sleep(interval_s)
                except Exception:
                    break
                continue

            try:
                meta2 = latest.get("meta") if isinstance(latest.get("meta"), dict) else {}
                ts2 = meta2.get("timestamp") if isinstance(meta2, dict) else None
                if min_timestamp is not None and isinstance(ts2, (int, float)):
                    if float(ts2) >= float(min_timestamp):
                        return latest
            except Exception:
                pass

            try:
                time.sleep(interval_s)
            except Exception:
                break

        return latest

    @staticmethod
    def _looks_like_explicit_command(text: str) -> bool:
        low = (text or "").strip().lower()
        return bool(
            re.match(
                r"^(double\s+click|click|scroll|page\s+down|page\s+up|type|enter|ocr|read|screenshot|capture|reload|refresh|focus|switch\s+to|bring\s+up|activate|open|launch|start|play|cancel|stop|never\s+mind|forget\s+it|undo|undo\s+that|go\s+back|reverse\s+that)\b",
                low,
            )
        )

    def _inherit_leading_verb(self, first: str, rest: str) -> str:
        if self._looks_like_explicit_command(rest):
            return rest.strip()
        first_low = (first or "").strip().lower()
        if first_low.startswith("double click "):
            return f"double click {rest.strip()}"
        if first_low.startswith("click "):
            return f"click {rest.strip()}"
        if first_low.startswith("scroll "):
            return f"scroll {rest.strip()}"
        return rest.strip()

    @staticmethod
    def _rect_center(rect: tuple[int, int, int, int]) -> tuple[int, int]:
        l, t, r, b = rect
        return (int((l + r) / 2), int((t + b) / 2))

    def _what_is_focused(self, snapshot: dict | None) -> str:
        if not isinstance(snapshot, dict) or not snapshot:
            return "Perception snapshot unavailable; can't determine focus safely."

        uia = snapshot.get("uia") if isinstance(snapshot.get("uia"), dict) else {}
        elements = uia.get("elements") if isinstance(uia.get("elements"), list) else []
        for el in elements:
            if isinstance(el, dict) and el.get("focused"):
                name = el.get("name") or "(unnamed)"
                ctype = el.get("control_type") or "unknown"
                return f"Focused element: {name} [{ctype}]."
        return "I couldn't determine the focused element from the current snapshot."

    def _handle_click(self, x: str, y: str, snapshot: dict | None) -> str:
        result = self.automation.click(int(x), int(y))
        return self._finalize_result("desktop_click", result)

    def _handle_double_click(self, x: str, y: str, snapshot: dict | None) -> str:
        result = self.automation.double_click(int(x), int(y))
        return self._finalize_result("desktop_double_click", result)

    def _handle_scroll(self, direction: str, n: str, snapshot: dict | None) -> str:
        amt = int(n)
        if (direction or "").lower().strip() == "down":
            amt = -abs(amt)
            self._last_scroll_direction = "down"
        else:
            amt = abs(amt)
            self._last_scroll_direction = "up"
        self._last_scroll_amount = abs(int(amt))
        result = self.automation.scroll(amt)
        return self._finalize_result("desktop_scroll", result)

    def _find_uia_element(self, snapshot: dict, query: str) -> tuple[dict, tuple[int, int, int, int]] | None:
        q = (query or "").strip().lower()
        if not q:
            return None

        uia = snapshot.get("uia") if isinstance(snapshot.get("uia"), dict) else {}
        elements = uia.get("elements") if isinstance(uia.get("elements"), list) else []

        candidates = []
        for el in elements:
            if not isinstance(el, dict):
                continue
            name = el.get("name")
            rect = el.get("bounding_rect")
            if not isinstance(name, str) or not name.strip():
                continue
            if not (
                isinstance(rect, (list, tuple))
                and len(rect) == 4
                and all(isinstance(v, (int, float)) for v in rect)
                and float(rect[2]) > float(rect[0])
                and float(rect[3]) > float(rect[1])
            ):
                continue
            nl = name.strip().lower()
            if q == nl:
                candidates.append((0, len(nl), el, (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))))
            elif q in nl:
                candidates.append((1, len(nl), el, (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))))

        if not candidates:
            return None
        candidates.sort(key=lambda x: (x[0], x[1]))
        _, _, el, rect = candidates[0]
        return el, rect

    def _handle_click_element(self, name: str, snapshot: dict | None) -> str:
        if not isinstance(snapshot, dict) or not snapshot:
            return "Perception snapshot unavailable; can't click element safely."

        q = self._strip_quotes(name)
        found = self._find_uia_element(snapshot, q)
        if not found:
            preview = self._preview_clickable_uia(snapshot)
            return (
                f"I couldn't find an element named '{q}' with a clickable bounding box in the current snapshot. "
                f"Clickable UIA names I can see: {preview}."
            )
        el, rect = found
        cx, cy = self._rect_center(rect)
        self._record_tool_result("matched_uia_element", AutomationResponse(True, f"name={el.get('name')} rect={rect}"))
        result = self.automation.click(cx, cy)
        return self._finalize_result("desktop_click_element", result)

    @staticmethod
    def _merge_rects(rects: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
        left = min(r[0] for r in rects)
        top = min(r[1] for r in rects)
        right = max(r[2] for r in rects)
        bottom = max(r[3] for r in rects)
        return (left, top, right, bottom)

    def _handle_click_text(self, phrase: str, snapshot: dict | None) -> str:
        if not isinstance(snapshot, dict) or not snapshot:
            return "Perception snapshot unavailable; can't click text safely."

        q = self._strip_quotes(phrase).lower()
        if not q:
            return "Please provide text to click."

        found = self._find_uia_element(snapshot, q)
        if found:
            el, rect = found
            cx, cy = self._rect_center(rect)
            self._record_tool_result(
                "matched_uia_text",
                AutomationResponse(True, f"name={el.get('name')} rect={rect}"),
            )
            result = self.automation.click(cx, cy)
            return self._finalize_result("desktop_click_text", result)

        ocr = snapshot.get("ocr") if isinstance(snapshot.get("ocr"), dict) else {}
        boxes = ocr.get("word_boxes") if isinstance(ocr.get("word_boxes"), list) else []
        if not boxes:
            return "No OCR word boxes are available in the current snapshot. Run OCR first (e.g., 'ocr region x y w h' or 'ocr screen')."

        tokens = [t for t in re.split(r"\s+", q) if t]
        words: list[str] = []
        rects: list[tuple[int, int, int, int]] = []
        for b in boxes:
            if not isinstance(b, dict):
                continue
            txt = b.get("text")
            rect = b.get("bounding_rect")
            if not isinstance(txt, str) or not txt.strip():
                continue
            if not (
                isinstance(rect, (list, tuple))
                and len(rect) == 4
                and all(isinstance(v, (int, float)) for v in rect)
            ):
                continue
            words.append(txt.strip().lower())
            rects.append((int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])))

        match_rect: tuple[int, int, int, int] | None = None
        if tokens and len(tokens) <= len(words):
            for i in range(0, len(words) - len(tokens) + 1):
                if words[i : i + len(tokens)] == tokens:
                    match_rect = self._merge_rects(rects[i : i + len(tokens)])
                    break
        if match_rect is None:
            for i, w in enumerate(words):
                if q in w:
                    match_rect = rects[i]
                    break
        if match_rect is None:
            return f"I couldn't find text '{q}' in the OCR snapshot."

        cx, cy = self._rect_center(match_rect)
        self._record_tool_result("matched_ocr_text", AutomationResponse(True, f"phrase={q} rect={match_rect}"))
        result = self.automation.click(cx, cy)
        return self._finalize_result("desktop_click_text", result)

    def _describe_screen(self, snapshot: dict | None) -> str:
        if isinstance(snapshot, dict) and snapshot:
            try:
                return redact_snapshot_for_prompt(snapshot)
            except Exception:
                pass

        if not self.awareness_state:
            return "Screen awareness is not enabled yet."

        window = self.awareness_state.get_window()
        if not window:
            return "I can't detect the current window yet."

        title = window.title or "(untitled)"
        app = window.app_exe or "(unknown app)"
        details = f"Active window: {title} ({app})."

        elements = [e for e in (window.elements or []) if e and e.name]
        if elements:
            names = ", ".join([e.name for e in elements[:5] if e.name])
            details += f" Visible elements: {names}."
        return details

    @staticmethod
    def _matches_amazon(text: str) -> bool:
        return "amazon" in text and any(keyword in text for keyword in _AMAZON_ACTION_KEYWORDS)

    @staticmethod
    def _matches_whatsapp(text: str) -> bool:
        if "whatsapp" in text:
            return True
        return bool(_WHATSAPP_PATTERN.search(text))

    @staticmethod
    def _matches_screen_intent(text: str) -> bool:
        return any(keyword in text for keyword in _SCREEN_INTENT_KEYWORDS) or bool(_SCREEN_INTENT_PATTERN.search(text))

    @staticmethod
    def _preview_clickable_uia(snapshot: dict, *, limit: int = 12) -> str:
        uia = snapshot.get("uia") if isinstance(snapshot.get("uia"), dict) else {}
        elements = uia.get("elements") if isinstance(uia.get("elements"), list) else []
        names: list[str] = []
        for el in elements:
            if not isinstance(el, dict):
                continue
            name = el.get("name")
            rect = el.get("bounding_rect")
            if not isinstance(name, str) or not name.strip():
                continue
            if not (
                isinstance(rect, (list, tuple))
                and len(rect) == 4
                and all(isinstance(v, (int, float)) for v in rect)
                and float(rect[2]) > float(rect[0])
                and float(rect[3]) > float(rect[1])
            ):
                continue
            names.append(name.strip())
            if len(names) >= limit:
                break
        if not names:
            return "(none)"
        return ", ".join(names)

    @staticmethod
    def _matches_browser_summary(text: str) -> bool:
        return bool(_BROWSER_INTENT_PATTERN.search(text))

    @staticmethod
    def _extract_app_name(command: str) -> Optional[str]:
        match = _LAUNCH_PATTERN.search(command)
        if not match:
            return None
        app = (match.group("app") or "").strip()
        if not app:
            return None
        normalized = app.lower()
        if normalized.startswith("the "):
            app = app[4:]
        return app.strip()

    @staticmethod
    def _extract_website(command: str) -> Optional[Tuple[str, Optional[str]]]:
        match = _WEBSITE_PATTERN.search(command)
        if not match:
            return None

        site = (match.group("site") or "").strip()
        if not site:
            return None

        browser = None
        click_first = False
        click_first = False
        lowered = site.lower()
        cmd_lower = command.lower()
        # Only divert to app launch for explicit media-play intent on Spotify
        if "play" in cmd_lower and lowered == "spotify":
            return None

        for keyword in ("in chrome", "on chrome", "in edge", "on edge", "in browser"):
            if keyword in lowered:
                pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                site = pattern.sub("", site).strip()
                if "chrome" in keyword:
                    browser = "chrome"
                elif "edge" in keyword:
                    browser = "edge"
                else:
                    browser = None
                break

        site = site.strip()
        if not site:
            return None
        return site, browser

    @staticmethod
    def _extract_youtube_search(command: str) -> Optional[Tuple[str, Optional[str], bool]]:
        """Extract a YouTube search query from commands like:
        - "open youtube and search hindi songs"
        - "search hindi songs on youtube"
        Optionally capture a browser hint like 'in chrome'/'on edge'.
        """
        text = command.strip()
        lowered = text.lower()

        browser = None
        click_first = False
        for keyword in ("in chrome", "on chrome", "in edge", "on edge"):
            if keyword in lowered:
                if "chrome" in keyword:
                    browser = "chrome"
                elif "edge" in keyword:
                    browser = "edge"
                break

        # Pattern 1: open youtube [and] search <query> [and click (on) (the) first (result|one)]
        m1 = re.search(r"open\s+(?:youtube|yt)\s+(?:and\s+)?search\s+(?P<q>.+)", text, flags=re.IGNORECASE)
        if m1:
            q = (m1.group("q") or "").strip()
            # Detect click-first intent
            if re.search(r"\bclick\s+(on\s+)?(the\s+)?first\s+(result|one)\b", q, flags=re.IGNORECASE):
                click_first = True
                q = re.sub(r"\b(and\s+)?click\s+(on\s+)?(the\s+)?first\s+(result|one)\b", "", q, flags=re.IGNORECASE).strip()
            # Strip any trailing browser hint
            q = re.sub(r"\s+(in|on)\s+(chrome|edge)\s*$", "", q, flags=re.IGNORECASE)
            return (q, browser, click_first) if q else None

        # Pattern 2: search <query> on youtube [and click (on) (the) first (result|one)]
        m2 = re.search(r"(?:search|find|look up)\s+(?P<q>.+?)\s+(?:on|in)\s+(?:youtube|yt)", text, flags=re.IGNORECASE)
        if m2:
            q = (m2.group("q") or "").strip()
            # optional trailing 'and click first result'
            if re.search(r"\bclick\s+(on\s+)?(the\s+)?first\s+(result|one)\b", text, flags=re.IGNORECASE):
                click_first = True
            return (q, browser, click_first) if q else None

        return None

    @staticmethod
    def _matches_screenshot(text: str) -> bool:
        return any(keyword in text for keyword in _SCREENSHOT_KEYWORDS)

    @staticmethod
    def _wants_focus(text: str) -> bool:
        """Check if the given text wants to focus on a window."""
        return bool(_FOCUS_PATTERN.search(text))

    @staticmethod
    def _extract_contact_message(command: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract contact and message from the given command."""
        match = _WHATSAPP_PATTERN.search(command)
        if not match:
            return None, None

        contact = (match.group("contact") or "").strip().strip("'\"")
        message = match.group("message")
        if message:
            message = message.strip().strip("'\"")
        return contact or None, message or None

    @staticmethod
    def _extract_focus_target(command: str) -> Optional[Tuple[Optional[str], Optional[str]]]:
        match = _FOCUS_PATTERN.search(command)
        if not match:
            return None
        target = (match.group("target") or "").strip()
        if not target:
            return None

        normalized = target.lower()
        if normalized in {"window", "the window", "this window", "that window"}:
            return None

        if normalized.endswith(".exe"):
            return None, target

        return target, None

    @staticmethod
    def _extract_type_text(command: str) -> Optional[str]:
        match = _TYPE_PATTERN.search(command)
        if not match:
            return None

        text = (match.group("text") or "").strip()
        if not text:
            return None

        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            text = text[1:-1]

        return text.strip() or None

    @staticmethod
    def _with_recovery(msg: str) -> str:
        low = (msg or "").lower()
        if any(k in low for k in ("failed", "couldn't", "error", "unavailable")):
            return msg + " I can try reloading or refocusing and retrying. Say 'retry' or 'reload and try again'."
        return msg
