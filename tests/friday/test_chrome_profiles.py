"""Tests for Chrome profile discovery + per-device selection.

Proves: profiles are discovered from Local State, selection resolves by
display name OR directory (case-insensitive, partial), config persists the
choice, env overrides config, and NO profile is hardcoded.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from friday.actions.chrome_profiles import (
    ChromeProfile,
    discover_profiles,
    resolve_profile,
)
from friday.config import browser_config as bc


def _make_user_data(tmp_path: Path, profiles: dict) -> Path:
    """Create a fake Chrome User Data dir with a Local State + profile dirs."""
    udd = tmp_path / "User Data"
    udd.mkdir()
    info_cache = {}
    for directory, name in profiles.items():
        (udd / directory).mkdir()
        info_cache[directory] = {"name": name}
    (udd / "Local State").write_text(
        json.dumps({"profile": {"info_cache": info_cache}}), encoding="utf-8"
    )
    return udd


class TestDiscovery:
    def test_discovers_profiles_with_display_names(self, tmp_path):
        udd = _make_user_data(tmp_path, {"Default": "Shreesh", "Profile 1": "Work"})
        profiles = discover_profiles(str(udd))
        names = {p.display_name for p in profiles}
        assert names == {"Shreesh", "Work"}

    def test_empty_when_no_user_data(self, tmp_path):
        assert discover_profiles(str(tmp_path / "nope")) == []

    def test_fallback_scans_profile_dirs(self, tmp_path):
        udd = tmp_path / "User Data"
        udd.mkdir()
        (udd / "Default").mkdir()
        (udd / "Profile 1").mkdir()
        # no Local State
        profiles = discover_profiles(str(udd))
        dirs = {p.directory for p in profiles}
        assert dirs == {"Default", "Profile 1"}


class TestResolve:
    def test_resolve_by_display_name(self, tmp_path):
        udd = _make_user_data(tmp_path, {"Profile 1": "Shreesh"})
        p = resolve_profile("Shreesh", user_data_dir=str(udd))
        assert p and p.directory == "Profile 1"

    def test_resolve_by_directory(self, tmp_path):
        udd = _make_user_data(tmp_path, {"Profile 1": "Shreesh"})
        p = resolve_profile("Profile 1", user_data_dir=str(udd))
        assert p and p.display_name == "Shreesh"

    def test_resolve_case_insensitive_partial(self, tmp_path):
        udd = _make_user_data(tmp_path, {"Profile 1": "Shreesh"})
        p = resolve_profile("shre", user_data_dir=str(udd))
        assert p and p.display_name == "Shreesh"

    def test_resolve_missing_returns_none(self, tmp_path):
        udd = _make_user_data(tmp_path, {"Default": "A"})
        assert resolve_profile("ZZZ", user_data_dir=str(udd)) is None


class TestConfigPersistence:
    def test_set_and_get_profile(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FRIDAY_CONFIG_DIR", str(tmp_path))
        monkeypatch.delenv("FRIDAY_CHROME_PROFILE", raising=False)
        bc.set_configured_profile("Shreesh")
        assert bc.get_configured_profile() == "Shreesh"
        # persisted to a file, not code
        assert (tmp_path / "config.json").is_file()

    def test_env_overrides_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FRIDAY_CONFIG_DIR", str(tmp_path))
        bc.set_configured_profile("FromConfig")
        monkeypatch.setenv("FRIDAY_CHROME_PROFILE", "FromEnv")
        assert bc.get_configured_profile() == "FromEnv"

    def test_unset_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FRIDAY_CONFIG_DIR", str(tmp_path))
        monkeypatch.delenv("FRIDAY_CHROME_PROFILE", raising=False)
        assert bc.get_configured_profile() is None


class TestResolveBrowserChoice:
    def test_dedicated_fallback_when_unset(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FRIDAY_CONFIG_DIR", str(tmp_path))
        monkeypatch.delenv("FRIDAY_CHROME_PROFILE", raising=False)
        choice = bc.resolve_browser_choice(use_dedicated_if_unset=True)
        assert choice.source == "dedicated"
        assert choice.profile_directory == "Default"

    def test_none_when_unset_and_no_dedicated(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FRIDAY_CONFIG_DIR", str(tmp_path))
        monkeypatch.delenv("FRIDAY_CHROME_PROFILE", raising=False)
        choice = bc.resolve_browser_choice(use_dedicated_if_unset=False)
        assert choice.source == "none"

    def test_no_profile_hardcoded_in_source(self):
        """Guard: the owner's profile name must never appear in source files."""
        import friday.actions.chrome_profiles as m1
        import friday.config.browser_config as m2
        import friday.actions.chrome_launcher as m3
        for mod in (m1, m2, m3):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            assert "Shreesh" not in src
