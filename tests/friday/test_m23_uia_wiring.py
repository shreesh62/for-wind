"""M23 — Universal Perception UIA wiring (production path).

Feature: m23-browser-generic-desktop-environment

Verifies the executor threads an awareness `state_cache` into a UIA-backed
DesktopPerception so the Accessibility tier of the fused WorldState is populated
on the live path. Hermetic: `populate_active_window` is stubbed to capture the
injected desktop source (no real screen/UIA/OCR I/O).
"""


def test_executor_threads_state_cache_into_desktop_perception(monkeypatch):
    # Validates: Requirements 1.1, 1.2 (UIA tier fed from the awareness state cache)
    import friday.executor as ex
    import friday.perception.active_window as aw

    captured = {}

    def _fake_populate(builder, *, desktop=None, ocr=None, screen=None,
                       vision=None, want_vision=False):
        captured["desktop"] = desktop
        return builder

    # Executor imports populate_active_window locally from this module at call time.
    monkeypatch.setattr(aw, "populate_active_window", _fake_populate)

    sentinel_cache = object()  # stands in for awareness_controller.state_cache
    executor = ex.GoalExecutor(state_cache=sentinel_cache)
    # Force the live path (verification/perception only runs when not dry-run).
    monkeypatch.setattr(executor, "_dry_run", False)

    executor._build_world_state()

    desktop = captured.get("desktop")
    assert desktop is not None, "no DesktopPerception was injected"
    assert getattr(desktop, "_state_cache", None) is sentinel_cache


def test_executor_without_state_cache_injects_no_desktop(monkeypatch):
    # Benchmark-runner path (no awareness controller): desktop defaults inside
    # populate_active_window (passed as None), behavior unchanged.
    import friday.executor as ex
    import friday.perception.active_window as aw

    captured = {}

    def _fake_populate(builder, *, desktop=None, **kw):
        captured["desktop"] = desktop
        return builder

    monkeypatch.setattr(aw, "populate_active_window", _fake_populate)
    executor = ex.GoalExecutor()  # no state_cache
    monkeypatch.setattr(executor, "_dry_run", False)
    executor._build_world_state()
    assert captured.get("desktop") is None
