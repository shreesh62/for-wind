"""Root pytest configuration — global safety for the ENTIRE test tree.

Forces FRIDAY_DRY_RUN=1 before any test/module imports so NO test (friday or
legacy) can launch a real browser, app, or drive keyboard/mouse. This applies
to `python -m pytest` (whole tree), not just `tests/friday/`.
"""

import os

os.environ.setdefault("FRIDAY_DRY_RUN", "1")
os.environ.setdefault("FRIDAY_REQUIRE_REAL_CHROME", "0")
os.environ.setdefault("AUTO_LAUNCH_CHROME", "0")
os.environ.setdefault("DISABLE_BROWSER_TRACKER", "1")
os.environ.setdefault("DISABLE_MIC", "1")
os.environ.setdefault("DISABLE_WAKE_WORD", "1")
