# Vision System

The live factory uses OpenCV machine vision through:

```text
vision/inspector.py
vision/opencv_inspector.py
ros2_ws/src/reconfactory_ros/reconfactory_ros/vision_inspector_node.py
```

`VisionInspector` is called by `FactorySupervisor` when a product finishes the
vision-station operation. In the default mode it creates a simulated inspection
frame and passes it to `OpenCVInspector`. In Gazebo mode it waits for one
aggregated camera result from the ROS 2 vision node.

## Modes

```text
VISION_SOURCE=synthetic
```

Default mode. The supervisor generates a deterministic image for the product and
OpenCV analyzes that frame. This works in PowerShell, Docker, CI, and any
environment without ROS 2 or Gazebo.

```text
VISION_SOURCE=gazebo
```

Closed-loop simulator mode. The Gazebo world renders pixels from the fixed RGB
camera at the vision station. `ros_gz_bridge` exposes that stream as
`sensor_msgs/Image`, and `/reconfactory_vision_inspector` uses the same OpenCV
analysis logic to classify the product.

Gazebo camera acceptance checks **color only**. Shape and area remain diagnostic
measurements and cannot reject a camera-inspected product. A wrong-color product
is rejected; an empty frame is not a valid inspection. Synthetic mode retains
its existing shape and missing-material checks.

Final Quality Control independently rejects injected `wrong_shape`, `missing_part`
and `quality_defect` flags. These are simulated structural checks, not camera
measurements. A structural defect can pass color inspection and processing, but
will be rejected at Quality with an explicit reason in the event log.

## Camera Flow

```text
Gazebo RGB Camera
-> /reconfactory/vision/image_raw
-> sensor_msgs/msg/Image
-> /reconfactory_vision_inspector
-> cv_bridge
-> OpenCVInspector.inspect_image()
-> multi-frame aggregation
-> /reconfactory/vision/result
-> /api/vision/result
-> FactorySupervisor
```

## Synthetic Detection Pipeline

1. Generate the simulated camera frame from the product recipe and defect state.
2. Convert BGR pixels to HSV.
3. Segment saturated product pixels from the light background.
4. Select a product contour, preferring compact central shapes.
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

## Supervisor Gating

```text
Product enters vision
-> station operation completes
-> supervisor waits for pending product result
-> Gazebo sync reports the product at vision
-> ROS node aggregates 5 valid frames
-> one result becomes authoritative
-> passed products continue
-> failed products go to reject output
```

OpenCV and NumPy are installed by the normal `requirements.txt`.

If OpenCV cannot load, `VisionInspector` uses a deterministic rule-based
fallback so production remains testable. The event payload identifies the
method as `opencv` or `rule_based_fallback`.

In Gazebo mode, if no camera result arrives before the configured timeout, the
supervisor emits `vision_camera_timeout` and uses synthetic OpenCV inspection so
the line does not hang forever.

## Result Payload

Gazebo camera results are JSON and include:

```json
{
  "product_id": "P-00001",
  "product_type": "red_block",
  "source": "gazebo_camera",
  "detected_color": "red",
  "detected_shape": "block",
  "area_ratio": 0.94,
  "missing_material": false,
  "confidence": 0.93,
  "accepted": true,
  "frame_count": 5,
  "inspection_latency_ms": 180.0
}
```

The same result is published on `/reconfactory/vision/result` as
`std_msgs/msg/String` and submitted to FastAPI through `/api/vision/result`.
The supervisor remains the source of truth for product state.

## Debug Image

The ROS 2 vision node publishes an annotated camera image on:

```text
/reconfactory/vision/debug_image
```

The image contains a selected contour, bounding box, detected color, detected
shape, area ratio, confidence, and PASS/FAIL text. It can be viewed with:

```bash
ros2 run rqt_image_view rqt_image_view /reconfactory/vision/debug_image
```

## Tests

```bash
python -m pytest tests/test_opencv_vision.py tests/test_gazebo_camera_vision.py tests/test_integration_flow.py
```

## Boundary

Synthetic mode performs real pixel analysis on generated frames. Gazebo mode
performs real pixel analysis on rendered simulator camera frames. A physical
camera is not part of this repository.

The camera's area ratio uses the synthetic reference area, not a calibrated
physical measurement. Camera shape and missing-material decisions are disabled.
Confidence is a heuristic score, not a calibrated probability. The five-frame
window uses color/shape majority votes, median area ratio, and mean confidence.
Only color affects camera acceptance. Results are sent once per active window;
HTTP retries reuse the payload without publishing a new ROS result.

The raw camera stream is continuous. Debug images are produced while a pending
product is visible at vision; an idle debug view may keep its last image.
The supervisor's timeout is five production ticks by default (about 3.25 seconds
at normal speed), and freezes while production is paused.

Perception source, confidence, area ratio, latency and frame count are stored in
inspection event JSON in SQLite. No database migration is required. See
[requirements audit](VISION_ACCEPTANCE_AUDIT.md) for the full acceptance checklist.
