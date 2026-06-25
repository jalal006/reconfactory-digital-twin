#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f /opt/ros/jazzy/setup.bash ]; then
  set +u
  source /opt/ros/jazzy/setup.bash
  set -u
fi

if ! command -v gz >/dev/null 2>&1; then
  echo "Gazebo 'gz' command was not found. Install Gazebo Sim or source your ROS/Gazebo setup first."
  exit 1
fi

WORLD="$(pwd)/gazebo_fallback/worlds/reconfactory.world.sdf"
echo "Starting Gazebo world: ${WORLD}"
gz sim -r "${WORLD}"
