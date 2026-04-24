#!/usr/bin/env bash
set -euo pipefail

export DROID_ENABLE_SIM_MOTION=1
export DROID_CONFIRM_SIMULATION=1

eval "$(micromamba shell hook --shell bash)"
set +u
micromamba activate "${DROID_ROBOT_RUNTIME_ENV:-polymetis-local}"
set -u

exec python /workspace/droid/scripts/openpi_droid_main.py \
    --execute \
    --simulation \
    --no_launch_robot \
    --no_reset \
    --mock_cameras \
    "$@"
