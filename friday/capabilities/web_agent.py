"""Generic web agent — observe → decide → act, on ANY site, ZERO hardcoding.

This is the answer to "don't hardcode Gmail/WhatsApp/etc." There is NO
site-specific logic. The loop is:

    1. OBSERVE   — read the live page's interactive elements (links, buttons,
                   inputs) with indices.
    2. DECIDE    — the LLM sees the goal + the current elements + history and
                   chooses ONE atomic next action (click N / type into N /
                   press key / navigate / done).
    3. ACT       — execute that single action via the browser controller.
    4. Repeat until the LLM says the goal is achieved (or step budget hit).

Because the LLM reasons over the ACTUAL live DOM each step, the same loop
handles Gmail, Instagram, YouTube, a bank, an unfamiliar site — anything a
human could operate by looking and clicking. New sites need no new code.

This composes the existing pieces (BrowserController.observe_interactive /
click_index / fill_index / press / navigate) under LLM control. It is the
capability the planner invokes for "operate a website" requirements.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


SYSTEM_PROMPT = (
    "You are operating a web browser to accomplish a user's goal, like a human "
    "looking at the screen and clicking. You are given the GOAL, the current "
    "page URL/title, a numbered list of INTERACTIVE elements on the page, and a "
    "short history of what you've done.\n\n"
    "Choose the SINGLE next action. Respond ONLY with a JSON object:\n"
    '  {"action": "click", "index": N, "why": "..."}\n'
    '  {"action": "type", "index": N, "text": "...", "why": "..."}\n'
    '  {"action": "press", "key": "Enter", "why": "..."}\n'
    '  {"action": "scroll", "direction": "down", "why": "reveal more results"}\n'
    '  {"action": "navigate", "url": "https://...", "why": "..."}\n'
    '  {"action": "click_vision", "describe": "the blue Send button at bottom right", "why": "..."}\n'
    '  {"action": "done", "why": "goal achieved because ..."}\n'
    '  {"action": "stuck", "why": "cannot proceed because ..."}\n\n'
    "Rules: prefer clicking by index from the list (most reliable). Elements "
    "marked (off-screen) need a 'scroll' first, or just click them (the system "
    "scrolls them into view). Use 'scroll' (direction down/up/top/bottom) to "
    "reveal content/elements not yet listed. Use 'click_vision' ONLY when the "
    "target is visible but NOT in the element list (canvas/icon/custom widget). "
    "Use 'done' only when the goal is actually complete. Use 'stuck' if blocked "
    "(login wall, captcha). One action only."
)


@dataclass
class WebAgentResult:
    """Outcome of running the generic web agent toward a goal."""

    goal: str
    achieved: bool = False
    steps_taken: int = 0
    final_url: str = ""
    history: List[str] = field(default_factory=list)
    stuck_reason: str = ""


class WebAgent:
    """LLM-driven observe→decide→act loop over a live browser. No hardcoding."""

    def __init__(self, browser_controller, model_router, *, max_steps: int = 12,
                 vision=None) -> None:
        self._browser = browser_controller
        self._router = model_router
        self._max_steps = max_steps
        # Vision fallback (ADR-014): used only when DOM can't resolve a target.
        if vision is None and model_router is not None:
            try:
                from friday.perception.vision import VisionPerception
                vision = VisionPerception(model_router=model_router)
            except Exception:
                vision = None
        self._vision = vision

    def run(self, goal: str, evidence=None) -> WebAgentResult:
        result = WebAgentResult(goal=goal)
        if not self._browser or not getattr(self._browser, "available", False):
            result.stuck_reason = "no browser available"
            return result
        if not self._router:
            result.stuck_reason = "no model router for decision-making"
            return result

        from friday.verification.screenshot_evidence import (
            is_blocked_page, capture_screenshot,
        )

        last_action_summary = "(none)"
        repeat_count = 0
        prev_signature = ""

        for step in range(self._max_steps):
            obs = self._browser.observe_interactive()
            if not obs.get("ok"):
                result.stuck_reason = f"observe failed: {obs.get('error')}"
                break

            elements = obs.get("elements", [])
            url, title = obs.get("url", ""), obs.get("title", "")

            # Block detection (captcha/login wall) — honest stop, no loop.
            page_text = self._browser.read_text(1500) if hasattr(self._browser, "read_text") else ""
            if is_blocked_page(page_text, url, title):
                shot = capture_screenshot(label="webagent_blocked")
                if evidence is not None and shot.is_real:
                    evidence.add_screenshot(shot.path, shot.size, "webagent_blocked")
                result.stuck_reason = "verification/login wall encountered"
                break

            decision = self._decide(goal, url, title, elements,
                                    result.history, last_action_summary)
            action = decision.get("action", "stuck")

            # Anti-loop: if the LLM repeats the same action+target with no page
            # change, force progress (a typed search box almost always needs
            # Enter; otherwise stop honestly).
            signature = f"{action}:{decision.get('index')}:{decision.get('text','')[:20]}:{url}"
            if signature == prev_signature:
                repeat_count += 1
            else:
                repeat_count = 0
            prev_signature = signature

            if repeat_count >= 1 and action == "type":
                # We already typed this; submit it instead of retyping.
                self._browser.press("Enter")
                last_action_summary = "pressed Enter to submit the typed text"
                result.history.append("press: Enter (auto-submit after repeated type)")
                self._record_step_evidence(evidence, step, url)
                result.steps_taken = step + 1
                continue
            if repeat_count >= 2:
                result.stuck_reason = f"repeated '{action}' with no progress"
                break

            result.history.append(f"{action}: {decision.get('why','')[:60]}")

            if action == "done":
                result.achieved = True
                break
            if action == "stuck":
                result.stuck_reason = decision.get("why", "agent stuck")
                break

            # Execute and capture the observable effect for next-step feedback.
            before_url = url
            if action == "navigate":
                r = self._browser.navigate(decision.get("url", ""))
                last_action_summary = f"navigated to {decision.get('url','')}"
            elif action == "click":
                r = self._browser.click_index(decision.get("index", -1), elements)
                last_action_summary = f"clicked element [{decision.get('index')}]"
                # Silent no-op escalation: if the click neither changed the URL
                # nor reported a state change, the locator likely hit the wrong
                # (or non-interactive) node. Auto-escalate to a vision click on
                # the element's own label so we don't silently stall.
                clicked_el = next(
                    (e for e in elements if e.get("index") == decision.get("index")), None)
                no_op = (isinstance(r, dict) and r.get("ok")
                         and r.get("changed") is False)
                if no_op and clicked_el and clicked_el.get("text"):
                    self._click_via_vision(clicked_el["text"], result)
                    last_action_summary += (
                        f" (no change — auto-escalated to vision click on "
                        f"'{clicked_el['text'][:30]}')")
            elif action == "click_vision":
                self._click_via_vision(decision.get("describe", ""), result)
                last_action_summary = f"vision-clicked '{decision.get('describe','')[:30]}'"
            elif action == "type":
                fr = self._browser.fill_index(decision.get("index", -1),
                                              decision.get("text", ""), elements)
                if fr.get("verified"):
                    last_action_summary = (
                        f"typed '{decision.get('text','')[:30]}' into element "
                        f"[{decision.get('index')}] and VERIFIED it landed. "
                        f"Now press Enter or click a result.")
                else:
                    last_action_summary = (
                        f"tried to type into element [{decision.get('index')}] but "
                        f"the text did NOT land (field shows '{fr.get('landed','')[:30]}'). "
                        f"Try a different input element index.")
            elif action == "press":
                self._browser.press(decision.get("key", "Enter"))
                last_action_summary = f"pressed {decision.get('key','Enter')}"
            elif action == "scroll":
                sr = self._browser.scroll(decision.get("direction", "down")) \
                    if hasattr(self._browser, "scroll") else {"scrolled": False}
                last_action_summary = (f"scrolled {decision.get('direction','down')}"
                                       f" ({'new content' if sr.get('scrolled') else 'no change'})")

            # Note whether the URL actually changed (key progress signal).
            after_url = (self._browser.current_url()
                        if hasattr(self._browser, "current_url") else before_url)
            if after_url != before_url:
                last_action_summary += f" → page changed to {after_url[:60]}"
            else:
                last_action_summary += " → page did NOT change"

            result.steps_taken = step + 1
            self._record_step_evidence(evidence, step, after_url)

        result.final_url = (self._browser.current_url()
                            if hasattr(self._browser, "current_url") else "")
        return result

    def _record_step_evidence(self, evidence, step, url) -> None:
        if evidence is None:
            return
        from friday.verification.screenshot_evidence import capture_screenshot
        if url:
            evidence.add_navigation(url)
        shot = capture_screenshot(label=f"webagent_step{step+1}")
        if shot.is_real:
            evidence.add_screenshot(shot.path, shot.size, f"webagent_step{step+1}")

    def _click_via_vision(self, description: str, result) -> None:
        """Vision fallback click: locate a described target visually and click it.

        Used when the DOM scan missed an element the user can see (canvas
        widgets, icons, image maps). Screenshots the page, asks the VLM for the
        target's normalized center, scales to viewport pixels, and clicks.
        """
        if not self._vision or not getattr(self._vision, "available", False):
            result.history.append("click_vision: vision unavailable")
            return
        if not hasattr(self._browser, "screenshot_image"):
            result.history.append("click_vision: browser cannot screenshot")
            return

        shot = self._browser.screenshot_image()
        if shot is None:
            result.history.append("click_vision: screenshot failed")
            return

        import concurrent.futures as cf
        import asyncio
        try:
            with cf.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(asyncio.run,
                                  self._vision.locate_element(shot, description))
                coords = fut.result(timeout=40)
        except Exception:
            coords = None

        if not coords:
            result.history.append(f"click_vision: '{description[:40]}' not found visually")
            return

        vp = self._browser.viewport_size() if hasattr(self._browser, "viewport_size") else {"width": 1280, "height": 800}
        px = int(coords[0] * vp["width"])
        py = int(coords[1] * vp["height"])
        self._browser.click_xy(px, py)
        result.history.append(f"click_vision: clicked '{description[:30]}' at ({px},{py})")

    def _decide(self, goal, url, title, elements, history, last_action="(none)") -> Dict[str, Any]:
        """Ask the LLM for the single next action given the live page."""
        el_lines = []
        for e in elements:
            kind = "input" if e.get("editable") else e.get("role", "el")
            marker = "" if e.get("in_view", True) else " (off-screen)"
            el_lines.append(f'[{e.get("index")}] {kind}{marker}: "{e.get("text","")}"')
        elements_text = "\n".join(el_lines) if el_lines else "(no interactive elements)"
        hist = "\n".join(f"- {h}" for h in history[-6:]) or "(none yet)"

        prompt = (
            f"GOAL: {goal}\n\n"
            f"PAGE: {title} — {url}\n\n"
            f"LAST ACTION RESULT: {last_action}\n\n"
            f"INTERACTIVE ELEMENTS:\n{elements_text}\n\n"
            f"HISTORY:\n{hist}\n\n"
            "IMPORTANT: if you just typed into a search box, the next action is "
            "usually 'press' Enter or 'click' the search/submit button — do NOT "
            "type the same thing again. If the page did NOT change after your "
            "last action, try a DIFFERENT action.\n"
            "Next action (JSON only):"
        )

        try:
            from friday.models.router import ModelCapability
            import concurrent.futures as cf
            with cf.ThreadPoolExecutor(max_workers=1) as pool:
                import asyncio
                fut = pool.submit(asyncio.run, self._router.complete(
                    prompt,
                    capability=ModelCapability.REASONING,
                    model="qwen/qwen3-next-80b-a3b-instruct",  # fast + accurate
                    max_tokens=200,
                    temperature=0.1,
                    system_prompt=SYSTEM_PROMPT,
                ))
                resp = fut.result(timeout=40)
            return self._parse(resp.text)
        except Exception as exc:
            return {"action": "stuck", "why": f"decision error: {exc}"}

    def _parse(self, text: str) -> Dict[str, Any]:
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start < 0 or end <= start:
                return {"action": "stuck", "why": "unparseable decision"}
            return json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError):
            return {"action": "stuck", "why": "invalid JSON decision"}
