"""Configuration loading and defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import MachineConfig, ProductRecipe

DEFAULT_RECIPES: dict[str, ProductRecipe] = {
    "red_block": ProductRecipe(
        product_type="red_block",
        display_name="Red Block",
        required_processes=["visual_inspection", "drill", "quality_check"],
        inspection_rule="Correct shape and colour",
        color="#ef4444",
        shape="block",
    ),
    "blue_cylinder": ProductRecipe(
        product_type="blue_cylinder",
        display_name="Blue Cylinder",
        required_processes=["visual_inspection", "polish", "quality_check"],
        inspection_rule="Correct diameter and orientation",
        color="#3b82f6",
        shape="cylinder",
    ),
    "green_component": ProductRecipe(
        product_type="green_component",
        display_name="Green Component",
        required_processes=["visual_inspection", "assemble", "quality_check"],
        inspection_rule="Required part present",
        color="#22c55e",
        shape="component",
    ),
}


DEFAULT_MACHINE_CONFIGS: dict[str, MachineConfig] = {
    "conveyor_main": MachineConfig(
        machine_id="conveyor_main",
        name="Main Conveyor",
        machine_type="conveyor",
        capabilities=["transport"],
        processing_time={"transport": 1},
        input_location="line_buffer",
        output_location="line_buffer",
    ),
    "vision": MachineConfig(
        machine_id="vision",
        name="Vision Inspection",
        machine_type="inspection",
        capabilities=["visual_inspection"],
        processing_time={"visual_inspection": 1},
        input_location="input_queue",
        output_location="post_vision_buffer",
    ),
    "station_a": MachineConfig(
        machine_id="station_a",
        name="Processing A",
        machine_type="processing",
        capabilities=["drill", "assemble"],
        processing_time={"drill": 3, "assemble": 4},
        input_location="processing_buffer",
        output_location="quality_buffer",
    ),
    "station_b": MachineConfig(
        machine_id="station_b",
        name="Processing B",
        machine_type="processing",
        capabilities=["drill", "polish"],
        processing_time={"drill": 4, "polish": 3},
        input_location="processing_buffer",
        output_location="quality_buffer",
    ),
    "quality": MachineConfig(
        machine_id="quality",
        name="Quality Control",
        machine_type="quality",
        capabilities=["quality_check"],
        processing_time={"quality_check": 2},
        input_location="quality_buffer",
        output_location="sorter",
    ),
}


DEFAULT_FAULT_RULES: dict[str, Any] = {
    "temperature_limit_c": 78.0,
    "vibration_limit_mm_s": 3.2,
    "heartbeat_timeout_s": 5.0,
    "process_timeout_ticks": 8,
}


DEFAULT_ROUTING_WEIGHTS: dict[str, float] = {
    "processing_time": 1.0,
    "utilization": 0.15,
    "station_a_preference": 0.0,
    "station_b_preference": 0.0,
}


def _safe_load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded or {}


def load_product_recipes(config_dir: str | Path = "config") -> dict[str, ProductRecipe]:
    data = _safe_load_yaml(Path(config_dir) / "products.yaml")
    if not data:
        return dict(DEFAULT_RECIPES)
    recipes: dict[str, ProductRecipe] = {}
    for product_type, value in data.get("products", {}).items():
        recipes[product_type] = ProductRecipe(
            product_type=product_type,
            display_name=value["display_name"],
            required_processes=list(value["required_processes"]),
            inspection_rule=value.get("inspection_rule", ""),
            color=value.get("color", "#64748b"),
            shape=value.get("shape", "part"),
        )
    return recipes or dict(DEFAULT_RECIPES)


def load_machine_configs(config_dir: str | Path = "config") -> dict[str, MachineConfig]:
    data = _safe_load_yaml(Path(config_dir) / "machines.yaml")
    if not data:
        return dict(DEFAULT_MACHINE_CONFIGS)
    machines: dict[str, MachineConfig] = {}
    for machine_id, value in data.get("machines", {}).items():
        machines[machine_id] = MachineConfig(
            machine_id=machine_id,
            name=value["name"],
            machine_type=value["machine_type"],
            capabilities=list(value.get("capabilities", [])),
            processing_time=dict(value.get("processing_time", {})),
            input_location=value.get("input_location", ""),
            output_location=value.get("output_location", ""),
        )
    return machines or dict(DEFAULT_MACHINE_CONFIGS)


def load_fault_rules(config_dir: str | Path = "config") -> dict[str, Any]:
    data = _safe_load_yaml(Path(config_dir) / "fault_rules.yaml")
    return {**DEFAULT_FAULT_RULES, **data.get("fault_rules", {})}


def load_routing_weights(config_dir: str | Path = "config") -> dict[str, float]:
    data = _safe_load_yaml(Path(config_dir) / "routing_weights.yaml")
    return {**DEFAULT_ROUTING_WEIGHTS, **data.get("routing_weights", {})}
