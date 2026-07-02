"""OCR module wrapping Tesseract with structured output.

Converts raw Tesseract output into OCRRegion objects with
bounding boxes and confidence scores for the WorldState.
"""

from __future__ import annotations

import time
from typing import List, Optional, Tuple

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from friday.perception.types import BoundingBox, OCRRegion


class OCREngine:
    """Tesseract OCR wrapper producing structured OCRRegion objects.

    Usage:
        engine = OCREngine()
        if engine.available:
            regions = engine.extract_regions(image)
            for r in regions:
                print(f"{r.text} @ {r.bbox} (conf={r.confidence:.2f})")
    """

    def __init__(self, min_confidence: float = 0.4, language: str = "eng") -> None:
        """Initialize OCR engine.

        Args:
            min_confidence: Minimum confidence threshold (0-1) for keeping words
            language: Tesseract language code
        """
        self._min_confidence = min_confidence
        self._language = language

    @property
    def available(self) -> bool:
        """Whether OCR is available (Tesseract installed + pytesseract package)."""
        if not TESSERACT_AVAILABLE:
            return False
        # Quick check that tesseract binary is accessible
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def extract_text(self, image: object) -> str:
        """Extract plain text from image.

        Args:
            image: PIL Image object

        Returns:
            Extracted text as string
        """
        if not TESSERACT_AVAILABLE:
            return ""
        try:
            return pytesseract.image_to_string(image, lang=self._language).strip()
        except Exception:
            return ""

    def extract_regions(
        self,
        image: object,
        min_confidence: Optional[float] = None,
    ) -> List[OCRRegion]:
        """Extract text regions with bounding boxes and confidence.

        Args:
            image: PIL Image object
            min_confidence: Override default confidence threshold

        Returns:
            List of OCRRegion objects
        """
        if not TESSERACT_AVAILABLE:
            return []

        threshold = min_confidence if min_confidence is not None else self._min_confidence

        try:
            data = pytesseract.image_to_data(
                image,
                lang=self._language,
                output_type=pytesseract.Output.DICT,
            )
        except Exception:
            return []

        regions: List[OCRRegion] = []
        n_boxes = len(data.get("text", []))

        for i in range(n_boxes):
            text = (data["text"][i] or "").strip()
            if not text:
                continue

            conf = float(data["conf"][i]) / 100.0  # Convert 0-100 to 0-1
            if conf < threshold:
                continue

            bbox = BoundingBox(
                x=int(data["left"][i]),
                y=int(data["top"][i]),
                width=int(data["width"][i]),
                height=int(data["height"][i]),
            )

            regions.append(OCRRegion(
                text=text,
                bbox=bbox,
                confidence=conf,
                language=self._language,
            ))

        return regions

    def extract_from_region(
        self,
        image: object,
        region: Tuple[int, int, int, int],
        min_confidence: Optional[float] = None,
    ) -> List[OCRRegion]:
        """Extract text from a specific image region.

        Args:
            image: PIL Image object
            region: (left, top, width, height) crop area
            min_confidence: Override default confidence threshold

        Returns:
            List of OCRRegion objects with coordinates adjusted to full image space
        """
        if not PIL_AVAILABLE or not isinstance(image, Image.Image):
            return []

        left, top, width, height = region
        cropped = image.crop((left, top, left + width, top + height))
        regions = self.extract_regions(cropped, min_confidence=min_confidence)

        # Adjust coordinates to full image space
        adjusted: List[OCRRegion] = []
        for r in regions:
            adjusted_bbox = BoundingBox(
                x=r.bbox.x + left,
                y=r.bbox.y + top,
                width=r.bbox.width,
                height=r.bbox.height,
            )
            adjusted.append(OCRRegion(
                text=r.text,
                bbox=adjusted_bbox,
                confidence=r.confidence,
                language=r.language,
            ))

        return adjusted
