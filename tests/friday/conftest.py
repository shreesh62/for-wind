"""Pytest configuration for FRIDAY tests.

CRITICAL SAFETY: forces FRIDAY_DRY_RUN=1 for the ENTIRE test session BEFORE
any test or module import runs. This guarantees that tests which exercise the
operator/executor end-to-end (e.g. operator.run("Open notepad")) can NEVER
launch a real application, browser, or perform real keyboard/mouse actions.

Root cause this fixes: tests like test_trace_records_steps called
operator.run("Open notepad") without mocking SystemActions, so the executor's
OPEN_APPLICATION path ran `subprocess.Popen("notepad", shell=True)` →
`cmd /c "notepad"` → a real Notepad window opened on the developer's machine
every test run. Dry-run blocks all real external actions.
"""

import os

# Set BEFORE any friday module is imported so module-level reads see it.
os.environ.setdefault("FRIDAY_DRY_RUN", "1")
os.environ.setdefault("FRIDAY_REQUIRE_REAL_CHROME", "0")
os.environ.setdefault("AUTO_LAUNCH_CHROME", "0")


import pytest


@pytest.fixture(autouse=True)
def _enforce_dry_run(monkeypatch):
    """Belt-and-suspenders: ensure dry-run stays on for every test."""
    monkeypatch.setenv("FRIDAY_DRY_RUN", "1")
    yield
