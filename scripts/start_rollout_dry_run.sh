#!/usr/bin/env bash
set -euo pipefail

eval "$(micromamba shell hook --shell bash)"
export DROID_OBSERVATION_WARMUP_STEPS="${DROID_OBSERVATION_WARMUP_STEPS:-30}"

runtime_env="${DROID_DRY_RUN_RUNTIME_ENV:-}"
if [[ -z "${runtime_env}" ]]; then
    uses_mock_robot_state=0
    help_only=0
    for arg in "$@"; do
        if [[ "${arg}" == "--mock_robot_state" ]]; then
            uses_mock_robot_state=1
            break
        fi
        if [[ "${arg}" == "--help" || "${arg}" == "-h" ]]; then
            help_only=1
            break
        fi
    done
    if [[ "${uses_mock_robot_state}" == "1" || "${help_only}" == "1" ]]; then
        runtime_env="droid"
    else
        runtime_env="${DROID_ROBOT_RUNTIME_ENV:-polymetis-local}"
        export DROID_ROBOT_READONLY="${DROID_ROBOT_READONLY:-1}"
        export DROID_SKIP_GRIPPER_LAUNCH="${DROID_SKIP_GRIPPER_LAUNCH:-1}"
        export DROID_MOCK_GRIPPER_POSITION="${DROID_MOCK_GRIPPER_POSITION:-0.0}"
    fi
fi

set +u
micromamba activate "${runtime_env}"
set -u

exec python /workspace/droid/scripts/openpi_droid_main.py \
    --dry-run \
    --no_reset \
    "$@"
