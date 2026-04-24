#!/usr/bin/env bash
set -euo pipefail

export DROID_ROBOT_READONLY=1
export DROID_SKIP_GRIPPER_LAUNCH=1
export DROID_MOCK_GRIPPER_POSITION="${DROID_MOCK_GRIPPER_POSITION:-0.0}"

eval "$(micromamba shell hook --shell bash)"
set +u
micromamba activate "${DROID_ROBOT_RUNTIME_ENV:-polymetis-local}"
set -u

exec python /workspace/runtime_scripts/capture_real_robot_state.py "$@"
