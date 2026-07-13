"""System actions — app launching, window management, file operations.

All actions return ActionResult. These are the lowest-level actuators
that the engine wraps with perception + verification.

Windows-focused for v1. Uses subprocess, pyautogui, and win32 APIs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Dict, List, Optional

from friday.actions.result import ActionResult, ActionEvidence, ActionTimer


def _is_dry_run() -> bool:
    return os.environ.get("FRIDAY_DRY_RUN", "0") == "1"


# Common Windows app launch commands
_APP_COMMANDS: Dict[str, str] = {
    "chrome": "chrome",
    "edge": "msedge",
    "firefox": "firefox",
    "notepad": "notepad",
    "calculator": "calc",
    "explorer": "explorer",
    "terminal": "wt",
    "cmd": "cmd",
    "powershell": "powershell",
    "vscode": "code",
    "spotify": "spotify",
    "settings": "ms-settings:",
    "paint": "mspaint",
    "task manager": "taskmgr",
}


class SystemActions:
    """System-level actuators that return ActionResult.

    Usage:
        sys_actions = SystemActions()
        result = sys_actions.launch_app("chrome")
        if result.is_success:
            print("Chrome launched")
    """

    def launch_app(self, app_name: str) -> ActionResult:
        """Launch an application by name.

        Args:
            app_name: App identifier (chrome, notepad, etc.) or full path

        Returns:
            ActionResult indicating success/failure
        """
        with ActionTimer() as timer:
            app_lower = app_name.lower().strip()
            command = _APP_COMMANDS.get(app_lower, app_lower)

            # DRY-RUN GUARD (defense-in-depth): the lowest-level actuator itself
            # must never perform a real launch under dry-run, so a direct caller
            # cannot bypass the executor's dry-run guard. Returns a simulated
            # success with no side effect and no process spawned.
            if _is_dry_run():
                return ActionResult.success(
                    action="launch_app",
                    target=app_name,
                    message=f"[DRY-RUN] Would launch {app_name}",
                    evidence=ActionEvidence(
                        state_changed=False,
                        raw={"dry_run": True, "command": command},
                    ),
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

            try:
                # SECURITY: never invoke a shell. `shell=True` with an interpolated
                # app string is a command-injection vector (e.g. "notepad & echo x"
                # would run two commands). Instead the app string is treated as a
                # SINGLE program/target so shell metacharacters cannot spawn a second
                # command:
                #   1. protocol/URI targets (e.g. "ms-settings:") -> ShellExecute;
                #   2. a real executable resolved on PATH -> argv list, shell=False;
                #   3. otherwise -> ShellExecute (Windows App Paths registry), which
                #      does NOT parse a command line, so injection is impossible.
                process = self._spawn(command)

                if process is not None:
                    # Give it a moment to start, then check it didn't immediately fail.
                    time.sleep(0.5)
                    poll = process.poll()
                    if poll is not None and poll != 0:
                        return ActionResult.failed(
                            action="launch_app",
                            error=f"Process exited with code {poll}",
                            target=app_name,
                            error_category="launch_failed",
                            repair_hints=["check_app_installed", "try_full_path"],
                            started_at=timer.started_at,
                            duration_ms=timer.duration_ms,
                        )
                    raw = {"command": command, "pid": process.pid}
                else:
                    # Launched via ShellExecute (no process handle available).
                    raw = {"command": command, "launcher": "shell_execute"}

                return ActionResult.success(
                    action="launch_app",
                    target=app_name,
                    message=f"Launched {app_name}",
                    evidence=ActionEvidence(state_changed=True, raw=raw),
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

            except FileNotFoundError:
                return ActionResult.failed(
                    action="launch_app",
                    error=f"Application '{app_name}' not found",
                    target=app_name,
                    error_category="not_found",
                    repair_hints=["check_app_installed", "verify_app_name"],
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )
            except Exception as exc:
                return ActionResult.failed(
                    action="launch_app",
                    error=str(exc),
                    target=app_name,
                    error_category="launch_error",
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

    def _spawn(self, command: str) -> Optional[subprocess.Popen]:
        """Launch ``command`` WITHOUT a shell (no command-injection surface).

        The command is always treated as a single program/target, never a shell
        command line, so metacharacters (``&``, ``|``, ``;``, ``&&``) cannot spawn
        a second process. Resolution order:

        1. Protocol/URI target (e.g. ``ms-settings:``) -> ``os.startfile`` (Windows
           ShellExecute). Returns ``None`` (no process handle).
        2. Executable resolvable on PATH -> ``subprocess.Popen([path], shell=False)``.
           Returns the ``Popen`` so the caller can poll for immediate failure.
        3. Fallback -> ``os.startfile`` (resolves App Paths registry entries such as
           ``spotify``/``msedge``). ShellExecute does not parse a command line, so a
           string containing shell metacharacters is treated as one literal target
           and simply fails to resolve (``FileNotFoundError``) — it cannot inject.
        """
        # 1. Protocol/URI (e.g. "ms-settings:", "mailto:", "https://...").
        if command.endswith(":") or "://" in command:
            os.startfile(command)  # type: ignore[attr-defined]  # Windows-only
            return None

        # 2. Real executable on PATH -> argv list, no shell.
        resolved = shutil.which(command)
        if resolved:
            return subprocess.Popen(
                [resolved],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # 3. Fallback: ShellExecute via App Paths registry (still no shell parsing).
        os.startfile(command)  # type: ignore[attr-defined]  # Windows-only
        return None

    def open_file(self, file_path: str) -> ActionResult:
        """Open a file with its default application."""
        with ActionTimer() as timer:
            path = os.path.expanduser(file_path)
            if not os.path.exists(path):
                return ActionResult.failed(
                    action="open_file",
                    error=f"File not found: {path}",
                    target=file_path,
                    error_category="not_found",
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

            try:
                os.startfile(path)  # Windows-specific
                return ActionResult.success(
                    action="open_file",
                    target=file_path,
                    message=f"Opened {os.path.basename(path)}",
                    evidence=ActionEvidence(state_changed=True, raw={"path": path}),
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )
            except Exception as exc:
                return ActionResult.failed(
                    action="open_file",
                    error=str(exc),
                    target=file_path,
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

    def focus_window(self, title_substring: str) -> ActionResult:
        """Bring a window to the foreground by title match."""
        with ActionTimer() as timer:
            try:
                import pyautogui
                windows = pyautogui.getWindowsWithTitle(title_substring)
                if not windows:
                    return ActionResult.failed(
                        action="focus_window",
                        error=f"No window matching '{title_substring}'",
                        target=title_substring,
                        error_category="window_not_found",
                        repair_hints=["check_app_open", "launch_app_first"],
                        started_at=timer.started_at,
                        duration_ms=timer.duration_ms,
                    )

                window = windows[0]
                try:
                    if window.isMinimized:
                        window.restore()
                    window.activate()
                except Exception:
                    pass

                return ActionResult.success(
                    action="focus_window",
                    target=title_substring,
                    message=f"Focused window: {window.title}",
                    evidence=ActionEvidence(
                        window_changed=True,
                        state_changed=True,
                        raw={"window_title": window.title},
                    ),
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )
            except Exception as exc:
                return ActionResult.failed(
                    action="focus_window",
                    error=str(exc),
                    target=title_substring,
                    started_at=timer.started_at,
                    duration_ms=timer.duration_ms,
                )

    def list_windows(self) -> List[str]:
        """List all open window titles."""
        try:
            import pyautogui
            return [w.title for w in pyautogui.getAllWindows() if w.title]
        except Exception:
            return []
