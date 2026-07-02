"""Tests for the generic web agent — observe→decide→act, no hardcoding.

Uses a fake browser (scripted pages) and a fake router (scripted decisions)
to prove the loop works on ARBITRARY sites without site-specific code.
"""

from __future__ import annotations

import json

import pytest

from friday.capabilities.web_agent import WebAgent, WebAgentResult


class FakeBrowser:
    """Scriptable fake browser exposing the observe/act surface."""

    def __init__(self, pages, blocked_text=""):
        self.available = True
        self._pages = pages          # list of element-lists per observe() call
        self._i = 0
        self._url = "https://site.test/start"
        self.actions = []
        self._blocked_text = blocked_text

    def observe_interactive(self, limit=60):
        els = self._pages[min(self._i, len(self._pages) - 1)]
        return {"ok": True, "url": self._url, "title": "Page", "elements": els}

    def read_text(self, n=1500):
        return self._blocked_text

    def click_index(self, index, elements):
        self.actions.append(("click", index))
        self._i += 1
        self._url = f"https://site.test/after_click_{index}"
        return {"ok": True}

    def fill_index(self, index, value, elements):
        self.actions.append(("type", index, value))
        return {"ok": True}

    def press(self, key):
        self.actions.append(("press", key))
        self._i += 1
        return {"ok": True}

    def navigate(self, url):
        self.actions.append(("navigate", url))
        self._url = url
        self._i += 1
        return {"ok": True, "url": url}

    def scroll(self, direction="down", amount=600):
        self.actions.append(("scroll", direction))
        self._i += 1
        return {"ok": True, "direction": direction, "scrolled": True}

    def current_url(self):
        return self._url


class FakeRouter:
    """Returns scripted JSON decisions in order."""

    def __init__(self, decisions):
        self._decisions = decisions
        self._i = 0

    async def complete(self, prompt, **kwargs):
        from friday.models.router import ModelResponse
        d = self._decisions[min(self._i, len(self._decisions) - 1)]
        self._i += 1
        return ModelResponse(text=json.dumps(d), model_used="fake", provider="fake")


def _els(*texts):
    return [{"index": i, "role": "button", "tag": "button", "text": t,
             "editable": ("input" in t.lower()), "x": 10 + i, "y": 20 + i}
            for i, t in enumerate(texts)]


class TestWebAgentLoop:
    def test_reaches_done_via_clicks(self):
        browser = FakeBrowser(pages=[
            _els("Compose", "Inbox"),
            _els("To input", "Send"),
            _els("Sent"),
        ])
        router = FakeRouter([
            {"action": "click", "index": 0, "why": "open compose"},
            {"action": "click", "index": 1, "why": "send"},
            {"action": "done", "why": "message sent"},
        ])
        agent = WebAgent(browser, router, max_steps=6)
        result = agent.run("send a message")
        assert result.achieved is True
        assert ("click", 0) in browser.actions
        assert ("click", 1) in browser.actions

    def test_type_action_dispatched(self):
        browser = FakeBrowser(pages=[_els("search input", "Go"), _els("Result")])
        router = FakeRouter([
            {"action": "type", "index": 0, "text": "laptops", "why": "search"},
            {"action": "done", "why": "done"},
        ])
        agent = WebAgent(browser, router, max_steps=4)
        result = agent.run("search laptops")
        assert result.achieved is True
        assert ("type", 0, "laptops") in browser.actions

    def test_stuck_is_honest(self):
        browser = FakeBrowser(pages=[_els("Nothing useful")])
        router = FakeRouter([{"action": "stuck", "why": "no path"}])
        agent = WebAgent(browser, router, max_steps=4)
        result = agent.run("do impossible thing")
        assert result.achieved is False
        assert "no path" in result.stuck_reason

    def test_blocked_page_stops_loop(self):
        browser = FakeBrowser(pages=[_els("Login")], blocked_text="verify you are human captcha")
        router = FakeRouter([{"action": "click", "index": 0, "why": "x"}])
        agent = WebAgent(browser, router, max_steps=4)
        result = agent.run("open inbox")
        assert result.achieved is False
        assert "wall" in result.stuck_reason.lower()

    def test_no_browser_is_honest(self):
        agent = WebAgent(None, FakeRouter([]), max_steps=4)
        result = agent.run("anything")
        assert result.achieved is False
        assert "no browser" in result.stuck_reason.lower()

    def test_step_budget_respected(self):
        # Agent that never says done — must stop at max_steps.
        browser = FakeBrowser(pages=[_els("A", "B")])
        router = FakeRouter([{"action": "click", "index": 0, "why": "loop"}])
        agent = WebAgent(browser, router, max_steps=3)
        result = agent.run("never ends")
        assert result.steps_taken <= 3
        assert result.achieved is False

    def test_scroll_action_dispatched(self):
        browser = FakeBrowser(pages=[_els("top item"), _els("revealed item"), _els("done marker")])
        router = FakeRouter([
            {"action": "scroll", "direction": "down", "why": "reveal more"},
            {"action": "done", "why": "found it"},
        ])
        agent = WebAgent(browser, router, max_steps=4)
        result = agent.run("scroll to find content")
        assert result.achieved is True
        assert ("scroll", "down") in browser.actions


class TestVisionFallback:
    def test_click_vision_locates_and_clicks(self, monkeypatch):
        """When DOM lacks the target, click_vision uses vision coords + clicks."""
        from PIL import Image
        from friday.perception.screen import Screenshot

        class _Shot:
            image = Image.new("RGB", (1280, 800))
            width = 1280
            height = 800

        clicks = []

        class _Browser(FakeBrowser):
            def screenshot_image(self):
                return _Shot()
            def viewport_size(self):
                return {"width": 1280, "height": 800}
            def click_xy(self, x, y):
                clicks.append((x, y))
                return {"ok": True}

        class _Vision:
            available = True
            async def locate_element(self, shot, desc):
                return (0.5, 0.25)  # normalized center

        browser = _Browser(pages=[_els("only-a-canvas")])
        router = FakeRouter([
            {"action": "click_vision", "describe": "the play button", "why": "canvas"},
            {"action": "done", "why": "done"},
        ])
        agent = WebAgent(browser, router, max_steps=4, vision=_Vision())
        result = agent.run("press play on the video")
        assert result.achieved is True
        # 0.5*1280=640, 0.25*800=200
        assert (640, 200) in clicks

    def test_click_vision_not_found_is_handled(self):
        class _Vision:
            available = True
            async def locate_element(self, shot, desc):
                return None

        class _Browser(FakeBrowser):
            def screenshot_image(self):
                class S: image=None
                return S()
            def viewport_size(self):
                return {"width": 1280, "height": 800}

        browser = _Browser(pages=[_els("x")])
        router = FakeRouter([
            {"action": "click_vision", "describe": "ghost", "why": "x"},
            {"action": "stuck", "why": "cant find"},
        ])
        agent = WebAgent(browser, router, max_steps=3, vision=_Vision())
        result = agent.run("click ghost")
        assert result.achieved is False


class TestVisionCoordParse:
    def test_parse_normalized_coords(self):
        from friday.perception.vision import VisionPerception
        v = VisionPerception(model_router=None)
        assert v._parse_coords("x=0.82 y=0.94") == (0.82, 0.94)

    def test_parse_not_found(self):
        from friday.perception.vision import VisionPerception
        v = VisionPerception(model_router=None)
        assert v._parse_coords("NOT_FOUND") is None

    def test_parse_out_of_range_rejected(self):
        from friday.perception.vision import VisionPerception
        v = VisionPerception(model_router=None)
        assert v._parse_coords("x=5.0 y=0.5") is None


class TestNoHardcoding:
    def test_no_site_names_in_source(self):
        """The web agent must contain NO site-specific logic."""
        from pathlib import Path
        import friday.capabilities.web_agent as m
        src = Path(m.__file__).read_text(encoding="utf-8").lower()
        # Site names may appear ONLY in the module docstring as examples, not
        # as logic. Assert there are no conditional branches on site names.
        for site in ["gmail", "whatsapp", "instagram"]:
            # allowed in comments/docstring; forbid in if-statements
            assert f'"{site}"' not in src and f"'{site}'" not in src


class TestSilentNoOpEscalation:
    """A click that reports ok but changed=False auto-escalates to vision."""

    def test_no_op_click_escalates_to_vision(self):
        from PIL import Image

        vision_clicks = []

        class _Shot:
            image = Image.new("RGB", (1280, 800))
            width = 1280
            height = 800

        class _Browser(FakeBrowser):
            def click_index(self, index, elements):
                self.actions.append(("click", index))
                # Report success but NO page change (the silent no-op case).
                return {"ok": True, "changed": False,
                        "url_before": self._url, "url_after": self._url}
            def screenshot_image(self):
                return _Shot()
            def viewport_size(self):
                return {"width": 1280, "height": 800}
            def click_xy(self, x, y):
                vision_clicks.append((x, y))
                return {"ok": True}

        class _Vision:
            available = True
            async def locate_element(self, shot, desc):
                return (0.5, 0.5)

        browser = _Browser(pages=[_els("Submit", "Other")])
        router = FakeRouter([
            {"action": "click", "index": 0, "why": "submit the form"},
            {"action": "done", "why": "done"},
        ])
        agent = WebAgent(browser, router, max_steps=3, vision=_Vision())
        result = agent.run("submit form")
        # The no-op click must have triggered a vision click fallback.
        assert vision_clicks, "expected vision escalation after silent no-op click"
        assert (640, 400) in vision_clicks
