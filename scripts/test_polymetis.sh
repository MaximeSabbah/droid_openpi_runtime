#!/usr/bin/env bash
set -u

eval "$(micromamba shell hook --shell bash)"
RUNTIME_ENV="${DROID_ROBOT_RUNTIME_ENV:-${DROID_POLYMETIS_CONDA_ENV:-polymetis-local}}"
POLYMETIS_CONFIG_OVERLAY="${DROID_POLYMETIS_CONFIG_DIR:-/workspace/runtime_config/polymetis}"
ROBOT_CLIENT_CONFIG="${DROID_ROBOT_CLIENT_CONFIG:-droid_franka_hardware}"
ROBOT_MODEL_CONFIG="${DROID_ROBOT_MODEL_CONFIG:-droid_franka_panda}"

if ! micromamba env list | awk '{print $1}' | grep -Fxq "${RUNTIME_ENV}"; then
    echo "Missing robot-control micromamba env: ${RUNTIME_ENV}" >&2
    echo "Run /workspace/runtime_scripts/bootstrap_fairo_franka.sh after initializing droid/fairo." >&2
    exit 1
fi

set +u
micromamba activate "${RUNTIME_ENV}"
set -u

failures=0

check_cmd() {
    local label="$1"
    shift
    echo "== $label =="
    "$@"
    local status=$?
    echo "status=$status"
    if [[ "$status" != "0" ]]; then
        failures=$((failures + 1))
    fi
}

check_cmd "python" python --version
check_cmd "grpc import" python -c "import grpc; print(grpc.__version__)"
check_cmd "torch import" python -c "import torch; print(torch.__version__)"
check_cmd "polymetis import from FAIRO" python -c "import polymetis; print(polymetis.__file__); from polymetis import RobotInterface, GripperInterface; print(RobotInterface, GripperInterface)"
check_cmd "launch_robot.py" bash -lc "command -v launch_robot.py && launch_robot.py --help >/tmp/launch_robot_help.txt 2>&1"
check_cmd "launch_gripper.py" bash -lc "command -v launch_gripper.py && launch_gripper.py --help >/tmp/launch_gripper_help.txt 2>&1"
check_cmd "franka_panda_client" bash -lc "command -v franka_panda_client"
check_cmd "franka_hand_client" bash -lc "command -v franka_hand_client"
check_cmd "DROID Franka import" python -c "from droid.franka.robot import FrankaRobot; print(FrankaRobot)"

if [[ -d "${POLYMETIS_CONFIG_OVERLAY}" ]]; then
    check_cmd "DROID Polymetis config overlay" bash -lc "launch_robot.py --cfg job --config-dir ${POLYMETIS_CONFIG_OVERLAY} robot_client=${ROBOT_CLIENT_CONFIG} robot_model=${ROBOT_MODEL_CONFIG} >/tmp/droid_polymetis_config.yaml"
else
    echo "== DROID Polymetis config overlay =="
    echo "missing ${POLYMETIS_CONFIG_OVERLAY}; run bootstrap_fairo_franka.sh to install DROID configs"
    failures=$((failures + 1))
fi

echo "== fairo submodule =="
if [[ -d /workspace/droid/droid/fairo/polymetis ]]; then
    echo "found /workspace/droid/droid/fairo/polymetis"
else
    echo "missing /workspace/droid/droid/fairo/polymetis"
    failures=$((failures + 1))
fi

if [[ "$failures" != "0" ]]; then
    echo "FAIRO/Polymetis low-level check failed with $failures missing pieces." >&2
    exit 1
fi

echo "FAIRO/Polymetis low-level check passed."
