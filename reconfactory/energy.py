"""Deterministic simulation energy model and geometric estimates; no ROS imports."""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class BatteryConfig:
    capacity_wh: float = 100.0
    initial_soc: float = 0.9
    idle_power_w: float = 18.0
    linear_cost_wh_per_m: float = 0.2
    angular_cost_wh_per_rad: float = 0.03
    payload_multiplier: float = 1.25
    planning_reserve_soc: float = 0.2
    critical_soc: float = 0.05
    charge_target_soc: float = 0.8
    charging_power_w: float = 7200.0
    estimate_speed_m_s: float = 0.35
    turn_allowance_rad: float = math.pi
    estimate_safety_factor: float = 1.4
    dock_tolerance_m: float = 0.18

    def __post_init__(self):
        if any(not math.isfinite(v) or v < 0 for v in asdict(self).values()):
            raise ValueError("Energy configuration must be finite and nonnegative")
        if not (self.capacity_wh > 0 and self.estimate_speed_m_s > 0):
            raise ValueError("Battery capacity and estimate speed must be positive")
        if not (
            0 <= self.initial_soc <= 1
            and 0 <= self.critical_soc < self.planning_reserve_soc < self.charge_target_soc <= 1
        ):
            raise ValueError("Invalid SOC thresholds")
        if self.charging_power_w <= self.idle_power_w:
            raise ValueError("Charging power must exceed idle load")
        if self.payload_multiplier < 1 or self.estimate_safety_factor < 1:
            raise ValueError("Energy multipliers must be at least one")

    @classmethod
    def load(cls, config_dir: Path):
        path = config_dir / "energy.yaml"
        data = yaml.safe_load(path.read_text()) if path.exists() else {}
        if "AMR_INITIAL_SOC" in os.environ:
            data["initial_soc"] = float(os.environ["AMR_INITIAL_SOC"])
        return cls(**data)


class Battery:
    def __init__(self, config: BatteryConfig):
        self.config = config
        self.remaining_wh = config.capacity_wh * config.initial_soc
        self.energy_consumed_wh = 0.0
        self.energy_charged_wh = 0.0
        self.is_charging = False
        self.minimum_soc = self.state_of_charge

    @property
    def state_of_charge(self) -> float:
        return min(1.0, max(0.0, self.remaining_wh / self.config.capacity_wh))

    def update(
        self,
        dt: float,
        linear_speed: float = 0.0,
        angular_speed: float = 0.0,
        *,
        payload_loaded: bool = False,
        charging: bool = False,
    ) -> float:
        if not all(math.isfinite(v) for v in (dt, linear_speed, angular_speed)) or dt < 0:
            raise ValueError(
                "Battery time and velocities must be finite; dt must be nonnegative"
            )
        if dt == 0:
            return 0.0
        c = self.config
        self.is_charging = charging and self.state_of_charge < c.charge_target_soc
        multiplier = c.payload_multiplier if payload_loaded else 1.0
        used = c.idle_power_w * dt / 3600 + multiplier * dt * (
            c.linear_cost_wh_per_m * abs(linear_speed)
            + c.angular_cost_wh_per_rad * abs(angular_speed)
        )
        consumed = min(self.remaining_wh, used)
        self.energy_consumed_wh += consumed
        self.remaining_wh -= consumed
        if self.is_charging:
            added = min(
                c.charging_power_w * dt / 3600,
                max(0.0, c.capacity_wh * c.charge_target_soc - self.remaining_wh),
            )
            self.remaining_wh += added
            self.energy_charged_wh += added
        self.remaining_wh = min(c.capacity_wh, max(0.0, self.remaining_wh))
        self.minimum_soc = min(self.minimum_soc, self.state_of_charge)
        if self.state_of_charge >= c.charge_target_soc - 1e-10:
            self.is_charging = False
        return consumed

    def snapshot(self) -> dict:
        return {
            "capacity_wh": self.config.capacity_wh,
            "remaining_wh": self.remaining_wh,
            "state_of_charge": self.state_of_charge,
            "is_charging": self.is_charging,
            "energy_consumed_wh": self.energy_consumed_wh,
            "energy_charged_wh": self.energy_charged_wh,
            "minimum_soc": self.minimum_soc,
        }


def distance(a: dict, b: dict) -> float:
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def leg_energy(config: BatteryConfig, meters: float, loaded: bool) -> float:
    if not math.isfinite(meters) or meters < 0:
        raise ValueError("Distance must be finite and nonnegative")
    multiplier = config.payload_multiplier if loaded else 1.0
    return config.estimate_safety_factor * (
        config.idle_power_w * meters / config.estimate_speed_m_s / 3600
        + multiplier
        * (
            config.linear_cost_wh_per_m * meters
            + config.angular_cost_wh_per_rad * config.turn_allowance_rad
        )
    )


def estimate_mission(
    config: BatteryConfig,
    current: dict,
    pickup: dict,
    destination: dict,
    *,
    payload_loaded: bool = False,
) -> float:
    return (
        0 if payload_loaded else leg_energy(config, distance(current, pickup), False)
    ) + leg_energy(config, distance(current if payload_loaded else pickup, destination), True)


def battery_ros_fields(snapshot: dict) -> dict:
    """Only SOC/status are modeled. Ah, voltage, temperature and chemistry are unknown."""
    return {
        "percentage": snapshot["state_of_charge"],
        "present": True,
        "power_supply_status": 1 if snapshot["is_charging"] else 2,
        "voltage": math.nan,
        "temperature": math.nan,
        "current": math.nan,
        "charge": math.nan,
        "capacity": math.nan,
        "design_capacity": math.nan,
    }
