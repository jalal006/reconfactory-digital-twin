"""OpenCV-based inspection helpers for synthetic product images."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reconfactory.models import ProductRecipe
from vision.inspector import InspectionResult


@dataclass(frozen=True)
class ImageInspectionFeatures:
    dominant_color: str
    detected_shape: str
    area: float
    expected_area: float
    area_ratio: float
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "dominant_color": self.dominant_color,
            "detected_shape": self.detected_shape,
            "area": self.area,
            "expected_area": self.expected_area,
            "area_ratio": self.area_ratio,
            "confidence": self.confidence,
        }


class OpenCVInspector:
    def __init__(self) -> None:
        try:
            import cv2  # noqa: F401
            import numpy  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV inspection requires opencv-python and numpy. Install requirements.txt."
            ) from exc

    def create_synthetic_image(
        self,
        recipe: ProductRecipe,
        *,
        wrong_color: bool = False,
        wrong_shape: bool = False,
        missing_section: bool = False,
    ):
        import cv2
        import numpy as np

        image = np.full((220, 220, 3), 245, dtype=np.uint8)
        color = _wrong_color_for(recipe.color) if wrong_color else _hex_to_bgr(recipe.color)
        if wrong_shape:
            shape = "block" if recipe.shape == "cylinder" else "cylinder"
        else:
            shape = recipe.shape

        if shape == "cylinder":
            cv2.circle(image, (110, 110), 55, color, -1)
        elif shape == "component":
            points = np.array(
                [[65, 65], [155, 65], [155, 105], [130, 105], [130, 155], [65, 155]]
            )
            cv2.fillPoly(image, [points], color)
        else:
            cv2.rectangle(image, (60, 60), (160, 160), color, -1)

        if missing_section:
            cv2.rectangle(image, (130, 50), (180, 100), (245, 245, 245), -1)
        return image

    def inspect_image(
        self, image, expected_recipe: ProductRecipe
    ) -> tuple[InspectionResult, ImageInspectionFeatures]:
        import cv2
        import numpy as np

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([0, 40, 40]), np.array([179, 255, 255]))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            expected_area = _expected_area(expected_recipe.shape)
            features = ImageInspectionFeatures(
                "unknown", "unknown", 0.0, expected_area, 0.0, 0.0
            )
            return (
                InspectionResult(False, 0.0, None, "No product contour detected"),
                features,
            )

        contour = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(contour))
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
        circularity = 4 * np.pi * area / max(perimeter * perimeter, 1.0)

        if circularity > 0.82:
            shape = "cylinder"
        elif not cv2.isContourConvex(approx):
            shape = "component"
        elif len(approx) > 4:
            x, y, w, h = cv2.boundingRect(contour)
            extent = area / max(float(w * h), 1.0)
            aspect = w / max(h, 1)
            shape = "block" if extent > 0.82 and 0.75 <= aspect <= 1.35 else "component"
        else:
            x, y, w, h = cv2.boundingRect(contour)
            aspect = w / max(h, 1)
            shape = "block" if 0.75 <= aspect <= 1.35 else "component"

        mean_bgr = cv2.mean(image, mask=mask)[:3]
        dominant = _classify_color(mean_bgr)
        expected_color = _classify_color(_hex_to_bgr(expected_recipe.color))
        expected_area = _expected_area(expected_recipe.shape)
        area_ratio = area / expected_area

        shape_ok = shape == expected_recipe.shape
        color_ok = dominant == expected_color
        area_ok = 0.92 <= area_ratio <= 1.08
        confidence = round(
            (0.4 if color_ok else 0.0) + (0.4 if shape_ok else 0.0) + (0.2 if area_ok else 0.0),
            2,
        )

        defect = None
        if not color_ok:
            defect = "incorrect_colour"
        elif area_ratio < 0.92:
            defect = "missing_section_or_invalid_dimensions"
        elif not shape_ok:
            defect = "incorrect_shape"
        elif area_ratio > 1.08:
            defect = "missing_section_or_invalid_dimensions"

        features = ImageInspectionFeatures(
            dominant,
            shape,
            round(area, 2),
            round(expected_area, 2),
            round(area_ratio, 3),
            confidence,
        )
        return (
            InspectionResult(
                passed=defect is None,
                confidence=confidence,
                detected_type=expected_recipe.product_type if defect is None else None,
                defect_reason=defect,
            ),
            features,
        )


def _hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    return b, g, r


def _wrong_color_for(hex_color: str) -> tuple[int, int, int]:
    expected = _classify_color(_hex_to_bgr(hex_color))
    if expected == "blue":
        return _hex_to_bgr("#ef4444")
    if expected == "red":
        return _hex_to_bgr("#3b82f6")
    return _hex_to_bgr("#ef4444")


def _expected_area(shape: str) -> float:
    if shape == "cylinder":
        return 9322.0
    if shape == "component":
        return 6850.5
    return 10000.0


def _classify_color(bgr: tuple[float, float, float]) -> str:
    b, g, r = bgr
    if r > g and r > b:
        return "red"
    if b > r and b > g:
        return "blue"
    if g > r and g > b:
        return "green"
    return "unknown"
