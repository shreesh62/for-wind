"""Root pytest configuration — global safety for the ENTIRE test tree.

Forces FRIDAY_DRY_RUN=1 before any test/module imports so NO test (friday or
legacy) can launch a real browser, app, or drive keyboard/mouse. This applies
to `python -m pytest` (whole tree), not just `tests/friday/`.
"""

import os
import shutil
import tempfile

os.environ.setdefault("FRIDAY_DRY_RUN", "1")
os.environ.setdefault("FRIDAY_REQUIRE_REAL_CHROME", "0")
os.environ.setdefault("AUTO_LAUNCH_CHROME", "0")
os.environ.setdefault("DISABLE_BROWSER_TRACKER", "1")
os.environ.setdefault("DISABLE_MIC", "1")
os.environ.setdefault("DISABLE_WAKE_WORD", "1")

# HERMETICITY: redirect legacy runtime-state files (memory.json, memory.index,
# interaction_log.json — see vector_memory.py / memory_core.py) OUT of the repo
# tree into a temp dir, so tests never mutate tracked worktree state. Set before
# any module import so the modules' import-time path resolution sees it. When we
# own the default location, start each session from a CLEAN slate so state never
# accumulates across runs.
if "FRIDAY_STATE_DIR" not in os.environ:
    _state_dir = os.path.join(tempfile.gettempdir(), "friday_test_state")
    shutil.rmtree(_state_dir, ignore_errors=True)
    os.makedirs(_state_dir, exist_ok=True)
    os.environ["FRIDAY_STATE_DIR"] = _state_dir
