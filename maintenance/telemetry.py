"""Seeded simulator shared by dataset generation and maintenance experiments."""

from __future__ import annotations

import math
import random

from .health import SensorPoint

SCENARIOS = ("healthy", "bearing", "overheating", "mechanical_load")


def generate_sequence(
    machine_id: str = "station_a",
    *,
    seed: int = 42,
    samples: int = 120,
    scenario: str = "healthy",
) -> list[SensorPoint]:
    if scenario not in SCENARIOS or samples < 2:
        raise ValueError("Unknown scenario or insufficient samples")
    rng = random.Random(seed)
    baseline = rng.uniform(30, 36)
    noise = rng.uniform(0, 0.35)
    points = []
    for tick in range(samples):
        load = tick % 8 < 5
        temperature = baseline + 0.8 * math.sin(tick / 8) + rng.gauss(0, noise)
        vibration = max(0.02, 0.08 + rng.gauss(0, noise * 0.05))
        current = (1.25 if load else 0.5) + rng.gauss(0, noise * 0.1)
        progress = max(0.0, (tick / (samples - 1) - 0.2) / 0.8)
        if scenario == "bearing":
            vibration += progress * 3.6
            current += progress * 0.8
        elif scenario == "overheating":
            temperature += progress * 60
            current += progress * 0.6
        elif scenario == "mechanical_load":
            current += progress * 2.4
            vibration += progress * 2.6
        points.append(SensorPoint(machine_id, temperature, vibration, current))
    return points
