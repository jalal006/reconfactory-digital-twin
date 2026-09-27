"""The destructive runtime checks must never select unrelated processes."""

import pytest

from scripts.check_amr_resilience import owned_process


def process(root, pid, parent, partition="reconfactory_test_123"):
    directory = root / str(pid)
    directory.mkdir()
    (directory / "cmdline").write_bytes(b"python\0scripts/run_factory.py\0")
    (directory / "status").write_text(f"PPid:\t{parent}\n")
    (directory / "environ").write_bytes(
        f"ROS_DOMAIN_ID=73\0GZ_PARTITION={partition}\0".encode()
    )


def test_select_only_descendant_even_with_separate_session(tmp_path):
    process(tmp_path, 101, 100)
    process(tmp_path, 201, 200)
    pid, argv, env = owned_process(100, "scripts/run_factory.py", tmp_path)
    assert pid == 101 and argv[0] == "python"
    assert env["GZ_PARTITION"] == "reconfactory_test_123"


def test_refuse_non_test_partition(tmp_path):
    process(tmp_path, 101, 100, "user_factory")
    with pytest.raises(RuntimeError, match="non-test"):
        owned_process(100, "scripts/run_factory.py", tmp_path)


def test_refuse_ambiguous_processes(tmp_path):
    process(tmp_path, 101, 100)
    process(tmp_path, 102, 100)
    with pytest.raises(RuntimeError, match="found 2"):
        owned_process(100, "scripts/run_factory.py", tmp_path)
