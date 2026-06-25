#!/usr/bin/env python3
"""Synchronize the FastAPI digital twin state into Gazebo Sim.

Run this while the FastAPI backend and Gazebo world are already running.
It uses Gazebo Sim transport services to create, move, and remove product
models so dashboard buttons are reflected in the 3D scene.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

LAYOUT = {
    "input_queue": (0.25, 0.0, 0.54),
    "vision": (2.0, 0.0, 0.54),
    "processing_buffer": (2.18, 0.0, 0.54),
    "station_a": (4.0, 1.25, 0.54),
    "station_b": (4.0, -1.25, 0.54),
    "quality_buffer": (5.95, 0.0, 0.54),
    "quality": (6.20, 0.0, 0.54),
    "accepted_output": (8.45, 0.72, 0.54),
    "reject_output": (8.45, -0.72, 0.54),
    "recovery_buffer": (6.80, -1.58, 0.54),
}

STATUS_LIGHTS = {
    "input_queue": (0.0, 0.0, 0.92),
    "conveyor_main": (3.0, 2.05, 1.22),
    "vision": (2.0, 0.0, 1.45),
    "station_a": (4.0, 1.25, 1.22),
    "station_b": (4.0, -1.25, 1.22),
    "processing_buffer": (2.95, 0.0, 0.76),
    "quality_buffer": (5.25, 0.0, 0.76),
    "quality": (6.2, 0.0, 1.25),
    "accepted_output": (8.45, 0.72, 0.86),
    "reject_output": (8.45, -0.72, 0.86),
    "recovery_buffer": (6.8, -1.75, 0.72),
}

ROUTES = {
    ("input_queue", "vision"): [
        LAYOUT["input_queue"],
        (0.70, 0.0, 0.36),
        (1.25, 0.0, 0.36),
        (1.75, 0.0, 0.36),
        LAYOUT["vision"],
    ],
    ("vision", "processing_buffer"): [
        LAYOUT["vision"],
        (2.05, 0.0, 0.36),
        LAYOUT["processing_buffer"],
    ],
    ("vision", "station_a"): [
        LAYOUT["vision"],
        LAYOUT["processing_buffer"],
        (2.35, 0.15, 0.36),
        (2.90, 0.62, 0.36),
        (3.48, 1.02, 0.36),
        LAYOUT["station_a"],
    ],
    ("vision", "station_b"): [
        LAYOUT["vision"],
        LAYOUT["processing_buffer"],
        (2.35, -0.15, 0.36),
        (2.90, -0.62, 0.36),
        (3.48, -1.02, 0.36),
        LAYOUT["station_b"],
    ],
    ("processing_buffer", "station_a"): [
        LAYOUT["processing_buffer"],
        (2.35, 0.15, 0.36),
        (2.90, 0.62, 0.36),
        (3.48, 1.02, 0.36),
        LAYOUT["station_a"],
    ],
    ("processing_buffer", "station_b"): [
        LAYOUT["processing_buffer"],
        (2.35, -0.15, 0.36),
        (2.90, -0.62, 0.36),
        (3.48, -1.02, 0.36),
        LAYOUT["station_b"],
    ],
    ("station_a", "quality_buffer"): [
        LAYOUT["station_a"],
        (4.28, 1.16, 0.36),
        (4.52, 1.02, 0.36),
        (5.10, 0.62, 0.36),
        (5.70, 0.15, 0.36),
        LAYOUT["quality_buffer"],
    ],
    ("station_a", "quality"): [
        LAYOUT["station_a"],
        (4.28, 1.16, 0.36),
        (4.52, 1.02, 0.36),
        (5.10, 0.62, 0.36),
        (5.70, 0.15, 0.36),
        LAYOUT["quality_buffer"],
        LAYOUT["quality"],
    ],
    ("station_b", "quality_buffer"): [
        LAYOUT["station_b"],
        (4.28, -1.16, 0.36),
        (4.52, -1.02, 0.36),
        (5.10, -0.62, 0.36),
        (5.70, -0.15, 0.36),
        LAYOUT["quality_buffer"],
    ],
    ("station_b", "quality"): [
        LAYOUT["station_b"],
        (4.28, -1.16, 0.36),
        (4.52, -1.02, 0.36),
        (5.10, -0.62, 0.36),
        (5.70, -0.15, 0.36),
        LAYOUT["quality_buffer"],
        LAYOUT["quality"],
    ],
    ("quality_buffer", "quality"): [LAYOUT["quality_buffer"], LAYOUT["quality"]],
    ("quality", "accepted_output"): [
        LAYOUT["quality"],
        (6.75, 0.0, 0.36),
        (7.45, 0.0, 0.36),
        (8.25, 0.36, 0.36),
        LAYOUT["accepted_output"],
    ],
    ("quality", "reject_output"): [
        LAYOUT["quality"],
        (6.75, 0.0, 0.36),
        (7.45, 0.0, 0.36),
        (8.25, -0.36, 0.36),
        LAYOUT["reject_output"],
    ],
    ("station_a", "recovery_buffer"): [
        LAYOUT["station_a"],
        (4.35, 0.80, 0.36),
        (5.15, -0.15, 0.36),
        (6.05, -1.05, 0.36),
        LAYOUT["recovery_buffer"],
    ],
    ("station_b", "recovery_buffer"): [
        LAYOUT["station_b"],
        (4.50, -1.35, 0.36),
        (5.55, -1.55, 0.36),
        LAYOUT["recovery_buffer"],
    ],
}

ROUTE_NAMES = {
    ("input_queue", "vision"): "input_to_vision",
    ("vision", "processing_buffer"): "vision_to_buffer",
    ("vision", "station_a"): "vision_to_station_a",
    ("vision", "station_b"): "vision_to_station_b",
    ("processing_buffer", "station_a"): "processing_buffer_to_station_a",
    ("processing_buffer", "station_b"): "processing_buffer_to_station_b",
    ("station_a", "quality_buffer"): "station_a_to_quality_buffer",
    ("station_a", "quality"): "station_a_to_quality",
    ("station_b", "quality_buffer"): "station_b_to_quality_buffer",
    ("station_b", "quality"): "station_b_to_quality",
    ("quality_buffer", "quality"): "quality_buffer_to_quality",
    ("quality", "accepted_output"): "quality_to_accepted",
    ("quality", "reject_output"): "quality_to_reject",
    ("station_a", "recovery_buffer"): "station_to_recovery",
    ("station_b", "recovery_buffer"): "station_to_recovery",
}

PRODUCT_COLORS = {
    "red_block": (1.0, 0.08, 0.08, 1.0),
    "blue_cylinder": (0.08, 0.26, 1.0, 1.0),
    "green_component": (0.08, 0.78, 0.24, 1.0),
}

STATUS_COLORS = {
    "idle": (0.42, 0.42, 0.40, 1.0),
    "processing": (0.95, 0.48, 0.05, 1.0),
    "done": (0.08, 0.65, 0.24, 1.0),
    "fault": (1.0, 0.06, 0.06, 1.0),
    "emergency_stop": (1.0, 0.06, 0.06, 1.0),
    "paused": (0.95, 0.48, 0.05, 1.0),
    "blocked": (0.95, 0.48, 0.05, 1.0),
    "maintenance": (0.95, 0.48, 0.05, 1.0),
}

SERVICE_DWELL_SECONDS = {
    "arrival_settle": 0.45,
    "vision": 1.0,
    "station_a": 1.8,
    "station_b": 1.8,
    "quality": 1.3,
}

DONE_INDICATION_SECONDS = 1.5


@dataclass
class Pose:
    x: float
    y: float
    z: float
    yaw: float = 0.0

    def lerp(self, target: Pose, alpha: float) -> Pose:
        return Pose(
            self.x + (target.x - self.x) * alpha,
            self.y + (target.y - self.y) * alpha,
            self.z + (target.z - self.z) * alpha,
            self.yaw + shortest_angle_delta(self.yaw, target.yaw) * alpha,
        )


ROUTE_ARROWS = {
    "input_to_vision": [Pose(0.82, 0.0, 0.39, 0.0), Pose(1.45, 0.0, 0.39, 0.0)],
    "vision_to_buffer": [Pose(2.12, 0.0, 0.39, 0.0)],
    "vision_to_station_a": [Pose(2.55, 0.22, 0.39, 0.55), Pose(3.18, 0.74, 0.39, 0.55)],
    "vision_to_station_b": [Pose(2.55, -0.22, 0.39, -0.55), Pose(3.18, -0.74, 0.39, -0.55)],
    "processing_buffer_to_station_a": [
        Pose(2.55, 0.22, 0.39, 0.55),
        Pose(3.18, 0.74, 0.39, 0.55),
    ],
    "processing_buffer_to_station_b": [
        Pose(2.55, -0.22, 0.39, -0.55),
        Pose(3.18, -0.74, 0.39, -0.55),
    ],
    "station_a_to_quality_buffer": [
        Pose(4.65, 0.90, 0.39, -0.55),
        Pose(5.35, 0.40, 0.39, -0.55),
    ],
    "station_a_to_quality": [Pose(4.65, 0.90, 0.39, -0.55), Pose(5.35, 0.40, 0.39, -0.55)],
    "station_b_to_quality_buffer": [
        Pose(4.65, -0.90, 0.39, 0.55),
        Pose(5.35, -0.40, 0.39, 0.55),
    ],
    "station_b_to_quality": [Pose(4.65, -0.90, 0.39, 0.55), Pose(5.35, -0.40, 0.39, 0.55)],
    "quality_buffer_to_quality": [Pose(6.05, 0.0, 0.39, 0.0)],
    "quality_to_accepted": [Pose(6.85, 0.0, 0.39, 0.0), Pose(7.55, 0.18, 0.39, 0.42)],
    "quality_to_reject": [Pose(6.85, 0.0, 0.39, 0.0), Pose(7.55, -0.18, 0.39, -0.42)],
    "station_to_recovery": [Pose(5.25, -1.15, 0.39, -0.85), Pose(6.05, -1.48, 0.39, -0.35)],
}


def pose_from_tuple(values: tuple[float, float, float]) -> Pose:
    return Pose(values[0], values[1], values[2])


def shortest_angle_delta(start: float, end: float) -> float:
    return (end - start + math.pi) % (math.tau) - math.pi


def pose_distance(a: Pose, b: Pose) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def path_length(points: list[Pose]) -> float:
    return sum(
        pose_distance(points[index], points[index + 1]) for index in range(len(points) - 1)
    )


def resample_path(points: list[Pose], spacing: float = 0.075) -> list[Pose]:
    if len(points) < 2:
        return points
    dense = [points[0]]
    for index in range(len(points) - 1):
        start = points[index]
        end = points[index + 1]
        segment = pose_distance(start, end)
        steps = max(1, int(math.ceil(segment / spacing)))
        for step in range(1, steps + 1):
            dense.append(start.lerp(end, step / steps))
    return dense


def smooth_path(
    points: list[Pose], *, iterations: int = 2, spacing: float = 0.075
) -> list[Pose]:
    if len(points) < 3:
        return resample_path(points, spacing)
    smoothed = points
    for _ in range(iterations):
        next_points = [smoothed[0]]
        for index in range(len(smoothed) - 1):
            start = smoothed[index]
            end = smoothed[index + 1]
            next_points.append(start.lerp(end, 0.28))
            next_points.append(start.lerp(end, 0.72))
        next_points.append(smoothed[-1])
        smoothed = next_points
    return resample_path(smoothed, spacing)


def pose_on_path(points: list[Pose], progress: float) -> Pose:
    if not points:
        return Pose(0, 0, 0)
    if len(points) == 1:
        return points[0]
    total = max(0.001, path_length(points))
    remaining = total * max(0.0, min(1.0, progress))
    for index in range(len(points) - 1):
        start = points[index]
        end = points[index + 1]
        segment = pose_distance(start, end)
        if remaining <= segment:
            alpha = remaining / segment if segment else 1.0
            return start.lerp(end, alpha)
        remaining -= segment
    return points[-1]


def pose_heading(start: Pose, end: Pose, fallback: float = 0.0) -> float:
    dx = end.x - start.x
    dy = end.y - start.y
    if abs(dx) < 0.001 and abs(dy) < 0.001:
        return fallback
    return math.atan2(dy, dx)


def advance_toward(current: Pose, desired: Pose, *, max_distance: float) -> Pose:
    distance = pose_distance(current, desired)
    if distance <= 0.001:
        return Pose(desired.x, desired.y, desired.z, desired.yaw)
    alpha = min(1.0, max_distance / distance)
    yaw = pose_heading(current, desired, current.yaw)
    return Pose(
        current.x + (desired.x - current.x) * alpha,
        current.y + (desired.y - current.y) * alpha,
        current.z + (desired.z - current.z) * alpha,
        current.yaw + shortest_angle_delta(current.yaw, yaw) * min(1.0, alpha * 1.8),
    )


def sanitize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", value)


def stable_hash(value: str) -> int:
    result = 0
    for char in value:
        result = (result * 31 + ord(char)) & 0xFFFFFFFF
    return result


def text_format_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def rgba(values: tuple[float, float, float, float]) -> str:
    return " ".join(f"{value:.3f}" for value in values)


def fetch_json(url: str, timeout: float = 2.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, Any], timeout: float = 0.4) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


def product_sdf(model_name: str, product_type: str) -> str:
    color = rgba(PRODUCT_COLORS.get(product_type, (0.45, 0.5, 0.58, 1.0)))
    if product_type == "blue_cylinder":
        geometry = "<cylinder><radius>0.18</radius><length>0.24</length></cylinder>"
    elif product_type == "green_component":
        geometry = "<box><size>0.36 0.22 0.18</size></box>"
    else:
        geometry = "<box><size>0.40 0.40 0.36</size></box>"

    return f"""
<sdf version="1.10">
  <model name="{model_name}">
    <static>false</static>
    <self_collide>false</self_collide>
    <link name="body">
      <gravity>false</gravity>
      <kinematic>true</kinematic>
      <inertial><mass>0.2</mass></inertial>
      <visual name="amr_base">
        <pose>0 0 -0.10 0 0 0</pose>
        <geometry><box><size>0.50 0.34 0.12</size></box></geometry>
        <material>
          <ambient>0.10 0.12 0.14 1</ambient>
          <diffuse>0.14 0.16 0.18 1</diffuse>
          <specular>0.25 0.25 0.25 1</specular>
        </material>
      </visual>
      <visual name="front_sensor">
        <pose>0.27 0 0.00 0 1.5708 0</pose>
        <geometry><cylinder><radius>0.055</radius><length>0.035</length></cylinder></geometry>
        <material>
          <ambient>0.02 0.54 0.62 1</ambient>
          <diffuse>0.02 0.74 0.82 1</diffuse>
          <emissive>0.0 0.15 0.18 1</emissive>
        </material>
      </visual>
      <visual name="left_wheel">
        <pose>0 -0.205 -0.12 1.5708 0 0</pose>
        <geometry><cylinder><radius>0.07</radius><length>0.045</length></cylinder></geometry>
        <material><ambient>0.02 0.02 0.025 1</ambient><diffuse>0.02 0.02 0.025 1</diffuse></material>
      </visual>
      <visual name="right_wheel">
        <pose>0 0.205 -0.12 1.5708 0 0</pose>
        <geometry><cylinder><radius>0.07</radius><length>0.045</length></cylinder></geometry>
        <material><ambient>0.02 0.02 0.025 1</ambient><diffuse>0.02 0.02 0.025 1</diffuse></material>
      </visual>
      <visual name="front_bumper">
        <pose>0.285 0 -0.075 0 0 0</pose>
        <geometry><box><size>0.035 0.38 0.055</size></box></geometry>
        <material><ambient>0.035 0.04 0.045 1</ambient><diffuse>0.045 0.05 0.055 1</diffuse></material>
      </visual>
      <visual name="rear_bumper">
        <pose>-0.285 0 -0.075 0 0 0</pose>
        <geometry><box><size>0.035 0.38 0.055</size></box></geometry>
        <material><ambient>0.035 0.04 0.045 1</ambient><diffuse>0.045 0.05 0.055 1</diffuse></material>
      </visual>
      <visual name="left_wheel_hub">
        <pose>0 -0.232 -0.12 1.5708 0 0</pose>
        <geometry><cylinder><radius>0.035</radius><length>0.012</length></cylinder></geometry>
        <material><ambient>0.36 0.38 0.40 1</ambient><diffuse>0.46 0.48 0.50 1</diffuse></material>
      </visual>
      <visual name="right_wheel_hub">
        <pose>0 0.232 -0.12 1.5708 0 0</pose>
        <geometry><cylinder><radius>0.035</radius><length>0.012</length></cylinder></geometry>
        <material><ambient>0.36 0.38 0.40 1</ambient><diffuse>0.46 0.48 0.50 1</diffuse></material>
      </visual>
      <visual name="cargo_tray">
        <pose>0 0 0.015 0 0 0</pose>
        <geometry><box><size>0.44 0.32 0.035</size></box></geometry>
        <material><ambient>0.38 0.39 0.38 1</ambient><diffuse>0.48 0.49 0.48 1</diffuse><specular>0.18 0.18 0.18 1</specular></material>
      </visual>
      <visual name="cargo_left_clamp">
        <pose>0 -0.18 0.105 0 0 0</pose>
        <geometry><box><size>0.34 0.035 0.11</size></box></geometry>
        <material><ambient>0.10 0.10 0.09 1</ambient><diffuse>0.14 0.14 0.13 1</diffuse></material>
      </visual>
      <visual name="cargo_right_clamp">
        <pose>0 0.18 0.105 0 0 0</pose>
        <geometry><box><size>0.34 0.035 0.11</size></box></geometry>
        <material><ambient>0.10 0.10 0.09 1</ambient><diffuse>0.14 0.14 0.13 1</diffuse></material>
      </visual>
      <visual name="front_marker_left">
        <pose>0.305 -0.11 -0.035 0 1.5708 0</pose>
        <geometry><cylinder><radius>0.018</radius><length>0.012</length></cylinder></geometry>
        <material><ambient>0.95 0.62 0.05 1</ambient><diffuse>1.00 0.72 0.08 1</diffuse><emissive>0.12 0.07 0.0 1</emissive></material>
      </visual>
      <visual name="front_marker_right">
        <pose>0.305 0.11 -0.035 0 1.5708 0</pose>
        <geometry><cylinder><radius>0.018</radius><length>0.012</length></cylinder></geometry>
        <material><ambient>0.95 0.62 0.05 1</ambient><diffuse>1.00 0.72 0.08 1</diffuse><emissive>0.12 0.07 0.0 1</emissive></material>
      </visual>
      <visual name="cargo">
        <pose>0 0 0.09 0 0 0</pose>
        <geometry>{geometry}</geometry>
        <material>
          <ambient>{color}</ambient>
          <diffuse>{color}</diffuse>
          <specular>0.18 0.18 0.18 1</specular>
        </material>
      </visual>
    </link>
  </model>
</sdf>
""".strip()


def status_light_sdf(model_name: str, state: str) -> str:
    color = rgba(STATUS_COLORS.get(state, STATUS_COLORS["idle"]))
    return f"""
<sdf version="1.10">
  <model name="{model_name}">
    <static>true</static>
    <link name="body">
      <visual name="mount_pole">
        <pose>0 0 -0.22 0 0 0</pose>
        <geometry><cylinder><radius>0.025</radius><length>0.38</length></cylinder></geometry>
        <material>
          <ambient>0.08 0.09 0.10 1</ambient>
          <diffuse>0.08 0.09 0.10 1</diffuse>
        </material>
      </visual>
      <visual name="beacon_housing">
        <pose>0 0 0 0 0 0</pose>
        <geometry><box><size>0.26 0.18 0.14</size></box></geometry>
        <material>
          <ambient>0.03 0.035 0.04 1</ambient>
          <diffuse>0.04 0.045 0.05 1</diffuse>
          <specular>0.2 0.2 0.2 1</specular>
        </material>
      </visual>
      <visual name="beacon_lens">
        <pose>0 0 0.018 0 0 0</pose>
        <geometry><box><size>0.18 0.11 0.08</size></box></geometry>
        <material>
          <ambient>{color}</ambient>
          <diffuse>{color}</diffuse>
          <emissive>{color}</emissive>
        </material>
      </visual>
    </link>
  </model>
</sdf>
""".strip()


def route_arrow_sdf(model_name: str) -> str:
    color = "1.000 0.560 0.030 1.000"
    return f"""
<sdf version="1.10">
  <model name="{model_name}">
    <static>true</static>
    <link name="body">
      <visual name="shaft">
        <pose>-0.055 0 0 0 0 0</pose>
        <geometry><box><size>0.20 0.055 0.035</size></box></geometry>
        <material>
          <ambient>{color}</ambient>
          <diffuse>{color}</diffuse>
          <emissive>{color}</emissive>
        </material>
      </visual>
      <visual name="head">
        <pose>0.085 0 0 0 1.5708 0</pose>
        <geometry><cone><radius>0.075</radius><length>0.12</length></cone></geometry>
        <material>
          <ambient>{color}</ambient>
          <diffuse>{color}</diffuse>
          <emissive>{color}</emissive>
        </material>
      </visual>
    </link>
  </model>
</sdf>
""".strip()


class GazeboSync:
    def __init__(
        self,
        *,
        backend_url: str,
        world: str,
        interval: float,
        dry_run: bool,
        poll_interval: float = 0.16,
        status_interval: float = 0.35,
        publish_visuals: bool = False,
    ) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.world = world
        self.interval = interval
        self.poll_interval = poll_interval
        self.status_interval = status_interval
        self.dry_run = dry_run
        self.spawned_products: set[str] = set()
        self.product_poses: dict[str, Pose] = {}
        self.product_locations: dict[str, str] = {}
        self.product_destinations: dict[str, str] = {}
        self.product_pending_destinations: dict[str, list[str]] = {}
        self.product_paths: dict[str, list[Pose]] = {}
        self.product_path_routes: dict[str, str] = {}
        self.product_last_route: dict[str, str] = {}
        self.product_waypoint_index: dict[str, int] = {}
        self.product_path_start: dict[str, float] = {}
        self.product_path_duration: dict[str, float] = {}
        self.product_motion_speed: dict[str, float] = {}
        self.product_last_motion: dict[str, float] = {}
        self.product_dwell_until: dict[str, float] = {}
        self.product_dwell_location: dict[str, str] = {}
        self.product_dwelled_destination: dict[str, str] = {}
        self.product_arrival_settle_until: dict[str, float] = {}
        self.product_arrival_settle_location: dict[str, str] = {}
        self.product_arrival_settled_destination: dict[str, str] = {}
        self.product_ids_by_model: dict[str, str] = {}
        self.status_states: dict[str, str] = {}
        self.active_arrow_models: set[str] = set()
        self.active_route_until: dict[str, float] = {}
        self.active_route_location_until: dict[str, float] = {}
        self.done_until: dict[str, float] = {}
        self.seen_events: set[str] = set()
        self.last_tick: int | None = None
        self.latest_state: dict[str, Any] | None = None
        self.last_visual_publish = 0.0
        self.publish_visuals_enabled = publish_visuals
        self.command_latency_ema_s = 0.0

    @property
    def create_service(self) -> str:
        return f"/world/{self.world}/create"

    @property
    def remove_service(self) -> str:
        return f"/world/{self.world}/remove"

    @property
    def set_pose_service(self) -> str:
        return f"/world/{self.world}/set_pose"

    def run_command(
        self, args: list[str], *, check: bool = False
    ) -> subprocess.CompletedProcess[str]:
        if self.dry_run:
            print("DRY:", " ".join(args))
            return subprocess.CompletedProcess(args, 0, "", "")
        started = time.monotonic()
        result = subprocess.run(args, text=True, capture_output=True, check=False)
        elapsed = time.monotonic() - started
        self.command_latency_ema_s = (
            elapsed
            if self.command_latency_ema_s == 0.0
            else self.command_latency_ema_s * 0.8 + elapsed * 0.2
        )
        if check and result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"Gazebo command failed: {' '.join(args)}\n{message}")
        return result

    def wait_for_services(self, timeout_s: float = 90.0) -> None:
        if self.dry_run:
            return
        deadline = time.monotonic() + timeout_s
        required = {self.create_service, self.remove_service, self.set_pose_service}
        while time.monotonic() < deadline:
            result = subprocess.run(
                ["gz", "service", "-l"], text=True, capture_output=True, check=False
            )
            services = set(result.stdout.splitlines())
            if required.issubset(services):
                print(f"Connected to Gazebo world '{self.world}'.")
                return
            time.sleep(0.8)
        raise RuntimeError(
            "Gazebo services are not available. Start the world first with: bash scripts/run_gazebo.sh"
        )

    def create_model(self, name: str, sdf: str, pose: Pose) -> None:
        request = (
            f'name: "{name}" '
            f'sdf: "{text_format_string(sdf)}" '
            f"pose {{ position {{ x: {pose.x:.4f} y: {pose.y:.4f} z: {pose.z:.4f} }} orientation {{ w: 1 }} }} "
            "allow_renaming: false"
        )
        self.run_command(
            [
                "gz",
                "service",
                "-s",
                self.create_service,
                "--reqtype",
                "gz.msgs.EntityFactory",
                "--reptype",
                "gz.msgs.Boolean",
                "--timeout",
                "900",
                "--req",
                request,
            ]
        )

    def remove_model(self, name: str) -> None:
        self.run_command(
            [
                "gz",
                "service",
                "-s",
                self.remove_service,
                "--reqtype",
                "gz.msgs.Entity",
                "--reptype",
                "gz.msgs.Boolean",
                "--timeout",
                "500",
                "--req",
                f'name: "{name}" type: MODEL',
            ]
        )

    def set_pose(self, name: str, pose: Pose) -> None:
        half_yaw = pose.yaw / 2.0
        self.run_command(
            [
                "gz",
                "service",
                "-s",
                self.set_pose_service,
                "--reqtype",
                "gz.msgs.Pose",
                "--reptype",
                "gz.msgs.Boolean",
                "--timeout",
                "500",
                "--req",
                (
                    f'name: "{name}" '
                    f"position {{ x: {pose.x:.4f} y: {pose.y:.4f} z: {pose.z:.4f} }} "
                    f"orientation {{ z: {math.sin(half_yaw):.5f} w: {math.cos(half_yaw):.5f} }}"
                ),
            ]
        )

    def product_model_name(self, product_id: str) -> str:
        return f"rf_product_{sanitize(product_id)}"

    def status_model_name(self, machine_id: str) -> str:
        return f"rf_status_{sanitize(machine_id)}"

    def location_key(self, product: dict[str, Any]) -> str:
        if product.get("status") == "paused":
            return "recovery_buffer"
        if product.get("status") == "processing" and product.get("assigned_station"):
            return str(product["assigned_station"])
        return str(product.get("current_location") or "processing_buffer")

    def product_target(self, product: dict[str, Any], index: int) -> Pose:
        location = self.location_key(product)
        return self.target_for_location(product["product_id"], location)

    def target_for_location(self, product_id: str, location: str) -> Pose:
        x, y, z = LAYOUT.get(location, LAYOUT["processing_buffer"])
        lane = ((stable_hash(f"{product_id}-lane") % 3) - 1) * 0.025
        return Pose(x, y + lane, z)

    def product_start_pose(self, product: dict[str, Any]) -> Pose:
        lane = ((stable_hash(f"{product['product_id']}-lane") % 3) - 1) * 0.025
        x, y, z = LAYOUT["input_queue"]
        return Pose(x, y + lane, z)

    def visual_targets_for_product(
        self, product: dict[str, Any], current_location: str
    ) -> list[str]:
        route = [
            str(location)
            for location in product.get("route", [])
            if isinstance(location, str) and location in LAYOUT
        ]
        target = self.location_key(product)
        if target not in route:
            route.append(target)
        try:
            start_index = len(route) - 1 - route[::-1].index(current_location)
            targets = route[start_index + 1 :]
        except ValueError:
            targets = [target]
        deduped: list[str] = []
        for location in targets:
            if location == current_location:
                continue
            if deduped and deduped[-1] == location:
                continue
            deduped.append(location)
        return deduped

    def merge_pending_destinations(self, model_name: str, destinations: list[str]) -> None:
        if not destinations:
            return
        queue = self.product_pending_destinations.setdefault(model_name, [])
        for destination in destinations:
            if queue and queue[-1] == destination:
                continue
            if destination in queue:
                continue
            queue.append(destination)

    def next_pending_destination(self, model_name: str) -> str | None:
        queue = self.product_pending_destinations.get(model_name)
        if not queue:
            self.product_pending_destinations.pop(model_name, None)
            return None
        destination = queue.pop(0)
        if not queue:
            self.product_pending_destinations.pop(model_name, None)
        return destination

    def transition_path(
        self, from_location: str, to_location: str, current: Pose, target: Pose
    ) -> list[Pose]:
        routed = ROUTES.get((from_location, to_location))
        if routed:
            points = smooth_path([pose_from_tuple(point) for point in routed])
        else:
            points = smooth_path([current, target], iterations=0)
        points[0] = current
        points[-1] = target
        return points

    def route_name(self, from_location: str, to_location: str) -> str:
        return ROUTE_NAMES.get(
            (from_location, to_location), f"{from_location}_to_{to_location}"
        )

    def transition_duration(self, path: list[Pose], state: dict[str, Any]) -> float:
        sync = state.get("visual_sync", {})
        speed = max(0.25, float(state.get("simulation_speed") or 1.0))
        min_s = (
            float(sync.get("gazebo_min_transition_ms", sync.get("min_transition_ms", 650)))
            / 1000.0
            / speed
        )
        max_s = (
            float(sync.get("gazebo_max_transition_ms", sync.get("max_transition_ms", 1500)))
            / 1000.0
            / speed
        )
        meters_per_second = float(sync.get("gazebo_meters_per_second", 1.85)) * speed
        latency_multiplier = float(sync.get("gazebo_latency_multiplier", 4.0))
        base = path_length(path) / max(0.1, meters_per_second)
        latency_padding = min(0.15, self.command_latency_ema_s * latency_multiplier)
        return max(min_s, min(max_s, base + latency_padding))

    def clear_products(self) -> None:
        for model_name in list(self.spawned_products):
            self.remove_model(model_name)
        for model_name in list(self.active_arrow_models):
            self.remove_model(model_name)
        for indicator_id in list(self.status_states):
            self.remove_model(self.status_model_name(indicator_id))
        self.spawned_products.clear()
        self.active_arrow_models.clear()
        self.status_states.clear()
        self.product_poses.clear()
        self.product_locations.clear()
        self.product_destinations.clear()
        self.product_pending_destinations.clear()
        self.product_paths.clear()
        self.product_path_routes.clear()
        self.product_last_route.clear()
        self.product_waypoint_index.clear()
        self.product_path_start.clear()
        self.product_path_duration.clear()
        self.product_motion_speed.clear()
        self.product_last_motion.clear()
        self.product_dwell_until.clear()
        self.product_dwell_location.clear()
        self.product_dwelled_destination.clear()
        self.product_arrival_settle_until.clear()
        self.product_arrival_settle_location.clear()
        self.product_arrival_settled_destination.clear()
        self.product_ids_by_model.clear()
        self.active_route_until.clear()
        self.active_route_location_until.clear()

    def path_completed(self, model_name: str, tolerance: float = 0.08) -> bool:
        path = self.product_paths.get(model_name)
        pose = self.product_poses.get(model_name)
        if not path or pose is None:
            return True
        return (
            self.product_waypoint_index.get(model_name, 0) >= len(path) - 1
            and pose_distance(pose, path[-1]) <= tolerance
        )

    def set_product_path(
        self,
        model_name: str,
        path: list[Pose],
        state: dict[str, Any],
        *,
        destination: str,
        route_name: str = "",
    ) -> None:
        duration = self.transition_duration(path, state)
        self.product_paths[model_name] = path
        previous_route = self.product_last_route.get(model_name)
        if previous_route and previous_route != route_name:
            self.active_route_until.pop(previous_route, None)
        self.product_path_routes[model_name] = route_name
        self.product_last_route[model_name] = route_name
        self.product_waypoint_index[model_name] = 1 if len(path) > 1 else 0
        self.product_path_start[model_name] = time.monotonic()
        self.product_path_duration[model_name] = duration
        sync = state.get("visual_sync", {})
        speed = max(0.25, float(state.get("simulation_speed") or 1.0))
        robot_speed = float(sync.get("gazebo_robot_meters_per_second", 1.15)) * speed
        self.product_motion_speed[model_name] = max(0.35, robot_speed)
        self.product_last_motion[model_name] = time.monotonic()
        self.product_destinations[model_name] = destination
        hold_until = time.monotonic() + max(duration, 0.85)
        if route_name:
            self.active_route_until[route_name] = hold_until
        self.active_route_location_until[destination] = hold_until
        if self.product_dwelled_destination.get(model_name) != destination:
            self.product_dwelled_destination.pop(model_name, None)

    def sync_product_targets(self, state: dict[str, Any]) -> None:
        self.latest_state = state
        running = bool(state.get("running", True))
        tick = int(state.get("tick", 0))
        if self.last_tick is not None and tick < self.last_tick:
            self.clear_products()
        self.last_tick = tick

        products = state.get("products", [])
        live_model_names = set()
        for index, product in enumerate(products):
            model_name = self.product_model_name(product["product_id"])
            self.product_ids_by_model[model_name] = product["product_id"]
            live_model_names.add(model_name)
            next_location = self.location_key(product)
            target = self.product_target(product, index)
            if model_name not in self.spawned_products:
                start_pose = self.product_start_pose(product)
                self.create_model(
                    model_name,
                    product_sdf(model_name, product.get("product_type", "")),
                    start_pose,
                )
                self.spawned_products.add(model_name)
                self.product_poses[model_name] = start_pose
                self.product_locations[model_name] = "input_queue"
                self.product_destinations[model_name] = "input_queue"
                if not running:
                    continue
                targets = self.visual_targets_for_product(product, "input_queue")
                next_location = targets[0] if targets else next_location
                self.merge_pending_destinations(model_name, targets[1:])
                target = self.target_for_location(product["product_id"], next_location)
                self.set_product_path(
                    model_name,
                    self.transition_path("input_queue", next_location, start_pose, target),
                    state,
                    destination=next_location,
                    route_name=self.route_name("input_queue", next_location),
                )
            current = self.product_poses.get(model_name, target)
            active_destination = self.product_destinations.get(
                model_name, self.product_locations.get(model_name, "input_queue")
            )
            if not running:
                continue
            if active_destination != next_location:
                current_location = self.product_locations.get(model_name, active_destination)
                targets = self.visual_targets_for_product(product, current_location)
                if active_destination in targets:
                    targets = targets[targets.index(active_destination) + 1 :]
                self.merge_pending_destinations(model_name, targets)
                if (
                    model_name in self.product_dwell_until
                    and next_location != "recovery_buffer"
                ):
                    continue
                should_reroute_now = next_location == "recovery_buffer" or self.path_completed(
                    model_name
                )
                if not should_reroute_now:
                    continue
                queued_location = self.next_pending_destination(model_name)
                if queued_location:
                    next_location = queued_location
                    target = self.target_for_location(product["product_id"], next_location)
                path = self.transition_path(
                    self.product_locations.get(model_name, active_destination),
                    next_location,
                    current,
                    target,
                )
                from_location = self.product_locations.get(model_name, active_destination)
                self.product_pending_destinations.pop(model_name, None)
                self.set_product_path(
                    model_name,
                    path,
                    state,
                    destination=next_location,
                    route_name=self.route_name(from_location, next_location),
                )

        for model_name in list(self.spawned_products - live_model_names):
            self.remove_model(model_name)
            self.spawned_products.remove(model_name)
            self.product_poses.pop(model_name, None)
            self.product_locations.pop(model_name, None)
            self.product_destinations.pop(model_name, None)
            self.product_pending_destinations.pop(model_name, None)
            self.product_paths.pop(model_name, None)
            self.product_path_routes.pop(model_name, None)
            self.product_last_route.pop(model_name, None)
            self.product_waypoint_index.pop(model_name, None)
            self.product_path_start.pop(model_name, None)
            self.product_path_duration.pop(model_name, None)
            self.product_motion_speed.pop(model_name, None)
            self.product_last_motion.pop(model_name, None)
            self.product_dwell_until.pop(model_name, None)
            self.product_dwell_location.pop(model_name, None)
            self.product_dwelled_destination.pop(model_name, None)
            self.product_arrival_settle_until.pop(model_name, None)
            self.product_arrival_settle_location.pop(model_name, None)
            self.product_arrival_settled_destination.pop(model_name, None)
            self.product_ids_by_model.pop(model_name, None)

    def advance_products(self) -> None:
        now = time.monotonic()
        running = bool((self.latest_state or {}).get("running", True))
        for model_name in list(self.spawned_products):
            current = self.product_poses.get(model_name)
            if current is None:
                continue
            dwell_until = self.product_dwell_until.get(model_name)
            if dwell_until is not None and (not running or now < dwell_until):
                self.product_last_motion[model_name] = now
                self.set_pose(model_name, current)
                continue
            if dwell_until is not None and now >= dwell_until:
                location = self.product_dwell_location.pop(model_name, "")
                self.product_dwell_until.pop(model_name, None)
                if location:
                    self.product_dwelled_destination[model_name] = location
                    self.done_until[location] = now + DONE_INDICATION_SECONDS
            settle_until = self.product_arrival_settle_until.get(model_name)
            if settle_until is not None and (not running or now < settle_until):
                self.product_last_motion[model_name] = now
                self.set_pose(model_name, current)
                continue
            if settle_until is not None and now >= settle_until:
                location = self.product_arrival_settle_location.pop(model_name, "")
                self.product_arrival_settle_until.pop(model_name, None)
                if location:
                    self.product_arrival_settled_destination[model_name] = location
            path = self.product_paths.get(model_name, [current])
            if not self.path_completed(model_name):
                transport_until = self.product_path_start.get(
                    model_name, now
                ) + self.product_path_duration.get(model_name, 0.0)
                if now < transport_until:
                    self.product_last_motion[model_name] = now
                    self.set_pose(model_name, current)
                    continue
                next_pose = path[-1]
                self.product_waypoint_index[model_name] = max(0, len(path) - 1)
                self.product_last_motion[model_name] = now
                self.product_poses[model_name] = next_pose
                self.set_pose(model_name, next_pose)
            else:
                next_pose = current
            if self.path_completed(model_name):
                reached = self.product_destinations.get(model_name)
                if reached:
                    self.product_locations[model_name] = reached
                    if (
                        reached in {"accepted_output", "reject_output"}
                        and self.product_dwelled_destination.get(model_name) != reached
                    ):
                        self.product_dwelled_destination[model_name] = reached
                        self.done_until[reached] = now + DONE_INDICATION_SECONDS
                if not running:
                    continue
                speed = max(
                    0.25, float((self.latest_state or {}).get("simulation_speed") or 1.0)
                )
                if (
                    reached in SERVICE_DWELL_SECONDS
                    and self.product_dwelled_destination.get(model_name) != reached
                ):
                    if self.product_arrival_settled_destination.get(model_name) != reached:
                        self.product_arrival_settle_location[model_name] = reached
                        self.product_arrival_settle_until[model_name] = (
                            now + SERVICE_DWELL_SECONDS["arrival_settle"] / speed
                        )
                        continue
                    self.product_dwell_location[model_name] = reached
                    self.product_dwell_until[model_name] = (
                        now + SERVICE_DWELL_SECONDS[reached] / speed
                    )
                    continue
                pending = self.next_pending_destination(model_name)
                if pending and reached and pending != reached:
                    product_id = self.product_ids_by_model.get(model_name, model_name)
                    target = self.target_for_location(product_id, pending)
                    self.set_product_path(
                        model_name,
                        self.transition_path(reached, pending, next_pose, target),
                        self.latest_state or {},
                        destination=pending,
                        route_name=self.route_name(reached, pending),
                    )

    def sync_products(self, state: dict[str, Any]) -> None:
        self.sync_product_targets(state)
        self.advance_products()

    def publish_visuals(self) -> None:
        if not self.publish_visuals_enabled:
            return
        now = time.monotonic()
        if now - self.last_visual_publish < 0.08:
            return
        self.last_visual_publish = now
        products: dict[str, dict[str, float]] = {}
        product_locations: dict[str, str] = {}
        for model_name, pose in self.product_poses.items():
            product_id = self.product_ids_by_model.get(model_name)
            if not product_id:
                continue
            products[product_id] = {
                "x": pose.x,
                "y": pose.y,
                "z": pose.z,
                "yaw": pose.yaw,
            }
            if model_name in self.product_dwell_location:
                product_locations[product_id] = self.product_dwell_location[model_name]
            elif model_name in self.product_arrival_settle_location:
                product_locations[product_id] = self.product_arrival_settle_location[model_name]
            else:
                product_locations[product_id] = self.product_locations.get(model_name, "")
        try:
            processing_locations = set(self.product_dwell_location.values()) | set(
                self.product_arrival_settle_location.values()
            )
            post_json(
                f"{self.backend_url}/api/gazebo/visuals",
                {
                    "products": products,
                    "product_locations": product_locations,
                    "processing_locations": sorted(processing_locations),
                    "done_locations": sorted(
                        location for location, until in self.done_until.items() if until > now
                    ),
                    "active_routes": sorted(self.active_transport_routes()),
                    "active_route_locations": sorted(self.active_transport_locations()),
                    "updated_at": time.time(),
                },
            )
        except (urllib.error.URLError, TimeoutError):
            return

    def active_transport_routes(self) -> set[str]:
        now = time.monotonic()
        routes: set[str] = set()
        for model_name in self.spawned_products:
            if self.path_completed(model_name):
                continue
            transport_until = self.product_path_start.get(
                model_name, now
            ) + self.product_path_duration.get(model_name, 0.0)
            if now >= transport_until:
                continue
            route = self.product_path_routes.get(model_name, "")
            if route:
                routes.add(route)
                self.active_route_until[route] = now + 0.85
        for route, until in list(self.active_route_until.items()):
            if until > now:
                routes.add(route)
            else:
                self.active_route_until.pop(route, None)
        return routes

    def active_transport_locations(self) -> set[str]:
        now = time.monotonic()
        locations: set[str] = set()
        for model_name in self.spawned_products:
            if self.path_completed(model_name):
                continue
            transport_until = self.product_path_start.get(
                model_name, now
            ) + self.product_path_duration.get(model_name, 0.0)
            if now >= transport_until:
                continue
            destination = self.product_destinations.get(model_name)
            if destination:
                locations.add(destination)
                self.active_route_location_until[destination] = now + 0.85
        for location, until in list(self.active_route_location_until.items()):
            if until > now:
                locations.add(location)
            else:
                self.active_route_location_until.pop(location, None)
        return locations

    def route_arrow_model_name(self, route: str, index: int) -> str:
        return f"rf_route_arrow_{sanitize(route)}_{index}"

    def sync_transport_arrows(self) -> None:
        active_routes = self.active_transport_routes()
        desired_models: set[str] = set()
        for route in active_routes:
            for index, pose in enumerate(ROUTE_ARROWS.get(route, [])):
                model_name = self.route_arrow_model_name(route, index)
                desired_models.add(model_name)
                if model_name not in self.active_arrow_models:
                    self.create_model(model_name, route_arrow_sdf(model_name), pose)
                    self.active_arrow_models.add(model_name)
        for model_name in list(self.active_arrow_models - desired_models):
            self.remove_model(model_name)
            self.active_arrow_models.remove(model_name)

    def process_events(self, state: dict[str, Any]) -> None:
        for event in state.get("events", []):
            event_id = event.get("event_id")
            if not event_id or event_id in self.seen_events:
                continue
            self.seen_events.add(event_id)

    def indicator_status(
        self,
        indicator_id: str,
        state: dict[str, Any],
        machines: dict[str, dict[str, Any]],
        location_counts: dict[str, int],
        processing_locations: set[str],
        moving_products: int,
    ) -> str:
        now = time.monotonic()
        machine = machines.get(indicator_id)
        if machine and machine.get("state") in {"fault", "emergency_stop"}:
            return "fault"
        if indicator_id in processing_locations:
            return "processing"
        if self.done_until.get(indicator_id, 0.0) > now:
            return "done"
        if indicator_id in {
            "processing_buffer",
            "quality_buffer",
            "recovery_buffer",
        } and location_counts.get(indicator_id, 0):
            return "processing"
        if indicator_id == "input_queue" and location_counts.get(indicator_id, 0):
            return "processing"
        if indicator_id == "conveyor_main" and moving_products:
            return "processing"
        return "idle"

    def sync_status_lights(self, state: dict[str, Any], *, max_updates: int = 1) -> None:
        self.process_events(state)
        machines = {machine["machine_id"]: machine for machine in state.get("machines", [])}
        location_counts: dict[str, int] = {}
        processing_locations = set(self.product_dwell_location.values()) | set(
            self.product_arrival_settle_location.values()
        )
        moving_products = 0
        for model_name in self.spawned_products:
            if model_name in self.product_dwell_location:
                location = self.product_dwell_location[model_name]
            elif self.path_completed(model_name):
                location = self.product_locations.get(model_name, "")
            else:
                moving_products += 1
                location = ""
            if not location:
                continue
            location_counts[location] = location_counts.get(location, 0) + 1

        pending: list[tuple[str, str]] = []
        for indicator_id in STATUS_LIGHTS:
            status = self.indicator_status(
                indicator_id,
                state,
                machines,
                location_counts,
                processing_locations,
                moving_products,
            )
            if self.status_states.get(indicator_id) == status:
                continue
            if status == "idle" and indicator_id not in self.status_states:
                continue
            pending.append((indicator_id, status))

        priority = {"fault": 0, "emergency_stop": 0, "processing": 1, "done": 1, "idle": 2}
        pending.sort(key=lambda item: priority.get(item[1], 2))

        for indicator_id, status in pending[:max_updates]:
            model_name = self.status_model_name(indicator_id)
            if status == "idle":
                self.remove_model(model_name)
                self.status_states.pop(indicator_id, None)
                continue
            if indicator_id in self.status_states:
                self.remove_model(model_name)
            pose = Pose(*STATUS_LIGHTS[indicator_id])
            self.create_model(model_name, status_light_sdf(model_name, status), pose)
            self.status_states[indicator_id] = status

    def step(self) -> None:
        state = fetch_json(f"{self.backend_url}/api/status")
        self.sync_product_targets(state)
        self.advance_products()
        self.sync_transport_arrows()
        self.publish_visuals()

    def loop(self, *, once: bool) -> None:
        self.wait_for_services()
        next_poll = 0.0
        while True:
            started = time.monotonic()
            try:
                if once:
                    self.step()
                    return
                now = time.monotonic()
                if self.latest_state is None or now >= next_poll:
                    self.sync_product_targets(fetch_json(f"{self.backend_url}/api/status"))
                    next_poll = now + self.poll_interval
                self.advance_products()
                self.sync_transport_arrows()
                self.publish_visuals()
            except (urllib.error.URLError, TimeoutError) as exc:
                print(f"Backend not reachable at {self.backend_url}: {exc}")
            except RuntimeError as exc:
                print(exc)
            elapsed = time.monotonic() - started
            time.sleep(max(0.02, self.interval - elapsed))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync ReConFactory FastAPI state to Gazebo.")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--world", default="reconfactory_world")
    parser.add_argument("--interval", type=float, default=0.03)
    parser.add_argument("--poll-interval", type=float, default=0.16)
    parser.add_argument("--status-interval", type=float, default=0.35)
    parser.add_argument("--publish-visuals", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.dry_run and shutil.which("gz") is None:
        raise SystemExit("Gazebo 'gz' command was not found. Source ROS/Gazebo first.")
    sync = GazeboSync(
        backend_url=args.backend_url,
        world=args.world,
        interval=max(0.02, args.interval),
        poll_interval=max(0.03, args.poll_interval),
        status_interval=max(0.15, args.status_interval),
        publish_visuals=args.publish_visuals,
        dry_run=args.dry_run,
    )
    sync.loop(once=args.once)


if __name__ == "__main__":
    main()
