#!/usr/bin/env bash
set -euo pipefail

# Simulation-only motion guards. These do not permit real robot execution.
export DROID_ENABLE_SIM_MOTION=1
export DROID_CONFIRM_SIMULATION=1
export DROID_ROLLOUT_LOG_DIR="${DROID_ROLLOUT_LOG_DIR:-/workspace/reports/sim_preview_debug}"
export DROID_ROLLOUT_LOG_CSV="${DROID_ROLLOUT_LOG_CSV:-${DROID_ROLLOUT_LOG_DIR}/rollout.csv}"
export DROID_OBSERVATION_WARMUP_STEPS="${DROID_OBSERVATION_WARMUP_STEPS:-30}"

eval "$(micromamba shell hook --shell bash)"
set +u
micromamba activate "${DROID_ROBOT_RUNTIME_ENV:-polymetis-local}"
set -u

exec python /workspace/droid/scripts/openpi_droid_main.py \
    --execute \
    --simulation \
    --no_launch_robot \
    --no_reset \
    "$@"
