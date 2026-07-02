"""Tests for friday.verification — verifier and evidence collection."""

import pytest

from friday.actions.result import ActionEvidence, ActionResult, ActionStatus
from friday.perception.types import BoundingBox, BrowserElement, UIElement, WindowInfo
from friday.perception.world_state import WorldState, WorldStateBuilder
from friday.verification.evidence import collect_evidence
from friday.verification.verifier import ActionVerifier, VerificationVerdict


def _make_state(
    window_title="App",
    process="app.exe",
    url=None,
    browser_title=None,
    ui_texts=None,
    ocr_texts=None,
    browser_texts=None,
    screenshot_hash="hash1",
) -> WorldState:
    """Helper to build a WorldState with minimal boilerplate."""
    builder = WorldStateBuilder()
    builder.set_window_info(WindowInfo(
        title=window_title, process_name=process, pid=100
    ))
    builder.set_screenshot_hash(screenshot_hash)

    if url:
        elements = []
        if browser_texts:
            for text in browser_texts:
                elements.append(BrowserElement(
                    tag="button", text=text, role="button", clickable=True
                ))
        builder.set_browser_state(url=url, title=browser_title or "", elements=elements)

    if ui_texts:
        elements = []
        for text in ui_texts:
            elements.append(UIElement(
                text=text, control_type="Button",
                bbox=BoundingBox(x=0, y=0, width=50, height=25),
            ))
        builder.add_ui_elements(elements)

    return builder.build()


class TestCollectEvidence:
    """Test evidence collection from WorldState diffs."""

    def test_no_change(self):
        """Same state produces no-evidence result."""
        state = _make_state(screenshot_hash="aaa")
        evidence = collect_evidence(state, state)

        # Same state, same hash => technically no change
        assert evidence.before_hash == evidence.after_hash
        assert evidence.state_changed is False

    def test_url_changed(self):
        """URL change is detected."""
        before = _make_state(url="https://google.com", screenshot_hash="a1")
        after = _make_state(url="https://gmail.com", screenshot_hash="a2")
        evidence = collect_evidence(before, after)

        assert evidence.url_changed is True
        assert evidence.state_changed is True

    def test_window_changed(self):
        """Window title change is detected."""
        before = _make_state(window_title="Chrome", screenshot_hash="b1")
        after = _make_state(window_title="Notepad", screenshot_hash="b2")
        evidence = collect_evidence(before, after)

        assert evidence.window_changed is True

    def test_text_appeared(self):
        """New text appearing is detected."""
        before = _make_state(ui_texts=["OK"], screenshot_hash="c1")
        after = _make_state(ui_texts=["OK", "Success message"], screenshot_hash="c2")
        evidence = collect_evidence(before, after)

        assert evidence.text_appeared is not None
        assert "Success" in evidence.text_appeared

    def test_text_disappeared(self):
        """Text disappearing is detected."""
        before = _make_state(ui_texts=["Error: Connection failed"], screenshot_hash="d1")
        after = _make_state(ui_texts=[], screenshot_hash="d2")
        evidence = collect_evidence(before, after)

        assert evidence.text_disappeared is not None
        assert "Error" in evidence.text_disappeared

    def test_element_appeared(self):
        """New element appearing is detected."""
        before = _make_state(ui_texts=["Input"], screenshot_hash="e1")
        after = _make_state(ui_texts=["Input", "Submit Form"], screenshot_hash="e2")
        evidence = collect_evidence(before, after)

        assert evidence.element_appeared is not None


class TestActionVerifier:
    """Test ActionVerifier strategies."""

    def setup_method(self):
        self.verifier = ActionVerifier()

    def test_click_verified_on_state_change(self):
        """Click is verified when state changes."""
        before = _make_state(url="https://example.com/page1", screenshot_hash="f1")
        after = _make_state(url="https://example.com/page2", screenshot_hash="f2")

        result = self.verifier.verify("click", "Next button", before, after)

        assert result.verdict == VerificationVerdict.VERIFIED
        assert result.confidence > 0.7

    def test_click_unverified_on_no_change(self):
        """Click is unverified when nothing changes."""
        state = _make_state(screenshot_hash="same")

        result = self.verifier.verify("click", "button", state, state)

        assert result.verdict == VerificationVerdict.UNVERIFIED
        assert "retry_click" in result.repair_hints

    def test_navigate_verified_on_url_match(self):
        """Navigation is verified when URL changes to target."""
        before = _make_state(url="https://google.com", screenshot_hash="g1")
        after = _make_state(url="https://gmail.com", screenshot_hash="g2")

        result = self.verifier.verify(
            "navigate", "gmail",
            before, after,
            expected={"url": "gmail.com"},
        )

        assert result.verdict == VerificationVerdict.VERIFIED
        assert result.confidence >= 0.9

    def test_navigate_unverified_no_url_change(self):
        """Navigation is unverified when URL doesn't change."""
        state = _make_state(url="https://google.com", screenshot_hash="same")

        result = self.verifier.verify("navigate", "gmail.com", state, state)

        assert result.verdict == VerificationVerdict.UNVERIFIED
        assert "retry_navigation" in result.repair_hints

    def test_type_verified_with_text_present(self):
        """Typing is verified when typed text appears in state."""
        before = _make_state(ui_texts=["Search"], screenshot_hash="h1")
        after = _make_state(ui_texts=["Search", "hello world"], screenshot_hash="h2")

        result = self.verifier.verify(
            "type", "search box",
            before, after,
            expected={"typed_text": "hello world"},
        )

        assert result.verdict == VerificationVerdict.VERIFIED
        assert result.confidence >= 0.8

    def test_type_unverified_no_change(self):
        """Typing is unverified when nothing changes."""
        state = _make_state(ui_texts=["Search"], screenshot_hash="same")

        result = self.verifier.verify("type", "input", state, state)

        assert result.verdict == VerificationVerdict.UNVERIFIED
        assert "retype" in result.repair_hints

    def test_scroll_verified_on_content_change(self):
        """Scroll is verified when screen content changes."""
        before = _make_state(screenshot_hash="before_scroll")
        after = _make_state(screenshot_hash="after_scroll")

        result = self.verifier.verify("scroll", "down", before, after)

        assert result.verdict == VerificationVerdict.VERIFIED

    def test_scroll_with_target_text_appearing(self):
        """Scroll is verified when target text becomes visible."""
        before = _make_state(ui_texts=["Header"], screenshot_hash="s1")
        after = _make_state(ui_texts=["Header", "Footer section"], screenshot_hash="s2")

        result = self.verifier.verify("scroll", "Footer", before, after)

        assert result.verdict == VerificationVerdict.VERIFIED
        assert result.confidence >= 0.7

    def test_focus_verified_on_window_change(self):
        """Focus is verified when window changes to target."""
        before = _make_state(window_title="Chrome", screenshot_hash="j1")
        after = _make_state(window_title="Notepad", screenshot_hash="j2")

        result = self.verifier.verify("focus", "Notepad", before, after)

        assert result.verdict == VerificationVerdict.VERIFIED
        assert result.confidence >= 0.9

    def test_dismiss_verified_when_dialog_gone(self):
        """Dismiss is verified when error dialog disappears."""
        before = _make_state(
            ui_texts=["Error: Something failed", "Retry"],
            screenshot_hash="k1",
        )
        after = _make_state(ui_texts=["Welcome"], screenshot_hash="k2")

        result = self.verifier.verify("dismiss_dialog", "error", before, after)

        assert result.verdict == VerificationVerdict.VERIFIED

    def test_login_verified_when_login_screen_gone(self):
        """Login is verified when login keywords disappear."""
        before = _make_state(
            url="https://accounts.google.com/login",
            ui_texts=["Password", "Sign In"],
            screenshot_hash="l1",
        )
        after = _make_state(
            url="https://mail.google.com/inbox",
            ui_texts=["Inbox", "Compose"],
            screenshot_hash="l2",
        )

        result = self.verifier.verify("login", "google", before, after)

        assert result.verdict == VerificationVerdict.VERIFIED
        assert result.confidence >= 0.8

    def test_login_failed_with_error(self):
        """Login fails when error appears after attempt."""
        before = _make_state(
            url="https://login.example.com",
            ui_texts=["Password", "Sign In"],
            screenshot_hash="m1",
        )
        after = _make_state(
            url="https://login.example.com",
            ui_texts=["Password", "Sign In", "Error: Wrong password"],
            screenshot_hash="m2",
        )

        result = self.verifier.verify("login", "example", before, after)

        assert result.verdict == VerificationVerdict.FAILED
        assert "check_credentials" in result.repair_hints

    def test_generic_verification_with_evidence(self):
        """Unknown action types use generic hash-based verification."""
        before = _make_state(screenshot_hash="n1")
        after = _make_state(screenshot_hash="n2")

        result = self.verifier.verify("custom_action", "target", before, after)

        assert result.verdict == VerificationVerdict.VERIFIED
        assert result.confidence == 0.5

    def test_verify_action_result_upgrades_evidence(self):
        """verify_action_result attaches evidence to ActionResult."""
        before = _make_state(url="https://a.com", screenshot_hash="o1")
        after = _make_state(url="https://b.com", screenshot_hash="o2")

        action_result = ActionResult.success(action="navigate", target="b.com")
        assert action_result.verified is False  # No evidence yet

        upgraded = self.verifier.verify_action_result(action_result, before, after)

        assert upgraded.evidence.url_changed is True
        assert upgraded.evidence.has_evidence is True
        assert upgraded.verified is True

    def test_verify_action_result_marks_needs_repair(self):
        """verify_action_result marks failed verification as needs_repair."""
        state = _make_state(screenshot_hash="same")

        # Action claims success but nothing changed
        action_result = ActionResult.success(action="click", target="button")

        upgraded = self.verifier.verify_action_result(action_result, state, state)

        # Should be downgraded since verification found no evidence
        assert upgraded.status == ActionStatus.NEEDS_REPAIR
        assert "retry_click" in upgraded.repair_hints
