"""Generate the AMR collision overlay and static map from the existing world."""

from __future__ import annotations

import copy
import math
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "ros2_ws/src/reconfactory_amr/maps"
# Conservative machine footprints matching the existing zone/table geometry.
FOOTPRINTS = {
    "input_station": (0.8, 0.65),
    "vision_camera_station": (0.95, 0.72),
    "processing_station_a": (1.2, 1.1),
    "processing_station_b": (1.2, 1.1),
    "quality_control_station": (1.1, 0.8),
    "accepted_output_bin": (0.88, 0.78),
    "reject_output_bin": (0.88, 0.78),
}


def pose(element):
    return [float(x) for x in (element.findtext("pose") or "0 0 0 0 0 0").split()]


def compose(a, b):
    c, s = math.cos(a[5]), math.sin(a[5])
    return [
        a[0] + c * b[0] - s * b[1],
        a[1] + s * b[0] + c * b[1],
        a[2] + b[2],
        0,
        0,
        a[5] + b[5],
    ]


def layout_config():
    return yaml.safe_load((MAP_DIR.parent / "config/factory_layout.yaml").read_text())


def shift(element, offset):
    values = pose(element)
    values[0] += offset[0]
    values[1] += offset[1]
    element.find("pose").text = " ".join(map(str, values))


def arrange_workcells(world):
    config = layout_config()
    offsets = {}
    for name, xy in config["stations"].items():
        model = world.find(f"model[@name='{name}']")
        old = pose(model)
        offsets[name] = (xy[0] - old[0], xy[1] - old[1])
        shift(model, offsets[name])

    # Robot transport replaces connecting conveyors, not the station surfaces.
    for name in (
        "conveyor_input_to_vision",
        "junction_to_station_a",
        "junction_to_station_b",
        "station_a_to_quality",
        "station_b_to_quality",
        "quality_to_outputs",
    ):
        world.remove(world.find(f"model[@name='{name}']"))
    groups = {
        "processing_station_a": ("station_a_", "drill_head", "cell_a_zone"),
        "processing_station_b": ("station_b_", "polish_wheel", "cell_b_zone"),
        "vision_camera_station": ("vision_",),
        "quality_control_station": ("quality_",),
        "input_station": ("input_zone",),
    }
    for model_name in (
        "factory_shell_and_safety_details",
        "conveyor_rollers_supports_and_machine_panels",
        "factory_realism_detail_pack",
    ):
        link = world.find(f"model[@name='{model_name}']/link")
        for visual in list(link.findall("visual")):
            name = visual.get("name")
            if (
                name.startswith(
                    (
                        "main_roller_",
                        "out_roller_",
                        "leg_",
                        "a_feed_",
                        "b_feed_",
                        "a_return_",
                        "b_return_",
                        "input_support_",
                        "output_support_",
                        "input_left_guard",
                        "input_right_guard",
                        "output_left_guard",
                        "output_right_guard",
                        "reject_diverter_",
                    )
                )
                or "photoeye" in name
            ):
                link.remove(visual)
                continue
            for station, prefixes in groups.items():
                if name.startswith(prefixes):
                    shift(visual, offsets[station])
                    break
            if name.startswith("plc_"):
                shift(visual, config["service"]["plc_offset"])
            elif name.startswith(
                (
                    "front_safety_fence_",
                    "fence_post_",
                    "estop_",
                    "operator_walkway",
                    "walkway_center",
                )
            ):
                shift(visual, config["service"]["fence_offset"])
            elif name.startswith("maintenance_cart"):
                shift(visual, config["service"]["cart_offset"])


def prepare_world():
    tree = ET.parse(ROOT / "gazebo_fallback/worlds/reconfactory.world.sdf")
    world = tree.getroot().find("world")
    arrange_workcells(world)
    config = layout_config()["floor"]
    cx, cy = config["center"]
    width, height = config["size"]
    floor = world.find("model[@name='factory_floor']")
    floor.find("pose").text = f"{cx} {cy} -0.03 0 0 0"
    for size in floor.findall("link/*/geometry/box/size"):
        size.text = f"{width} {height} 0.06"
    world.find("gui/camera/pose").text = "5 -10 9 0 0.7 0.85"
    shell = world.find("model[@name='factory_shell_and_safety_details']/link")
    for name, x, y, w, h in (
        ("right_wall", cx + width / 2, cy, 0.08, height),
        ("left_wall", cx - width / 2, cy, 0.08, height),
        ("back_wall", cx, cy + height / 2, width, 0.08),
    ):
        visual = shell.find(f"visual[@name='{name}']")
        visual.find("pose").text = f"{x} {y} 0.72 0 0 0"
        visual.find("geometry/box/size").text = f"{w} {h} 1.5"
    for name in ("back_wall", "left_wall", "right_wall"):
        visual = shell.find(f"visual[@name='{name}']")
        collision = ET.SubElement(shell, "collision", name=f"amr_{name}")
        collision.append(copy.deepcopy(visual.find("pose")))
        collision.append(copy.deepcopy(visual.find("geometry")))
    for model in world.findall("model"):
        if model.get("name") in FOOTPRINTS:
            w, h = FOOTPRINTS[model.get("name")]
            link = model.find("link")
            collision = ET.SubElement(link, "collision", name="amr_machine_footprint")
            ET.SubElement(collision, "pose").text = f"0 0 {0.25 - pose(model)[2]} 0 0 0"
            geometry = ET.SubElement(collision, "geometry")
            ET.SubElement(ET.SubElement(geometry, "box"), "size").text = f"{w} {h} 0.5"
    # Cabinets, conveyor guards and safety fences were previously visual-only.
    for model in world.findall("model"):
        if model.get("name") == "factory_floor":
            continue
        for link in model.findall("link"):
            for visual in link.findall("visual"):
                size = visual.findtext("geometry/box/size")
                if not size:
                    continue
                depth = float(size.split()[2])
                p = compose(compose(pose(model), pose(link)), pose(visual))
                if p[2] + depth / 2 <= 0.07 or p[2] - depth / 2 >= 0.75:
                    continue
                collision = ET.SubElement(
                    link, "collision", name=f"amr_visual_{visual.get('name')}"
                )
                if visual.find("pose") is not None:
                    collision.append(copy.deepcopy(visual.find("pose")))
                collision.append(copy.deepcopy(visual.find("geometry")))
    return tree


def obstacle_boxes(tree):
    boxes = []
    for model in tree.getroot().find("world").findall("model"):
        if model.get("name") == "factory_floor":
            continue
        for link in model.findall("link"):
            parent = compose(pose(model), pose(link))
            for collision in link.findall("collision"):
                size = collision.findtext("geometry/box/size")
                if size:
                    w, h, depth = map(float, size.split())
                    p = compose(parent, pose(collision))
                    if p[2] - depth / 2 < 0.75 and p[2] + depth / 2 > 0.07:
                        boxes.append((p[0], p[1], p[5], w, h))
    return boxes


def lidar_boxes(tree):
    robot = ET.parse(ROOT / "ros2_ws/src/reconfactory_amr/urdf/amr.urdf.xacro").getroot()
    height = sum(
        float(robot.find(f"joint[@name='{name}']/origin").get("xyz").split()[2])
        for name in ("base_joint", "laser_joint")
    )
    boxes = []
    for model in tree.getroot().find("world").findall("model"):
        for link in model.findall("link"):
            parent = compose(pose(model), pose(link))
            for visual in link.findall("visual"):
                size = visual.findtext("geometry/box/size")
                if not size:
                    continue
                w, h, depth = map(float, size.split())
                p = compose(parent, pose(visual))
                if p[2] - depth / 2 <= height <= p[2] + depth / 2:
                    boxes.append((p[0], p[1], p[5], w, h))
    return boxes


def occupied(x, y, boxes):
    for cx, cy, yaw, w, h in boxes:
        dx, dy = x - cx, y - cy
        if (
            abs(math.cos(yaw) * dx + math.sin(yaw) * dy) <= w / 2
            and abs(-math.sin(yaw) * dx + math.cos(yaw) * dy) <= h / 2
        ):
            return True
    return False


def main():
    tree = prepare_world()
    generated = ROOT / "data/amr"
    generated.mkdir(parents=True, exist_ok=True)
    tree.write(generated / "factory.world.sdf", encoding="utf-8", xml_declaration=True)
    config = layout_config()["floor"]
    resolution = config["resolution"]
    cx, cy = config["center"]
    w, h = config["size"]
    ox, oy = cx - w / 2 - 0.1, cy - h / 2 - 0.1
    width, height = round((w + 0.2) / resolution), round((h + 0.2) / resolution)
    boxes = obstacle_boxes(tree)
    visible = lidar_boxes(tree)
    pixels = bytearray()
    lidar_pixels = bytearray()
    for row in range(height):
        for col in range(width):
            x, y = ox + (col + 0.5) * resolution, oy + (height - row - 0.5) * resolution
            blocked = not (
                cx - w / 2 + 0.04 < x < cx + w / 2 - 0.04
                and cy - h / 2 + 0.04 < y < cy + h / 2 - 0.04
            ) or occupied(x, y, boxes)
            pixels.append(0 if blocked else 254)
            # AMCL must not match invisible safety envelopes or floor edges.
            lidar_pixels.append(0 if occupied(x, y, visible) else 254)
    MAP_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("reconfactory_map", "reconfactory_lidar_map"):
        (MAP_DIR / f"{name}.yaml").write_text(
            yaml.safe_dump(
                {
                    "image": f"{name}.pgm",
                    "mode": "trinary",
                    "resolution": resolution,
                    "origin": [ox, oy, 0.0],
                    "negate": 0,
                    "occupied_thresh": 0.65,
                    "free_thresh": 0.25,
                },
                sort_keys=False,
            )
        )
    (MAP_DIR / "reconfactory_map.pgm").write_bytes(
        f"P5\n{width} {height}\n255\n".encode() + pixels
    )
    (MAP_DIR / "reconfactory_lidar_map.pgm").write_bytes(
        f"P5\n{width} {height}\n255\n".encode() + lidar_pixels
    )
    print(
        f"Generated AMR world and {width}x{height} static map from {len(boxes)} collision boxes"
    )


if __name__ == "__main__":
    main()
