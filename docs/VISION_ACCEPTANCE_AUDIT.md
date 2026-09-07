# Camera Perception Requirements Audit

Audit date: 2026-09-06, with regression updates on 2026-09-07.
The original camera-pipeline prompt was reviewed together with the
later instruction to make Gazebo camera acceptance **color-only**.

## Scope Decision

Camera shape classification and area measurements are diagnostic only. They do
not reject products. Wrong-color products can be rejected. Synthetic mode still
checks color, shape and missing material. Camera timeout deliberately falls back
to synthetic inspection and can therefore apply those synthetic checks.

The original requirements for camera shape/area defect rejection are superseded
by the color-only instruction. They must not be presented as implemented camera
quality checks in a portfolio demo.

## Architecture And Evidence

```text
Supervisor product state -> Gazebo sync -> product at vision
Gazebo RGB camera -> ros_gz_bridge -> sensor_msgs/Image
-> ROS vision node -> cv_bridge -> shared OpenCV inspector
-> five-frame result -> ROS JSON publication + HTTP submission
-> supervisor _apply_vision_result -> routing + SQLite events
```

The ROS result topic is an observation channel. The same payload reaches the
supervisor through HTTP; a separate ROS topic subscriber does not control the
factory. The supervisor remains the only production state machine.

| Prompt item | Implementation and qualification |
|---|---|
| 1. Camera | `gazebo_fallback/worlds/reconfactory.world.sdf`: fixed downward camera at vision, 640x480, 15 Hz, 1.20 rad FOV, lens below housing, scene lighting. Explicit Physics, UserCommands, Sensors and SceneBroadcaster plugins. |
| 2. Bridge | `gazebo_fallback/config/ros_gz_bridge.yaml`: RGB and camera-info mappings plus original state/fault bridges. Camera-info delivery still needs runtime confirmation. |
| 3. Shared inspector | `vision/opencv_inspector.py`: arbitrary BGR arrays and generated images share analysis and aggregation; backward-compatible result fields. |
| 4. ROS node | `ros2_ws/src/reconfactory_ros/reconfactory_ros/vision_inspector_node.py`: Image subscription, cv_bridge conversion, JSON String result publication and HTTP submission. |
| 5. Gating | Requires supervisor pending product and Gazebo visual location `vision`. Five valid frames; majority color/shape, median area, mean confidence. Final payload retained for HTTP retries. Empty/unknown frames do not produce decisions. |
| 6. Debug | Annotated contour, bounding box, color, diagnostic shape/area, score and PASS/FAIL on `/reconfactory/vision/debug_image`. Updates during active inspections. |
| 7. Supervisor | `reconfactory/supervisor.py`, `vision/inspector.py`, `app/main.py`: same routing path for camera and synthetic results, pending-product gate, timeout fallback. |
| 8. Analytics | Existing SQLite event JSON contains inspection method, confidence, source, area ratio, frame count and latency. No destructive schema changes or dedicated perception charts. |
| 9. Visualization | Optional `rviz/vision_debug.rviz` includes raw/debug displays; topic property aligned with installed Jazzy example. rqt instructions provided. GUI rendering not reverified in this audit. |
| 10. Launch | `run_ubuntu.sh` selects available mode and starts normal stack; `scripts/run_ros_bridge.sh` builds changed package sources. Explicit camera request falls back if prerequisites are missing. |
| 11. Dependencies | `requirements.txt`, ROS `package.xml`, `setup.py`: OpenCV/NumPy, sensor_msgs/cv_bridge, launch dependencies and vision entry point. ROS remains outside normal Python requirements. |
| 12. Tests | Existing synthetic, fault, recovery, routing and analytics tests retained; camera and verification tests added. Normal pytest does not import live ROS dependencies. |
| 13. Verification | `scripts/check_vision_pipeline.py`: graph checks, duplicate node detection, bounded subscription requiring actual image dimensions/bytes, nonzero exit on failure. Classification must still be checked with a spawned product. |
| 14. Acceptance | See A-P status below; runtime acceptance is not certified from source/tests alone. |
| 15. Commands | Python tests, Ruff, integration detection, colcon, SDF validation and bounded ROS checks performed; results below. |
| 16. Documentation | README, vision, ROS and Gazebo guides cover modes, topics, running, viewers and limitations. This audit records exceptions and evidence. |
| 17. Quality | Focused changes with type hints, lazy ROS imports, throttled warnings and finite HTTP retry intervals. Heuristic vision remains scene-dependent. |
| 18. Authority | Supervisor controls state; Gazebo renders, ROS transports, OpenCV inspects. No parallel production controller added. |
| 19. Handoff | Changes, commands, limitations, tests and demo sequence are recorded here. |

## Acceptance A-P

| Criteria | Status |
|---|---|
| A-B: browser independence and synthetic inspection | Source and non-ROS tests verified; fresh browser GUI/Docker launch not performed. |
| C: inspection camera in world | SDF definition reviewed and validated; final camera framing needs a live view. |
| D-G: images, ROS node, conversion, rendered-pixel inspection | Implemented and dependencies installed. Current session lacks the vision node and delivered images; live recheck required. |
| H-I: structured result and supervisor consumption | Serialization, routing, no synthetic reinspection, duplicate handling and persistence tested. Live result delivery not reverified. |
| J-K: pass/fail | All three recipes tested for correct/wrong color with shape ignored in camera mode. Live normal/wrong-color demo remains to be repeated. |
| L: annotated display | Implemented; optional RViz property corrected, GUI viewing remains unverified. |
| M-O: tests and Ruff | Latest regression: 132 Python tests and eight browser movement scenarios pass; lint and formatting checks pass. |
| P: reproduction docs | Updated with mode distinction, commands, fallback behavior and limitations. |

## Verification Results

Latest follow-up verification (2026-09-07): 132 Python tests pass in WSL, eight
JavaScript movement scenarios pass in a V8 harness, and Ruff lint/format checks
pass. These include API responsiveness during slow optional checks, structural
quality rejection, terminal outputs and delayed station updates. The live ROS
observations below were collected during the original audit; they are not a
statement about every subsequent user session.

- Windows `.venv`: `python -m pytest` passed all 110 tests.
- WSL `.venv-wsl`: all 110 tests passed with ROS `PYTHONPATH` removed for the
  test command. Both `python -m ruff check .` and `format --check .` passed.
- Ruff executable: lint passed; format check passed for 57 Python files.
- WSL `scripts/check_integrations.py`: Python, FastAPI, ROS 2 Jazzy, Gazebo,
  ros_gz_bridge, cv_bridge, colcon and optional OPC UA reported installed.
- `colcon build --packages-select reconfactory_ros --symlink-install`: succeeded.
- `gz sdf -k gazebo_fallback/worlds/reconfactory.world.sdf`: Valid.
- `bash -n run_ubuntu.sh scripts/run_ros_bridge.sh`: succeeded.
- Read-only ROS graph: duplicate supervisor/controller/fault/logger node names;
  vision-inspector node and result/debug topics missing. Raw image topic exists.
- Bounded camera sampling received **zero valid image messages** in three seconds.
  A topic name alone does not prove that Gazebo is delivering images.
- No new full stack was started alongside the existing duplicate graph. Continuous
  result echo, RViz/rqt viewing, browser controls and live defective products were
  not exercised in this audit. The user's earlier successful run is separate
  from these verification results.

## Files In This Feature

Added by the camera feature: the ROS vision node, optional RViz config,
`scripts/check_vision_pipeline.py`, `tests/test_gazebo_camera_vision.py`.

Added during this audit: `tests/test_vision_pipeline_check.py` and this report.

Feature modifications span `vision/`, supervisor/API, integration detection,
Gazebo world/bridge/sync/launch, ROS package/launch metadata, Ubuntu/ROS launchers,
Gazebo/ROS tests, README and the architecture/API/database/vision/ROS/Gazebo docs.
Existing local modifications were preserved throughout the audit.

Audit fixes specifically: launcher prerequisite fallback, persisted camera-timeout
method, required ROS launch/OpenCV dependencies, RViz topic properties, checker
image sampling/timeout handling/duplicate detection, and reproduction documentation.

## Reproduce And Verify

Stop previous ReConFactory launchers with Ctrl+C in their owning terminals before
starting one stack. Do not run multiple factory stacks in the same ROS domain.
From the repository root in Ubuntu/WSL:

```bash
VISION_SOURCE=gazebo bash run_ubuntu.sh
```

In a second terminal, also from the repository root:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash
python3 scripts/check_vision_pipeline.py --sample-seconds 5
ros2 node list
ros2 topic list
ros2 topic echo /reconfactory/vision/result
```

Keep echo running before spawning. In the dashboard reset/start production, spawn
a normal red block, then a red block with `wrong_colour`. Expect one result per
product with `source=gazebo_camera`, the observed color, five frames, and opposite
acceptance values. Check the matching dashboard inspection method and product ID.
A timeout method does not count as successful camera acceptance.

Optional image viewers (each is a separate foreground command):

```bash
sudo apt install ros-jazzy-rqt-image-view ros-jazzy-rviz2
ros2 run rqt_image_view rqt_image_view /reconfactory/vision/image_raw
ros2 run rqt_image_view rqt_image_view /reconfactory/vision/debug_image
rviz2 -d ros2_ws/src/reconfactory_ros/rviz/vision_debug.rviz
```

For the image rate use `ros2 topic hz /reconfactory/vision/image_raw` and Ctrl+C
after a few seconds. Test browser-only mode from an activated Python environment:

```bash
VISION_SOURCE=synthetic python scripts/run_factory.py
```

Regression commands (activated project environment):

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
python scripts/check_integrations.py
```

If a sourced ROS terminal makes pytest fail during plugin loading with missing
`lark`, run the pure Python suite without the inherited ROS package path:

```bash
env -u PYTHONPATH .venv-wsl/bin/python -m pytest
```

This runs the same tests and keeps normal project plugins enabled. Keep the ROS
environment sourced for the camera verifier, ROS nodes and colcon.

## Limitations And Demo

Color segmentation is heuristic and sensitive to lighting, occlusion and colored
scene clutter. Area is relative to synthetic reference pixels, not calibrated
dimensions. Confidence is not a statistical probability. Gazebo positions are
reported by the synchronization process, not independently identified from pixels.
Reset/restart or timeout can make late results inapplicable; the supervisor ignores
results without a matching pending product. Full cross-reset request identities
are not implemented. A ROS publisher restart can republish a pending product.

For a 30-60 second demo: show the factory and raw/debug image, spawn a normal red
block and display its camera acceptance, then spawn a wrong-color red block and
show the observed color plus rejection. End with the matching dashboard event and
production metrics. Have the stack and image/result viewers ready before recording.
