"""Browser configuration — per-device, persisted, never hardcoded.

Resolution order for which Chrome profile FRIDAY uses (highest first):
  1. Explicit argument passed in code/tests
  2. Environment variable FRIDAY_CHROME_PROFILE (display name or directory)
  3. Persisted device config at ~/.friday/config.json -> "chrome_profile"
  4. None  -> caller decides (e.g. dedicated debug profile, or prompt the user)

The owner sets their profile ONCE (env or config) on their machine; shared
builds let each user select theirs via the same mechanism / a setup wizard.
No profile name is ever written into source code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _config_path() -> Path:
    base = os.environ.get("FRIDAY_CONFIG_DIR")
    d = Path(base) if base else (Path.home() / ".friday")
    d.mkdir(parents=True, exist_ok=True)
    return d / "config.json"


def _load() -> dict:
    p = _config_path()
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(data: dict) -> None:
    _config_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_configured_profile() -> Optional[str]:
    """Return the selected profile (env > config), or None if unset."""
    env = os.environ.get("FRIDAY_CHROME_PROFILE")
    if env and env.strip():
        return env.strip()
    val = _load().get("chrome_profile")
    return val.strip() if isinstance(val, str) and val.strip() else None


def set_configured_profile(selection: str) -> None:
    """Persist the chosen profile (display name or directory) for this device."""
    data = _load()
    data["chrome_profile"] = selection.strip()
    _save(data)


def get_configured_user_data_dir() -> Optional[str]:
    """Return a configured User Data dir override (env > config), or None."""
    for var in ("FRIDAY_CHROME_USER_DATA_DIR", "JARVIS_CHROME_USER_DATA_DIR"):
        v = os.environ.get(var)
        if v and v.strip():
            return v.strip()
    val = _load().get("chrome_user_data_dir")
    return val.strip() if isinstance(val, str) and val.strip() else None


def set_configured_user_data_dir(path: str) -> None:
    data = _load()
    data["chrome_user_data_dir"] = path.strip()
    _save(data)


@dataclass
class ResolvedBrowserChoice:
    """The fully-resolved browser launch choice for this device."""

    user_data_dir: Optional[str]
    profile_directory: Optional[str]   # e.g. "Default", "Profile 1"
    display_name: Optional[str]
    source: str                        # "configured" | "dedicated" | "none"


def resolve_browser_choice(use_dedicated_if_unset: bool = True) -> ResolvedBrowserChoice:
    """Resolve which profile FRIDAY should launch on THIS device.

    - If a profile is configured (env/config) and exists, use it.
    - Else, optionally fall back to a dedicated FRIDAY debug profile.
    - Else, return a 'none' choice (caller decides).
    """
    from friday.actions.chrome_profiles import (
        default_user_data_dir, resolve_profile,
    )

    udd = get_configured_user_data_dir() or default_user_data_dir()
    selection = get_configured_profile()

    if selection:
        profile = resolve_profile(selection, user_data_dir=udd)
        if profile:
            return ResolvedBrowserChoice(
                user_data_dir=profile.user_data_dir,
                profile_directory=profile.directory,
                display_name=profile.display_name,
                source="configured",
            )

    if use_dedicated_if_unset:
        # Dedicated, isolated profile FRIDAY fully controls (no user logins
        # until they sign in there). Lives outside the main User Data dir.
        local = os.environ.get("LOCALAPPDATA") or str(Path.home())
        dedicated = os.path.join(local, "friday_chrome_debug")
        return ResolvedBrowserChoice(
            user_data_dir=dedicated,
            profile_directory="Default",
            display_name="FRIDAY (dedicated)",
            source="dedicated",
        )

    return ResolvedBrowserChoice(
        user_data_dir=udd, profile_directory=None,
        display_name=None, source="none",
    )
