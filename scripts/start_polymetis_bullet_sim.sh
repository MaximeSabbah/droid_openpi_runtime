#!/usr/bin/env bash
set -euo pipefail

eval "$(micromamba shell hook --shell bash)"
set +u
micromamba activate "${DROID_ROBOT_RUNTIME_ENV:-polymetis-local}"
set -u

ARM_PORT="${POLYMETIS_SIM_ARM_PORT:-50051}"
GRIPPER_PORT="${POLYMETIS_SIM_GRIPPER_PORT:-50052}"
ARM_IP="${POLYMETIS_SIM_ARM_IP:-localhost}"
GRIPPER_IP="${POLYMETIS_SIM_GRIPPER_IP:-localhost}"

children=()
cleanup() {
    for child in "${children[@]:-}"; do
        kill "$child" >/dev/null 2>&1 || true
    done
}
trap cleanup EXIT INT TERM

wait_for_port() {
    local host="$1"
    local port="$2"
    python - "$host" "$port" <<'PY'
import socket
import sys
import time

host, port = sys.argv[1], int(sys.argv[2])
deadline = time.time() + 15
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            raise SystemExit(0)
    except OSError:
        time.sleep(0.1)
raise SystemExit(f"Timed out waiting for {host}:{port}")
PY
}

launch_robot.py \
    robot_client=none \
    robot_model=franka_panda_with_hand \
    "ip=0.0.0.0" \
    "port=${ARM_PORT}" &
children+=("$!")
wait_for_port "127.0.0.1" "$ARM_PORT"

launch_gripper.py \
    gripper=none \
    "ip=0.0.0.0" \
    "port=${GRIPPER_PORT}" &
children+=("$!")
wait_for_port "127.0.0.1" "$GRIPPER_PORT"

cd /workspace/droid/droid/fairo/polymetis/polymetis/python/polysim/envs/experimental

exec python bullet_manipulator.py \
    "gui=${POLYMETIS_SIM_GUI:-false}" \
    "arm.ip=${ARM_IP}" \
    "arm.port=${ARM_PORT}" \
    "gripper.ip=${GRIPPER_IP}" \
    "gripper.port=${GRIPPER_PORT}"
