import json
import subprocess
import sys

import pytest

from scripts import check_vision_pipeline as checker


def test_ros_cli_timeout_is_reported_without_traceback(monkeypatch):
    monkeypatch.setattr(checker.shutil, "which", lambda _: "ros2")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("ros2", 5)

    monkeypatch.setattr(checker.subprocess, "run", timeout)
    assert checker._run_ros2(["node", "list"]) == (False, [])


@pytest.mark.parametrize(
    ("image_count", "duplicate", "expected_exit"),
    [(0, False, 1), (5, True, 1), (5, False, 0)],
)
def test_checker_requires_delivered_images_and_unique_nodes(
    monkeypatch, capsys, image_count, duplicate, expected_exit
):
    nodes = list(checker.EXPECTED_NODES) * (2 if duplicate else 1)
    monkeypatch.setattr(sys, "argv", ["check_vision_pipeline.py"])
    monkeypatch.setattr(
        checker,
        "_run_ros2",
        lambda args: (True, nodes if args[0] == "node" else list(checker.EXPECTED_TOPICS)),
    )
    monkeypatch.setattr(checker, "sample_images", lambda _: {"valid_images": image_count})
    assert checker.main() == expected_exit
    assert json.loads(capsys.readouterr().out)["ok"] is (expected_exit == 0)
