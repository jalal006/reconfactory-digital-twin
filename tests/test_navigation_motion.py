import math

import pytest

from scripts.check_amr_pipeline import MotionTrace


def test_motion_trace_wraps_heading_without_inventing_full_turn():
    trace = MotionTrace()
    trace.update(1, 0, 0, math.pi - 0.02)
    trace.update(2, 0.3, 0.4, -math.pi + 0.02)
    assert trace.distance == pytest.approx(0.5)
    assert trace.rotation == pytest.approx(0.04)


def test_motion_trace_detects_multiple_full_spins():
    trace = MotionTrace()
    for step in range(17):
        angle = step * math.pi / 4
        trace.update(step, 0, 0, math.atan2(math.sin(angle), math.cos(angle)))
    assert trace.rotation == pytest.approx(4 * math.pi)
    assert trace.distance == 0


def test_motion_trace_ignores_old_duplicate_and_invalid_samples():
    trace = MotionTrace()
    trace.update(2, 0, 0, 0)
    trace.update(1, 100, 0, 2)
    trace.update(2, 100, 0, 2)
    trace.update(3, float("nan"), 0, 2)
    trace.update(4, 1, 0, 0)
    assert trace.distance == 1
    assert trace.rotation == 0
