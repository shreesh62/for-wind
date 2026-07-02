"""Tests for friday.actions.system — system actuators."""

from unittest.mock import MagicMock, patch
import pytest

from friday.actions.system import SystemActions
from friday.actions.result import ActionStatus


class TestSystemActions:
    """Test system action handlers."""

    def setup_method(self):
        self.actions = SystemActions()

    @patch("friday.actions.system.subprocess.Popen")
    @patch("friday.actions.system.time.sleep")
    def test_launch_app_success(self, mock_sleep, mock_popen):
        """Launching an app returns success when process starts."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running
        mock_process.pid = 1234
        mock_popen.return_value = mock_process

        result = self.actions.launch_app("notepad")

        assert result.is_success is True
        assert result.action_type == "launch_app"
        assert "notepad" in result.target
        assert result.evidence.state_changed is True

    @patch("friday.actions.system.subprocess.Popen")
    @patch("friday.actions.system.time.sleep")
    def test_launch_app_process_fails(self, mock_sleep, mock_popen):
        """Launching fails when process exits with error code."""
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Exited with error
        mock_popen.return_value = mock_process

        result = self.actions.launch_app("badapp")

        assert result.is_success is False
        assert result.status == ActionStatus.FAILED

    @patch("friday.actions.system.subprocess.Popen")
    def test_launch_app_not_found(self, mock_popen):
        """Launching a missing app returns not_found error."""
        mock_popen.side_effect = FileNotFoundError("not found")

        result = self.actions.launch_app("nonexistent")

        assert result.is_success is False
        assert result.error_category == "not_found"
        assert "check_app_installed" in result.repair_hints

    def test_launch_known_app_uses_command(self):
        """Known apps map to correct commands."""
        with patch("friday.actions.system.subprocess.Popen") as mock_popen, \
             patch("friday.actions.system.time.sleep"):
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_process.pid = 1
            mock_popen.return_value = mock_process

            self.actions.launch_app("chrome")

            # Verify chrome command was used
            call_args = mock_popen.call_args
            assert call_args[0][0] == "chrome"

    def test_open_file_not_found(self):
        """Opening a missing file returns not_found."""
        result = self.actions.open_file("C:\\nonexistent\\file.txt")

        assert result.is_success is False
        assert result.error_category == "not_found"

    @patch("friday.actions.system.os.startfile", create=True)
    @patch("friday.actions.system.os.path.exists")
    def test_open_file_success(self, mock_exists, mock_startfile):
        """Opening an existing file succeeds."""
        mock_exists.return_value = True

        result = self.actions.open_file("C:\\test.txt")

        assert result.is_success is True
        mock_startfile.assert_called_once()

    def test_focus_window_not_found(self):
        """Focusing a non-existent window fails gracefully."""
        with patch("pyautogui.getWindowsWithTitle", return_value=[]):
            result = self.actions.focus_window("NonexistentApp")

            assert result.is_success is False
            assert result.error_category == "window_not_found"
            assert "launch_app_first" in result.repair_hints

    def test_focus_window_success(self):
        """Focusing an existing window succeeds."""
        mock_window = MagicMock()
        mock_window.title = "Notepad"
        mock_window.isMinimized = False

        with patch("pyautogui.getWindowsWithTitle", return_value=[mock_window]):
            result = self.actions.focus_window("Notepad")

            assert result.is_success is True
            assert result.evidence.window_changed is True
