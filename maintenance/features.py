"""Stable, per-machine rolling features; slopes are per telemetry sample."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .health import SensorPoint

SIGNALS = ("temperature_c", "vibration_mm_s", "current_a")
FEATURE_NAMES = tuple(
    f"{signal}_{stat}" for stat in ("last", "mean", "std", "slope") for signal in SIGNALS
)
WINDOW_SIZE = 12


def extract_features(
    history: Sequence[SensorPoint], window: int = WINDOW_SIZE
) -> np.ndarray | None:
    if window < 2:
        raise ValueError("Feature window must be at least two samples")
    if not history:
        return None
    recent = list(history)[-window:]
    if len({p.machine_id for p in recent}) != 1:
        raise ValueError("A feature window must contain exactly one machine")
    values = np.array([[getattr(p, signal) for signal in SIGNALS] for p in recent], dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Telemetry must be finite")
    if len(recent) < window:
        return None
    x = np.arange(window, dtype=float)
    x -= x.mean()
    return np.concatenate(
        (values[-1], values.mean(axis=0), values.std(axis=0), x @ values / (x @ x))
    )


def feature_rows(sequence: Sequence[SensorPoint], window: int = WINDOW_SIZE) -> np.ndarray:
    return np.array(
        [
            extract_features(sequence[i - window : i], window)
            for i in range(window, len(sequence) + 1)
        ]
    )
