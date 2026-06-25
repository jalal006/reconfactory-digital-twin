#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

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

ROS_AVAILABLE=false
if source_ros_setup && command -v ros2 >/dev/null 2>&1; then
  ROS_AVAILABLE=true
fi

if [ ! -x ".venv-wsl/bin/python" ]; then
  python3 -m venv .venv-wsl
fi

source .venv-wsl/bin/activate
python -m pip install -r requirements.txt

APP_PORT="${PORT:-8000}"
WSL_IP="$(hostname -I | awk '{print $1}')"
export RECONFACTORY_PUBLIC_URL="http://${WSL_IP}:${APP_PORT}"
BACKEND_URL="http://127.0.0.1:${APP_PORT}"
WORLD="$(pwd)/gazebo_fallback/worlds/reconfactory.world.sdf"
LOG_DIR="$(pwd)/logs"
mkdir -p "${LOG_DIR}"

PIDS=()

cleanup() {
  echo
  echo "Stopping ReConFactory..."
  for pid in "${PIDS[@]}"; do
    kill "${pid}" >/dev/null 2>&1 || true
  done
  wait >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "Starting ReConFactory backend..."
python scripts/run_factory.py --host 0.0.0.0 --port "${APP_PORT}" >"${LOG_DIR}/backend.log" 2>&1 &
PIDS+=("$!")

if ! python - <<PY
import sys
import time
import urllib.request

url = "${BACKEND_URL}/api/status"
for _ in range(80):
    try:
        urllib.request.urlopen(url, timeout=0.5).read()
        sys.exit(0)
    except Exception:
        time.sleep(0.25)
sys.exit(1)
PY
then
  echo "Backend did not start. Last backend log lines:"
  tail -80 "${LOG_DIR}/backend.log" || true
  exit 1
fi

echo "Open http://127.0.0.1:${APP_PORT}"
echo "WSL URL ${RECONFACTORY_PUBLIC_URL}"

if [ "${ROS_AVAILABLE}" = true ] && command -v colcon >/dev/null 2>&1; then
  echo "Starting ROS 2 bridge..."
  RECONFACTORY_BACKEND_URL="${BACKEND_URL}" \
  RECONFACTORY_ROS_BUILD_LOG="${LOG_DIR}/ros2_build.log" \
    bash scripts/run_ros_bridge.sh >"${LOG_DIR}/ros2.log" 2>&1 &
  ROS_PID="$!"
  PIDS+=("${ROS_PID}")

  ROS_READY=false
  for _ in {1..120}; do
    if ! kill -0 "${ROS_PID}" >/dev/null 2>&1; then
      break
    fi
    ROS_NODES="$(ros2 node list 2>/dev/null || true)"
    if printf '%s\n' "${ROS_NODES}" | grep -Fxq "/reconfactory_supervisor" \
      && printf '%s\n' "${ROS_NODES}" | grep -Fxq "/reconfactory_station_controller" \
      && printf '%s\n' "${ROS_NODES}" | grep -Fxq "/reconfactory_fault_detector" \
      && printf '%s\n' "${ROS_NODES}" | grep -Fxq "/reconfactory_logger"; then
      ROS_READY=true
      break
    fi
    sleep 0.25
  done

  if [ "${ROS_READY}" != true ]; then
    echo "ROS 2 bridge did not become ready. Last ROS log lines:"
    tail -80 "${LOG_DIR}/ros2.log" || true
    if [ -f "${LOG_DIR}/ros2_build.log" ]; then
      echo "Last ROS build log lines:"
      tail -80 "${LOG_DIR}/ros2_build.log" || true
    fi
    exit 1
  fi
  echo "ROS 2 bridge ready."
else
  echo "ROS 2 or colcon was not found, so the ROS bridge was skipped."
fi

if command -v gz >/dev/null 2>&1; then
  echo "Starting Gazebo factory..."
  gz sim -r "${WORLD}" >"${LOG_DIR}/gazebo.log" 2>&1 &
  PIDS+=("$!")

  echo "Starting Gazebo sync bridge..."
  python gazebo_fallback/scripts/sync_backend_to_gazebo.py --backend-url "${BACKEND_URL}" --poll-interval 0.04 --publish-visuals >"${LOG_DIR}/gazebo_sync.log" 2>&1 &
  PIDS+=("$!")
else
  echo "Gazebo 'gz' was not found, so only the browser dashboard is running."
fi

echo
echo "Everything is running from this terminal."
echo "Logs:"
echo "  ${LOG_DIR}/backend.log"
echo "  ${LOG_DIR}/ros2.log"
echo "  ${LOG_DIR}/ros2_build.log"
echo "  ${LOG_DIR}/gazebo.log"
echo "  ${LOG_DIR}/gazebo_sync.log"
echo
echo "Press Ctrl+C here to stop all of it."

wait -n "${PIDS[@]}"
