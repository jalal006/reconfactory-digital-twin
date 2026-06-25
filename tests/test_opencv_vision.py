from reconfactory.config import DEFAULT_RECIPES
from vision.opencv_inspector import OpenCVInspector


def test_opencv_inspector_accepts_valid_synthetic_product():
    inspector = OpenCVInspector()
    recipe = DEFAULT_RECIPES["red_block"]
    image = inspector.create_synthetic_image(recipe)

    result, features = inspector.inspect_image(image, recipe)

    assert result.passed
    assert result.detected_type == "red_block"
    assert features.detected_shape == "block"


def test_opencv_inspector_rejects_wrong_color():
    inspector = OpenCVInspector()
    recipe = DEFAULT_RECIPES["blue_cylinder"]
    image = inspector.create_synthetic_image(recipe, wrong_color=True)

    result, features = inspector.inspect_image(image, recipe)

    assert not result.passed
    assert result.defect_reason == "incorrect_colour"
    assert features.dominant_color != "blue"


def test_opencv_inspector_rejects_wrong_shape_for_cylinder():
    inspector = OpenCVInspector()
    recipe = DEFAULT_RECIPES["blue_cylinder"]
    image = inspector.create_synthetic_image(recipe, wrong_shape=True)

    result, features = inspector.inspect_image(image, recipe)

    assert not result.passed
    assert result.defect_reason == "incorrect_shape"
    assert features.detected_shape == "block"


def test_opencv_inspector_rejects_missing_section():
    inspector = OpenCVInspector()
    recipe = DEFAULT_RECIPES["red_block"]
    image = inspector.create_synthetic_image(recipe, missing_section=True)

    result, features = inspector.inspect_image(image, recipe)

    assert not result.passed
    assert result.defect_reason == "missing_section_or_invalid_dimensions"
    assert features.area_ratio < 0.92
