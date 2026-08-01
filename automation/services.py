"""High-level automation service functions for Jarvis."""

from __future__ import annotations

import asyncio
import hashlib
import time
import os
import subprocess
import ctypes
import webbrowser
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional
from urllib.parse import quote_plus, urlparse

try:
    from PIL import Image, ImageGrab  # type: ignore
except ImportError:  # pragma: no cover
    Image = None  # type: ignore
    ImageGrab = None  # type: ignore

from .playwright_manager import PlaywrightManager, PlaywrightUnavailable
from .devtools_bridge import DevToolsBridge, DevToolsConfig
from .desktop_actions import DesktopAutomation, DesktopAutomationUnavailable, FocusRequest
from .quick_actions import (
    AutomationResult,
    InstagramAutomation,
    WhatsAppAutomation,
    GmailComposeTemplateAutomation,
    GoogleCalendarAutomation,
)
from .amazon_shopping import AmazonSearchAutomation
from .gmail_actions import GmailAutomation

if TYPE_CHECKING:
    from awareness.state_cache import StateCache
    from core.telemetry import TelemetryLogger


@dataclass
class AutomationResponse:
    success: bool
    message: str
    action: str | None = None
    before_snapshot: dict | None = None
    after_snapshot: dict | None = None
    verification: dict | None = None

    @classmethod
    def from_result(
        cls,
        result: AutomationResult,
        *,
        action: str | None = None,
        before_snapshot: dict | None = None,
        after_snapshot: dict | None = None,
        verification: dict | None = None,
    ) -> "AutomationResponse":
        return cls(
            success=result.success,
            message=result.message,
            action=action,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            verification=verification,
        )


class AutomationServices:
    """Facade exposing automation actions to the rest of the assistant."""

    def __init__(
        self,
        headless: bool = True,
        *,
        use_chrome_profile: bool = True,
        chrome_profile: str = "Default",
        remote_debug_port: int = 9222,
        auto_launch: bool = False,
        enable_desktop: bool = True,
        desktop_fail_safe: bool = True,
        desktop_pause: float = 0.2,
        awareness_state: "StateCache | None" = None,
        telemetry: "TelemetryLogger | None" = None,
    ) -> None:
        kwargs = {
            "headless": headless,
            "use_chrome_profile": use_chrome_profile,
            "chrome_profile": chrome_profile,
            "remote_debug_port": remote_debug_port,
            "auto_launch": auto_launch,
        }
        self.whatsapp = WhatsAppAutomation(**kwargs)
        self.instagram = InstagramAutomation(**kwargs)
        self.gmail = GmailAutomation(**kwargs)
        self.gmail_template = GmailComposeTemplateAutomation(**kwargs)
        self.calendar = GoogleCalendarAutomation(**kwargs)
        self.amazon = AmazonSearchAutomation(**kwargs)
        self._devtools_manager = PlaywrightManager(
            "automation-services",
            headless=headless,
            use_chrome_profile=use_chrome_profile,
            chrome_profile=chrome_profile,
            remote_debug_port=remote_debug_port,
            auto_launch=auto_launch,
        )
        self._async_loop = None
        self._async_thread = None
        self._desktop: Optional[DesktopAutomation] = None
        if enable_desktop:
            try:
                self._desktop = DesktopAutomation(
                    fail_safe=desktop_fail_safe,
                    pause=desktop_pause,
                )
            except DesktopAutomationUnavailable:
                self._desktop = None
        self.awareness_state = awareness_state
        self.telemetry = telemetry
        self._app_commands = {
            "spotify": "spotify:",
            "chrome": "chrome",
            "google chrome": "chrome",
            "edge": "msedge",
            "microsoft edge": "msedge",
            "notepad": "notepad",
            "calculator": "calc",
            "calc": "calc",
            "terminal": "wt",
            "command prompt": "cmd",
            "cmd": "cmd",
            "explorer": "explorer",
            "alarm": "ms-clock:",
            "clock": "ms-clock:",
        }
        self._website_shortcuts = {
            "youtube": "https://www.youtube.com/",
            "yt": "https://www.youtube.com/",
            "spotify": "https://open.spotify.com/",
            "netflix": "https://www.netflix.com/",
            "gmail": "https://mail.google.com/",
            "google": "https://www.google.com/",
            "calendar": "https://calendar.google.com/",
            "drive": "https://drive.google.com/",
            "github": "https://github.com/",
            "linkedin": "https://www.linkedin.com/",
        }

    def shutdown(self) -> None:
        """Best-effort shutdown of background automation resources."""
        managers = []
        try:
            managers.append(getattr(self, "_devtools_manager", None))
        except Exception:
            pass
        for attr in ("whatsapp", "instagram", "gmail", "gmail_template", "calendar", "amazon"):
            try:
                inst = getattr(self, attr, None)
                mgr = getattr(inst, "manager", None) if inst is not None else None
                if mgr is not None:
                    managers.append(mgr)
            except Exception:
                pass

        for mgr in managers:
            if mgr is None:
                continue
            try:
                if hasattr(mgr, "close_async") and self._async_loop is not None:
                    try:
                        fut = asyncio.run_coroutine_threadsafe(mgr.close_async(), self._async_loop)
                        fut.result(timeout=5)
                        continue
                    except Exception:
                        pass
                if hasattr(mgr, "close"):
                    mgr.close()
            except Exception:
                pass

        loop = self._async_loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
        thread = self._async_thread
        if thread is not None:
            try:
                thread.join(timeout=2)
            except Exception:
                pass
        self._async_loop = None
        self._async_thread = None

    def _snapshot_safe(self) -> dict | None:
        try:
            if self.awareness_state is None:
                return None
            return self.awareness_state.get_snapshot()
        except Exception:
            return None

    @staticmethod
    def _verification(ok: bool, method: str, reason: str, extra: dict | None = None) -> dict:
        data = {"ok": bool(ok), "method": str(method or ""), "reason": str(reason or "")}
        if isinstance(extra, dict) and extra:
            for k, v in extra.items():
                if k not in data:
                    data[k] = v
        return data

    def _finalize_action(self, action: str, resp: AutomationResponse, before: dict | None, verification: dict | None) -> AutomationResponse:
        after = self._snapshot_safe()
        return AutomationResponse(
            success=bool(resp.success),
            message=resp.message,
            action=action,
            before_snapshot=before,
            after_snapshot=after,
            verification=verification,
        )

    @staticmethod
    def _screen_hash() -> str | None:
        if ImageGrab is None or Image is None:
            return None
        try:
            try:
                img = ImageGrab.grab(all_screens=True)
            except TypeError:
                img = ImageGrab.grab()
        except Exception:
            return None
        try:
            small = img.convert("L").resize((64, 64))
            return hashlib.md5(small.tobytes()).hexdigest()
        except Exception:
            return None

    @staticmethod
    def _active_window_key(snapshot: dict | None) -> tuple[str | None, str | None, int | None]:
        if not isinstance(snapshot, dict):
            return None, None, None
        win = snapshot.get("active_window") if isinstance(snapshot.get("active_window"), dict) else {}
        title = win.get("title") if isinstance(win.get("title"), str) else None
        proc = win.get("process") if isinstance(win.get("process"), str) else None
        pid = win.get("pid") if isinstance(win.get("pid"), int) else None
        return title, proc, pid

    @staticmethod
    def _focused_key(snapshot: dict | None) -> tuple[str | None, str | None]:
        if not isinstance(snapshot, dict):
            return None, None
        uia = snapshot.get("uia") if isinstance(snapshot.get("uia"), dict) else {}
        elements = uia.get("elements") if isinstance(uia.get("elements"), list) else []
        for el in elements:
            if isinstance(el, dict) and el.get("focused"):
                name = el.get("name") if isinstance(el.get("name"), str) else None
                ctype = el.get("control_type") if isinstance(el.get("control_type"), str) else None
                return name, ctype
        return None, None

    def send_whatsapp(self, contact: str, message: str) -> AutomationResponse:
        before = self._snapshot_safe()
        try:
            result = self.whatsapp.send_message(contact, message)
        except PlaywrightUnavailable as exc:
            resp = AutomationResponse(False, str(exc))
            return self._finalize_action("send_whatsapp", resp, before, self._verification(False, "exception", str(exc)))
        resp = AutomationResponse.from_result(result)
        return self._finalize_action(
            "send_whatsapp",
            resp,
            before,
            self._verification(bool(resp.success), "tool_success", "WhatsApp automation completed."),
        )

    def take_screenshot_region(self, x: int, y: int, w: int, h: int, path: str | None = None) -> AutomationResponse:
        before = self._snapshot_safe()
        try:
            desktop = self.require_desktop()
        except DesktopAutomationUnavailable as exc:
            resp = AutomationResponse(False, str(exc))
            return self._finalize_action("take_screenshot_region", resp, before, self._verification(False, "dependency", str(exc)))

        # Validate inputs
        try:
            xi, yi, wi, hi = int(x), int(y), int(w), int(h)
            if wi <= 0 or hi <= 0:
                resp = AutomationResponse(False, "Region width/height must be positive.")
                return self._finalize_action(
                    "take_screenshot_region", resp, before, self._verification(False, "input_validation", resp.message)
                )
        except Exception:
            resp = AutomationResponse(False, "Invalid region parameters.")
            return self._finalize_action(
                "take_screenshot_region", resp, before, self._verification(False, "input_validation", resp.message)
            )

        target_path = Path(path) if path else (self._default_screenshot_path().with_name(self._default_screenshot_path().stem + "-region.png"))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = desktop.screenshot_region(str(target_path), xi, yi, wi, hi)
            resp = AutomationResponse.from_result(result)
            ok = bool(resp.success) and target_path.exists()
            ver = self._verification(ok, "file_exists", "Screenshot region saved.", {"path": str(target_path)})
            return self._finalize_action("take_screenshot_region", resp, before, ver)
        except Exception as exc:
            resp = AutomationResponse(False, f"Failed to capture region: {exc}")
            return self._finalize_action("take_screenshot_region", resp, before, self._verification(False, "exception", str(exc)))

    def ocr_region(self, x: int, y: int, w: int, h: int) -> AutomationResponse:
        before = self._snapshot_safe()
        before_ts = None
        try:
            if isinstance(before, dict):
                ocr = before.get("ocr") if isinstance(before.get("ocr"), dict) else {}
                before_ts = ocr.get("timestamp") if isinstance(ocr.get("timestamp"), (int, float)) else None
        except Exception:
            before_ts = None
        try:
            desktop = self.require_desktop()
        except DesktopAutomationUnavailable as exc:
            resp = AutomationResponse(False, str(exc))
            return self._finalize_action("ocr_region", resp, before, self._verification(False, "dependency", str(exc)))

        try:
            xi, yi, wi, hi = int(x), int(y), int(w), int(h)
            if wi <= 0 or hi <= 0:
                resp = AutomationResponse(False, "Region width/height must be positive.")
                return self._finalize_action("ocr_region", resp, before, self._verification(False, "input_validation", resp.message))
        except Exception:
            resp = AutomationResponse(False, "Invalid region parameters.")
            return self._finalize_action("ocr_region", resp, before, self._verification(False, "input_validation", resp.message))

        result = desktop.ocr_region(xi, yi, wi, hi)
        data = result.data if isinstance(result.data, dict) else {}
        word_boxes = data.get("word_boxes") if isinstance(data.get("word_boxes"), list) else None
        confidence = data.get("confidence") if isinstance(data.get("confidence"), (int, float)) else None
        try:
            if self.awareness_state:
                if result.success:
                    self.awareness_state.update_ocr_result(result.message, confidence=confidence, word_boxes=word_boxes)
                else:
                    self.awareness_state.update_ocr_error(result.message, confidence=confidence, word_boxes=word_boxes)
        except Exception:
            pass
        resp = AutomationResponse(result.success, result.message)
        after = self._snapshot_safe()
        after_ts = None
        try:
            if isinstance(after, dict):
                ocr = after.get("ocr") if isinstance(after.get("ocr"), dict) else {}
                after_ts = ocr.get("timestamp") if isinstance(ocr.get("timestamp"), (int, float)) else None
        except Exception:
            after_ts = None
        updated = bool(after_ts is not None and (before_ts is None or float(after_ts) >= float(before_ts)))
        ver = self._verification(bool(resp.success) and updated, "ocr_timestamp", "OCR region updated.", {"updated": updated})
        return AutomationResponse(
            success=bool(resp.success),
            message=resp.message,
            action="ocr_region",
            before_snapshot=before,
            after_snapshot=after,
            verification=ver,
        )

    def ocr_screen(self) -> AutomationResponse:
        before = self._snapshot_safe()
        before_ts = None
        try:
            if isinstance(before, dict):
                ocr = before.get("ocr") if isinstance(before.get("ocr"), dict) else {}
                before_ts = ocr.get("timestamp") if isinstance(ocr.get("timestamp"), (int, float)) else None
        except Exception:
            before_ts = None
        try:
            desktop = self.require_desktop()
        except DesktopAutomationUnavailable as exc:
            resp = AutomationResponse(False, str(exc))
            return self._finalize_action("ocr_screen", resp, before, self._verification(False, "dependency", str(exc)))

        result = desktop.ocr_screen()
        data = result.data if isinstance(result.data, dict) else {}
        word_boxes = data.get("word_boxes") if isinstance(data.get("word_boxes"), list) else None
        confidence = data.get("confidence") if isinstance(data.get("confidence"), (int, float)) else None
        try:
            if self.awareness_state:
                if result.success:
                    self.awareness_state.update_ocr_result(result.message, confidence=confidence, word_boxes=word_boxes)
                else:
                    self.awareness_state.update_ocr_error(result.message, confidence=confidence, word_boxes=word_boxes)
        except Exception:
            pass

        resp = AutomationResponse(result.success, result.message)
        after = self._snapshot_safe()
        after_ts = None
        after_text = None
        try:
            if isinstance(after, dict):
                ocr = after.get("ocr") if isinstance(after.get("ocr"), dict) else {}
                after_ts = ocr.get("timestamp") if isinstance(ocr.get("timestamp"), (int, float)) else None
                after_text = ocr.get("text") if isinstance(ocr.get("text"), str) else None
        except Exception:
            after_ts, after_text = None, None

        updated = bool(after_ts is not None and (before_ts is None or float(after_ts) >= float(before_ts)))
        has_text = bool(after_text and after_text.strip())
        ver = self._verification(
            bool(resp.success) and updated and has_text,
            "ocr_timestamp",
            "OCR screen updated.",
            {"updated": updated, "has_text": has_text},
        )
        return AutomationResponse(
            success=bool(resp.success),
            message=resp.message,
            action="ocr_screen",
            before_snapshot=before,
            after_snapshot=after,
            verification=ver,
        )

    def send_instagram_dm(self, username: str, message: str) -> AutomationResponse:
        before = self._snapshot_safe()
        try:
            result = self.instagram.send_dm(username, message)
        except PlaywrightUnavailable as exc:
            resp = AutomationResponse(False, str(exc))
            return self._finalize_action("send_instagram_dm", resp, before, self._verification(False, "exception", str(exc)))
        resp = AutomationResponse.from_result(result)
        return self._finalize_action(
            "send_instagram_dm",
            resp,
            before,
            self._verification(bool(resp.success), "tool_success", "Instagram automation completed."),
        )

    def send_gmail(self, recipient: str, subject: str, body: str) -> AutomationResponse:
        before = self._snapshot_safe()
        result = self.gmail.send_email(recipient, subject, body)
        resp = AutomationResponse(result.success, result.message)
        ver = self._verification(bool(resp.success), "tool_success", "Gmail automation completed.")
        return self._finalize_action("send_gmail", resp, before, ver)

    def prepare_gmail_template(self) -> AutomationResponse:
        before = self._snapshot_safe()
        result = self.gmail_template.compose_email()
        resp = AutomationResponse(result.success, result.message)
        ver = self._verification(bool(resp.success), "tool_success", "Gmail template automation completed.")
        return self._finalize_action("prepare_gmail_template", resp, before, ver)

    def create_calendar_event(
        self,
        title: str,
        date_text: str | None = None,
        start_time: str | None = None,
    ) -> AutomationResponse:
        before = self._snapshot_safe()
        result = self.calendar.create_event(title, date_text, start_time)
        resp = AutomationResponse(result.success, result.message)
        ver = self._verification(bool(resp.success), "tool_success", "Calendar automation completed.")
        return self._finalize_action("create_calendar_event", resp, before, ver)

    def search_amazon(self, query: str) -> AutomationResponse:
        before = self._snapshot_safe()
        result = self.amazon.search(query)
        message = result.message

        if result.success and self.awareness_state:
            context = self.awareness_state.get_window()
            if context:
                title = context.title or context.app_exe or "Amazon"
                message = f"{message} Current window: {title}."

        resp = AutomationResponse(result.success, message)
        return self._finalize_action(
            "search_amazon",
            resp,
            before,
            self._verification(bool(resp.success), "tool_success", "Amazon search automation completed."),
        )

    # ------------------------------------------------------------------
    # Chrome DevTools helpers
    # ------------------------------------------------------------------
    def create_devtools_bridge(self, config: DevToolsConfig | None = None) -> DevToolsBridge:
        """Return a DevTools bridge bound to the shared Playwright manager."""

        return DevToolsBridge(self._devtools_manager, config=config)

    async def summarize_active_tab(self, *, include_dom: bool = False) -> dict:
        """Convenience wrapper to summarize the active Chrome tab via DevTools."""

        async with self.create_devtools_bridge() as bridge:
            return await bridge.summarize(include_dom=include_dom)

    def describe_active_tab(self, *, include_dom: bool = False) -> AutomationResponse:
        """Synchronously summarize the active browser tab via DevTools."""

        before = self._snapshot_safe()

        async def _summarize() -> dict:
            async with self.create_devtools_bridge() as bridge:
                return await bridge.summarize(include_dom=include_dom)

        try:
            summary = self._run_coroutine(_summarize())
        except PlaywrightUnavailable as exc:
            resp = AutomationResponse(False, str(exc))
            return self._finalize_action("describe_active_tab", resp, before, self._verification(False, "dependency", str(exc)))
        except Exception as exc:  # pragma: no cover - transport/runtime errors
            resp = AutomationResponse(False, f"DevTools summarize failed: {exc}")
            return self._finalize_action("describe_active_tab", resp, before, self._verification(False, "exception", str(exc)))

        if not summary:
            resp = AutomationResponse(False, "No active browser tab detected.")
            return self._finalize_action("describe_active_tab", resp, before, self._verification(False, "no_tab", resp.message))

        url = summary.get("url") or "Unknown URL"
        title = summary.get("title") or ""
        descriptor = title or url
        message = f"Active tab: {descriptor} ({url})." if title else f"Active tab: {url}."
        resp = AutomationResponse(True, message)
        ver = self._verification(True, "devtools", "Active tab retrieved.", {"url": url})
        return self._finalize_action("describe_active_tab", resp, before, ver)

    def reload_active_tab(self) -> AutomationResponse:
        """Reload the active tab via DevTools, with retries."""

        before = self._snapshot_safe()

        async def _reload() -> None:
            async with self._devtools_manager.session() as page:
                try:
                    await page.reload(wait_until='domcontentloaded')
                except TypeError:
                    await page.reload()

        try:
            self._run_coroutine_with_retries(lambda: _reload())
            resp = AutomationResponse(True, "Reloaded the active tab.")
            ver = self._verification(True, "devtools", "Reload issued.")
            return self._finalize_action("reload_active_tab", resp, before, ver)
        except PlaywrightUnavailable as exc:
            resp = AutomationResponse(False, str(exc))
            return self._finalize_action("reload_active_tab", resp, before, self._verification(False, "dependency", str(exc)))
        except Exception as exc:  # pragma: no cover
            resp = AutomationResponse(False, f"Reload failed: {exc}")
            return self._finalize_action("reload_active_tab", resp, before, self._verification(False, "exception", str(exc)))

    def launch_application(self, app_name: str, *, args: Optional[list[str]] = None) -> AutomationResponse:
        before = self._snapshot_safe()
        target = (app_name or "").strip().lower()
        if not target:
            resp = AutomationResponse(False, "Please tell me which application to open.")
            return self._finalize_action("launch_application", resp, before, self._verification(False, "input_validation", resp.message))

        command = self._app_commands.get(target)
        if not command:
            resp = AutomationResponse(False, f"I don't know how to open {app_name} yet.")
            return self._finalize_action("launch_application", resp, before, self._verification(False, "unsupported", resp.message))

        # If command is a protocol (e.g., 'spotify:', 'ms-clock:'), prefer os.startfile
        if ":" in command and not command.strip().startswith("http"):
            try:
                os.startfile(command)  # type: ignore[attr-defined]
                pretty = app_name.title()
                resp = AutomationResponse(True, f"Launching {pretty}.")
                ver = self._verification(True, "os_startfile", "Launch requested.", {"command": command})
                return self._finalize_action("launch_application", resp, before, ver)
            except OSError as exc:
                # Fallbacks for known protocols
                if command.startswith("spotify"):
                    # Open web player instead
                    web = self._website_shortcuts.get("spotify", "https://open.spotify.com/")
                    try:
                        webbrowser.open(web)
                        resp = AutomationResponse(True, "Opening Spotify in your browser.")
                        ver = self._verification(True, "webbrowser_open", "Browser open requested.", {"url": web})
                        return self._finalize_action("launch_application", resp, before, ver)
                    except Exception:
                        resp = AutomationResponse(False, f"Couldn't open Spotify: {exc}")
                        return self._finalize_action("launch_application", resp, before, self._verification(False, "exception", str(exc)))
                # Otherwise report failure
                resp = AutomationResponse(False, f"Couldn't launch {app_name}: {exc}")
                return self._finalize_action("launch_application", resp, before, self._verification(False, "exception", str(exc)))

        # CLI executable path. The launcher is cmd.exe, which parses shell
        # metacharacters in its OWN command line even under shell=False. Passing
        # an arg list lets subprocess build that line without quoting '&', so a
        # normal URL ("site.com/?a=1&b=2") was split at the '&' and the remainder
        # run as a separate command — a functional bug and an injection vector.
        # cmd treats metacharacters literally inside double quotes, so the command
        # line is built explicitly with every part quoted. A double quote inside an
        # argument would break that quoting, so those are rejected.
        arg_list = [str(a) for a in (args or [])]
        bad = [a for a in arg_list if '"' in a or any(ch in a for ch in "\r\n\x00")]
        if bad:
            resp = AutomationResponse(
                False, f"Couldn't launch {app_name}: unsafe characters in arguments."
            )
            return self._finalize_action(
                "launch_application", resp, before,
                self._verification(False, "unsafe_arguments", resp.message,
                                   {"rejected": bad}),
            )

        cmdline = f'cmd /c start "" "{command}"'
        for arg in arg_list:
            cmdline += f' "{arg}"'

        try:
            subprocess.Popen(cmdline, shell=False)
        except FileNotFoundError:
            resp = AutomationResponse(False, f"System could not locate {app_name} executable.")
            return self._finalize_action("launch_application", resp, before, self._verification(False, "not_found", resp.message))
        except Exception as exc:
            resp = AutomationResponse(False, f"Couldn't launch {app_name}: {exc}")
            return self._finalize_action("launch_application", resp, before, self._verification(False, "exception", str(exc)))

        details = f" with {' '.join(args)}" if args else ""
        pretty = app_name.title()
        resp = AutomationResponse(True, f"Launching {pretty}{details}.")
        ver = self._verification(True, "subprocess_popen", "Launch requested.", {"command": command, "args": args or []})
        return self._finalize_action("launch_application", resp, before, ver)

    def open_website(self, target: str, *, browser: Optional[str] = None) -> AutomationResponse:
        before = self._snapshot_safe()
        if not target:
            resp = AutomationResponse(False, "Please tell me which website to open.")
            return self._finalize_action("open_website", resp, before, self._verification(False, "input_validation", resp.message))

        # LEGACY CODE PATH DISABLED - Use chrome_pipeline.open_chrome() instead
        browser = (browser or "").lower().strip()
        if "chrome" in browser or not browser:
            raise RuntimeError(
                "Legacy Chrome opening is disabled. Use automation.chrome_pipeline.open_chrome() instead."
            )
        
        strict_attach = os.getenv("STRICT_CHROME_ATTACH", "0").strip().lower() in {"1", "true", "yes", "on"}
        try:
            open_timeout_s = float(os.getenv("OPEN_WEBSITE_TIMEOUT_S", "25") or "25")
        except Exception:
            open_timeout_s = 25.0
        url = self._resolve_url(target)

        def _host_matches(expected: str, actual: str | None) -> tuple[bool, str, str]:
            expected_host = (urlparse(expected).netloc or "").lower()
            actual_host = (urlparse(actual or "").netloc or "").lower() if actual else ""
            ok = bool(actual_host) and (not expected_host or expected_host in actual_host)
            return ok, expected_host, actual_host

        def _already_on_host(snapshot: dict | None, expected_host: str) -> bool:
            if not expected_host or not isinstance(snapshot, dict):
                return False
            try:
                browser_state = snapshot.get("browser") if isinstance(snapshot.get("browser"), dict) else {}
                cur = browser_state.get("url") if isinstance(browser_state.get("url"), str) else ""
                cur_host = (urlparse(cur).netloc or "").lower() if cur else ""
                return bool(cur_host and expected_host in cur_host)
            except Exception:
                return False

        def _try_focus_chrome() -> None:
            try:
                desktop = self.require_desktop()
                try:
                    desktop.focus_window(FocusRequest(title="Chrome"))
                    return
                except Exception:
                    pass
            except Exception:
                pass

            if os.name != "nt":
                return
            try:
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
            except Exception:
                return

            def _force_foreground(hwnd: int) -> None:
                try:
                    try:
                        user32.keybd_event(0x12, 0, 0, 0)
                        user32.keybd_event(0x12, 0, 2, 0)
                    except Exception:
                        pass
                    try:
                        user32.ShowWindow(hwnd, 9)
                    except Exception:
                        pass
                    fg = user32.GetForegroundWindow()
                    fg_tid = user32.GetWindowThreadProcessId(fg, 0)
                    tgt_tid = user32.GetWindowThreadProcessId(hwnd, 0)
                    try:
                        user32.AttachThreadInput(tgt_tid, fg_tid, True)
                    except Exception:
                        pass
                    try:
                        user32.SetForegroundWindow(hwnd)
                    except Exception:
                        pass
                    try:
                        user32.BringWindowToTop(hwnd)
                    except Exception:
                        pass
                    try:
                        user32.SetActiveWindow(hwnd)
                    except Exception:
                        pass
                    try:
                        user32.SwitchToThisWindow(hwnd, True)
                    except Exception:
                        pass
                    try:
                        user32.AttachThreadInput(tgt_tid, fg_tid, False)
                    except Exception:
                        pass
                except Exception:
                    pass

            matches: list[int] = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def enum_proc(hwnd, lparam):
                try:
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    cbuf = ctypes.create_unicode_buffer(256)
                    cls = ""
                    try:
                        if user32.GetClassNameW(hwnd, cbuf, 256):
                            cls = (cbuf.value or "").strip()
                    except Exception:
                        cls = ""

                    length = user32.GetWindowTextLengthW(hwnd)
                    buf = ctypes.create_unicode_buffer(max(2, length + 1))
                    try:
                        user32.GetWindowTextW(hwnd, buf, max(2, length + 1))
                    except Exception:
                        pass
                    title = (buf.value or "").strip()

                    if cls == "Chrome_WidgetWin_1":
                        matches.append(int(hwnd))
                        return False
                    if "chrome" in title.lower():
                        matches.append(int(hwnd))
                    return True
                except Exception:
                    return True

            try:
                user32.EnumWindows(enum_proc, 0)
            except Exception:
                return

            if not matches:
                return
            _force_foreground(matches[0])

        async def _devtools_navigate_verify() -> str | None:
            bridge = DevToolsBridge(
                self._devtools_manager,
                DevToolsConfig(remote_port=getattr(self._devtools_manager, "remote_debug_port", 9222)),
            )
            await bridge.connect()
            try:
                await bridge.navigate(url)
                deadline = time.time() + 8.0
                last_url: str | None = None
                expected_host = (urlparse(url).netloc or "").lower()
                while time.time() < deadline:
                    loc = await bridge.get_location()
                    candidate = loc.get("url") if isinstance(loc, dict) else None
                    if isinstance(candidate, str) and candidate:
                        last_url = candidate
                        host = (urlparse(candidate).netloc or "").lower()
                        if expected_host and expected_host in host:
                            return candidate
                    await asyncio.sleep(0.35)
                return last_url
            finally:
                try:
                    await bridge.close()
                except Exception:
                    pass

        if browser in {"chrome", "google chrome"}:
            # Try DevTools attach to existing Chrome first (with retries)
            async def _goto() -> tuple[str | None, bool]:
                async with self._devtools_manager.session() as page:
                    target_page = page

                    async def _navigate(p) -> tuple[str | None, bool]:
                        try:
                            if hasattr(p, "bring_to_front"):
                                await p.bring_to_front()
                        except Exception:
                            pass

                        try:
                            current_url = getattr(p, "url", None)
                        except Exception:
                            current_url = None
                        if isinstance(current_url, str) and current_url:
                            try:
                                ok, _, _ = _host_matches(url, current_url)
                            except Exception:
                                ok = False
                            if ok:
                                return current_url, True

                        await p.goto(url, wait_until="domcontentloaded", timeout=15000)
                        try:
                            if hasattr(p, "bring_to_front"):
                                await p.bring_to_front()
                        except Exception:
                            pass
                        try:
                            return p.url, False
                        except Exception:
                            return None, False

                    try:
                        return await _navigate(target_page)
                    except Exception:
                        try:
                            self._devtools_manager.invalidate_cache()
                        except Exception:
                            pass
                        raise
            try:
                nav_result = self._run_coroutine_with_retries(lambda: asyncio.wait_for(_goto(), timeout=open_timeout_s))
                actual_url = None
                already = False
                try:
                    if isinstance(nav_result, (list, tuple)) and len(nav_result) >= 2:
                        actual_url = nav_result[0]
                        already = bool(nav_result[1])
                    else:
                        actual_url = nav_result
                except Exception:
                    actual_url = nav_result
                ok, expected_host, actual_host = _host_matches(url, actual_url)
                display = self._site_display_name(url)
                msg = f"Opening {display} in Chrome."
                if already or _already_on_host(before, expected_host):
                    msg = f"You are already on {display}. Bringing Chrome to the front."
                resp = AutomationResponse(True, msg)
                _try_focus_chrome()
                ver = self._verification(
                    ok,
                    "devtools_url",
                    "Navigation verified via DevTools.",
                    {"expected": expected_host, "actual": actual_host},
                )
                return self._finalize_action("open_website", resp, before, ver)
            except asyncio.TimeoutError:
                resp = AutomationResponse(False, f"Timed out while opening {self._site_display_name(url)} in Chrome.")
                return self._finalize_action("open_website", resp, before, self._verification(False, "timeout", resp.message))
            except PlaywrightUnavailable:
                try:
                    actual_url = self._run_coroutine_with_retries(
                        lambda: asyncio.wait_for(_devtools_navigate_verify(), timeout=open_timeout_s),
                        attempts=2,
                        delay=0.4,
                    )
                    ok, expected_host, actual_host = _host_matches(url, actual_url)
                    display = self._site_display_name(url)
                    msg = f"Opening {display} in Chrome."
                    if _already_on_host(before, expected_host):
                        msg = f"You are already on {display}. Bringing Chrome to the front."
                    resp = AutomationResponse(True, msg)
                    _try_focus_chrome()
                    ver = self._verification(
                        ok,
                        "devtools_ws_url",
                        "Navigation verified via DevTools.",
                        {"expected": expected_host, "actual": actual_host},
                    )
                    return self._finalize_action("open_website", resp, before, ver)
                except Exception:
                    if strict_attach:
                        resp = AutomationResponse(
                            False,
                            (
                                "Chrome DevTools attach failed (STRICT_CHROME_ATTACH=1). "
                                "Start Chrome with --remote-debugging-port=9222 and try again."
                            ),
                        )
                        return self._finalize_action("open_website", resp, before, self._verification(False, "dependency", resp.message))
                    result = self.launch_application("chrome", args=[url])
                    if result.success:
                        resp = AutomationResponse(True, f"Opening {self._site_display_name(url)} in Chrome.")
                        ver = self._verification(False, "system_launch", "Launch requested but cannot verify navigation.", {"url": url})
                        return self._finalize_action("open_website", resp, before, ver)
                    return result
            except Exception as exc:
                try:
                    self._devtools_manager.invalidate_cache()
                except Exception:
                    pass
                try:
                    actual_url = self._run_coroutine_with_retries(lambda: _goto(), attempts=1)
                    resp = AutomationResponse(True, f"Opening {self._site_display_name(url)} in Chrome.")
                    ok, expected_host, actual_host = _host_matches(url, actual_url)
                    ver = self._verification(
                        ok,
                        "devtools_url",
                        "Navigation verified via DevTools.",
                        {"expected": expected_host, "actual": actual_host},
                    )
                    return self._finalize_action("open_website", resp, before, ver)
                except Exception:
                    if strict_attach:
                        resp = AutomationResponse(
                            False,
                            (
                                "Chrome DevTools attach failed (STRICT_CHROME_ATTACH=1). "
                                "Start Chrome with --remote-debugging-port=9222 and try again."
                            ),
                        )
                        return self._finalize_action("open_website", resp, before, self._verification(False, "dependency", resp.message))
                    try:
                        try:
                            actual_url = self._run_coroutine_with_retries(lambda: _devtools_navigate_verify(), attempts=1, delay=0.4)
                            resp = AutomationResponse(True, f"Opening {self._site_display_name(url)} in Chrome.")
                            ok, expected_host, actual_host = _host_matches(url, actual_url)
                            ver = self._verification(
                                ok,
                                "devtools_ws_url",
                                "Navigation verified via DevTools.",
                                {"expected": expected_host, "actual": actual_host},
                            )
                            return self._finalize_action("open_website", resp, before, ver)
                        except Exception:
                            webbrowser.open(url)
                            resp = AutomationResponse(
                                True,
                                (
                                    "DevTools attach failed; opening "
                                    f"{self._site_display_name(url)} in your default browser."
                                ),
                            )
                            ver = self._verification(False, "webbrowser_open", "Browser open requested but cannot verify navigation.", {"url": url})
                            return self._finalize_action("open_website", resp, before, ver)
                    except Exception:
                        resp = AutomationResponse(False, f"Couldn't open {url}: {exc}")
                        return self._finalize_action("open_website", resp, before, self._verification(False, "exception", str(exc)))
        if browser in {"edge", "microsoft edge"}:
            result = self.launch_application("edge", args=[url])
            if result.success:
                resp = AutomationResponse(True, f"Opening {self._site_display_name(url)} in Edge.")
                ver = self._verification(False, "system_launch", "Launch requested but cannot verify navigation.", {"url": url})
                return self._finalize_action("open_website", resp, before, ver)
            return result

        # Default case: prefer DevTools (attaches to your existing Chrome), else system default browser
        async def _goto_default() -> tuple[str | None, bool]:
            async with self._devtools_manager.session() as page:
                target_page = page

                async def _navigate(p) -> tuple[str | None, bool]:
                    try:
                        if hasattr(p, "bring_to_front"):
                            await p.bring_to_front()
                    except Exception:
                        pass

                    try:
                        current_url = getattr(p, "url", None)
                    except Exception:
                        current_url = None
                    if isinstance(current_url, str) and current_url:
                        try:
                            ok, _, _ = _host_matches(url, current_url)
                        except Exception:
                            ok = False
                        if ok:
                            return current_url, True

                    await p.goto(url, wait_until="domcontentloaded", timeout=15000)
                    try:
                        if hasattr(p, "bring_to_front"):
                            await p.bring_to_front()
                    except Exception:
                        pass
                    try:
                        return p.url, False
                    except Exception:
                        return None, False

                try:
                    return await _navigate(target_page)
                except Exception:
                    try:
                        self._devtools_manager.invalidate_cache()
                    except Exception:
                        pass
                    raise
        try:
            nav_result = self._run_coroutine_with_retries(lambda: asyncio.wait_for(_goto_default(), timeout=open_timeout_s))
            actual_url = None
            already = False
            try:
                if isinstance(nav_result, (list, tuple)) and len(nav_result) >= 2:
                    actual_url = nav_result[0]
                    already = bool(nav_result[1])
                else:
                    actual_url = nav_result
            except Exception:
                actual_url = nav_result
            expected_host = (urlparse(url).netloc or "").lower()
            actual_host = (urlparse(actual_url or "").netloc or "").lower() if actual_url else ""
            ok = bool(actual_url) and (not expected_host or expected_host in actual_host)
            display = self._site_display_name(url)
            msg = f"Opening {display} in Chrome."
            if already or _already_on_host(before, expected_host):
                msg = f"You are already on {display}. Bringing Chrome to the front."
            resp = AutomationResponse(True, msg)
            _try_focus_chrome()
            ver = self._verification(ok, "devtools_url", "Navigation verified via DevTools.", {"expected": expected_host, "actual": actual_host})
            return self._finalize_action("open_website", resp, before, ver)
        except asyncio.TimeoutError:
            resp = AutomationResponse(False, f"Timed out while opening {self._site_display_name(url)} in Chrome.")
            return self._finalize_action("open_website", resp, before, self._verification(False, "timeout", resp.message))
        except PlaywrightUnavailable:
            if strict_attach:
                resp = AutomationResponse(
                    False,
                    (
                        "Chrome DevTools is not available (STRICT_CHROME_ATTACH=1). "
                        "Start Chrome with --remote-debugging-port=9222 and try again."
                    ),
                )
                return self._finalize_action("open_website", resp, before, self._verification(False, "dependency", resp.message))
            try:
                webbrowser.open(url)
            except webbrowser.Error as exc:
                resp = AutomationResponse(False, f"Couldn't open {url}: {exc}")
                return self._finalize_action("open_website", resp, before, self._verification(False, "exception", str(exc)))
            resp = AutomationResponse(
                True,
                f"DevTools attach failed; opening {self._site_display_name(url)} in your default browser.",
            )
            ver = self._verification(False, "webbrowser_open", "Browser open requested but cannot verify navigation.", {"url": url})
            return self._finalize_action("open_website", resp, before, ver)
        except Exception as exc:
            try:
                self._devtools_manager.invalidate_cache()
            except Exception:
                pass
            try:
                nav_result = self._run_coroutine_with_retries(lambda: _goto_default(), attempts=1)
                actual_url = None
                try:
                    if isinstance(nav_result, (list, tuple)) and len(nav_result) >= 1:
                        actual_url = nav_result[0]
                    else:
                        actual_url = nav_result
                except Exception:
                    actual_url = nav_result
                resp = AutomationResponse(True, f"Opening {self._site_display_name(url)} in Chrome.")
                expected_host = (urlparse(url).netloc or "").lower()
                actual_host = (urlparse(actual_url or "").netloc or "").lower() if actual_url else ""
                ok = bool(actual_url) and (not expected_host or expected_host in actual_host)
                ver = self._verification(ok, "devtools_url", "Navigation verified via DevTools.", {"expected": expected_host, "actual": actual_host})
                return self._finalize_action("open_website", resp, before, ver)
            except Exception:
                if strict_attach:
                    resp = AutomationResponse(
                        False,
                        (
                            "Chrome DevTools attach failed (STRICT_CHROME_ATTACH=1). "
                            "Start Chrome with --remote-debugging-port=9222 and try again."
                        ),
                    )
                    return self._finalize_action("open_website", resp, before, self._verification(False, "dependency", resp.message))
                try:
                    webbrowser.open(url)
                    resp = AutomationResponse(
                        True,
                        f"DevTools attach failed; opening {self._site_display_name(url)} in your default browser.",
                    )
                    ver = self._verification(False, "webbrowser_open", "Browser open requested but cannot verify navigation.", {"url": url})
                    return self._finalize_action("open_website", resp, before, ver)
                except Exception:
                    resp = AutomationResponse(False, f"Couldn't open {url}: {exc}")
                    return self._finalize_action("open_website", resp, before, self._verification(False, "exception", str(exc)))

    def youtube_search_and_click_first(self, query: str) -> AutomationResponse:
        before = self._snapshot_safe()
        async def _task() -> str | None:
            async with self._devtools_manager.session() as page:
                url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
                await page.goto(url)
                await page.wait_for_load_state('domcontentloaded')
                await self._dismiss_youtube_consent(page)
                await self._click_first_watch_link(page)
                try:
                    await page.wait_for_timeout(800)
                except Exception:
                    pass
                try:
                    return page.url
                except Exception:
                    return None

        try:
            actual_url = self._run_coroutine_with_retries(lambda: _task())
            resp = AutomationResponse(True, f"Playing the first result for '{query}' on YouTube.")
            ok = bool(actual_url) and ("/watch" in (actual_url or ""))
            ver = self._verification(ok, "devtools_url", "YouTube result navigation verified.", {"url": actual_url})
            return self._finalize_action("youtube_search_and_click_first", resp, before, ver)
        except PlaywrightUnavailable as exc:
            # Fallback to default browser open when Chrome DevTools isn't available
            url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
            strict_attach = os.getenv("STRICT_CHROME_ATTACH", "0").strip().lower() in {"1", "true", "yes", "on"}
            if strict_attach:
                resp = AutomationResponse(
                    False,
                    (
                        "Chrome DevTools is not available (STRICT_CHROME_ATTACH=1). "
                        "Start Chrome with: chrome --remote-debugging-port=9222 --profile-directory=\"Default\""
                    ),
                )
                return self._finalize_action(
                    "youtube_search_and_click_first",
                    resp,
                    before,
                    self._verification(False, "dependency", resp.message),
                )
            try:
                webbrowser.open(url)
                resp = AutomationResponse(
                    True,
                    (
                        "Opening YouTube results in your default browser. "
                        "To auto-click the first result next time, start Chrome with: "
                        "chrome --remote-debugging-port=9222 --profile-directory=\"Default\""
                    ),
                )
                ver = self._verification(False, "webbrowser_open", "Browser open requested but cannot verify playback.", {"url": url})
                return self._finalize_action("youtube_search_and_click_first", resp, before, ver)
            except Exception:
                resp = AutomationResponse(False, str(exc))
                return self._finalize_action(
                    "youtube_search_and_click_first",
                    resp,
                    before,
                    self._verification(False, "exception", str(exc)),
                )
        except Exception as exc:  # pragma: no cover
            resp = AutomationResponse(False, f"YouTube automation failed: {exc}")
            return self._finalize_action(
                "youtube_search_and_click_first",
                resp,
                before,
                self._verification(False, "exception", str(exc)),
            )

    def youtube_open_and_click_first(self) -> AutomationResponse:
        before = self._snapshot_safe()
        async def _task() -> str | None:
            async with self._devtools_manager.session() as page:
                await page.goto("https://www.youtube.com/")
                await page.wait_for_load_state('domcontentloaded')
                await self._dismiss_youtube_consent(page)
                await self._click_first_watch_link(page)
                try:
                    await page.wait_for_timeout(800)
                except Exception:
                    pass
                try:
                    return page.url
                except Exception:
                    return None

        try:
            actual_url = self._run_coroutine_with_retries(lambda: _task())
            resp = AutomationResponse(True, "Playing the first video on YouTube Home.")
            ok = bool(actual_url) and ("/watch" in (actual_url or ""))
            ver = self._verification(ok, "devtools_url", "YouTube home navigation verified.", {"url": actual_url})
            return self._finalize_action("youtube_open_and_click_first", resp, before, ver)
        except PlaywrightUnavailable as exc:
            try:
                webbrowser.open("https://www.youtube.com/")
                resp = AutomationResponse(True, "Opening YouTube in your default browser.")
                ver = self._verification(False, "webbrowser_open", "Browser open requested but cannot verify playback.", {"url": "https://www.youtube.com/"})
                return self._finalize_action("youtube_open_and_click_first", resp, before, ver)
            except Exception:
                resp = AutomationResponse(False, str(exc))
                return self._finalize_action(
                    "youtube_open_and_click_first",
                    resp,
                    before,
                    self._verification(False, "exception", str(exc)),
                )
        except Exception as exc:
            resp = AutomationResponse(False, f"YouTube automation failed: {exc}")
            return self._finalize_action(
                "youtube_open_and_click_first",
                resp,
                before,
                self._verification(False, "exception", str(exc)),
            )

    def youtube_search_and_click_n(self, query: str, index: int) -> AutomationResponse:
        before = self._snapshot_safe()
        async def _task() -> str | None:
            async with self._devtools_manager.session() as page:
                url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
                await page.goto(url)
                await page.wait_for_load_state('domcontentloaded')
                await self._dismiss_youtube_consent(page)
                # Scroll and select Nth /watch link (skip shorts/channels)
                sel = 'a[href*="/watch"]'
                # Try up to 3 scrolls to load enough results
                for _ in range(3):
                    count = await page.locator(sel).count()
                    if count >= index:
                        break
                    await page.mouse.wheel(0, 2000)
                    await page.wait_for_timeout(400)
                await page.wait_for_selector(sel, timeout=20000)
                await page.locator(sel).nth(max(index - 1, 0)).click()
                try:
                    await page.wait_for_timeout(800)
                except Exception:
                    pass
                try:
                    return page.url
                except Exception:
                    return None

        try:
            actual_url = self._run_coroutine_with_retries(lambda: _task())
            resp = AutomationResponse(True, f"Playing the {index} video for '{query}' on YouTube.")
            ok = bool(actual_url) and ("/watch" in (actual_url or ""))
            ver = self._verification(ok, "devtools_url", "YouTube result navigation verified.", {"index": index, "url": actual_url})
            return self._finalize_action("youtube_search_and_click_n", resp, before, ver)
        except PlaywrightUnavailable as exc:
            try:
                url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
                webbrowser.open(url)
                resp = AutomationResponse(True, "Opening YouTube results in your default browser.")
                ver = self._verification(False, "webbrowser_open", "Browser open requested but cannot verify playback.", {"url": url})
                return self._finalize_action("youtube_search_and_click_n", resp, before, ver)
            except Exception:
                resp = AutomationResponse(False, str(exc))
                return self._finalize_action(
                    "youtube_search_and_click_n",
                    resp,
                    before,
                    self._verification(False, "exception", str(exc)),
                )
        except Exception as exc:
            resp = AutomationResponse(False, f"YouTube automation failed: {exc}")
            return self._finalize_action(
                "youtube_search_and_click_n",
                resp,
                before,
                self._verification(False, "exception", str(exc)),
            )

    def _with_player_focus(self, page) -> None:
        async def _focus():
            try:
                await page.click('video')
            except Exception:
                pass
        return _focus()

    def _click_first_watch_link(self, page) -> None:
        async def _click():
            # Prefer /watch video links over shorts or channel links
            selectors = [
                'a[href*="/watch"]',
                'ytd-video-renderer a#video-title',
                'a#video-title',
                'a#video-title-link',
            ]
            # Retry with small scrolls if none visible yet
            for attempt in range(4):
                for sel in selectors:
                    try:
                        loc = page.locator(sel)
                        if await loc.count() > 0:
                            await page.wait_for_selector(sel, timeout=20000)
                            await loc.first.scroll_into_view_if_needed()
                            await loc.first.click()
                            return
                    except Exception:
                        continue
                await page.mouse.wheel(0, 1500)
                await page.wait_for_timeout(350)
            raise RuntimeError("No clickable video link found on YouTube page.")
        return _click()

    def _dismiss_youtube_consent(self, page) -> None:
        async def _dismiss():
            try:
                await page.wait_for_timeout(500)
                selectors = [
                    'button:has-text("I agree")',
                    'button:has-text("Agree")',
                    'button:has-text("Accept all")',
                    'button:has-text("Accept")',
                    'form[action*="consent"] button:has-text("I agree")',
                ]
                for sel in selectors:
                    try:
                        loc = page.locator(sel)
                        if await loc.count() > 0:
                            await loc.first.click(timeout=2000)
                            await page.wait_for_timeout(400)
                            break
                    except Exception:
                        continue
            except Exception:
                pass
        return _dismiss()

    def youtube_next_video(self) -> AutomationResponse:
        before = self._snapshot_safe()
        async def _task() -> tuple[str | None, str | None]:
            async with self._devtools_manager.session() as page:
                await self._with_player_focus(page)
                try:
                    before_url = page.url
                except Exception:
                    before_url = None
                await page.keyboard.press('Shift+N')
                try:
                    await page.wait_for_timeout(800)
                except Exception:
                    pass
                try:
                    after_url = page.url
                except Exception:
                    after_url = None
                return before_url, after_url
        try:
            before_url, after_url = self._run_coroutine_with_retries(lambda: _task())
            resp = AutomationResponse(True, "Playing next video.")
            ok = bool(before_url and after_url and before_url != after_url)
            ver = self._verification(ok, "devtools_url_diff", "YouTube next verified.", {"before": before_url, "after": after_url})
            return self._finalize_action("youtube_next_video", resp, before, ver)
        except Exception as exc:
            resp = AutomationResponse(False, f"YouTube automation failed: {exc}")
            return self._finalize_action("youtube_next_video", resp, before, self._verification(False, "exception", str(exc)))

    def youtube_prev_video(self) -> AutomationResponse:
        before = self._snapshot_safe()
        async def _task() -> tuple[str | None, str | None]:
            async with self._devtools_manager.session() as page:
                await self._with_player_focus(page)
                try:
                    before_url = page.url
                except Exception:
                    before_url = None
                await page.keyboard.press('Shift+P')
                try:
                    await page.wait_for_timeout(800)
                except Exception:
                    pass
                try:
                    after_url = page.url
                except Exception:
                    after_url = None
                return before_url, after_url
        try:
            before_url, after_url = self._run_coroutine_with_retries(lambda: _task())
            resp = AutomationResponse(True, "Playing previous video.")
            ok = bool(before_url and after_url and before_url != after_url)
            ver = self._verification(ok, "devtools_url_diff", "YouTube previous verified.", {"before": before_url, "after": after_url})
            return self._finalize_action("youtube_prev_video", resp, before, ver)
        except Exception as exc:
            resp = AutomationResponse(False, f"YouTube automation failed: {exc}")
            return self._finalize_action("youtube_prev_video", resp, before, self._verification(False, "exception", str(exc)))

    def youtube_toggle_pause(self) -> AutomationResponse:
        before = self._snapshot_safe()
        async def _task() -> tuple[bool | None, bool | None]:
            async with self._devtools_manager.session() as page:
                await self._with_player_focus(page)
                try:
                    before_paused = await page.evaluate("""() => { const v = document.querySelector('video'); return v ? v.paused : null; }""")
                except Exception:
                    before_paused = None
                await page.keyboard.press('K')
                try:
                    await page.wait_for_timeout(500)
                except Exception:
                    pass
                try:
                    after_paused = await page.evaluate("""() => { const v = document.querySelector('video'); return v ? v.paused : null; }""")
                except Exception:
                    after_paused = None
                return before_paused, after_paused
        try:
            before_paused, after_paused = self._run_coroutine_with_retries(lambda: _task())
            resp = AutomationResponse(True, "Toggled play/pause.")
            ok = bool(before_paused is not None and after_paused is not None and bool(before_paused) != bool(after_paused))
            ver = self._verification(ok, "video_state", "YouTube play/pause verified.", {"before_paused": before_paused, "after_paused": after_paused})
            return self._finalize_action("youtube_toggle_pause", resp, before, ver)
        except Exception as exc:
            resp = AutomationResponse(False, f"YouTube automation failed: {exc}")
            return self._finalize_action("youtube_toggle_pause", resp, before, self._verification(False, "exception", str(exc)))

    def youtube_forward(self, seconds: int = 10) -> AutomationResponse:
        before = self._snapshot_safe()
        steps = max(int(seconds // 10), 1)
        async def _task() -> tuple[float | None, float | None]:
            async with self._devtools_manager.session() as page:
                await self._with_player_focus(page)
                try:
                    before_t = await page.evaluate("""() => { const v = document.querySelector('video'); return v ? v.currentTime : null; }""")
                except Exception:
                    before_t = None
                for _ in range(steps):
                    await page.keyboard.press('L')
                try:
                    await page.wait_for_timeout(500)
                except Exception:
                    pass
                try:
                    after_t = await page.evaluate("""() => { const v = document.querySelector('video'); return v ? v.currentTime : null; }""")
                except Exception:
                    after_t = None
                return before_t, after_t
        try:
            before_t, after_t = self._run_coroutine_with_retries(lambda: _task())
            resp = AutomationResponse(True, f"Fast forwarded {steps*10} seconds.")
            ok = bool(before_t is not None and after_t is not None and (float(after_t) - float(before_t)) >= 5.0)
            ver = self._verification(ok, "video_time", "YouTube forward verified.", {"before": before_t, "after": after_t, "seconds": steps * 10})
            return self._finalize_action("youtube_forward", resp, before, ver)
        except Exception as exc:
            resp = AutomationResponse(False, f"YouTube automation failed: {exc}")
            return self._finalize_action("youtube_forward", resp, before, self._verification(False, "exception", str(exc)))

    def youtube_rewind(self, seconds: int = 10) -> AutomationResponse:
        before = self._snapshot_safe()
        steps = max(int(seconds // 10), 1)
        async def _task() -> tuple[float | None, float | None]:
            async with self._devtools_manager.session() as page:
                await self._with_player_focus(page)
                try:
                    before_t = await page.evaluate("""() => { const v = document.querySelector('video'); return v ? v.currentTime : null; }""")
                except Exception:
                    before_t = None
                for _ in range(steps):
                    await page.keyboard.press('J')
                try:
                    await page.wait_for_timeout(500)
                except Exception:
                    pass
                try:
                    after_t = await page.evaluate("""() => { const v = document.querySelector('video'); return v ? v.currentTime : null; }""")
                except Exception:
                    after_t = None
                return before_t, after_t
        try:
            before_t, after_t = self._run_coroutine_with_retries(lambda: _task())
            resp = AutomationResponse(True, f"Rewound {steps*10} seconds.")
            ok = bool(before_t is not None and after_t is not None and (float(before_t) - float(after_t)) >= 5.0)
            ver = self._verification(ok, "video_time", "YouTube rewind verified.", {"before": before_t, "after": after_t, "seconds": steps * 10})
            return self._finalize_action("youtube_rewind", resp, before, ver)
        except Exception as exc:
            resp = AutomationResponse(False, f"YouTube automation failed: {exc}")
            return self._finalize_action("youtube_rewind", resp, before, self._verification(False, "exception", str(exc)))

    # ------------------------------------------------------------------
    # Desktop helpers
    # ------------------------------------------------------------------
    def require_desktop(self) -> DesktopAutomation:
        """Return the desktop automation helper or raise if unavailable."""

        if self._desktop is None:
            raise DesktopAutomationUnavailable(
                "Desktop automation is disabled or dependencies are missing."
            )
        return self._desktop

    def click(self, x: int, y: int, *, button: str = "left") -> AutomationResponse:
        before = self._snapshot_safe()
        before_hash = self._screen_hash()
        try:
            desktop = self.require_desktop()
        except DesktopAutomationUnavailable as exc:
            resp = AutomationResponse(False, str(exc))
            return self._finalize_action("desktop_click", resp, before, self._verification(False, "dependency", str(exc)))

        try:
            xi, yi = int(x), int(y)
        except Exception:
            resp = AutomationResponse(False, "Invalid click coordinates.")
            return self._finalize_action("desktop_click", resp, before, self._verification(False, "input_validation", resp.message))

        result = desktop.click((xi, yi), button=button)
        resp = AutomationResponse.from_result(result)
        win_before = self._active_window_key(before)
        foc_before = self._focused_key(before)
        try:
            if before_hash is not None:
                time.sleep(0.15)
        except Exception:
            pass
        after = self._snapshot_safe()
        after_hash = self._screen_hash()
        win_after = self._active_window_key(after)
        foc_after = self._focused_key(after)
        changed = bool(win_before != win_after or foc_before != foc_after)
        screen_changed = bool(before_hash is not None and after_hash is not None and before_hash != after_hash)
        ok = bool(resp.success) and (changed or screen_changed)
        reason = "Click verified." if ok else ("No detectable UI change after click." if before_hash is not None else "Unable to capture screenshots to verify click.")
        ver = self._verification(ok, "snapshot_or_screen", reason, {"focus_or_window_changed": changed, "screen_changed": screen_changed})
        return AutomationResponse(
            success=bool(resp.success),
            message=resp.message,
            action="desktop_click",
            before_snapshot=before,
            after_snapshot=after,
            verification=ver,
        )

    def double_click(self, x: int, y: int, *, button: str = "left") -> AutomationResponse:
        before = self._snapshot_safe()
        before_hash = self._screen_hash()
        try:
            desktop = self.require_desktop()
        except DesktopAutomationUnavailable as exc:
            resp = AutomationResponse(False, str(exc))
            return self._finalize_action("desktop_double_click", resp, before, self._verification(False, "dependency", str(exc)))

        try:
            xi, yi = int(x), int(y)
        except Exception:
            resp = AutomationResponse(False, "Invalid double-click coordinates.")
            return self._finalize_action(
                "desktop_double_click", resp, before, self._verification(False, "input_validation", resp.message)
            )

        result = desktop.double_click((xi, yi), button=button)
        resp = AutomationResponse.from_result(result)
        win_before = self._active_window_key(before)
        foc_before = self._focused_key(before)
        try:
            if before_hash is not None:
                time.sleep(0.15)
        except Exception:
            pass
        after = self._snapshot_safe()
        after_hash = self._screen_hash()
        win_after = self._active_window_key(after)
        foc_after = self._focused_key(after)
        changed = bool(win_before != win_after or foc_before != foc_after)
        screen_changed = bool(before_hash is not None and after_hash is not None and before_hash != after_hash)
        ok = bool(resp.success) and (changed or screen_changed)
        reason = "Double click verified." if ok else ("No detectable UI change after double click." if before_hash is not None else "Unable to capture screenshots to verify double click.")
        ver = self._verification(ok, "snapshot_or_screen", reason, {"focus_or_window_changed": changed, "screen_changed": screen_changed})
        return AutomationResponse(
            success=bool(resp.success),
            message=resp.message,
            action="desktop_double_click",
            before_snapshot=before,
            after_snapshot=after,
            verification=ver,
        )

    def scroll(self, amount: int) -> AutomationResponse:
        before = self._snapshot_safe()
        before_hash = self._screen_hash()
        win_before = self._active_window_key(before)
        foc_before = self._focused_key(before)
        try:
            desktop = self.require_desktop()
        except DesktopAutomationUnavailable as exc:
            resp = AutomationResponse(False, str(exc))
            return self._finalize_action("desktop_scroll", resp, before, self._verification(False, "dependency", str(exc)))

        try:
            amt = int(amount)
        except Exception:
            resp = AutomationResponse(False, "Invalid scroll amount.")
            return self._finalize_action("desktop_scroll", resp, before, self._verification(False, "input_validation", resp.message))

        result = desktop.scroll(amt)
        resp = AutomationResponse.from_result(result)
        try:
            if before_hash is not None:
                time.sleep(0.15)
        except Exception:
            pass
        after = self._snapshot_safe()
        after_hash = self._screen_hash()
        win_after = self._active_window_key(after)
        foc_after = self._focused_key(after)
        changed = bool(win_before != win_after or foc_before != foc_after)
        screen_changed = bool(before_hash is not None and after_hash is not None and before_hash != after_hash)
        ok = bool(resp.success) and (screen_changed or changed)
        reason = (
            "Scroll verified."
            if ok
            else (
                "No detectable UI change after scroll."
                if before_hash is not None
                else "Unable to capture screenshots to verify scroll."
            )
        )
        ver = self._verification(
            ok,
            "snapshot_or_screen",
            reason,
            {"focus_or_window_changed": changed, "screen_changed": screen_changed},
        )
        return AutomationResponse(
            success=bool(resp.success),
            message=resp.message,
            action="desktop_scroll",
            before_snapshot=before,
            after_snapshot=after,
            verification=ver,
        )

    def focus_window(self, *, title: str | None = None, exe: str | None = None) -> AutomationResponse:
        before = self._snapshot_safe()
        try:
            desktop = self.require_desktop()
        except DesktopAutomationUnavailable as exc:
            resp = AutomationResponse(False, str(exc))
            return self._finalize_action("focus_window", resp, before, self._verification(False, "dependency", str(exc)))

        request = FocusRequest(title=title, exe=exe)
        if not request.is_valid():
            resp = AutomationResponse(False, "Provide a window title or executable to focus.")
            return self._finalize_action("focus_window", resp, before, self._verification(False, "input_validation", resp.message))

        result = desktop.focus_window(request)
        resp = AutomationResponse.from_result(result)
        after = self._snapshot_safe()
        title_after, proc_after, _ = self._active_window_key(after)
        ok = bool(resp.success)
        if title:
            ok = ok and bool(title_after and title.lower() in title_after.lower())
        if exe:
            ok = ok and bool(proc_after and exe.lower() in proc_after.lower())
        ver = self._verification(ok, "active_window", "Focus verified.", {"title": title, "exe": exe})
        return AutomationResponse(
            success=bool(resp.success),
            message=resp.message,
            action="focus_window",
            before_snapshot=before,
            after_snapshot=after,
            verification=ver,
        )

    def type_text(self, text: str, *, interval: float = 0.0) -> AutomationResponse:
        before = self._snapshot_safe()
        try:
            desktop = self.require_desktop()
        except DesktopAutomationUnavailable as exc:
            resp = AutomationResponse(False, str(exc))
            return self._finalize_action("type_text", resp, before, self._verification(False, "dependency", str(exc)))

        if not text.strip():
            resp = AutomationResponse(False, "Nothing to type.")
            return self._finalize_action("type_text", resp, before, self._verification(False, "input_validation", resp.message))

        result = desktop.type_text(text, interval=interval)
        resp = AutomationResponse.from_result(result)
        try:
            if self.awareness_state is not None and resp.success:
                self.ocr_screen()
        except Exception:
            pass
        after = self._snapshot_safe()
        needle = (text or "").strip()
        needle = needle[:32]
        ocr_text = None
        try:
            if isinstance(after, dict):
                ocr = after.get("ocr") if isinstance(after.get("ocr"), dict) else {}
                ocr_text = ocr.get("text") if isinstance(ocr.get("text"), str) else None
        except Exception:
            ocr_text = None
        ok = bool(resp.success) and bool(ocr_text and needle and needle.lower() in ocr_text.lower())
        ver = self._verification(ok, "ocr_contains", "Typed text verified via OCR.", {"snippet": needle})
        return AutomationResponse(
            success=bool(resp.success),
            message=resp.message,
            action="type_text",
            before_snapshot=before,
            after_snapshot=after,
            verification=ver,
        )

    def press_hotkey(self, *keys: str) -> AutomationResponse:
        before = self._snapshot_safe()
        before_hash = self._screen_hash()
        win_before = self._active_window_key(before)
        foc_before = self._focused_key(before)
        try:
            desktop = self.require_desktop()
        except DesktopAutomationUnavailable as exc:
            resp = AutomationResponse(False, str(exc))
            return self._finalize_action("desktop_hotkey", resp, before, self._verification(False, "dependency", str(exc)))

        clean = [str(k).strip() for k in keys if str(k).strip()]
        if not clean:
            resp = AutomationResponse(False, "No hotkey specified.")
            return self._finalize_action(
                "desktop_hotkey",
                resp,
                before,
                self._verification(False, "input_validation", resp.message),
            )

        try:
            result = desktop.press_hotkey(*clean)
        except Exception as exc:  # pragma: no cover
            resp = AutomationResponse(False, f"Failed to press hotkey: {exc}")
            return self._finalize_action("desktop_hotkey", resp, before, self._verification(False, "exception", str(exc)))

        resp = AutomationResponse.from_result(result)
        try:
            if before_hash is not None:
                time.sleep(0.15)
        except Exception:
            pass
        after = self._snapshot_safe()
        after_hash = self._screen_hash()
        win_after = self._active_window_key(after)
        foc_after = self._focused_key(after)
        changed = bool(win_before != win_after or foc_before != foc_after)
        screen_changed = bool(before_hash is not None and after_hash is not None and before_hash != after_hash)
        ok = bool(resp.success) and (changed or screen_changed)
        reason = (
            "Hotkey verified."
            if ok
            else (
                "No detectable UI change after hotkey."
                if before_hash is not None
                else "Unable to capture screenshots to verify hotkey."
            )
        )
        ver = self._verification(
            ok,
            "snapshot_or_screen",
            reason,
            {"focus_or_window_changed": changed, "screen_changed": screen_changed, "keys": clean},
        )
        return AutomationResponse(
            success=bool(resp.success),
            message=resp.message,
            action="desktop_hotkey",
            before_snapshot=before,
            after_snapshot=after,
            verification=ver,
        )

    def take_screenshot(self, path: str | None = None) -> AutomationResponse:
        before = self._snapshot_safe()
        try:
            desktop = self.require_desktop()
        except DesktopAutomationUnavailable as exc:
            resp = AutomationResponse(False, str(exc))
            return self._finalize_action("take_screenshot", resp, before, self._verification(False, "dependency", str(exc)))

        target_path = Path(path) if path else self._default_screenshot_path()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            result = desktop.screenshot(str(target_path))
        except Exception as exc:  # pragma: no cover - pyautogui runtime errors
            resp = AutomationResponse(False, f"Failed to capture screenshot: {exc}")
            return self._finalize_action("take_screenshot", resp, before, self._verification(False, "exception", str(exc)))

        resp = AutomationResponse.from_result(result)
        ok = bool(resp.success) and target_path.exists()
        ver = self._verification(ok, "file_exists", "Screenshot saved.", {"path": str(target_path)})
        return self._finalize_action("take_screenshot", resp, before, ver)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _default_screenshot_path() -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return Path("screenshots") / f"screenshot-{timestamp}.png"

    def _run_coroutine(self, coro):
        loop = self._async_loop
        if loop is None:
            loop = asyncio.new_event_loop()

            def _runner() -> None:
                asyncio.set_event_loop(loop)
                loop.run_forever()

            import threading as _threading

            thread = _threading.Thread(target=_runner, daemon=True)
            thread.start()
            self._async_loop = loop
            self._async_thread = thread

        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            timeout_s = float(os.getenv("AUTOMATION_CORO_TIMEOUT_S", "90") or "90")
        except Exception:
            timeout_s = 90.0
        return fut.result(timeout=timeout_s)

    def _run_coroutine_with_retries(self, factory, attempts: int = 3, delay: float = 0.6):
        last_exc = None
        for i in range(max(1, attempts)):
            try:
                if self.telemetry:
                    try:
                        self.telemetry.log("automation_attempt", {"attempt": i + 1})
                    except Exception:
                        pass
                return self._run_coroutine(factory())
            except Exception as exc:
                last_exc = exc
                msg = str(exc)
                if "NoneType" in msg and "send" in msg:
                    try:
                        self._devtools_manager.invalidate_cache()
                    except Exception:
                        pass
                if self.telemetry:
                    try:
                        self.telemetry.log("automation_retry", {"attempt": i + 1, "error": str(exc)[:200]})
                    except Exception:
                        pass
                if i >= attempts - 1:
                    raise
                try:
                    time.sleep(delay)
                except Exception:
                    pass
        raise last_exc

    @staticmethod
    def _site_display_name(url: str) -> str:
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            host = ""
        mapping = {
            "www.youtube.com": "YouTube",
            "youtube.com": "YouTube",
            "open.spotify.com": "Spotify",
            "www.google.com": "Google",
            "calendar.google.com": "Google Calendar",
            "mail.google.com": "Gmail",
            "github.com": "GitHub",
            "www.netflix.com": "Netflix",
            "www.linkedin.com": "LinkedIn",
        }
        if host in mapping:
            return mapping[host]
        if host:
            base = host.split(".")
            if len(base) >= 2:
                return base[-2].capitalize()
            return host
        return url

    def _resolve_url(self, target: str) -> str:
        cleaned = (target or "").strip()
        lowered = cleaned.lower()
        if lowered in self._website_shortcuts:
            return self._website_shortcuts[lowered]
        if lowered.startswith("http://") or lowered.startswith("https://"):
            return cleaned
        if "." in lowered and " " not in lowered:
            return f"https://{cleaned}"
        query = quote_plus(cleaned)
        return f"https://www.google.com/search?q={query}"

    def execute_semantic_action(self, action, world_state, goal=None) -> tuple[bool, str, dict]:
        """Execute a semantic action and verify the expected change.
        
        This is the core execution engine for the cognitive control loop.
        It executes an action, refreshes the WorldState, and validates
        that the expected change occurred.
        
        NO ACTION IS SUCCESSFUL UNLESS POSTCONDITION IS VERIFIED.
        
        Args:
            action: The semantic Action to execute
            world_state: Current WorldState before action
            goal: Optional Goal for context (used to fill placeholders)
            
        Returns:
            Tuple of (success, message, verification_dict)
        """
        from .semantic_actions import ActionType
        from awareness.world_state import WorldState
        from .verification import build_verification_dict
        
        before_hash = world_state.compute_hash()
        
        # Execute based on action type
        try:
            if action.type == ActionType.OPEN_BROWSER:
                result = self._execute_open_browser()
            
            elif action.type == ActionType.NAVIGATE_TO_URL:
                url = action.url or action.target
                if url == "goal_target" and goal:
                    url = goal.target_entity or ""
                result = self._execute_navigate(url)
            
            elif action.type == ActionType.CLICK_ELEMENT:
                result = self._execute_click_element(action.target, world_state)
            
            elif action.type == ActionType.CLICK_COORDINATES:
                if action.coordinates:
                    x, y = action.coordinates
                    result = self._execute_click_coordinates(x, y)
                else:
                    result = (False, "No coordinates provided")
            
            elif action.type == ActionType.TYPE_TEXT:
                text = action.text_content
                if text == "goal_search_query" and goal and goal.search_query:
                    text = goal.search_query
                elif text == "goal_recipient" and goal and goal.target_entity:
                    text = goal.target_entity
                elif text == "goal_message_content" and goal and goal.message_content:
                    text = goal.message_content
                result = self._execute_type_text(text or "")
            
            elif action.type == ActionType.SEARCH_WEB:
                query = action.text_content
                if query == "goal_search_query" and goal and goal.search_query:
                    query = goal.search_query
                result = self._execute_search_web(query or "")
            
            elif action.type == ActionType.FOCUS_WINDOW:
                target = action.target
                if target == "goal_target_app" and goal and goal.target_app:
                    target = goal.target_app
                result = self._execute_focus_window(target or "")
            
            elif action.type == ActionType.DISMISS_DIALOG:
                result = self._execute_dismiss_dialog(world_state)
            
            elif action.type == ActionType.ACCEPT_CONSENT:
                result = self._execute_accept_consent(world_state)
            
            elif action.type == ActionType.WAIT_FOR_CHANGE:
                result = self._execute_wait_for_change(action.expected_change, world_state)
            
            elif action.type == ActionType.PRESS_KEY:
                result = self._execute_press_key(action.target or "Enter")
            
            elif action.type == ActionType.READ_SCREEN:
                result = self._execute_read_screen(world_state)
            
            else:
                result = (False, f"Unknown action type: {action.type}")
            
            success, message = result
            
        except Exception as e:
            success = False
            message = f"Action execution failed: {e}"
        
        # Refresh WorldState (wait for state change)
        from .timing import wait_for_state_change
        
        def get_current_hash():
            state = self._refresh_world_state()
            return state.compute_hash() if state else before_hash
        
        wait_for_state_change(get_current_hash, timeout=2.0, poll_interval=0.2)
        after_state = self._refresh_world_state()
        
        # Build action parameters for verification
        action_params = {
            "text_content": action.text_content,
            "url": action.url or action.target,
            "target": action.target,
        }
        
        # Build semantic verification dict
        verification = build_verification_dict(
            action.type,
            world_state,
            after_state,
            action_params
        )
        
        # ENFORCE: Action only succeeds if semantically verified
        if not verification.get("semantic_success"):
            return (
                False,
                f"Verification failed: {action.type} did not produce expected postcondition",
                verification
            )
        
        return success, message, verification

    def _refresh_world_state(self):
        """Refresh and return current WorldState."""
        if self.awareness_state:
            try:
                return self.awareness_state.build_world_state()
            except Exception:
                pass
        return None

    def _execute_open_browser(self) -> tuple[bool, str]:
        """Execute browser opening."""
        try:
            result = self.launch_application("chrome")
            return result.success, result.message
        except Exception as e:
            return False, str(e)

    def _execute_navigate(self, url: str) -> tuple[bool, str]:
        """Execute navigation to URL."""
        try:
            result = self.open_website(url)
            return result.success, result.message
        except Exception as e:
            return False, str(e)

    def _execute_click_element(self, target: str, world_state) -> tuple[bool, str]:
        """Execute click on element by text."""
        if not world_state:
            return False, "No world state available"
        
        elem = world_state.find_element_by_text(target)
        if elem and elem.bounding_box:
            l, t, r, b = elem.bounding_box
            x, y = (l + r) // 2, (t + b) // 2
            result = self.click(x, y)
            return result.success, result.message
        
        word = world_state.find_ocr_word(target)
        if word and word.bbox:
            l, t, r, b = word.bbox
            x, y = (l + r) // 2, (t + b) // 2
            result = self.click(x, y)
            return result.success, result.message
        
        return False, f"Element '{target}' not found"

    def _execute_click_coordinates(self, x: int, y: int) -> tuple[bool, str]:
        """Execute click at coordinates."""
        try:
            result = self.click(x, y)
            return result.success, result.message
        except Exception as e:
            return False, str(e)

    def _execute_type_text(self, text: str) -> tuple[bool, str]:
        """Execute typing text."""
        try:
            result = self.type_text(text)
            return result.success, result.message
        except Exception as e:
            return False, str(e)

    def _execute_search_web(self, query: str) -> tuple[bool, str]:
        """Execute web search."""
        try:
            search_url = f"https://www.google.com/search?q={quote_plus(query)}"
            result = self.open_website(search_url)
            return result.success, result.message
        except Exception as e:
            return False, str(e)

    def _execute_focus_window(self, target: str) -> tuple[bool, str]:
        """Execute window focus."""
        try:
            result = self.focus_window(title=target)
            return result.success, result.message
        except Exception as e:
            return False, str(e)

    def _execute_dismiss_dialog(self, world_state) -> tuple[bool, str]:
        """Execute dialog dismissal."""
        if not world_state:
            return False, "No world state available"
        
        for elem in world_state.ui_elements:
            if any(kw in elem.text.lower() for kw in ["close", "cancel", "dismiss", "no"]):
                return self._execute_click_element(elem.text, world_state)
        
        return False, "No dismiss button found"

    def _execute_accept_consent(self, world_state) -> tuple[bool, str]:
        """Execute consent acceptance."""
        if not world_state:
            return False, "No world state available"
        
        for elem in world_state.ui_elements:
            if any(kw in elem.text.lower() for kw in ["accept", "agree", "allow", "ok"]):
                return self._execute_click_element(elem.text, world_state)
        
        return False, "No accept button found"

    def _execute_wait_for_change(self, expected_change: str, world_state) -> tuple[bool, str]:
        """Execute wait for state change."""
        from .timing import wait_for_state_change
        
        before_hash = world_state.compute_hash() if world_state else ""
        
        def get_current_hash():
            state = self._refresh_world_state()
            return state.compute_hash() if state else before_hash
        
        changed = wait_for_state_change(get_current_hash, timeout=3.0, poll_interval=0.3)
        after_state = self._refresh_world_state()
        after_hash = after_state.compute_hash() if after_state else ""
        
        if after_hash != before_hash:
            return True, f"State changed: {expected_change}"
        return True, f"Waited for: {expected_change}"

    def _execute_press_key(self, key: str) -> tuple[bool, str]:
        """Execute key press."""
        try:
            import pyautogui
            pyautogui.press(key)
            return True, f"Pressed key: {key}"
        except Exception as e:
            return False, f"Key press failed: {e}"
    
    def unlock_chrome_extension(self) -> AutomationResponse:
        """OBSOLETE: Replaced by chrome_pipeline.open_chrome().
        
        Use automation.chrome_pipeline.open_chrome() instead.
        
        Returns:
            AutomationResponse with success status
        """
        from security.credential_vault import get_vault
        from automation.timing import wait_for_state_change
        
        vault = get_vault()
        vault_key = "chrome_extension_lock"
        
        # Check if trained
        if not vault.exists(vault_key):
            return AutomationResponse(
                success=False,
                message="Chrome extension unlock not trained. Run: train chrome_extension_unlock"
            )
        
        # Get password from vault (NEVER LOGGED)
        password = vault.get(vault_key)
        if not password:
            return AutomationResponse(
                success=False,
                message="Chrome extension password not found in vault"
            )
        
        # Focus Chrome
        focus_result = self.focus_window("Chrome")
        if not focus_result.success:
            return AutomationResponse(
                success=False,
                message="Cannot focus Chrome window"
            )
        
        # Get before state
        before_world = self._refresh_world_state()
        if not before_world:
            return AutomationResponse(
                success=False,
                message="Cannot capture before state"
            )
        
        before_hash = before_world.compute_hash()
        
        # Type password (NEVER LOGGED)
        import pyautogui
        import time
        time.sleep(0.3)
        pyautogui.typewrite(password, interval=0.05)
        
        # Wait for screen to change
        def get_hash():
            world = self._refresh_world_state()
            return world.compute_hash() if world else before_hash
        
        changed = wait_for_state_change(get_hash, timeout=5.0, poll_interval=0.3)
        
        if not changed:
            return AutomationResponse(
                success=False,
                message="Chrome did not unlock - screen unchanged after typing password"
            )
        
        # Verify unlock
        after_world = self._refresh_world_state()
        if not after_world:
            return AutomationResponse(
                success=False,
                message="Cannot capture after state"
            )
        
        after_hash = after_world.compute_hash()
        
        if after_hash == before_hash:
            return AutomationResponse(
                success=False,
                message="Verification failed: Screen did not change"
            )
        
        return AutomationResponse(
            success=True,
            message="Chrome extension unlocked successfully"
        )

    def _execute_read_screen(self, world_state) -> tuple[bool, str]:
        """Execute screen reading."""
        if not world_state:
            return False, "No world state available"
        
        content = []
        for elem in world_state.ui_elements[:10]:
            if elem.text:
                content.append(elem.text)
        for word in world_state.ocr_words[:20]:
            if word.text:
                content.append(word.text)
        
        if content:
            return True, " ".join(content)
        return False, "No readable content found"
