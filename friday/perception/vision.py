"""Vision perception — supplements semantic perception (ADR-014).

Vision is the SECOND-to-last priority source. It answers high-level
questions that DOM/UIA cannot:
- What application is visible?
- What type of page/screen is this?
- Is this a login screen / settings / error?
- Is there a visual anomaly?

Vision is NOT the primary source of truth. It supplements WorldState
when semantic sources are insufficient or ambiguous.

Uses NVIDIA vision models (llama-3.2-90b-vision-instruct) via the model router.
"""

from __future__ import annotations

import asyncio
import base64
import io
from dataclasses import dataclass
from typing import Optional

from friday.perception.screen import Screenshot


@dataclass
class VisionAnalysis:
    """Result of analyzing a screenshot with a vision model."""

    app_type: str = "unknown"       # browser, editor, terminal, settings, etc.
    screen_type: str = "unknown"    # login, form, error, content, dashboard
    description: str = ""
    is_login: bool = False
    is_error: bool = False
    has_anomaly: bool = False
    confidence: float = 0.0
    raw_response: str = ""


class VisionPerception:
    """Vision-based scene understanding using NVIDIA VLM.

    Supplements semantic perception. Only invoked when:
    - Semantic sources (DOM/UIA) are insufficient
    - High-level scene understanding is needed
    - Verification needs visual confirmation

    Usage:
        vision = VisionPerception(model_router=router)
        if vision.available:
            analysis = await vision.analyze(screenshot)
            print(analysis.screen_type)  # "login"
    """

    def __init__(self, model_router=None) -> None:
        self._router = model_router

    @property
    def available(self) -> bool:
        """Whether vision analysis is available (needs vision-capable model)."""
        if not self._router:
            return False
        try:
            from friday.models.router import ModelCapability
            models = self._router.get_models_for_capability(ModelCapability.VISION)
            return len(models) > 0
        except Exception:
            return False

    async def analyze(
        self,
        screenshot: Screenshot,
        question: Optional[str] = None,
    ) -> VisionAnalysis:
        """Analyze a screenshot with a vision model.

        Args:
            screenshot: The captured screenshot
            question: Optional specific question; defaults to scene classification

        Returns:
            VisionAnalysis with scene understanding
        """
        if not self.available:
            return VisionAnalysis(description="Vision unavailable")

        image_url = self._screenshot_to_data_url(screenshot)
        if not image_url:
            return VisionAnalysis(description="Failed to encode screenshot")

        prompt = question or (
            "Analyze this screenshot. Respond concisely with: "
            "(1) app type (browser/editor/terminal/settings/other), "
            "(2) screen type (login/form/error/content/dashboard/other), "
            "(3) one-line description. "
            "Format: APP: <type> | SCREEN: <type> | DESC: <text>"
        )

        try:
            from friday.models.router import ModelCapability
            response = await self._router.complete(
                prompt,
                capability=ModelCapability.VISION,
                max_tokens=150,
                temperature=0.2,
                image_url=image_url,
            )
            return self._parse_response(response.text)
        except Exception as exc:
            return VisionAnalysis(description=f"Vision error: {exc}")

    async def is_login_screen(self, screenshot: Screenshot) -> bool:
        """Quick check: is this a login screen?"""
        analysis = await self.analyze(
            screenshot,
            question="Is this a login or sign-in screen? Answer only YES or NO.",
        )
        return "yes" in analysis.raw_response.lower()

    async def identify_app(self, screenshot: Screenshot) -> str:
        """Identify which application is visible."""
        analysis = await self.analyze(
            screenshot,
            question="What application is shown? Answer with just the app name.",
        )
        return analysis.raw_response.strip()[:50]

    async def locate_element(self, screenshot: Screenshot, description: str) -> Optional[tuple]:
        """Locate a described UI element and return NORMALIZED (x, y) in 0..1.

        The vision FALLBACK (ADR-014): used only when DOM/UIA cannot resolve a
        target. Returns normalized coordinates so the caller can scale to the
        real page/screen size regardless of any downscaling done for the API.
        Returns None if the element is not found.

        Example: locate_element(shot, "the blue Send button") -> (0.82, 0.94)
        """
        if not self.available:
            return None
        image_url = self._screenshot_to_data_url(screenshot)
        if not image_url:
            return None

        prompt = (
            f"Find this UI element in the screenshot: \"{description}\".\n"
            "Respond ONLY with the element's CENTER as normalized coordinates "
            "in the range 0 to 1, where (0,0) is top-left and (1,1) is "
            "bottom-right. Format EXACTLY: x=<float> y=<float>. "
            "If the element is not visible, respond: NOT_FOUND."
        )
        try:
            from friday.models.router import ModelCapability
            response = await self._router.complete(
                prompt,
                capability=ModelCapability.VISION,
                max_tokens=40,
                temperature=0.0,
                image_url=image_url,
            )
            return self._parse_coords(response.text)
        except Exception:
            return None

    def _parse_coords(self, text: str) -> Optional[tuple]:
        """Parse 'x=<float> y=<float>' into a normalized (x, y) tuple."""
        import re
        if "not_found" in text.lower():
            return None
        xs = re.search(r"x\s*=\s*([0-9]*\.?[0-9]+)", text)
        ys = re.search(r"y\s*=\s*([0-9]*\.?[0-9]+)", text)
        if not xs or not ys:
            return None
        try:
            x, y = float(xs.group(1)), float(ys.group(1))
            # Clamp to [0,1]; reject obviously out-of-range
            if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                return (x, y)
        except ValueError:
            pass
        return None

    def _screenshot_to_data_url(self, screenshot: Screenshot) -> Optional[str]:
        """Convert a screenshot to a base64 data URL for the vision API."""
        try:
            from PIL import Image
            img = screenshot.image
            if not isinstance(img, Image.Image):
                return None

            # Downscale large screenshots to reduce payload (vision models
            # don't need full resolution for scene understanding)
            max_dim = 1280
            if img.width > max_dim or img.height > max_dim:
                ratio = max_dim / max(img.width, img.height)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size)

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=80)
            b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
        except Exception:
            return None

    def _parse_response(self, text: str) -> VisionAnalysis:
        """Parse the vision model's structured response."""
        analysis = VisionAnalysis(raw_response=text, confidence=0.6)
        lower = text.lower()

        # Parse structured format if present
        if "app:" in lower:
            try:
                app_part = text.split("APP:")[1].split("|")[0].strip()
                analysis.app_type = app_part.lower()[:30]
            except (IndexError, AttributeError):
                pass

        if "screen:" in lower:
            try:
                screen_part = text.split("SCREEN:")[1].split("|")[0].strip()
                analysis.screen_type = screen_part.lower()[:30]
            except (IndexError, AttributeError):
                pass

        if "desc:" in lower:
            try:
                analysis.description = text.split("DESC:")[1].strip()[:200]
            except (IndexError, AttributeError):
                analysis.description = text[:200]
        else:
            analysis.description = text[:200]

        # Derive flags
        analysis.is_login = "login" in lower or "sign in" in lower or "sign-in" in lower
        analysis.is_error = "error" in lower or "failed" in lower
        analysis.has_anomaly = "anomaly" in lower or "unusual" in lower

        return analysis
