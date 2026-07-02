"""Chrome launcher — start the user's REAL Chrome with the CDP debug port.

M2: FRIDAY must operate the user's actual Chrome (with their logins), not a
fresh Chromium. That requires Chrome to be running with
--remote-debugging-port=9222 against the user's profile.

This module:
- checks whether CDP is already reachable (cdp_reachable)
- finds the Chrome executable on Windows
- launches Chrome with the debug port + the user's profile
- waits until CDP responds

Pure orchestration; no Playwright here. The BrowserController connects
over CDP once this has made the port live.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import List, Optional


def cdp_reachable(port: int = 9222, host: str = "127.0.0.1", timeout: float = 1.5) -> bool:
    """Return True if a CDP endpoint is accepting connections on the port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _default_user_data_dir() -> Optional[str]:
    """Best-effort path to the user's Chrome User Data directory on Windows."""
    env = os.environ.get("JARVIS_CHROME_USER_DATA_DIR")
    if env:
        return env
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidate = os.path.join(local, "Google", "Chrome", "User Data")
        if os.path.isdir(candidate):
            return candidate
    return None


def _find_chrome_exe() -> Optional[str]:
    """Locate the Chrome executable on Windows."""
    candidates: List[str] = []
    for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base:
            candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    candidates += [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def chrome_running_without_debug(port: int = 9222) -> bool:
    """True if Chrome processes exist but the CDP port is not reachable.

    This is the #1 real-world failure: Chrome is already open on the user's
    profile, so launching chrome.exe --remote-debugging-port just forwards to
    the existing instance and the flag is ignored (profile dir is locked).
    """
    if cdp_reachable(port):
        return False
    try:
        import subprocess
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
            capture_output=True, text=True, timeout=5,
        )
        return "chrome.exe" in (out.stdout or "").lower()
    except Exception:
        return False


def _debug_profile_dir() -> str:
    """A dedicated user-data dir for FRIDAY's debug Chrome (avoids the lock)."""
    base = os.environ.get("FRIDAY_CHROME_DEBUG_PROFILE")
    if base:
        return base
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(local, "friday_chrome_debug")


@dataclass
class LaunchResult:
    """Outcome of attempting to make a real-Chrome CDP session available."""

    ok: bool
    already_running: bool = False
    launched: bool = False
    port: int = 9222
    chrome_path: str = ""
    user_data_dir: str = ""
    used_dedicated_profile: bool = False
    error: str = ""


def ensure_chrome_debug(
    port: int = 9222,
    user_data_dir: Optional[str] = None,
    profile_directory: Optional[str] = None,
    wait_seconds: float = 20.0,
    allow_dedicated_profile: bool = True,
    login_clone: bool = False,
    force_dedicated: bool = False,
) -> LaunchResult:
    """Ensure Chrome is running with the CDP debug port.

    Reliable strategy for "any task, anytime":
    - login_clone=True: clone the configured profile's session into a dedicated
      automation dir and run CDP there (keeps most logins, avoids Google's
      CDP-block on synced profiles, never locks the live profile).
    - force_dedicated=True: always use a clean dedicated profile (most reliable
      CDP; no logins). Best for no-login tasks (research/public sites).
    - Otherwise: reuse a running CDP session, or launch the given profile, or
      fall back to a clean dedicated profile if the live one is locked.

    Returns a LaunchResult. Never raises.
    """
    if cdp_reachable(port):
        return LaunchResult(ok=True, already_running=True, port=port)

    chrome = _find_chrome_exe()
    if not chrome:
        return LaunchResult(
            ok=False, port=port,
            error="Chrome executable not found. Set CHROME_PATH or install Chrome.",
        )

    used_dedicated = False
    resolved_profile_dir = profile_directory

    # --- Force dedicated clean profile (most reliable CDP, no logins) ---
    if force_dedicated and not login_clone:
        udd = _debug_profile_dir()
        resolved_profile_dir = "Default"
        used_dedicated = True
        os.makedirs(udd, exist_ok=True)
    # --- Login-clone path: keep the user's logins, get reliable CDP ---
    elif login_clone:
        from friday.actions.profile_clone import clone_profile_session, automation_user_data_dir
        src_udd = user_data_dir or _default_user_data_dir()
        src_profile = profile_directory or "Default"
        clone = clone_profile_session(src_udd, src_profile)
        if clone.ok:
            udd = clone.clone_user_data_dir
            resolved_profile_dir = clone.clone_profile_dir
        else:
            # Clone failed — fall back to a clean dedicated profile (no logins).
            udd = _debug_profile_dir()
            resolved_profile_dir = "Default"
            used_dedicated = True
    else:
        blocked_main_profile = chrome_running_without_debug(port)
        if blocked_main_profile and allow_dedicated_profile:
            udd = _debug_profile_dir()
            resolved_profile_dir = "Default"
            used_dedicated = True
            os.makedirs(udd, exist_ok=True)
        else:
            udd = user_data_dir or _default_user_data_dir()

    args = [chrome, f"--remote-debugging-port={port}"]
    if udd:
        args.append(f"--user-data-dir={udd}")
    if resolved_profile_dir:
        args.append(f"--profile-directory={resolved_profile_dir}")
    args += ["--no-first-run", "--no-default-browser-check",
             "--restore-last-session=false", "--no-sync"]

    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),
        )
    except Exception as exc:
        return LaunchResult(ok=False, port=port, chrome_path=chrome,
                            user_data_dir=udd or "", used_dedicated_profile=used_dedicated,
                            error=str(exc))

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if cdp_reachable(port):
            return LaunchResult(
                ok=True, launched=True, port=port,
                chrome_path=chrome, user_data_dir=udd or "",
                used_dedicated_profile=used_dedicated,
            )
        time.sleep(0.5)

    return LaunchResult(
        ok=False, launched=True, port=port, chrome_path=chrome,
        user_data_dir=udd or "", used_dedicated_profile=used_dedicated,
        error=f"Launched Chrome but CDP port {port} did not become reachable "
              f"within {wait_seconds:.0f}s.",
    )
