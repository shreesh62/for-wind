"""Tests for friday.perception.vision — VLM scene understanding."""

import asyncio
from unittest.mock import MagicMock, AsyncMock
import pytest

from friday.perception.vision import VisionPerception, VisionAnalysis
from friday.perception.screen import Screenshot
from friday.models.router import ModelCapability, ModelInfo, ModelResponse


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def _make_router(has_vision=True, response_text=""):
    """Create a mock router with optional vision capability."""
    router = MagicMock()

    if has_vision:
        vision_model = ModelInfo(
            provider="nvidia",
            model_id="meta/llama-3.2-90b-vision-instruct",
            capabilities=[ModelCapability.VISION],
            priority=10,
        )
        router.get_models_for_capability.return_value = [vision_model]
    else:
        router.get_models_for_capability.return_value = []

    async def fake_complete(prompt, **kwargs):
        return ModelResponse(
            text=response_text,
            model_used="vision-model",
            provider="nvidia",
        )
    router.complete = fake_complete

    return router


def _make_screenshot():
    """Create a screenshot with a real PIL image."""
    from PIL import Image
    img = Image.new("RGB", (200, 100), color=(255, 255, 255))
    return Screenshot(
        image=img,
        width=200,
        height=100,
        pixel_hash="testhash",
        timestamp=0.0,
    )


class TestVisionPerception:
    """Test vision-based scene understanding."""

    def test_unavailable_without_router(self):
        vision = VisionPerception(model_router=None)
        assert vision.available is False

    def test_unavailable_without_vision_model(self):
        router = _make_router(has_vision=False)
        vision = VisionPerception(model_router=router)
        assert vision.available is False

    def test_available_with_vision_model(self):
        router = _make_router(has_vision=True)
        vision = VisionPerception(model_router=router)
        assert vision.available is True

    def test_analyze_parses_structured_response(self):
        router = _make_router(
            has_vision=True,
            response_text="APP: browser | SCREEN: login | DESC: Google sign-in page",
        )
        vision = VisionPerception(model_router=router)

        result = _run(vision.analyze(_make_screenshot()))

        assert result.app_type == "browser"
        assert result.screen_type == "login"
        assert "sign-in" in result.description.lower() or "sign in" in result.description.lower()
        assert result.is_login is True

    def test_analyze_detects_error(self):
        router = _make_router(
            has_vision=True,
            response_text="APP: browser | SCREEN: error | DESC: 404 page not found error",
        )
        vision = VisionPerception(model_router=router)

        result = _run(vision.analyze(_make_screenshot()))
        assert result.is_error is True

    def test_analyze_unavailable_returns_gracefully(self):
        router = _make_router(has_vision=False)
        vision = VisionPerception(model_router=router)

        result = _run(vision.analyze(_make_screenshot()))
        assert result.app_type == "unknown"
        assert "unavailable" in result.description.lower()

    def test_is_login_screen(self):
        router = _make_router(has_vision=True, response_text="YES, this is a login screen")
        vision = VisionPerception(model_router=router)

        result = _run(vision.is_login_screen(_make_screenshot()))
        assert result is True

    def test_is_not_login_screen(self):
        router = _make_router(has_vision=True, response_text="NO, this is a dashboard")
        vision = VisionPerception(model_router=router)

        result = _run(vision.is_login_screen(_make_screenshot()))
        assert result is False

    def test_identify_app(self):
        router = _make_router(has_vision=True, response_text="Visual Studio Code")
        vision = VisionPerception(model_router=router)

        result = _run(vision.identify_app(_make_screenshot()))
        assert "Visual Studio Code" in result

    def test_screenshot_encoding(self):
        """Screenshot converts to data URL."""
        router = _make_router(has_vision=True)
        vision = VisionPerception(model_router=router)

        url = vision._screenshot_to_data_url(_make_screenshot())
        assert url is not None
        assert url.startswith("data:image/jpeg;base64,")

    def test_parse_unstructured_response(self):
        """Parser handles non-structured responses gracefully."""
        router = _make_router(has_vision=True, response_text="This appears to be a settings page.")
        vision = VisionPerception(model_router=router)

        result = _run(vision.analyze(_make_screenshot()))
        assert result.description != ""
        assert result.raw_response == "This appears to be a settings page."
