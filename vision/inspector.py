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
        reason_map = {
            "incorrect_colour": "Colour does not match recipe",
            "incorrect_shape": "Shape does not match recipe",
            "missing_section_or_invalid_dimensions": "Required part is missing",
        }
        return replace(
            result,
            defect_reason=reason_map.get(result.defect_reason, result.defect_reason),
            method="opencv",
            features=features.to_dict(),
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
