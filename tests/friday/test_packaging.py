"""Tests for packaging/first_run.py setup wizard."""

import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest

# Load the first_run module
ROOT = Path(__file__).resolve().parent.parent.parent
spec = importlib.util.spec_from_file_location(
    "first_run", ROOT / "packaging" / "first_run.py"
)
first_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(first_run)


class TestDependencyCheck:
    def test_check_dependencies_returns_tuple(self):
        ok, missing = first_run.check_dependencies()
        assert isinstance(ok, bool)
        assert isinstance(missing, list)

    def test_required_deps_present(self):
        # In the test environment, all required deps should be installed
        ok, missing = first_run.check_dependencies()
        assert ok is True
        assert len(missing) == 0

    def test_check_optional_returns_dict(self):
        status = first_run.check_optional()
        assert isinstance(status, dict)
        assert "groq" in status
        assert "mss" in status


class TestEnvHandling:
    def test_ensure_env_creates_file(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            monkeypatch.setattr(first_run, "ROOT", tmp_root)

            env_path = first_run.ensure_env()
            assert env_path.exists()
            content = env_path.read_text()
            assert "REMOTE_API_KEY" in content

    def test_ensure_env_preserves_existing(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            monkeypatch.setattr(first_run, "ROOT", tmp_root)

            existing = tmp_root / ".env"
            existing.write_text("REMOTE_API_KEY=my-existing-key\n")

            env_path = first_run.ensure_env()
            assert "my-existing-key" in env_path.read_text()


class TestConnectivity:
    def test_test_connectivity_returns_dict(self):
        result = first_run.test_connectivity()
        assert "nvidia_configured" in result
        assert "groq_configured" in result
        assert "any_provider" in result


class TestWizard:
    def test_wizard_runs_non_interactive(self):
        # Should complete without prompting
        result = first_run.run_wizard(interactive=False)
        assert isinstance(result, bool)
