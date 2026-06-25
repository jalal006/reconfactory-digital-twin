# Vision System

The live factory uses OpenCV machine vision through:

```text
vision/inspector.py
vision/opencv_inspector.py
```

`VisionInspector` is called by `FactorySupervisor` when a product finishes the
vision-station operation. It creates a simulated inspection frame and passes it
to `OpenCVInspector`.

## Detection Pipeline

1. Generate the simulated camera frame from the product recipe and defect state.
2. Convert BGR pixels to HSV.
3. Segment saturated product pixels from the light background.
4. Select the largest contour.
5. Determine dominant red, blue, or green color.
6. Classify block, cylinder, or component geometry.
7. Compare contour area with the recipe reference area.
8. Return confidence, extracted features, and a pass/fail result.

It detects:

- Known product class identification
- Wrong color
- Wrong shape
- Missing sections or invalid dimensions
- Unidentified product simulation
- Inspection confidence
- Defect reason
- Reject routing

## Current Flow

```text
Product enters -> Vision station runs -> passed products continue -> failed products go to reject output
```

OpenCV and NumPy are installed by the normal `requirements.txt`.

If OpenCV cannot load, `VisionInspector` uses a deterministic rule-based
fallback so production remains testable. The event payload identifies the
method as `opencv` or `rule_based_fallback`.

## Tests

```bash
python -m pytest tests/test_opencv_vision.py tests/test_integration_flow.py
```

## Current Boundary

The implementation performs real pixel analysis, but the images are generated
inside the simulation. Reading frames from a Gazebo camera sensor or physical
camera is a future hardware/simulator integration, not a current claim.
