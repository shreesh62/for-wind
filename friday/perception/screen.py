"""Screen capture module using MSS for fast, cross-process screenshots.

MSS is preferred over PIL.ImageGrab because:
- Faster (direct memory access)
- Supports multi-monitor
- Works without focus (captures behind windows)
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Optional, Tuple

try:
    import mss
    import mss.tools
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


@dataclass
class Screenshot:
    """A captured screenshot with metadata."""

    image: object  # PIL.Image or mss raw
    width: int
    height: int
    pixel_hash: str
    timestamp: float
    monitor_index: int = 0
    capture_ms: float = 0.0

    def save(self, path: str) -> None:
        """Save screenshot to disk."""
        if PIL_AVAILABLE and isinstance(self.image, Image.Image):
            self.image.save(path)
        elif hasattr(self.image, 'save'):
            self.image.save(path)


class ScreenCapture:
    """Fast screen capture using MSS with PIL fallback.

    Usage:
        capture = ScreenCapture()
        screenshot = capture.grab()
        print(f"Hash: {screenshot.pixel_hash}")
        print(f"Size: {screenshot.width}x{screenshot.height}")
    """

    def __init__(self) -> None:
        self._sct: Optional[object] = None
        if MSS_AVAILABLE:
            self._sct = mss.mss()

    @property
    def available(self) -> bool:
        """Whether screen capture is available."""
        return MSS_AVAILABLE or PIL_AVAILABLE

    def grab(
        self,
        monitor: int = 0,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> Optional[Screenshot]:
        """Capture the screen or a region.

        Args:
            monitor: Monitor index (0 = all monitors combined, 1+ = specific)
            region: Optional (left, top, width, height) region to capture

        Returns:
            Screenshot object or None if capture fails
        """
        start = time.perf_counter()

        if MSS_AVAILABLE and self._sct:
            return self._grab_mss(monitor, region, start)
        elif PIL_AVAILABLE:
            return self._grab_pil(region, start)

        return None

    def grab_hash_only(
        self,
        monitor: int = 0,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> str:
        """Capture screen and return only the hash (for change detection).

        More memory-efficient when the image isn't needed.
        """
        screenshot = self.grab(monitor=monitor, region=region)
        if screenshot:
            return screenshot.pixel_hash
        return ""

    def _grab_mss(
        self,
        monitor: int,
        region: Optional[Tuple[int, int, int, int]],
        start: float,
    ) -> Optional[Screenshot]:
        """Capture using MSS."""
        try:
            if region:
                left, top, width, height = region
                grab_area = {"left": left, "top": top, "width": width, "height": height}
            else:
                monitors = self._sct.monitors
                if monitor < len(monitors):
                    grab_area = monitors[monitor]
                else:
                    grab_area = monitors[0]

            raw = self._sct.grab(grab_area)
            capture_ms = (time.perf_counter() - start) * 1000

            # Compute hash from raw pixels
            pixel_hash = hashlib.sha256(raw.rgb).hexdigest()[:16]

            # Convert to PIL Image if available
            image = None
            width = raw.width
            height = raw.height
            if PIL_AVAILABLE:
                image = Image.frombytes("RGB", (width, height), raw.rgb)
            else:
                image = raw

            return Screenshot(
                image=image,
                width=width,
                height=height,
                pixel_hash=pixel_hash,
                timestamp=time.time(),
                monitor_index=monitor,
                capture_ms=capture_ms,
            )
        except Exception:
            return None

    def _grab_pil(
        self,
        region: Optional[Tuple[int, int, int, int]],
        start: float,
    ) -> Optional[Screenshot]:
        """Capture using PIL.ImageGrab (fallback)."""
        try:
            from PIL import ImageGrab

            if region:
                left, top, width, height = region
                bbox = (left, top, left + width, top + height)
                image = ImageGrab.grab(bbox=bbox)
            else:
                image = ImageGrab.grab()

            capture_ms = (time.perf_counter() - start) * 1000

            # Compute hash
            pixel_hash = hashlib.sha256(image.tobytes()).hexdigest()[:16]

            return Screenshot(
                image=image,
                width=image.width,
                height=image.height,
                pixel_hash=pixel_hash,
                timestamp=time.time(),
                monitor_index=0,
                capture_ms=capture_ms,
            )
        except Exception:
            return None

    def close(self) -> None:
        """Release MSS resources."""
        if self._sct and hasattr(self._sct, 'close'):
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None
