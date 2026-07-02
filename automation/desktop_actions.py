"""Desktop automation utilities built on top of PyAutoGUI and Pywinauto."""

from __future__ import annotations

import os
import ctypes
import re
from dataclasses import dataclass
from typing import Any, Optional, Tuple
from pathlib import Path
from datetime import datetime

try:  # Optional dependencies runtime-checked during use
    import pyautogui  # type: ignore
except ImportError:  # pragma: no cover
    pyautogui = None  # type: ignore

try:  # Optional dependency
    from pywinauto import Desktop  # type: ignore
except ImportError:  # pragma: no cover
    Desktop = None  # type: ignore

try:
    import mss  # type: ignore
except ImportError:  # pragma: no cover
    mss = None  # type: ignore

try:
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover
    np = None  # type: ignore

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore

try:
    import pytesseract  # type: ignore
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore

try:
    from PIL import Image, ImageGrab  # type: ignore
except ImportError:  # pragma: no cover
    Image = None  # type: ignore
    ImageGrab = None  # type: ignore

try:
    import easyocr  # type: ignore
except ImportError:  # pragma: no cover
    easyocr = None  # type: ignore

from .quick_actions import AutomationResult

Point = Tuple[int, int]


class DesktopAutomationUnavailable(RuntimeError):
    """Raised when desktop automation features cannot be used."""


@dataclass(slots=True)
class FocusRequest:
    """Represents a request to focus a particular window."""

    title: Optional[str] = None
    exe: Optional[str] = None

    def is_valid(self) -> bool:
        return bool(self.title or self.exe)


class DesktopAutomation:
    """High-level wrapper around PyAutoGUI and Pywinauto for desktop control."""

    def __init__(self, *, fail_safe: bool = True, pause: float = 0.2) -> None:
        if pyautogui is None:
            raise DesktopAutomationUnavailable(
                "pyautogui is not installed. Install it to enable desktop automation."
            )

        self._ensure_dpi_awareness()
        self._pyautogui = pyautogui
        self._pyautogui.FAILSAFE = fail_safe
        self._pyautogui.PAUSE = pause

    @staticmethod
    def _ensure_dpi_awareness() -> None:
        try:
            if os.name != "nt":
                return
        except Exception:
            return
        try:
            import ctypes

            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
                return
            except Exception:
                pass
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        except Exception:
            pass

    def _grab_image(self, *, bbox: tuple[int, int, int, int] | None = None):
        if ImageGrab is None:
            return None
        try:
            if bbox is None:
                try:
                    return ImageGrab.grab(all_screens=True)
                except TypeError:
                    return ImageGrab.grab()
            try:
                return ImageGrab.grab(bbox=bbox, all_screens=True)
            except TypeError:
                return ImageGrab.grab(bbox=bbox)
        except Exception:
            return None

    def _grab_virtual_screen_with_origin(self):
        """Return (img, origin_left, origin_top) for the full virtual desktop."""
        if mss is not None and Image is not None:
            try:
                with mss.mss() as sct:
                    mon = sct.monitors[0]
                    grab = sct.grab(mon)
                    img = Image.frombytes("RGB", grab.size, grab.rgb)
                    return img, int(mon.get("left", 0)), int(mon.get("top", 0))
            except Exception:
                pass

        img = self._grab_image()
        if img is not None:
            return img, 0, 0

        return None, 0, 0

    # ------------------------------------------------------------------
    # Mouse helpers
    # ------------------------------------------------------------------
    def move_to(self, point: Point, *, duration: float = 0.0) -> AutomationResult:
        self._pyautogui.moveTo(point[0], point[1], duration=duration)
        return AutomationResult(True, f"Moved mouse to {point}.")

    def click(self, point: Point, *, button: str = "left", duration: float = 0.0) -> AutomationResult:
        self._pyautogui.moveTo(point[0], point[1], duration=duration)
        self._pyautogui.click(button=button)
        return AutomationResult(True, f"Clicked {button} at {point}.")

    def double_click(self, point: Point, *, button: str = "left") -> AutomationResult:
        self._pyautogui.moveTo(point[0], point[1])
        self._pyautogui.doubleClick(button=button)
        return AutomationResult(True, f"Double clicked {button} at {point}.")

    def scroll(self, amount: int) -> AutomationResult:
        self._pyautogui.scroll(amount)
        direction = "up" if amount > 0 else "down"
        return AutomationResult(True, f"Scrolled {direction} by {abs(amount)} units.")

    # ------------------------------------------------------------------
    # Keyboard helpers
    # ------------------------------------------------------------------
    def type_text(self, text: str, *, interval: float = 0.0) -> AutomationResult:
        self._pyautogui.write(text, interval=interval)
        return AutomationResult(True, "Typed text successfully.")

    def press_hotkey(self, *keys: str) -> AutomationResult:
        if len(keys) == 1:
            self._pyautogui.press(keys[0])
        else:
            self._pyautogui.hotkey(*keys)
        return AutomationResult(True, f"Pressed hotkey: {' + '.join(keys)}.")

    # ------------------------------------------------------------------
    # Window helpers
    # ------------------------------------------------------------------
    def focus_window(self, request: FocusRequest, *, timeout: float = 3.0) -> AutomationResult:
        if not request.is_valid():
            return AutomationResult(False, "Provide a window title or executable to focus.")

        title_re = None
        if request.title:
            try:
                title_re = re.compile(r".*" + re.escape(request.title) + r".*", re.IGNORECASE)
            except Exception:
                title_re = None

        prefer_chrome_class = False
        try:
            prefer_chrome_class = bool(request.title and "chrome" in request.title.lower())
        except Exception:
            prefer_chrome_class = False

        def _force_foreground(hwnd: int) -> None:
            if os.name != "nt":
                return
            try:
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                try:
                    self._pyautogui.press("alt")
                except Exception:
                    pass
                try:
                    user32.ShowWindow(hwnd, 9)
                except Exception:
                    pass
                try:
                    fg = user32.GetForegroundWindow()
                    fg_tid = user32.GetWindowThreadProcessId(fg, 0)
                    tgt_tid = user32.GetWindowThreadProcessId(hwnd, 0)
                    try:
                        user32.AttachThreadInput(tgt_tid, fg_tid, True)
                    except Exception:
                        pass
                    try:
                        user32.BringWindowToTop(hwnd)
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
                        user32.SetFocus(hwnd)
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
                    try:
                        user32.SetForegroundWindow(hwnd)
                    except Exception:
                        pass
            except Exception:
                return

        if Desktop is None:
            if os.name != "nt":
                return AutomationResult(False, "Unable to focus window: unsupported OS")
            try:
                user32 = ctypes.windll.user32
            except Exception as exc:
                return AutomationResult(False, f"Unable to focus window: {exc}")

            matches: list[int] = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def enum_proc(hwnd, lparam):
                try:
                    if not user32.IsWindowVisible(hwnd):
                        return True
                    length = user32.GetWindowTextLengthW(hwnd)
                    if not length:
                        return True
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    txt = buf.value or ""
                    if title_re is not None:
                        try:
                            if title_re.search(txt):
                                matches.append(int(hwnd))
                        except Exception:
                            pass
                    if prefer_chrome_class and not matches:
                        try:
                            cbuf = ctypes.create_unicode_buffer(256)
                            if user32.GetClassNameW(hwnd, cbuf, 256):
                                cls = (cbuf.value or "").strip()
                                if cls == "Chrome_WidgetWin_1":
                                    matches.append(int(hwnd))
                        except Exception:
                            pass
                    return True
                except Exception:
                    return True

            try:
                user32.EnumWindows(enum_proc, 0)
            except Exception as exc:
                return AutomationResult(False, f"Unable to focus window: {exc}")

            if not matches:
                return AutomationResult(False, "Unable to focus window: no matching window")

            try:
                _force_foreground(matches[0])
                return AutomationResult(True, "Window focus changed successfully.")
            except Exception as exc:
                return AutomationResult(False, f"Unable to focus window: {exc}")

        match_kwargs = {}
        if title_re is not None:
            match_kwargs["title_re"] = title_re
        if prefer_chrome_class:
            try:
                match_kwargs["class_name"] = "Chrome_WidgetWin_1"
            except Exception:
                pass
        if request.exe:
            try:
                match_kwargs["process"] = int(str(request.exe).strip())
            except Exception:
                pass

        last_exc: Exception | None = None
        for backend in ("win32", "uia"):
            try:
                desktop = Desktop(backend=backend)
                window = desktop.window(**match_kwargs)
                window.wait("visible", timeout=timeout)
                try:
                    window.restore()
                except Exception:
                    pass
                try:
                    window.set_focus()
                except Exception:
                    pass
                hwnd = None
                try:
                    hwnd = int(getattr(window, "handle", 0) or 0)
                except Exception:
                    hwnd = None
                if hwnd:
                    _force_foreground(hwnd)
                ok = True
                try:
                    ok = bool(window.has_focus())
                except Exception:
                    ok = True
                if ok:
                    return AutomationResult(True, "Window focus changed successfully.")
            except Exception as exc:  # pragma: no cover - robustness in production
                last_exc = exc
                continue

        return AutomationResult(False, f"Unable to focus window: {last_exc}")

    def screenshot(self, path: str) -> AutomationResult:
        try:
            img = self._grab_image()
            if img is not None:
                img.save(path)
                return AutomationResult(True, f"Screenshot saved to {path}.")
        except Exception:
            pass
        self._pyautogui.screenshot(path)
        return AutomationResult(True, f"Screenshot saved to {path}.")

    def screenshot_region(self, path: str, x: int, y: int, w: int, h: int) -> AutomationResult:
        try:
            img = self._grab_image(bbox=(x, y, x + w, y + h))
            if img is not None:
                img.save(path)
                return AutomationResult(True, f"Region screenshot saved to {path}.")
        except Exception:
            pass
        self._pyautogui.screenshot(path, region=(x, y, w, h))
        return AutomationResult(True, f"Region screenshot saved to {path}.")

    def _ocr_image(self, img) -> AutomationResult:
        if pytesseract is not None:
            try:
                cmd = None
                try:
                    cmd = (os.getenv("TESSERACT_CMD") or "").strip() or None
                except Exception:
                    cmd = None
                if cmd:
                    try:
                        p = Path(cmd)
                        if p.exists():
                            pytesseract.pytesseract.tesseract_cmd = str(p)
                    except Exception:
                        pass
                else:
                    candidates = [
                        r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
                        r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe",
                    ]
                    for c in candidates:
                        try:
                            p = Path(c)
                            if p.exists():
                                pytesseract.pytesseract.tesseract_cmd = str(p)
                                break
                        except Exception:
                            continue
            except Exception:
                pass
            try:
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                texts = data.get("text") or []
                lefts = data.get("left") or []
                tops = data.get("top") or []
                widths = data.get("width") or []
                heights = data.get("height") or []
                confs = data.get("conf") or []

                word_boxes: list[dict[str, Any]] = []
                conf_vals: list[float] = []
                parts: list[str] = []
                n = min(len(texts), len(lefts), len(tops), len(widths), len(heights), len(confs))
                for i in range(n):
                    raw = texts[i]
                    txt = raw.strip() if isinstance(raw, str) else ""
                    if not txt:
                        continue
                    try:
                        c_raw = confs[i]
                        c = float(c_raw)
                    except Exception:
                        c = -1.0
                    c_norm = None
                    if c >= 0:
                        c_norm = max(0.0, min(1.0, c / 100.0))
                        conf_vals.append(c_norm)
                    try:
                        l = int(lefts[i])
                        t = int(tops[i])
                        w = int(widths[i])
                        h = int(heights[i])
                        bbox = (l, t, l + w, t + h)
                    except Exception:
                        bbox = None
                    word_boxes.append({"text": txt, "bounding_rect": bbox, "confidence": c_norm})
                    parts.append(txt)

                text = " ".join(parts).strip()
                confidence = (sum(conf_vals) / len(conf_vals)) if conf_vals else None
                return AutomationResult(
                    True,
                    text,
                    data={"text": text, "word_boxes": word_boxes, "confidence": confidence},
                )
            except Exception as exc:
                low = str(exc).lower()
                if "tesseract is not installed" in low or "not in your path" in low or "tesseractnotfounderror" in low:
                    return AutomationResult(
                        False,
                        "OCR failed: Tesseract OCR is not installed (or not in PATH). Install Tesseract and/or set TESSERACT_CMD to the full path of tesseract.exe.",
                        data={"error": str(exc)},
                    )
                pyt_err = exc
        else:
            pyt_err = None

        if easyocr is not None and np is not None:
            try:
                reader = easyocr.Reader(["en"], gpu=False, verbose=False)
                np_img = np.array(img)
                items = reader.readtext(np_img, detail=1)
                word_boxes = []
                conf_vals = []
                parts = []
                for item in items:
                    if not isinstance(item, (list, tuple)) or len(item) < 3:
                        continue
                    bbox_pts, txt, conf = item[0], item[1], item[2]
                    if not isinstance(txt, str) or not txt.strip():
                        continue
                    parts.append(txt.strip())
                    try:
                        c = float(conf)
                        c_norm = max(0.0, min(1.0, c))
                        conf_vals.append(c_norm)
                    except Exception:
                        c_norm = None

                    bbox = None
                    try:
                        xs = [p[0] for p in bbox_pts]
                        ys = [p[1] for p in bbox_pts]
                        bbox = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
                    except Exception:
                        bbox = None
                    word_boxes.append({"text": txt.strip(), "bounding_rect": bbox, "confidence": c_norm})

                text = " ".join(parts).strip()
                confidence = (sum(conf_vals) / len(conf_vals)) if conf_vals else None
                return AutomationResult(
                    True,
                    text,
                    data={"text": text, "word_boxes": word_boxes, "confidence": confidence},
                )
            except Exception as exc:
                return AutomationResult(False, f"OCR failed (easyocr): {exc}")

        reason = f"pytesseract failed: {pyt_err}" if pyt_err else "pytesseract/easyocr not available"
        return AutomationResult(False, f"OCR failed: {reason}")

    def ocr_region(self, x: int, y: int, w: int, h: int) -> AutomationResult:
        img = None
        try:
            img = self._grab_image(bbox=(x, y, x + w, y + h))
        except Exception:
            img = None
        if img is None:
            try:
                img = self._pyautogui.screenshot(region=(x, y, w, h))
            except Exception as exc:
                return AutomationResult(
                    False,
                    "OCR screenshot capture failed. Install Pillow (pip install pillow) to enable screenshots.",
                    data={"error": str(exc)},
                )
        res = self._ocr_image(img)
        try:
            data = res.data if isinstance(res.data, dict) else None
            boxes = data.get("word_boxes") if isinstance(data, dict) else None
            if isinstance(boxes, list) and boxes:
                adj = []
                for item in boxes:
                    if not isinstance(item, dict):
                        continue
                    rect = item.get("bounding_rect")
                    if (
                        isinstance(rect, (list, tuple))
                        and len(rect) == 4
                        and all(isinstance(v, (int, float)) for v in rect)
                    ):
                        l, t, r, b = rect
                        item = dict(item)
                        item["bounding_rect"] = (int(l + x), int(t + y), int(r + x), int(b + y))
                    adj.append(item)
                data["word_boxes"] = adj
        except Exception:
            pass
        return res

    def ocr_screen(self) -> AutomationResult:
        img, ox, oy = None, 0, 0
        try:
            img, ox, oy = self._grab_virtual_screen_with_origin()
        except Exception:
            img, ox, oy = None, 0, 0

        if img is None:
            try:
                img = self._pyautogui.screenshot()
            except Exception as exc:
                return AutomationResult(
                    False,
                    "OCR screenshot capture failed. Install Pillow (pip install pillow) to enable screenshots.",
                    data={"error": str(exc)},
                )

        res = self._ocr_image(img)
        if ox or oy:
            try:
                data = res.data if isinstance(res.data, dict) else None
                boxes = data.get("word_boxes") if isinstance(data, dict) else None
                if isinstance(boxes, list) and boxes:
                    adj = []
                    for item in boxes:
                        if not isinstance(item, dict):
                            continue
                        rect = item.get("bounding_rect")
                        if (
                            isinstance(rect, (list, tuple))
                            and len(rect) == 4
                            and all(isinstance(v, (int, float)) for v in rect)
                        ):
                            l, t, r, b = rect
                            item = dict(item)
                            item["bounding_rect"] = (int(l + ox), int(t + oy), int(r + ox), int(b + oy))
                        adj.append(item)
                    data["word_boxes"] = adj
            except Exception:
                pass
        return res

    def find_image(self, template_path: str, *, confidence: float = 0.85) -> AutomationResult:
        if cv2 is None or np is None:
            return AutomationResult(False, "opencv-python and numpy are required for template matching.")
        try:
            screen = self._pyautogui.screenshot()
            screen = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)
            template = cv2.imread(template_path, cv2.IMREAD_COLOR)
            if template is None:
                return AutomationResult(False, "Template image not found.")
            res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            if max_val < confidence:
                return AutomationResult(False, f"No match above confidence {confidence:.2f}.")
            th, tw = template.shape[:2]
            center = (max_loc[0] + tw // 2, max_loc[1] + th // 2)
            return AutomationResult(True, f"Found at {center} (conf {max_val:.2f}).", data={"point": center, "confidence": float(max_val)})
        except Exception as exc:
            return AutomationResult(False, f"Template match failed: {exc}")
