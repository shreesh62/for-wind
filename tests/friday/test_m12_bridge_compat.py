"""M12 — Bridge backward-compatibility tests.

Verifies the bridge's kernel routing is a pure superset: default config (no
kernel) preserves the legacy Operator path, and the kernel path degrades safely
when no kernel is wired.

Validates: Requirements 3.1, 3.2, 3.3, 3.4
"""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")

from unittest.mock import patch

from friday.bridge import BridgeConfig, FridayBridge
from friday.router.classifier import ComplexityLevel


def _bridge(**kwargs):
    return FridayBridge(config=BridgeConfig(allow_legacy_fallback=False), **kwargs)


# --------------------------------------------------------------------------- #
# Property 5 — default routes through the kernel (the flip is applied)
# --------------------------------------------------------------------------- #
def test_property5_default_has_kernel_execution_enabled():
    """The BridgeConfig default is now kernel-backed execution (M13 qualified)."""
    bridge = _bridge()
    # Without an injected kernel the bridge degrades to the legacy path, but the
    # CONFIG flag itself is True.
    assert bridge._config.use_kernel_execution is True


def test_property5_multistep_routes_to_kernel_when_kernel_is_wired():
    """With a kernel injected, multi-step goals take the kernel path."""
    from unittest.mock import MagicMock
    from friday.bridge import BridgeConfig, FridayBridge

    kernel = MagicMock()
    bridge = FridayBridge(
        model_router=None,
        config=BridgeConfig(use_kernel_execution=True),
        kernel=kernel,
    )
    with patch.object(bridge, "_execute_multi_step", return_value="LEGACY") as legacy, \
         patch.object(bridge, "_execute_via_kernel", return_value="KERNEL") as kern:
        result = bridge._handle_friday("do a and b", {"automation": None}, ComplexityLevel.MULTI_STEP)
    assert result == "KERNEL"


def test_property5_multistep_degrades_to_legacy_without_kernel():
    """Without a kernel injected, the legacy path is used even though the flag is on."""
    bridge = _bridge()
    with patch.object(bridge, "_execute_multi_step", return_value="LEGACY") as legacy, \
         patch.object(bridge, "_execute_via_kernel", return_value="KERNEL") as kern:
        result = bridge._handle_friday("do a and b", {"automation": None}, ComplexityLevel.MULTI_STEP)
    assert result == "LEGACY"
    legacy.assert_called_once()
    kern.assert_not_called()


def test_property5_flag_on_but_no_kernel_still_legacy():
    # Flag on but kernel not wired ⇒ still legacy (guard requires both).
    bridge = FridayBridge(
        config=BridgeConfig(allow_legacy_fallback=False, use_kernel_execution=True),
    )
    assert bridge._kernel is None
    with patch.object(bridge, "_execute_multi_step", return_value="LEGACY") as legacy, \
         patch.object(bridge, "_execute_via_kernel", return_value="KERNEL") as kern:
        result = bridge._handle_friday("do a and b", {"automation": None}, ComplexityLevel.MULTI_STEP)
    assert result == "LEGACY"
    legacy.assert_called_once()
    kern.assert_not_called()


# --------------------------------------------------------------------------- #
# Property 6 — kernel path degrades safely
# --------------------------------------------------------------------------- #
def test_property6_via_kernel_without_kernel_falls_back_to_legacy():
    bridge = _bridge()
    with patch.object(bridge, "_execute_multi_step", return_value="LEGACY-FALLBACK") as legacy:
        result = bridge._execute_via_kernel("do a and b")
    assert result == "LEGACY-FALLBACK"
    legacy.assert_called_once()


def test_property6_via_kernel_returns_nonempty_string():
    bridge = _bridge()
    with patch.object(bridge, "_execute_multi_step", return_value="something"):
        result = bridge._execute_via_kernel("goal")
    assert isinstance(result, str) and result


# --------------------------------------------------------------------------- #
# Kernel path routing when a kernel IS wired
# --------------------------------------------------------------------------- #
def test_kernel_path_used_when_flag_on_and_kernel_present():
    class _StubKernel:
        def subscribe(self, pattern, handler):
            return "s"

        def submit_goal(self, text, constraints=None):
            return "gid"

    bridge = FridayBridge(
        config=BridgeConfig(allow_legacy_fallback=False, use_kernel_execution=True),
        kernel=_StubKernel(),
    )
    with patch.object(bridge, "_execute_via_kernel", return_value="KERNEL") as kern, \
         patch.object(bridge, "_execute_multi_step", return_value="LEGACY") as legacy:
        result = bridge._handle_friday("multi step goal", {"automation": None}, ComplexityLevel.MULTI_STEP)
    assert result == "KERNEL"
    kern.assert_called_once()
    legacy.assert_not_called()
