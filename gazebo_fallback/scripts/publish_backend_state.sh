#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"

if [ -f /opt/ros/jazzy/setup.bash ]; then
  set +u
  source /opt/ros/jazzy/setup.bash
  set -u
fi

if ! command -v gz >/dev/null 2>&1; then
  echo "gz command not found."
  exit 1
fi

while true; do
  payload="$(python3 - <<PY
import json, urllib.request
with urllib.request.urlopen("${BACKEND_URL}/api/status", timeout=2) as r:
    print(json.dumps(json.loads(r.read().decode("utf-8"))))
PY
)"
  escaped="${payload//\"/\\\"}"
  gz topic -t /reconfactory/factory_state -m gz.msgs.StringMsg -p "data: \"${escaped}\"" >/dev/null 2>&1 || true
  sleep 0.5
done
