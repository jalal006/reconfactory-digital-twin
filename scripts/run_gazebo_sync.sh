#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f /opt/ros/jazzy/setup.bash ]; then
  set +u
  source /opt/ros/jazzy/setup.bash
  set -u
fi

if ! command -v gz >/dev/null 2>&1; then
  echo "Gazebo 'gz' command was not found. Start this from Ubuntu/WSL after ROS/Gazebo is installed."
  exit 1
fi

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"
python3 gazebo_fallback/scripts/sync_backend_to_gazebo.py --backend-url "${BACKEND_URL}" --publish-visuals
