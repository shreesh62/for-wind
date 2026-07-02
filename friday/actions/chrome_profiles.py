"""Chrome profile discovery + selection — device-local, never hardcoded.

The owner wants FRIDAY to use their real Chrome profile (with their logins),
while shareable builds let each user pick their own profile on their device.
Nothing about any specific person's profile is baked into the code.

How Chrome stores profiles (Windows):
  <User Data>/                      <- the user-data-dir
    Local State                     <- JSON with profile.info_cache:
                                       { "Default": {"name": "Alex"},
                                         "Profile 1": {"name": "Work"} }
    Default/                        <- profile directory
    Profile 1/

To open a specific profile you pass BOTH:
  --user-data-dir=<User Data>
  --profile-directory=<dir name, e.g. "Default" or "Profile 1">

This module:
- finds the default User Data dir (or honors an env override)
- reads Local State to list profiles as (directory, display_name)
- resolves a user's chosen profile (by display name OR directory) to a directory
- never hardcodes any profile; selection is config/env driven
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class ChromeProfile:
    """A discovered Chrome profile."""

    directory: str        # e.g. "Default", "Profile 1"
    display_name: str     # e.g. "Alex", "Work"
    user_data_dir: str    # the User Data root this profile lives under

    @property
    def label(self) -> str:
        return f"{self.display_name} [{self.directory}]"


def default_user_data_dir() -> Optional[str]:
    """Locate Chrome's User Data directory.

    Honors FRIDAY_CHROME_USER_DATA_DIR / JARVIS_CHROME_USER_DATA_DIR first,
    then falls back to the standard Windows location. Never hardcodes a
    specific user's path — uses %LOCALAPPDATA% of whoever runs FRIDAY.
    """
    for var in ("FRIDAY_CHROME_USER_DATA_DIR", "JARVIS_CHROME_USER_DATA_DIR"):
        val = os.environ.get(var)
        if val and os.path.isdir(val):
            return val
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidate = os.path.join(local, "Google", "Chrome", "User Data")
        if os.path.isdir(candidate):
            return candidate
    return None


def discover_profiles(user_data_dir: Optional[str] = None) -> List[ChromeProfile]:
    """List Chrome profiles found on THIS device.

    Reads <User Data>/Local State's profile.info_cache. Falls back to scanning
    for profile directories if Local State is missing/unreadable.
    """
    udd = user_data_dir or default_user_data_dir()
    if not udd or not os.path.isdir(udd):
        return []

    profiles: List[ChromeProfile] = []
    local_state = Path(udd) / "Local State"
    if local_state.is_file():
        try:
            data = json.loads(local_state.read_text(encoding="utf-8", errors="replace"))
            info_cache = (data.get("profile", {}) or {}).get("info_cache", {}) or {}
            for directory, meta in info_cache.items():
                name = (meta or {}).get("name") or directory
                if (Path(udd) / directory).is_dir():
                    profiles.append(ChromeProfile(
                        directory=directory, display_name=name, user_data_dir=udd,
                    ))
        except (json.JSONDecodeError, OSError):
            pass

    # Fallback: scan for profile directories if Local State gave nothing.
    if not profiles:
        for entry in sorted(Path(udd).iterdir() if Path(udd).is_dir() else []):
            if entry.is_dir() and (entry.name == "Default" or entry.name.startswith("Profile ")):
                profiles.append(ChromeProfile(
                    directory=entry.name, display_name=entry.name, user_data_dir=udd,
                ))

    return profiles


def resolve_profile(
    selection: str,
    user_data_dir: Optional[str] = None,
) -> Optional[ChromeProfile]:
    """Resolve a selection (display name OR directory) to a ChromeProfile.

    Matching is case-insensitive. Returns None if not found.
    """
    if not selection:
        return None
    profiles = discover_profiles(user_data_dir)
    sel = selection.strip().lower()
    # Exact directory match first, then display-name match.
    for p in profiles:
        if p.directory.lower() == sel:
            return p
    for p in profiles:
        if p.display_name.lower() == sel:
            return p
    # Partial display-name match (e.g. "ale" -> "Alex").
    for p in profiles:
        if sel in p.display_name.lower():
            return p
    return None
