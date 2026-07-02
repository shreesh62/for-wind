"""Playwright automation manager for web app control."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
import os
import subprocess
import shutil
import time
import threading
import socket

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
except ImportError:  # pragma: no cover - optional dependency
    async_playwright = None  # type: ignore[assignment]
    Browser = BrowserContext = Page = None  # type: ignore[assignment]


class PlaywrightUnavailable(RuntimeError):
    """Raised when Playwright is not installed but required."""


# Store Playwright session files in a safe local folder outside OneDrive
STORAGE_DIR = Path(r"C:\Projects\JARVIS\playwright_storage")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


_CHROME_LAUNCH_LOCKS: dict[tuple[int, str], threading.Lock] = {}
_CHROME_LAUNCH_LOCKS_GUARD = threading.Lock()
_CHROME_LAUNCH_LAST_ATTEMPT: dict[tuple[int, str], float] = {}

_CHROME_LAUNCH_DEBOUNCE_S = 60.0


def _get_chrome_launch_lock(port: int, user_data_dir: Path) -> threading.Lock:
    key = (int(port), str(user_data_dir))
    with _CHROME_LAUNCH_LOCKS_GUARD:
        lock = _CHROME_LAUNCH_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _CHROME_LAUNCH_LOCKS[key] = lock
        return lock


class PlaywrightManager:
    """Manages Playwright browser sessions with persistent storage."""

    def __init__(
        self,
        storage_name: str,
        headless: bool = True,
        *,
        use_chrome_profile: bool = False,
        chrome_profile: str = "Default",
        remote_debug_port: int = 9222,
        auto_launch: bool = False,
    ) -> None:
        self.storage_path = STORAGE_DIR / f"{storage_name}.json"
        self.headless = headless
        self.use_chrome_profile = use_chrome_profile
        self.chrome_profile = chrome_profile
        self.remote_debug_port = remote_debug_port
        self.auto_launch = auto_launch
        self._lock = asyncio.Lock()
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._chrome_process: Optional[subprocess.Popen] = None
        self._page: Optional[Page] = None
        self._chrome_user_data_dir = os.getenv(
            "JARVIS_CHROME_USER_DATA_DIR",
            str(Path(r"C:\Projects\JARVIS\chrome_user_data"))
        )

    async def close_async(self) -> None:
        """Best-effort cleanup to avoid Playwright driver broken-pipe errors on exit."""
        async with self._lock:
            page = self._page
            browser = self._browser
            context = self._context
            playwright = self._playwright

            self._page = None
            self._browser = None
            self._context = None
            self._playwright = None

        try:
            if page is not None:
                try:
                    if hasattr(page, "is_closed") and not page.is_closed():
                        await page.close()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if context is not None:
                try:
                    if hasattr(context, "is_closed") and not context.is_closed():
                        await context.close()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if browser is not None:
                try:
                    if hasattr(browser, "is_connected") and browser.is_connected():
                        await browser.close()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if playwright is not None:
                try:
                    await playwright.stop()
                except Exception:
                    pass
        except Exception:
            pass

    def ensure_chrome_remote_debug(self) -> bool:
        """Ensure Chrome is running with remote debugging enabled.
        
        Returns:
            True if Chrome is available, False otherwise
        """
        # Check if Chrome DevTools port is already open
        try:
            sock = socket.create_connection(
                ("127.0.0.1", self.remote_debug_port),
                timeout=1.0
            )
            sock.close()
            return True
        except (socket.error, socket.timeout, OSError):
            pass
        
        # Auto-launch Chrome with remote debugging
        if not self.auto_launch:
            return False
        
        # Find Chrome executable
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        
        chrome_path = None
        for path in chrome_paths:
            if os.path.exists(path):
                chrome_path = path
                break
        
        if not chrome_path:
            return False
        
        # Launch Chrome with remote debugging
        try:
            user_data_dir = Path(self._chrome_user_data_dir)
            user_data_dir.mkdir(parents=True, exist_ok=True)
            
            subprocess.Popen(
                [
                    chrome_path,
                    f"--remote-debugging-port={self.remote_debug_port}",
                    f"--user-data-dir={user_data_dir}",
                    f"--profile-directory={self.chrome_profile}",
                ],
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            # Wait for port to become available
            return self._wait_for_port(self.remote_debug_port, timeout=10.0)
        except Exception:
            return False
    
    def _wait_for_port(self, port: int, timeout: float = 10.0) -> bool:
        """Wait for a port to become available.
        
        Args:
            port: Port number to wait for
            timeout: Maximum seconds to wait
            
        Returns:
            True if port became available, False if timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                sock = socket.create_connection(("127.0.0.1", port), timeout=0.5)
                sock.close()
                return True
            except (socket.error, socket.timeout, OSError):
                time.sleep(0.3)
        return False

    def close(self) -> None:
        """Synchronous wrapper around close_async()."""
        try:
            asyncio.get_running_loop()
            # If a loop is running, schedule cleanup best-effort.
            try:
                asyncio.create_task(self.close_async())
            except Exception:
                pass
            return
        except RuntimeError:
            pass

        try:
            asyncio.run(self.close_async())
        except Exception:
            pass

    @asynccontextmanager
    async def session(self) -> Page:
        if async_playwright is None:
            raise PlaywrightUnavailable(
                "Playwright is not installed. Run 'pip install playwright' and execute 'playwright install'."
            )
        if self.use_chrome_profile:
            browser, context = await self._ensure_chrome_profile()
            page = None
            try:
                if self._page is not None:
                    try:
                        if not (hasattr(self._page, "is_closed") and self._page.is_closed()):
                            page = self._page
                    except Exception:
                        page = None
            except Exception:
                page = None

            if page is None:
                try:
                    for candidate in list(getattr(context, "pages", []) or []):
                        try:
                            if hasattr(candidate, "is_closed") and candidate.is_closed():
                                continue
                        except Exception:
                            pass
                        page = candidate
                        break
                except Exception:
                    page = None

            if page is None:
                page = await context.new_page()
            self._page = page
            yield page
            return

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                storage_state=str(self.storage_path) if self.storage_path.exists() else None
            )
            try:
                page = await context.new_page()
                yield page
            finally:
                await context.storage_state(path=str(self.storage_path))
                await context.close()
                await browser.close()

    async def _ensure_playwright(self):
        if self._playwright is not None:
            return self._playwright
        # Keep a persistent Playwright instance for CDP reuse.
        self._playwright = await async_playwright().start()
        return self._playwright

    async def _ensure_chrome_profile(self) -> tuple[Browser, BrowserContext]:
        async with self._lock:
            if self._browser is not None and self._context is not None:
                try:
                    is_connected = True
                    if hasattr(self._browser, "is_connected"):
                        is_connected = bool(self._browser.is_connected())
                    is_closed = False
                    if hasattr(self._context, "is_closed"):
                        is_closed = bool(self._context.is_closed())
                    if is_connected and not is_closed:
                        return self._browser, self._context
                except Exception:
                    pass
                # Reset stale cached session
                self._browser = None
                self._context = None
                self._page = None

            # RUNTIME STABILIZATION: Auto-launch Chrome if not available
            self.ensure_chrome_remote_debug()
            
            playwright = await self._ensure_playwright()
            browser, context = await self._connect_chrome_profile(playwright)
            self._browser = browser
            self._context = context
            return browser, context

    def invalidate_cache(self) -> None:
        """Clear cached CDP browser/context references.

        This is a lightweight recovery tool for cases where Chrome disconnects or the
        underlying transport becomes unusable. The next session() call will reconnect.
        """

        self._browser = None
        self._context = None
        self._page = None

    async def _connect_chrome_profile(self, playwright) -> tuple[Browser, BrowserContext]:
        chrome_path = self._resolve_chrome_executable()
        user_data_dir = self._resolve_user_data_dir()

        def _port_listening(host: str, port: int) -> bool:
            try:
                with socket.create_connection((host, int(port)), timeout=0.35):
                    return True
            except Exception:
                return False

        # Attempt to connect first (in case another session already launched Chrome).
        browser = await self._try_connect_existing(playwright)
        if browser is None:
            if not self.auto_launch:
                raise PlaywrightUnavailable(
                    (
                        "Chrome is not running with remote debugging enabled. "
                        "Launch it using '{chrome} --remote-debugging-port={port} --user-data-dir=\"{user_data}\" --profile-directory=\"{profile}\"' "
                        "and try again."
                    ).format(
                        chrome=chrome_path,
                        port=self.remote_debug_port,
                        user_data=user_data_dir,
                        profile=self.chrome_profile,
                    )
                )
            launch_lock = _get_chrome_launch_lock(self.remote_debug_port, user_data_dir)
            with launch_lock:
                browser = await self._try_connect_existing(playwright)
                if browser is None:
                    # If the port is already listening, avoid spawning chrome.exe again (which can
                    # open a new window) and instead wait for the endpoint to become attachable.
                    if _port_listening("127.0.0.1", self.remote_debug_port):
                        browser = await self._wait_for_chrome(playwright)
                    if browser is None:
                        # If still unavailable and the port is listening, something else is likely
                        # using the port; launching Chrome won't help.
                        if _port_listening("127.0.0.1", self.remote_debug_port):
                            raise PlaywrightUnavailable(
                                "Chrome DevTools port is in use but not attachable. "
                                "Close the process using the port or set CHROME_REMOTE_DEBUG_PORT to a different value."
                            )
                    key = (int(self.remote_debug_port), str(user_data_dir))
                    last = _CHROME_LAUNCH_LAST_ATTEMPT.get(key)
                    now = time.time()
                    recent_attempt = bool(
                        isinstance(last, (int, float)) and (now - float(last)) < _CHROME_LAUNCH_DEBOUNCE_S
                    )
                    if recent_attempt:
                        browser = await self._wait_for_chrome(playwright)
                    else:
                        _CHROME_LAUNCH_LAST_ATTEMPT[key] = now
                        chrome_args = [
                            str(chrome_path),
                            "--remote-debugging-address=127.0.0.1",
                            f"--remote-debugging-port={self.remote_debug_port}",
                            "--remote-allow-origins=*",
                            f"--user-data-dir={user_data_dir}",
                            f"--profile-directory={self.chrome_profile}",
                            "--start-maximized",
                            "--disable-features=DialMediaRouteController",
                        ]

                        self._chrome_process = subprocess.Popen(
                            chrome_args,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )

                        time.sleep(0.25)
                        if self._chrome_process.poll() is not None:
                            # On Windows, chrome.exe may exit quickly after handing off to an
                            # existing process. Try to connect briefly before failing.
                            browser = None
                            for _ in range(10):
                                browser = await self._try_connect_existing(playwright)
                                if browser is not None:
                                    break
                                await asyncio.sleep(0.25)
                            if browser is None:
                                raise PlaywrightUnavailable(
                                    "Chrome failed to launch with remote debugging enabled. "
                                    "Try a different CHROME_REMOTE_DEBUG_PORT or a different JARVIS_CHROME_USER_DATA_DIR."
                                )

                        if browser is None:
                            browser = await self._wait_for_chrome(playwright)

        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context()
        return browser, context

    async def _try_connect_existing(self, playwright) -> Optional[Browser]:
        try:
            return await playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{self.remote_debug_port}"
            )
        except Exception:
            return None

    async def _wait_for_chrome(self, playwright) -> Browser:
        for _ in range(40):
            browser = await self._try_connect_existing(playwright)
            if browser:
                return browser
            await asyncio.sleep(0.5)
        raise PlaywrightUnavailable(
            "Unable to connect to Chrome via remote debugging. Ensure Chrome is closed and try again."
        )

    def _resolve_chrome_executable(self) -> Path:
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate

        found = shutil.which("chrome") or shutil.which("google-chrome")
        if found:
            return Path(found)

        raise PlaywrightUnavailable("Google Chrome executable was not found on this system.")

    def _resolve_user_data_dir(self) -> Path:
        override = os.environ.get("JARVIS_CHROME_USER_DATA_DIR") or os.environ.get("CHROME_USER_DATA_DIR")
        if override:
            try:
                base = Path(override).expanduser().resolve()
            except Exception:
                base = Path(override)
            base.mkdir(parents=True, exist_ok=True)
            return base

        if self.auto_launch:
            base = STORAGE_DIR.parent / "chrome_user_data"
            base.mkdir(parents=True, exist_ok=True)
            return base

        base = Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data"
        if not base.exists():
            raise PlaywrightUnavailable(
                "Chrome user data directory not found. Launch Chrome at least once with the desired profile."
            )
        profile_dir = base / self.chrome_profile
        if not profile_dir.exists():
            raise PlaywrightUnavailable(
                f"Chrome profile '{self.chrome_profile}' not found in {base}."
            )
        return base
