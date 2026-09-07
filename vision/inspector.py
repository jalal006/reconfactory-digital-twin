"""Machine-vision inspection used by the live factory simulation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from reconfactory.models import Product, ProductRecipe


@dataclass(frozen=True)
class InspectionResult:
    passed: bool
    confidence: float
    detected_type: str | None
    defect_reason: str | None = None
    method: str = "rule_based"
    features: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "confidence": self.confidence,
            "detected_type": self.detected_type,
            "defect_reason": self.defect_reason,
            "method": self.method,
            "features": dict(self.features),
        }


REASON_MAP = {
    "incorrect_colour": "Colour does not match recipe",
    "incorrect_shape": "Shape does not match recipe",
    "missing_section_or_invalid_dimensions": "Required part is missing",
    "no_product_contour_detected": "No product contour detected",
    "No product contour detected": "No product contour detected",
}


class VisionInspector:
    def __init__(self, recipes: dict[str, ProductRecipe]) -> None:
        self.recipes = recipes
        self._opencv = self._load_opencv()

    @staticmethod
    def _load_opencv():
        try:
            from vision.opencv_inspector import OpenCVInspector

            return OpenCVInspector()
        except (ImportError, RuntimeError):
            return None

    def inspect(self, product: Product) -> InspectionResult:
        if self._opencv and "unidentified" not in product.defect_flags:
            return self._inspect_with_opencv(product)
        return self._inspect_with_rules(product)

    def _inspect_with_opencv(self, product: Product) -> InspectionResult:
        recipe = self.recipes[product.product_type]
        image = self._opencv.create_synthetic_image(
            recipe,
            wrong_color="wrong_colour" in product.defect_flags,
            wrong_shape="wrong_shape" in product.defect_flags,
            missing_section="missing_part" in product.defect_flags,
        )
        result, features = self._opencv.inspect_image(image, recipe)
        return replace(
            result,
            defect_reason=REASON_MAP.get(result.defect_reason, result.defect_reason),
            method="opencv",
            features=features.to_dict(),
        )

    @staticmethod
    def from_external_payload(payload: dict[str, Any], product: Product) -> InspectionResult:
        accepted_value = payload.get("accepted")
        if accepted_value is None:
            accepted_value = payload.get("passed", False)
        accepted = bool(accepted_value)
        confidence = float(payload.get("confidence") or 0.0)
        detected_type = payload.get("detected_type")
        if accepted and detected_type is None:
            detected_type = product.product_type
        defect_reason = payload.get("defect_reason")
        features = dict(payload.get("features") or {})
        for key in (
            "detected_color",
            "detected_shape",
            "area_ratio",
            "missing_material",
            "frame_count",
            "source",
            "inspection_latency_ms",
        ):
            if key in payload and key not in features:
                features[key] = payload[key]
        if "detected_color" in features and "dominant_color" not in features:
            features["dominant_color"] = features["detected_color"]
        return InspectionResult(
            passed=accepted,
            confidence=confidence,
            detected_type=str(detected_type) if detected_type else None,
            defect_reason=REASON_MAP.get(defect_reason, defect_reason),
            method=str(payload.get("source") or payload.get("inspection_method") or "external"),
            features=features,
        )

    @staticmethod
    def _inspect_with_rules(product: Product) -> InspectionResult:
        if "unidentified" in product.defect_flags:
            return InspectionResult(
                passed=False,
                confidence=0.32,
                detected_type=None,
                defect_reason="Vision could not identify product type",
                method="rule_based_fallback",
            )
        if "wrong_colour" in product.defect_flags:
            return InspectionResult(
                passed=False,
                confidence=0.81,
                detected_type=product.product_type,
                defect_reason="Colour does not match recipe",
                method="rule_based_fallback",
            )
        if "wrong_shape" in product.defect_flags:
            return InspectionResult(
                passed=False,
                confidence=0.78,
                detected_type=product.product_type,
                defect_reason="Shape does not match recipe",
                method="rule_based_fallback",
            )
        if "missing_part" in product.defect_flags:
            return InspectionResult(
                passed=False,
                confidence=0.84,
                detected_type=product.product_type,
                defect_reason="Required part is missing",
                method="rule_based_fallback",
            )
        return InspectionResult(
            passed=True,
            confidence=0.96,
            detected_type=product.product_type,
            defect_reason=None,
            method="rule_based_fallback",
        )
