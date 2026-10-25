#!/usr/bin/env bash
set -eo pipefail
cd "$(dirname "$0")/.."
source /opt/ros/jazzy/setup.bash
ROOT="$(pwd)"
cd ros2_ws
if [ "${RECONFACTORY_AMR_PREBUILT:-0}" != "1" ]; then
  colcon build --packages-up-to reconfactory_amr --symlink-install
fi
source install/setup.bash
exec ros2 launch reconfactory_amr amr_navigation.launch.py \
  project_root:="${ROOT}" \
  enable_nav2:="${RECONFACTORY_AMR_NAV2:-true}" \
  enable_manager:="${RECONFACTORY_AMR_MANAGER:-true}" \
  unsafe_baseline:="${RECONFACTORY_TEST_UNGATED:-false}" \
  backend_url:="${RECONFACTORY_BACKEND_URL:-http://127.0.0.1:8000}"
