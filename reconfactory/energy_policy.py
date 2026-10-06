"""Supervisor-owned energy decisions shared by real transport and logical fallback."""

from __future__ import annotations

from .energy import Battery, BatteryConfig, distance, estimate_mission, leg_energy
from .models import Severity


class EnergyPolicy:
    def __init__(self, factory, stations, config: BatteryConfig):
        self.factory = factory
        self.stations = stations
        self.battery = Battery(config)
        self.state = "ready"
        self.reason = None
        self.deferred = None
        self.estimate_wh = None
        self.logical_pose = stations["home"]
        self.logical_distance_left = 0.0
        self.charge_cycles = 0
        self.charging_seconds = 0.0
        self.elapsed_seconds = 0.0
        self.deferrals = 0

    def event(self, kind, **data):
        self.factory._emit(
            kind,
            kind.replace("_", " ").capitalize(),
            source="amr_energy",
            severity=Severity.WARNING
            if any(word in kind for word in ("critical", "failed", "blocked"))
            else Severity.INFO,
            data={**self.snapshot(), **data},
        )

    def snapshot(self):
        return {
            **self.battery.snapshot(),
            "state": self.state,
            "reason": self.reason,
            "deferred_transport": self.deferred,
            "estimated_energy_wh": self.estimate_wh,
            "planning_reserve_soc": self.battery.config.planning_reserve_soc,
            "critical_soc": self.battery.config.critical_soc,
            "charge_target_soc": self.battery.config.charge_target_soc,
            "charge_cycles": self.charge_cycles,
            "charging_seconds": self.charging_seconds,
            "missions_deferred": self.deferrals,
            "source": "odometry" if self.factory.transport_mode == "amr" else "logical",
        }

    def critical(self, reason):
        if self.state != "critical_energy":
            self.state, self.reason = "critical_energy", reason
            self.event("critical_energy")

    def authorize(self, product_id, origin, destination, current, loaded=False):
        if self.state in {"critical_energy", "blocked_energy"}:
            return False
        c = self.battery.config
        estimate = estimate_mission(
            c, current, self.stations[origin], self.stations[destination], payload_loaded=loaded
        )
        self.estimate_wh = estimate
        reserve = c.critical_soc if loaded else c.planning_reserve_soc
        escape = (
            0
            if loaded
            else leg_energy(
                c, distance(self.stations[destination], self.stations["charging_dock"]), False
            )
        )
        needed = max(
            estimate + reserve * c.capacity_wh,
            estimate + escape + c.critical_soc * c.capacity_wh,
        )
        if self.battery.remaining_wh >= needed:
            self.deferred = None
            return True
        if loaded:
            self.critical(
                "Loaded replacement cannot preserve critical reserve; payload held for operator recovery"
            )
            return False
        intent = {"product_id": product_id, "origin": origin, "destination": destination}
        if self.deferred is None:
            self.deferrals += 1
            self.deferred = intent
            self.event("transport_deferred_for_energy", estimated_energy_wh=estimate)
        if needed > c.capacity_wh * c.charge_target_soc:
            self.state = "blocked_energy"
            self.reason = "Mission exceeds charge-target budget; adjust capacity or workload"
            self.event("energy_mission_blocked")
            return False
        self.state = "charge_required"
        return False

    def begin_charge_trip(self, current):
        c = self.battery.config
        energy = leg_energy(c, distance(current, self.stations["charging_dock"]), False)
        if self.battery.remaining_wh < energy + c.capacity_wh * c.critical_soc:
            self.critical("Insufficient energy to reach charger with critical reserve")
            return False
        self.state, self.reason = "navigating_to_charger", None
        return True

    def arrived_at_charger(self):
        self.state = "charging"
        self.charge_cycles += 1
        self.event("charge_started")

    def update(self, dt, linear=0.0, angular=0.0, loaded=False, at_charger=False):
        charging = self.state == "charging" and at_charger
        self.battery.update(dt, linear, angular, payload_loaded=loaded, charging=charging)
        self.elapsed_seconds += dt
        if charging:
            self.charging_seconds += dt
            if self.battery.state_of_charge >= self.battery.config.charge_target_soc - 1e-10:
                self.state, self.reason = "ready", None
                self.event("charge_completed")
        elif self.battery.state_of_charge <= self.battery.config.critical_soc:
            self.critical(
                "Battery reached critical reserve; cancel navigation and retain payload"
            )

    def logical_tick(self, dt):
        c = self.battery.config
        if self.state == "navigating_to_charger":
            moved = min(self.logical_distance_left, c.estimate_speed_m_s * dt)
            self.logical_distance_left -= moved
            self.update(dt, moved / dt)
            if self.logical_distance_left <= 1e-9 and self.state != "critical_energy":
                self.logical_pose = self.stations["charging_dock"]
                self.arrived_at_charger()
        else:
            self.update(dt, at_charger=self.state == "charging")

    def logical_transfer(self, product, destination):
        if self.state not in {"ready", "charge_required"}:
            return False
        origin = next(
            (loc for loc in reversed(product.route) if loc in self.stations), "input_queue"
        )
        if not self.authorize(product.product_id, origin, destination, self.logical_pose):
            if self.state == "charge_required" and self.begin_charge_trip(self.logical_pose):
                self.logical_distance_left = distance(
                    self.logical_pose, self.stations["charging_dock"]
                )
            return False
        c = self.battery.config
        # Existing browser transport is logical, not a second Nav2 simulator.
        for target, loaded in (
            (self.stations[origin], False),
            (self.stations[destination], True),
        ):
            meters = distance(self.logical_pose, target)
            self.update(meters / c.estimate_speed_m_s, c.estimate_speed_m_s, loaded=loaded)
            self.logical_pose = target
        return True
