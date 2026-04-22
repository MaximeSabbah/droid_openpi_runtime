#!/usr/bin/env bash
set -euo pipefail

export DROID_GRIPPER_DRY_RUN=1
eval "$(micromamba shell hook --shell bash)"

runtime_env="${DROID_POLYMETIS_CONDA_ENV:-polymetis-local}"
if ! micromamba env list | awk '{print $1}' | grep -Fxq "${runtime_env}"; then
    export DROID_POLYMETIS_CONDA_ENV=droid
    export DROID_ENV_ACTIVATE='eval "$(micromamba shell hook --shell bash)" && micromamba activate droid'
fi

bash /workspace/droid/droid/franka/launch_gripper.sh
