"""Shared OpenCV inspection for generated and Gazebo-rendered product images."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import mean, median
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
    missing_material: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "dominant_color": self.dominant_color,
            "detected_color": self.dominant_color,
            "detected_shape": self.detected_shape,
            "area": self.area,
            "expected_area": self.expected_area,
            "area_ratio": self.area_ratio,
            "confidence": self.confidence,
            "missing_material": self.missing_material,
        }


@dataclass(frozen=True)
class AggregatedInspection:
    result: InspectionResult
    features: ImageInspectionFeatures
    frame_count: int

    def to_payload(self, *, product_id: str, source: str = "gazebo_camera") -> dict[str, Any]:
        return {
            "product_id": product_id,
            "source": source,
            "accepted": self.result.passed,
            "passed": self.result.passed,
            "detected_type": self.result.detected_type,
            "detected_color": self.features.dominant_color,
            "detected_shape": self.features.detected_shape,
            "area_ratio": self.features.area_ratio,
            "missing_material": self.features.missing_material,
            "confidence": self.result.confidence,
            "defect_reason": self.result.defect_reason,
            "inspection_method": self.result.method,
            "frame_count": self.frame_count,
            "features": self.features.to_dict(),
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
        self,
        image,
        expected_recipe: ProductRecipe,
        *,
        enforce_area: bool = True,
        enforce_shape: bool = True,
    ) -> tuple[InspectionResult, ImageInspectionFeatures]:
        import cv2
        import numpy as np

        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        expected_color = _classify_color(_hex_to_bgr(expected_recipe.color))
        expected_mask = _product_color_mask(hsv, expected_color)
        fallback_mask = _product_color_mask(hsv)
        mask = expected_mask if cv2.countNonZero(expected_mask) else fallback_mask
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            expected_area = _expected_area(expected_recipe.shape)
            features = ImageInspectionFeatures(
                "unknown", "unknown", 0.0, expected_area, 0.0, 0.0, True
            )
            return (
                InspectionResult(
                    False,
                    0.0,
                    None,
                    "No product contour detected",
                    method="opencv",
                    features=features.to_dict(),
                ),
                features,
            )

        contour = _select_product_contour(contours, image.shape)
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

        contour_mask = np.zeros(mask.shape, dtype=np.uint8)
        cv2.drawContours(contour_mask, [contour], -1, 255, -1)
        mean_bgr = cv2.mean(image, mask=contour_mask)[:3]
        dominant = _classify_color(mean_bgr)
        expected_area = _expected_area(expected_recipe.shape)
        area_ratio = area / expected_area

        shape_ok = not enforce_shape or shape == expected_recipe.shape
        color_ok = dominant == expected_color
        area_ok = True if not enforce_area else 0.92 <= area_ratio <= 1.08
        missing_material = bool(enforce_area and area_ratio < 0.92)
        confidence = round(
            (0.4 if color_ok else 0.0) + (0.4 if shape_ok else 0.0) + (0.2 if area_ok else 0.0),
            2,
        )

        defect = None
        if not color_ok:
            defect = "incorrect_colour"
        elif enforce_area and missing_material:
            defect = "missing_section_or_invalid_dimensions"
        elif not shape_ok:
            defect = "incorrect_shape"
        elif enforce_area and area_ratio > 1.08:
            defect = "missing_section_or_invalid_dimensions"

        features = ImageInspectionFeatures(
            dominant,
            shape,
            round(area, 2),
            round(expected_area, 2),
            round(area_ratio, 3),
            confidence,
            missing_material,
        )
        features_dict = features.to_dict()
        return (
            InspectionResult(
                passed=defect is None,
                confidence=confidence,
                detected_type=expected_recipe.product_type if defect is None else None,
                defect_reason=defect,
                method="opencv",
                features=features_dict,
            ),
            features,
        )

    def aggregate_results(
        self,
        inspections: list[tuple[InspectionResult, ImageInspectionFeatures]],
        expected_recipe: ProductRecipe,
        *,
        enforce_area: bool = True,
        enforce_shape: bool = True,
    ) -> AggregatedInspection:
        if not inspections:
            features = ImageInspectionFeatures(
                "unknown",
                "unknown",
                0.0,
                _expected_area(expected_recipe.shape),
                0.0,
                0.0,
                True,
            )
            return AggregatedInspection(
                InspectionResult(
                    False,
                    0.0,
                    None,
                    "No valid inspection frames",
                    method="gazebo_camera",
                    features=features.to_dict(),
                ),
                features,
                0,
            )

        features_list = [features for _, features in inspections]
        detected_color = _majority([features.dominant_color for features in features_list])
        detected_shape = _majority([features.detected_shape for features in features_list])
        area_ratio = round(float(median(features.area_ratio for features in features_list)), 3)
        confidence = round(float(mean(result.confidence for result, _ in inspections)), 2)
        expected_color = _classify_color(_hex_to_bgr(expected_recipe.color))
        color_ok = detected_color == expected_color
        shape_ok = not enforce_shape or detected_shape == expected_recipe.shape
        area_ok = True if not enforce_area else 0.92 <= area_ratio <= 1.08
        missing_material = bool(enforce_area and area_ratio < 0.92)

        defect = None
        if not color_ok:
            defect = "incorrect_colour"
        elif enforce_area and missing_material:
            defect = "missing_section_or_invalid_dimensions"
        elif not shape_ok:
            defect = "incorrect_shape"
        elif enforce_area and not area_ok:
            defect = "missing_section_or_invalid_dimensions"

        features = ImageInspectionFeatures(
            dominant_color=detected_color,
            detected_shape=detected_shape,
            area=round(float(median(features.area for features in features_list)), 2),
            expected_area=round(_expected_area(expected_recipe.shape), 2),
            area_ratio=area_ratio,
            confidence=confidence,
            missing_material=missing_material,
        )
        result = InspectionResult(
            passed=defect is None,
            confidence=confidence,
            detected_type=expected_recipe.product_type if defect is None else None,
            defect_reason=defect,
            method="gazebo_camera",
            features=features.to_dict(),
        )
        return AggregatedInspection(result, features, len(inspections))

    def annotate_image(
        self,
        image,
        result: InspectionResult,
        features: ImageInspectionFeatures,
    ):
        import cv2

        annotated = image.copy()
        hsv = cv2.cvtColor(annotated, cv2.COLOR_BGR2HSV)
        mask = _product_color_mask(hsv)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            contour = _select_product_contour(contours, annotated.shape)
            cv2.drawContours(annotated, [contour], -1, (0, 255, 255), 2)
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(annotated, (x, y), (x + w, y + h), (255, 255, 255), 2)
        status = "PASS" if result.passed else "FAIL"
        text = (
            f"{status} {features.dominant_color} {features.detected_shape} "
            f"area={features.area_ratio:.2f} conf={result.confidence:.2f}"
        )
        cv2.putText(
            annotated,
            text,
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (0, 180, 0) if result.passed else (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        return annotated


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


def _product_color_mask(hsv, expected_color: str | None = None):
    import cv2
    import numpy as np

    red_low = cv2.inRange(hsv, np.array([0, 70, 45]), np.array([12, 255, 255]))
    red_high = cv2.inRange(hsv, np.array([165, 70, 45]), np.array([179, 255, 255]))
    red = red_low | red_high
    blue = cv2.inRange(hsv, np.array([85, 55, 45]), np.array([135, 255, 255]))
    green = cv2.inRange(hsv, np.array([38, 55, 45]), np.array([88, 255, 255]))
    if expected_color == "red":
        return red
    if expected_color == "blue":
        return blue
    if expected_color == "green":
        return green
    return red_low | red_high | blue | green


def _select_product_contour(contours, image_shape):
    import cv2

    height, width = image_shape[:2]

    def score(contour) -> float:
        area = float(cv2.contourArea(contour))
        if area < 40.0:
            return 0.0
        x, y, w, h = cv2.boundingRect(contour)
        if w <= 0 or h <= 0:
            return 0.0
        touches_edge = x <= 1 or y <= 1 or x + w >= width - 1 or y + h >= height - 1
        edge_factor = 0.35 if touches_edge else 1.0
        aspect = max(w, h) / max(min(w, h), 1)
        compact_factor = min(1.0, 1.9 / max(aspect, 1.0))
        center_x = x + w / 2.0
        center_y = y + h / 2.0
        normalized_distance = (
            abs(center_x - width / 2.0) / max(width / 2.0, 1.0)
            + abs(center_y - height / 2.0) / max(height / 2.0, 1.0)
        ) / 2.0
        center_factor = max(0.25, 1.0 - normalized_distance)
        return area * compact_factor * center_factor * edge_factor

    return max(contours, key=score)


def _majority(values: list[str]) -> str:
    if not values:
        return "unknown"
    counts = Counter(values)
    return counts.most_common(1)[0][0]
