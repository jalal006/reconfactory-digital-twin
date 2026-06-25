#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

source_ros_setup() {
  local setup_file=""
  if [ -n "${ROS_DISTRO:-}" ] && [ -f "/opt/ros/${ROS_DISTRO}/setup.bash" ]; then
    setup_file="/opt/ros/${ROS_DISTRO}/setup.bash"
  else
    local distro
    for distro in jazzy humble rolling; do
      if [ -f "/opt/ros/${distro}/setup.bash" ]; then
        setup_file="/opt/ros/${distro}/setup.bash"
        break
      fi
    done
  fi
  [ -n "${setup_file}" ] || return 1
  set +u
  source "${setup_file}"
  set -u
}

if ! source_ros_setup || ! command -v ros2 >/dev/null 2>&1; then
  echo "ROS 2 Jazzy or Humble was not found."
  exit 1
fi
if ! command -v colcon >/dev/null 2>&1; then
  echo "colcon was not found."
  exit 1
fi

BACKEND_URL="${RECONFACTORY_BACKEND_URL:-http://127.0.0.1:8000}"
WORKSPACE="$(pwd)/ros2_ws"
PACKAGE_SOURCE="${WORKSPACE}/src/reconfactory_ros"
BUILD_STAMP="${WORKSPACE}/build/reconfactory_ros/.reconfactory_source_stamp"
INSTALL_SETUP="${WORKSPACE}/install/setup.bash"
NEEDS_BUILD=false

if [ ! -f "${INSTALL_SETUP}" ] || [ ! -f "${BUILD_STAMP}" ]; then
  NEEDS_BUILD=true
elif [ -n "$(find "${PACKAGE_SOURCE}" -type f -newer "${BUILD_STAMP}" -print -quit)" ]; then
  NEEDS_BUILD=true
fi

cd "${WORKSPACE}"
if [ "${NEEDS_BUILD}" = true ]; then
  echo "Building ReConFactory ROS 2 package..."
  if [ -n "${RECONFACTORY_ROS_BUILD_LOG:-}" ]; then
    colcon build --packages-select reconfactory_ros --symlink-install \
      >"${RECONFACTORY_ROS_BUILD_LOG}" 2>&1
  else
    colcon build --packages-select reconfactory_ros --symlink-install
  fi
  mkdir -p "$(dirname "${BUILD_STAMP}")"
  touch "${BUILD_STAMP}"
else
  echo "ROS 2 package is up to date."
fi

set +u
source "${INSTALL_SETUP}"
set -u

echo "Launching ROS 2 bridge for ${BACKEND_URL}..."
exec ros2 launch reconfactory_ros reconfactory_bridge.launch.py \
  backend_url:="${BACKEND_URL}"
