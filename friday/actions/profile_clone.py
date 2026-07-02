"""Profile clone — logged-in CDP automation without touching the live profile.

THE RELIABLE ANSWER for "any task, anytime":
Google blocks --remote-debugging-port on a profile that is signed in with sync
(security: stops cookie/token theft). So CDP fails on your real "Shreesh"
profile but works on a fresh one. A fresh one has no logins, though.

The fix used by every serious automation setup: CLONE the login-bearing state
(cookies, login data, local/session storage, etc.) from your real profile into
a dedicated automation User-Data dir, and run CDP Chrome on THAT. You keep your
logins (you're signed into Instagram/Gmail/etc.) AND CDP works. Your live Chrome
is never touched and never locked.

The clone is refreshed on demand so sessions stay current. This is per-device
and never hardcodes any specific profile (uses the configured one).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


# Files/dirs that carry login/session state. Copying these gives the clone the
# user's authenticated sessions without copying the whole (huge) profile.
_SESSION_ITEMS = [
    "Cookies",
    "Cookies-journal",
    "Login Data",
    "Login Data-journal",
    "Web Data",
    "Web Data-journal",
    "Local Storage",
    "Session Storage",
    "IndexedDB",
    "Network",            # newer Chrome stores Cookies under Network/
    "Preferences",
    "Secure Preferences",
]


def automation_user_data_dir() -> str:
    """Dedicated User-Data dir for the logged-in automation clone."""
    base = os.environ.get("FRIDAY_CLONE_USER_DATA_DIR")
    if base:
        return base
    local = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return os.path.join(local, "friday_chrome_clone")


@dataclass
class CloneResult:
    ok: bool
    clone_user_data_dir: str = ""
    clone_profile_dir: str = "Default"   # always 'Default' inside the clone
    copied: List[str] = None             # type: ignore
    error: str = ""

    def __post_init__(self):
        if self.copied is None:
            self.copied = []


def clone_profile_session(
    source_user_data_dir: str,
    source_profile_dir: str,
) -> CloneResult:
    """Clone login/session state from a real profile into the automation dir.

    Args:
        source_user_data_dir: e.g. C:\\...\\Chrome\\User Data
        source_profile_dir:   e.g. "Profile 1" (the signed-in profile)

    The clone always uses profile directory "Default" internally so the launch
    command is simple and stable.
    """
    src = Path(source_user_data_dir) / source_profile_dir
    if not src.is_dir():
        return CloneResult(ok=False, error=f"source profile not found: {src}")

    clone_root = Path(automation_user_data_dir())
    dst = clone_root / "Default"
    dst.mkdir(parents=True, exist_ok=True)

    # Copy the top-level "Local State" (holds the encryption key reference).
    copied: List[str] = []
    try:
        src_local_state = Path(source_user_data_dir) / "Local State"
        if src_local_state.is_file():
            shutil.copy2(src_local_state, clone_root / "Local State")
            copied.append("Local State")
    except Exception:
        pass

    for item in _SESSION_ITEMS:
        s = src / item
        d = dst / item
        try:
            if s.is_dir():
                if d.exists():
                    shutil.rmtree(d, ignore_errors=True)
                shutil.copytree(s, d, dirs_exist_ok=True)
                copied.append(item + "/")
            elif s.is_file():
                shutil.copy2(s, d)
                copied.append(item)
        except Exception:
            # Skip locked/missing items; best-effort session transfer.
            continue

    if not copied:
        return CloneResult(ok=False, clone_user_data_dir=str(clone_root),
                           error="no session files could be copied")

    return CloneResult(
        ok=True,
        clone_user_data_dir=str(clone_root),
        clone_profile_dir="Default",
        copied=copied,
    )
