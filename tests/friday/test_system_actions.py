"""Tests for friday.actions.system — system actuators.

Launch-path tests assert the M18-audit security contract (see
friday/actions/system.py::launch_app / _spawn):
  * dry-run performs NO real launch (no Popen / no ShellExecute);
  * the launcher NEVER uses shell=True (no command-injection surface);
  * an app string with shell metacharacters is treated as ONE target.
The conftest forces FRIDAY_DRY_RUN=1 session-wide; tests that exercise the real
launch path opt out locally via monkeypatch.setenv("FRIDAY_DRY_RUN", "0").
"""

from unittest.mock import MagicMock, patch
import pytest

from friday.actions.system import SystemActions
from friday.actions.result import ActionStatus


class TestSystemActionsLaunch:
    """Launch path — dry-run guard + shell-free (injection-proof) spawning."""

    def setup_method(self):
        self.actions = SystemActions()

    def test_dry_run_does_not_spawn(self, monkeypatch):
        """Under dry-run the actuator performs no real launch (defense-in-depth):
        no Popen, no ShellExecute — a direct caller cannot bypass dry-run."""
        monkeypatch.setenv("FRIDAY_DRY_RUN", "1")
        with patch("friday.actions.system.subprocess.Popen") as popen, \
             patch("friday.actions.system.os.startfile", create=True) as startfile:
            result = self.actions.launch_app("notepad")

        assert result.is_success is True
        assert result.evidence.raw.get("dry_run") is True
        assert result.evidence.state_changed is False
        popen.assert_not_called()
        startfile.assert_not_called()

    def test_launch_success_via_path_uses_argv_no_shell(self, monkeypatch):
        """A PATH-resolvable app launches via an argv list with shell=False."""
        monkeypatch.setenv("FRIDAY_DRY_RUN", "0")
        proc = MagicMock()
        proc.poll.return_value = None  # still running
        proc.pid = 1234
        with patch("friday.actions.system.shutil.which",
                   return_value=r"C:\Windows\System32\notepad.exe"), \
             patch("friday.actions.system.subprocess.Popen", return_value=proc) as popen, \
             patch("friday.actions.system.time.sleep"):
            result = self.actions.launch_app("notepad")

        assert result.is_success is True
        assert result.evidence.state_changed is True
        args, kwargs = popen.call_args
        # SECURITY: argv list + shell=False (never a shell command string).
        assert args[0] == [r"C:\Windows\System32\notepad.exe"]
        assert kwargs.get("shell") is False

    def test_launch_process_fails(self, monkeypatch):
        """A process that immediately exits non-zero reports failure."""
        monkeypatch.setenv("FRIDAY_DRY_RUN", "0")
        proc = MagicMock()
        proc.poll.return_value = 1  # exited with error
        with patch("friday.actions.system.shutil.which", return_value=r"C:\bad.exe"), \
             patch("friday.actions.system.subprocess.Popen", return_value=proc), \
             patch("friday.actions.system.time.sleep"):
            result = self.actions.launch_app("badapp")

        assert result.is_success is False
        assert result.status == ActionStatus.FAILED

    def test_launch_not_found(self, monkeypatch):
        """Unknown app: which() misses and ShellExecute raises -> not_found."""
        monkeypatch.setenv("FRIDAY_DRY_RUN", "0")
        with patch("friday.actions.system.shutil.which", return_value=None), \
             patch("friday.actions.system.os.startfile", create=True,
                   side_effect=FileNotFoundError("not found")):
            result = self.actions.launch_app("nonexistent")

        assert result.is_success is False
        assert result.error_category == "not_found"
        assert "check_app_installed" in result.repair_hints

    def test_never_uses_shell_true_on_injection_string(self, monkeypatch):
        """SECURITY regression: an app string with shell metacharacters is handed
        to ShellExecute as a SINGLE literal target — never to a shell — so it can
        never spawn a second command."""
        monkeypatch.setenv("FRIDAY_DRY_RUN", "0")
        injected = "notepad & echo pwned"
        with patch("friday.actions.system.shutil.which", return_value=None), \
             patch("friday.actions.system.subprocess.Popen") as popen, \
             patch("friday.actions.system.os.startfile", create=True) as startfile:
            self.actions.launch_app(injected)

        # Popen, if ever used on any path, must be shell=False.
        if popen.called:
            _, kwargs = popen.call_args
            assert kwargs.get("shell") is False
        # The full string went to ShellExecute as one target (no shell parsing).
        startfile.assert_called_once_with(injected)

    def test_protocol_target_uses_shell_execute_not_popen(self, monkeypatch):
        """A protocol/URI target (settings -> ms-settings:) uses ShellExecute."""
        monkeypatch.setenv("FRIDAY_DRY_RUN", "0")
        with patch("friday.actions.system.os.startfile", create=True) as startfile, \
             patch("friday.actions.system.subprocess.Popen") as popen:
            result = self.actions.launch_app("settings")

        startfile.assert_called_once_with("ms-settings:")
        popen.assert_not_called()
        assert result.is_success is True


class TestSystemActionsFiles:
    """File + window actuators (unchanged by the M18 security fix)."""

    def setup_method(self):
        self.actions = SystemActions()

    def test_open_file_not_found(self):
        result = self.actions.open_file("C:\\nonexistent\\file.txt")
        assert result.is_success is False
        assert result.error_category == "not_found"

    @patch("friday.actions.system.os.startfile", create=True)
    @patch("friday.actions.system.os.path.exists")
    def test_open_file_success(self, mock_exists, mock_startfile):
        mock_exists.return_value = True
        result = self.actions.open_file("C:\\test.txt")
        assert result.is_success is True
        mock_startfile.assert_called_once()

    def test_focus_window_not_found(self):
        with patch("pyautogui.getWindowsWithTitle", return_value=[]):
            result = self.actions.focus_window("NonexistentApp")
            assert result.is_success is False
            assert result.error_category == "window_not_found"
            assert "launch_app_first" in result.repair_hints

    def test_focus_window_success(self):
        mock_window = MagicMock()
        mock_window.title = "Notepad"
        mock_window.isMinimized = False
        with patch("pyautogui.getWindowsWithTitle", return_value=[mock_window]):
            result = self.actions.focus_window("Notepad")
            assert result.is_success is True
            assert result.evidence.window_changed is True
