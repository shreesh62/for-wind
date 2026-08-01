"""Browser Controller — persistent Playwright session on a dedicated loop.

THE FIX for cross-step browser failures: Playwright objects are bound to
the event loop that created them. Spawning a new asyncio loop per step
(via asyncio.run in a thread pool) kills the connection from prior steps.

This controller runs ONE event loop in ONE background thread for the
ENTIRE session. The Playwright browser + page stay alive across all steps.
Every browser operation is submitted to that single loop.

This makes multi-step browser tasks actually work end-to-end.
"""

from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import Future
from typing import Any, Dict, List, Optional


class BrowserController:
    """Persistent browser session running on a dedicated event loop thread.

    Usage:
        controller = BrowserController()
        controller.start()  # spawns the loop thread + connects Playwright

        controller.navigate("https://instagram.com")   # blocking, returns dict
        text = controller.read_text()                   # same live page
        controller.click("Messages")                    # same live page
        links = controller.get_links()

        controller.stop()
    """

    def __init__(
        self,
        chrome_user_data_dir: Optional[str] = None,
        remote_debug_port: int = 9222,
        require_real_chrome: bool = False,
    ) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._started = False
        self._chrome_user_data_dir = chrome_user_data_dir
        self._remote_debug_port = remote_debug_port
        # When True, a CDP failure raises loudly instead of silently launching
        # a fresh Chromium that fakes the user's real (logged-in) session.
        self._require_real_chrome = require_real_chrome
        self._connection_mode: Optional[str] = None  # "cdp" | "fresh" | None
        self._last_dialog: Optional[dict] = None      # last auto-handled dialog
        self._error: Optional[str] = None

    @property
    def available(self) -> bool:
        return self._started and self._page is not None

    @property
    def connection_mode(self) -> Optional[str]:
        """How the browser is connected: 'cdp' (real Chrome) or 'fresh'."""
        return self._connection_mode

    @property
    def is_real_chrome(self) -> bool:
        """True only when connected to the user's real Chrome via CDP."""
        return self._connection_mode == "cdp"

    @property
    def last_error(self) -> Optional[str]:
        return self._error

    def start(self) -> bool:
        """Start the dedicated event loop thread and connect Playwright."""
        if self._started:
            return True

        # HARD SAFETY: never launch/connect a browser in dry-run mode (tests).
        import os
        if os.environ.get("FRIDAY_DRY_RUN", "0") == "1":
            self._error = "dry-run: browser launch suppressed"
            return False

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        # Wait for loop to be ready
        for _ in range(50):
            if self._loop is not None:
                break
            time.sleep(0.05)

        if self._loop is None:
            self._error = "Event loop failed to start"
            return False

        # Connect Playwright on the loop
        try:
            fut = asyncio.run_coroutine_threadsafe(self._connect(), self._loop)
            fut.result(timeout=30)
            self._started = True
            return True
        except Exception as exc:
            self._error = f"Playwright connection failed: {exc}"
            return False

    def _run_loop(self) -> None:
        """Run the dedicated event loop forever in this thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _connect(self) -> None:
        """Connect to Chrome via CDP (existing instance with debug port).

        If require_real_chrome is set, a CDP failure raises loudly instead of
        silently launching fresh Chromium (which would fake the user's
        logged-in session and produce misleading "browser available" state).
        """
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        # Connect to existing Chrome with remote debugging
        endpoint = f"http://127.0.0.1:{self._remote_debug_port}"
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(endpoint)
            # Use existing context (the user's real Chrome with logins)
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = await self._browser.new_context()

            # REUSE an existing page — this is critical. The user is already
            # logged into sites in their existing tabs. Opening a NEW page loses
            # all session cookies/state for that context. Pick the most recent
            # non-blank page, or the first available one.
            pages = self._context.pages
            active_page = None
            for p in reversed(pages):
                url = p.url
                if url and url != "about:blank" and not url.startswith("chrome://"):
                    active_page = p
                    break
            if active_page is None and pages:
                active_page = pages[-1]
            if active_page is None:
                active_page = await self._context.new_page()
            self._page = active_page
            self._connection_mode = "cdp"

            # Stealth: remove automation signals that trigger captchas.
            # When Playwright connects over CDP to a user's real Chrome, the
            # browser itself is NOT launched by Playwright (so no webdriver flag),
            # but Playwright's page hooks can still leave detectable traces.
            # Patch the most common detection vectors.
            try:
                await self._page.evaluate("""() => {
                    // Remove webdriver flag
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    // Remove Playwright-specific markers
                    delete window.__playwright;
                    delete window.__pwInitialized;
                }""")
            except Exception:
                pass  # Some pages restrict eval; stealth is best-effort
        except Exception as exc:
            if self._require_real_chrome:
                # Do NOT fake it. Surface the real reason loudly.
                raise RuntimeError(
                    f"Cannot connect to your real Chrome on CDP port "
                    f"{self._remote_debug_port}: {exc}. "
                    f"Start Chrome with --remote-debugging-port="
                    f"{self._remote_debug_port} (use launch_chrome_debug.py)."
                ) from exc
            # Fallback: launch a fresh browser (NOT the user's session).
            self._browser = await self._playwright.chromium.launch(headless=False)
            self._context = await self._browser.new_context()
            self._page = await self._context.new_page()
            self._connection_mode = "fresh"

        # Track new tabs/popups so target=_blank links and window.open don't
        # leave us reading a stale page (best-in-class tab management).
        self._context.on("page", self._on_new_page)
        self._attach_dialog_handler(self._page)

    def _on_new_page(self, page) -> None:
        """A new tab/popup opened — make it the active page and watch dialogs."""
        try:
            self._page = page
            self._attach_dialog_handler(page)
        except Exception:
            pass

    def _attach_dialog_handler(self, page) -> None:
        """Auto-handle native dialogs (alert/confirm/beforeunload) so they don't
        block automation. Accepts by default; records the message."""
        async def _on_dialog(dialog):
            try:
                self._last_dialog = {"type": dialog.type, "message": dialog.message}
                await dialog.accept()
            except Exception:
                try:
                    await dialog.dismiss()
                except Exception:
                    pass
        try:
            page.on("dialog", _on_dialog)
        except Exception:
            pass

    def _submit(self, coro) -> Any:
        """Submit a coroutine to the dedicated loop and wait for result.

        Every synchronous operation funnels through here, so this is also where an
        operational failure is recorded on ``last_error``. Previously ``_error`` was
        only ever set during ``start()``, so after the browser died mid-session
        ``last_error`` stayed ``None`` and the failure was visible only in the
        returned dict — a caller that ignored return values saw nothing wrong.
        The exception is still raised; this only makes the failure observable.
        """
        if not self._loop:
            self._error = "Browser controller not started"
            raise RuntimeError(self._error)
        fut: Future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            result = fut.result(timeout=30)
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            raise
        self._error = None  # a successful operation clears a stale error
        return result

    # --- Public synchronous operations (run on the persistent loop) ---

    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL. Returns {url, title, ok}.

        Waits for DOM content loaded, then waits for interactive elements to
        actually appear (SPAs like Instagram/React take 2-4s to hydrate after
        domcontentloaded fires). Without this, observe_interactive() returns
        empty on any modern React/Angular/Vue app.
        """
        async def _nav():
            await self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
            # Wait for the page to become interactive — SPAs hydrate AFTER
            # domcontentloaded. Poll for clickable elements to appear.
            for _ in range(8):  # up to 4s total (8 × 500ms)
                await self._page.wait_for_timeout(500)
                try:
                    count = await self._page.evaluate(
                        "document.querySelectorAll('a,button,input,textarea,[role=button]').length"
                    )
                    if count >= 3:
                        break
                except Exception:
                    break
            return {"url": self._page.url, "title": await self._page.title(), "ok": True}
        try:
            return self._submit(_nav())
        except Exception as exc:
            return {"url": "", "title": "", "ok": False, "error": str(exc)}

    def read_text(self, max_chars: int = 4000) -> str:
        """Read visible text from the current page."""
        async def _read():
            try:
                text = await self._page.inner_text("body")
                return text[:max_chars]
            except Exception:
                return ""
        try:
            return self._submit(_read())
        except Exception:
            return ""

    def get_links(self, limit: int = 30) -> List[Dict[str, str]]:
        """Get links from the current page."""
        async def _links():
            return await self._page.eval_on_selector_all(
                "a[href]",
                """(els) => els.slice(0, 50).map(e => ({
                    text: e.innerText.trim().substring(0,100),
                    href: e.href
                })).filter(l => l.text.length > 0)"""
            )
        try:
            return self._submit(_links())[:limit]
        except Exception:
            return []

    def click(self, text: str) -> Dict[str, Any]:
        """Click an element by visible text."""
        async def _click():
            before = self._page.url
            await self._page.get_by_text(text, exact=False).first.click(timeout=10000)
            await self._page.wait_for_timeout(800)
            return {"clicked": text, "url_before": before, "url_after": self._page.url, "ok": True}
        try:
            return self._submit(_click())
        except Exception as exc:
            return {"clicked": text, "ok": False, "error": str(exc)}

    def type_text(self, text: str, selector: Optional[str] = None) -> Dict[str, Any]:
        """Type text into a field (or focused element)."""
        async def _type():
            if selector:
                await self._page.fill(selector, text, timeout=10000)
            else:
                await self._page.keyboard.type(text)
            return {"typed": text[:50], "ok": True}
        try:
            return self._submit(_type())
        except Exception as exc:
            return {"typed": text[:50], "ok": False, "error": str(exc)}

    def observe_interactive(self, limit: int = 60) -> Dict[str, Any]:
        """Read the live page's INTERACTIVE elements for agentic reasoning.

        Returns a structured snapshot the LLM can reason over to pick the next
        action — generic across ANY site (no hardcoding). Each element has an
        index, role, text/label, and editable flag. The index is used to act
        precisely (click_index / fill_index).

        Waits for the page to settle and retries once if a navigation destroys
        the execution context mid-read.
        """
        async def _observe():
            # Let any in-flight navigation settle before reading.
            try:
                await self._page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            await self._page.wait_for_timeout(400)
            url = self._page.url
            title = await self._page.title()
            elements = await self._page.evaluate(
                """() => {
                    const out = [];
                    const vh = window.innerHeight || 800;
                    const sel = 'a,button,input,textarea,select,[role=button],[role=link],[role=textbox],[role=menuitem],[contenteditable=true]';
                    let i = 0;
                    // Walk a root (document or shadowRoot), descending into open
                    // shadow DOM and same-origin iframes. frameOff offsets coords
                    // so nested-frame elements get correct page positions.
                    const walk = (root, frameOff) => {
                        if (!root || i >= 150) return;
                        let nodes = [];
                        try { nodes = Array.from(root.querySelectorAll(sel)); } catch (e) {}
                        for (const el of nodes) {
                            if (i >= 150) break;
                            const r = el.getBoundingClientRect();
                            if (r.width === 0 || r.height === 0) continue;
                            const style = window.getComputedStyle(el);
                            if (style.visibility === 'hidden' || style.display === 'none') continue;
                            const tag = el.tagName.toLowerCase();
                            const role = el.getAttribute('role') || tag;
                            const label = (el.innerText || el.value || el.getAttribute('aria-label') ||
                                           el.getAttribute('placeholder') || el.getAttribute('name') || '').trim().substring(0,80);
                            const editable = (tag === 'input' || tag === 'textarea' ||
                                              el.getAttribute('contenteditable') === 'true' ||
                                              role === 'textbox');
                            if (!label && !editable) continue;
                            let selector = '';
                            if (el.id) selector = '#' + CSS.escape(el.id);
                            else if (el.getAttribute('name')) selector = tag + '[name="' + el.getAttribute('name') + '"]';
                            const ax = r.x + frameOff.x;
                            const ay = r.y + frameOff.y;
                            const inView = (ay >= 0 && ay < vh);
                            out.push({ index: i++, role, tag, text: label, editable, selector,
                                       in_view: inView,
                                       x: Math.round(ax + r.width/2),
                                       y: Math.round(ay + r.height/2 + window.scrollY) });
                        }
                        // Descend into open shadow roots.
                        let hosts = [];
                        try { hosts = Array.from(root.querySelectorAll('*')).filter(e => e.shadowRoot); } catch (e) {}
                        for (const h of hosts) { if (i >= 150) break; walk(h.shadowRoot, frameOff); }
                        // Descend into same-origin iframes.
                        let frames = [];
                        try { frames = Array.from(root.querySelectorAll('iframe')); } catch (e) {}
                        for (const f of frames) {
                            if (i >= 150) break;
                            let doc = null;
                            try { doc = f.contentDocument; } catch (e) { doc = null; }
                            if (!doc) continue;  // cross-origin: skip safely
                            const fr = f.getBoundingClientRect();
                            walk(doc, { x: frameOff.x + fr.x, y: frameOff.y + fr.y });
                        }
                    };
                    walk(document, { x: 0, y: 0 });
                    return out;
                }"""
            )
            return {"url": url, "title": title, "elements": elements[:limit], "ok": True}
        # Retry once if a navigation destroyed the context mid-read.
        for _attempt in range(2):
            try:
                return self._submit(_observe())
            except Exception as exc:
                if "context was destroyed" in str(exc) or "navigation" in str(exc).lower():
                    try:
                        self._submit(self._settle())
                    except Exception:
                        pass
                    continue
                return {"url": "", "title": "", "elements": [], "ok": False, "error": str(exc)}
        return {"url": "", "title": "", "elements": [], "ok": False, "error": "context unstable after navigation"}

    async def _settle(self):
        """Wait for the page to reach a stable state after navigation."""
        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=8000)
            await self._page.wait_for_timeout(600)
        except Exception:
            pass

    def click_index(self, index: int, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Click element at the given observe index, scrolling it into view first.

        Re-locates the element live by its stable signature (tag/text/role) and
        uses a real Playwright locator click (auto scroll-into-view, actionability
        checks) instead of stale frozen coordinates. Falls back to coordinate
        click only if live re-location fails.
        """
        async def _click():
            el = next((e for e in elements if e.get("index") == index), None)
            if not el:
                return {"ok": False, "error": f"no element index {index}"}
            before = self._page.url
            loc = await self._locate(el)
            if loc is not None:
                try:
                    await loc.scroll_into_view_if_needed(timeout=4000)
                    await loc.click(timeout=8000)
                    await self._page.wait_for_timeout(700)
                    after = self._page.url
                    return {"ok": True, "clicked_index": index, "text": el.get("text", ""),
                            "method": "locator", "url_before": before, "url_after": after,
                            "changed": after != before}
                except Exception:
                    pass  # fall through to coordinate click
            # Fallback: scroll so the element's page-y is near viewport center,
            # then click at its viewport position.
            try:
                await self._page.evaluate(f"window.scrollTo(0, Math.max(0, {el['y']} - 300))")
                await self._page.wait_for_timeout(250)
                vy = el['y'] - await self._page.evaluate("window.scrollY")
                await self._page.mouse.click(el["x"], vy)
                await self._page.wait_for_timeout(700)
                after = self._page.url
                return {"ok": True, "clicked_index": index, "text": el.get("text", ""),
                        "method": "coords", "url_before": before, "url_after": after,
                        "changed": after != before}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
        try:
            return self._submit(_click())
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def _locate(self, el: Dict[str, Any]):
        """Build a best-effort live Playwright locator for an observed element."""
        text = (el.get("text") or "").strip()
        tag = el.get("tag", "")
        try:
            if el.get("selector"):
                loc = self._page.locator(el["selector"]).first
                if await loc.count() > 0:
                    return loc
        except Exception:
            pass
        if text:
            try:
                loc = self._page.get_by_text(text, exact=False).first
                if await loc.count() > 0:
                    return loc
            except Exception:
                pass
            # role-based for buttons/links
            try:
                role = "button" if tag == "button" else ("link" if tag == "a" else None)
                if role:
                    loc = self._page.get_by_role(role, name=text).first
                    if await loc.count() > 0:
                        return loc
            except Exception:
                pass
        return None

    def scroll(self, direction: str = "down", amount: int = 600) -> Dict[str, Any]:
        """Scroll the page (down/up/top/bottom) to reveal off-screen content."""
        async def _scroll():
            before = await self._page.evaluate("window.scrollY")
            if direction == "top":
                await self._page.evaluate("window.scrollTo(0, 0)")
            elif direction == "bottom":
                await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            elif direction == "up":
                await self._page.evaluate(f"window.scrollBy(0, -{abs(amount)})")
            else:  # down
                await self._page.evaluate(f"window.scrollBy(0, {abs(amount)})")
            await self._page.wait_for_timeout(500)
            after = await self._page.evaluate("window.scrollY")
            return {"ok": True, "direction": direction,
                    "scrolled": after != before, "y": after}
        try:
            return self._submit(_scroll())
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def upload_file(self, paths, index: int = None,
                    elements: List[Dict[str, Any]] = None,
                    selector: str = None) -> Dict[str, Any]:
        """Upload file(s) to a file input.

        Accepts a single path or a list. Targets the input either by observe
        index (preferred, via live re-location), an explicit selector, or the
        first <input type=file> on the page. Generic across any site.
        """
        import os as _os
        files = [paths] if isinstance(paths, str) else list(paths)
        for p in files:
            if not _os.path.isfile(p):
                return {"ok": False, "error": f"file not found: {p}"}

        async def _upload():
            loc = None
            if index is not None and elements:
                el = next((e for e in elements if e.get("index") == index), None)
                if el:
                    loc = await self._locate(el)
            if loc is None and selector:
                loc = self._page.locator(selector).first
            if loc is None:
                loc = self._page.locator("input[type=file]").first
            try:
                if await loc.count() == 0:
                    return {"ok": False, "error": "no file input found"}
            except Exception:
                pass
            await loc.set_input_files(files, timeout=10000)
            await self._page.wait_for_timeout(300)
            return {"ok": True, "uploaded": [_os.path.basename(f) for f in files]}
        try:
            return self._submit(_upload())
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def download_file(self, trigger_index: int, elements: List[Dict[str, Any]],
                      dest_dir: str = None) -> Dict[str, Any]:
        """Click the element at trigger_index and capture the resulting download.

        Saves to dest_dir (default ~/.friday/downloads) and returns the saved
        path. Generic — the trigger is any observed element (link/button).
        """
        import os as _os
        dest_dir = dest_dir or _os.path.join(
            _os.path.expanduser("~"), ".friday", "downloads")
        _os.makedirs(dest_dir, exist_ok=True)
        el = next((e for e in (elements or []) if e.get("index") == trigger_index), None)
        if not el:
            return {"ok": False, "error": f"no element index {trigger_index}"}

        async def _download():
            loc = await self._locate(el)
            try:
                async with self._page.expect_download(timeout=30000) as dl_info:
                    if loc is not None:
                        await loc.click(timeout=8000)
                    else:
                        vy = el['y'] - await self._page.evaluate("window.scrollY")
                        await self._page.mouse.click(el["x"], vy)
                download = await dl_info.value
                suggested = download.suggested_filename or "download"
                path = _os.path.join(dest_dir, suggested)
                await download.save_as(path)
                return {"ok": True, "path": path, "filename": suggested}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
        try:
            return self._submit(_download())
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def fill_index(self, index: int, value: str, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Focus the element at the given index, clear it, type, and VERIFY.

        Uses click-to-focus then keyboard typing (works with most widgets), and
        confirms the value actually landed in an input/textarea. Returns the
        observed value so the agent knows whether typing worked.
        """
        async def _fill():
            el = next((e for e in elements if e.get("index") == index), None)
            if not el:
                return {"ok": False, "error": f"no element index {index}"}
            # Prefer a live locator: scroll into view + fill (handles off-screen,
            # actionability, and most input widgets reliably).
            loc = await self._locate(el)
            if loc is not None:
                try:
                    await loc.scroll_into_view_if_needed(timeout=4000)
                    await loc.fill(value, timeout=6000)
                    await self._page.wait_for_timeout(200)
                    return {"ok": True, "filled_index": index, "value": value[:50],
                            "method": "locator", "verified": True}
                except Exception:
                    pass  # fall back to coordinate-based typing
            # Fallback: scroll element into view, click at corrected viewport y, type.
            await self._page.evaluate(f"window.scrollTo(0, Math.max(0, {el['y']} - 300))")
            await self._page.wait_for_timeout(200)
            vy = el['y'] - await self._page.evaluate("window.scrollY")
            await self._page.mouse.click(el["x"], vy)
            await self._page.wait_for_timeout(200)
            try:
                await self._page.keyboard.press("Control+A")
                await self._page.keyboard.press("Delete")
            except Exception:
                pass
            await self._page.keyboard.type(value, delay=25)
            await self._page.wait_for_timeout(250)
            # Verify what the focused element actually contains.
            try:
                landed = await self._page.evaluate(
                    "() => { const a=document.activeElement; "
                    "return a ? (a.value || a.innerText || '') : ''; }"
                )
            except Exception:
                landed = ""
            ok = value.strip()[:20].lower() in (landed or "").lower()
            return {"ok": True, "filled_index": index, "value": value[:50],
                    "landed": (landed or "")[:80], "verified": ok}
        try:
            return self._submit(_fill())
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def press(self, key: str) -> Dict[str, Any]:
        """Press a keyboard key (e.g. 'Enter', 'Escape', 'Tab')."""
        async def _press():
            await self._page.keyboard.press(key)
            # Allow a possible navigation/results load to settle.
            try:
                await self._page.wait_for_load_state("domcontentloaded", timeout=6000)
            except Exception:
                pass
            await self._page.wait_for_timeout(600)
            return {"ok": True, "key": key, "url": self._page.url}
        try:
            return self._submit(_press())
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def screenshot_image(self):
        """Capture the current page as a PIL Image (for vision fallback).

        Returns a Screenshot-like object with an `.image` PIL attribute, or
        None on failure. Used when DOM observation can't resolve a target and
        vision must locate it (ADR-014 fallback).
        """
        async def _shot():
            return await self._page.screenshot(type="png")
        try:
            png_bytes = self._submit(_shot())
            from PIL import Image
            import io as _io
            img = Image.open(_io.BytesIO(png_bytes)).convert("RGB")
            from friday.perception.screen import Screenshot
            import hashlib, time as _t
            return Screenshot(
                image=img, width=img.width, height=img.height,
                pixel_hash=hashlib.sha256(png_bytes).hexdigest()[:16],
                timestamp=_t.time(),
            )
        except Exception:
            return None

    def viewport_size(self) -> Dict[str, int]:
        """Return the current viewport pixel size {width, height}.

        Over CDP `page.viewport_size` is often None (Playwright didn't create
        the context), which previously made vision-click coordinate scaling use
        a wrong 1280x800 default. Fall back to the live window dimensions and
        device pixel ratio so vision clicks land correctly on HiDPI/real Chrome.
        """
        async def _vs():
            vs = self._page.viewport_size
            if vs and vs.get("width") and vs.get("height"):
                return {"width": vs["width"], "height": vs["height"],
                        "device_pixel_ratio": 1.0}
            dims = await self._page.evaluate(
                "() => ({ w: window.innerWidth, h: window.innerHeight,"
                " dpr: window.devicePixelRatio || 1 })"
            )
            return {"width": int(dims.get("w") or 1280),
                    "height": int(dims.get("h") or 800),
                    "device_pixel_ratio": float(dims.get("dpr") or 1.0)}
        try:
            return self._submit(_vs())
        except Exception:
            return {"width": 1280, "height": 800, "device_pixel_ratio": 1.0}

    def click_xy(self, x: int, y: int) -> Dict[str, Any]:
        """Click at absolute viewport pixel coordinates (vision fallback)."""
        async def _c():
            before = self._page.url
            await self._page.mouse.click(x, y)
            await self._page.wait_for_timeout(800)
            return {"ok": True, "x": x, "y": y,
                    "url_before": before, "url_after": self._page.url}
        try:
            return self._submit(_c())
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def search_web(self, query: str) -> Dict[str, Any]:
        """Perform a web search and return result text + links.

        Uses a configurable search engine. Defaults to DuckDuckGo's HTML
        endpoint, which does NOT throw the "unusual traffic" captcha wall that
        Google shows to automated sessions (the cause of the captcha tab-loop).
        Override with FRIDAY_SEARCH_ENGINE=google|duckduckgo|bing.
        """
        import os as _os
        engine = _os.environ.get("FRIDAY_SEARCH_ENGINE", "duckduckgo").lower()
        q = query.replace(" ", "+")
        if engine == "google":
            search_url = f"https://www.google.com/search?q={q}"
        elif engine == "bing":
            search_url = f"https://www.bing.com/search?q={q}"
        else:  # duckduckgo (default — captcha-resistant HTML endpoint)
            search_url = f"https://duckduckgo.com/html/?q={q}"

        async def _search():
            await self._page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await self._page.wait_for_timeout(1500)
            text = ""
            try:
                text = await self._page.inner_text("body")
            except Exception:
                pass
            links = []
            try:
                links = await self._page.eval_on_selector_all(
                    "a[href]",
                    """(els) => els.slice(0,30).map(e => ({
                        text: e.innerText.trim().substring(0,120), href: e.href
                    })).filter(l => l.text.length > 5 && l.href.startsWith('http'))"""
                )
            except Exception:
                pass
            return {"query": query, "text": text[:5000], "links": links[:15], "ok": True, "engine": engine}
        try:
            return self._submit(_search())
        except Exception as exc:
            return {"query": query, "text": "", "links": [], "ok": False, "error": str(exc)}

    def current_url(self) -> str:
        async def _url():
            return self._page.url
        try:
            return self._submit(_url())
        except Exception:
            return ""

    def list_tabs(self) -> List[Dict[str, Any]]:
        """List open tabs as [{index, url, title, active}].

        Lets the agent reason over multiple tabs (e.g. a target=_blank link
        opened a new tab) instead of being stuck on one page.
        """
        async def _list():
            out = []
            pages = list(self._context.pages) if self._context else []
            for i, pg in enumerate(pages):
                try:
                    title = await pg.title()
                except Exception:
                    title = ""
                out.append({"index": i, "url": pg.url, "title": title,
                            "active": pg is self._page})
            return out
        try:
            return self._submit(_list())
        except Exception:
            return []

    def switch_tab(self, index: int) -> Dict[str, Any]:
        """Make tab `index` the active page and bring it to the front."""
        async def _switch():
            pages = list(self._context.pages) if self._context else []
            if index < 0 or index >= len(pages):
                return {"ok": False, "error": f"tab {index} out of range (have {len(pages)})"}
            pg = pages[index]
            self._page = pg
            self._attach_dialog_handler(pg)
            try:
                await pg.bring_to_front()
            except Exception:
                pass
            return {"ok": True, "index": index, "url": pg.url}
        try:
            return self._submit(_switch())
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def last_dialog(self) -> Optional[dict]:
        """Return the most recent auto-handled native dialog, if any."""
        return self._last_dialog

    def stop(self) -> None:
        """Stop the controller and clean up."""
        if self._loop and self._started:
            async def _cleanup():
                try:
                    if self._playwright:
                        await self._playwright.stop()
                except Exception:
                    pass
            try:
                self._submit(_cleanup())
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._started = False
        self._page = None
