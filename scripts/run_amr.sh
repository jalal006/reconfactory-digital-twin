#!/usr/bin/env bash
set -eo pipefail
cd "$(dirname "$0")/.."
source /opt/ros/jazzy/setup.bash
ROOT="$(pwd)"
cd ros2_ws
colcon build --packages-select reconfactory_amr --symlink-install
source install/setup.bash
exec ros2 launch reconfactory_amr amr_navigation.launch.py \
  project_root:="${ROOT}" \
  enable_nav2:="${RECONFACTORY_AMR_NAV2:-true}" \
  backend_url:="${RECONFACTORY_BACKEND_URL:-http://127.0.0.1:8000}"
