"""M23 — Browser Independence property tests.

Feature: m23-browser-generic-desktop-environment

Property 7: strategy defaults to DESKTOP_CONTROL; a CDP mode appears only when
the CDP optimization is explicitly enabled.
Property 6: with CDP disabled vs enabled, the executor records the SAME evidence
kinds from an identical controller behavior (correctness is CDP-independent).
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from friday.actions.browser_strategy import BrowserMode, resolve_browser_strategy


@settings(max_examples=100)
@given(goal=st.text(max_size=48))
def test_p7_default_desktop_cdp_only_when_enabled(goal):
    # Feature: m23-browser-generic-desktop-environment, Property 7:
    # desktop-first default; CDP only when the flag is truthy.
    # Validates: Requirements 3.4, 11.4
    disabled = resolve_browser_strategy(
        goal,
        cdp_reachable_fn=lambda p: True,
        chrome_running_fn=lambda p: True,
        cdp_enabled_fn=lambda: False,
    )
    assert disabled.mode == BrowserMode.DESKTOP_CONTROL

    enabled = resolve_browser_strategy(
        goal,
        cdp_reachable_fn=lambda p: True,
        chrome_running_fn=lambda p: True,
        cdp_enabled_fn=lambda: True,
    )
    assert enabled.uses_cdp  # CDP reachable + enabled -> a CDP mode


class _Controller:
    """A duck-typed controller whose behavior is identical whether it is the CDP
    plugin or the desktop pipeline (the executor only sees the return shapes)."""

    available = True

    def __init__(self):
        self._url = ""

    def navigate(self, url):
        self._url = url
        return {"ok": True, "url": url}

    def read_text(self, max_chars=4000):
        return ""

    def current_url(self):
        return self._url


def _evidence_signature(controller, monkeypatch):
    from friday.executor import GoalExecutor, ExecutionContext
    from friday.tools.registry import ToolCapability
    from friday.verification.evidence_law import EvidenceKind

    # Stub screenshot capture so the test is hermetic (no real screen grab) and
    # deterministic for BOTH controllers.
    import friday.verification.screenshot_evidence as se
    monkeypatch.setattr(
        se, "capture_screenshot",
        lambda *a, **k: type("S", (), {"is_real": False, "path": "", "size": 0})(),
    )

    ex = GoalExecutor(browser_controller=controller)
    ctx = ExecutionContext(goal="open a public page")
    ex._dispatch_navigate("https://example.com", ToolCapability.NAVIGATE_URL, ctx)
    return {k: len(ctx.evidence.of_kind(k)) for k in EvidenceKind}


def test_p6_cdp_equivalence_same_evidence_kinds(monkeypatch):
    # Feature: m23-browser-generic-desktop-environment, Property 6:
    # identical controller behavior yields identical evidence kinds whether the
    # backend is CDP or desktop. Validates: Requirements 3.1, 3.2, 3.3, 3.5
    cdp_like = _Controller()      # stands in for the CDP plugin
    desktop_like = _Controller()  # stands in for the desktop pipeline

    sig_cdp = _evidence_signature(cdp_like, monkeypatch)
    sig_desktop = _evidence_signature(desktop_like, monkeypatch)

    assert sig_cdp == sig_desktop
    # And navigation correctness was actually recorded (not a vacuous match).
    from friday.verification.evidence_law import EvidenceKind
    assert sig_cdp[EvidenceKind.NAVIGATION] == 1
