#!/usr/bin/env bash
set -euo pipefail

if [[ "${DROID_ENABLE_ROBOT_MOTION:-0}" != "1" || "${CONFIRM_REAL_ROBOT:-0}" != "1" ]]; then
    echo "Refusing to execute. Set DROID_ENABLE_ROBOT_MOTION=1 and CONFIRM_REAL_ROBOT=1." >&2
    exit 1
fi

eval "$(micromamba shell hook --shell bash)"
micromamba activate "${DROID_ROBOT_RUNTIME_ENV:-polymetis-local}"

exec python /workspace/droid/scripts/openpi_droid_main.py \
    --execute \
    "$@"
