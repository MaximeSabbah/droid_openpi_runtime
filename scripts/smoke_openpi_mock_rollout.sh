#!/usr/bin/env bash
set -euo pipefail

eval "$(micromamba shell hook --shell bash)"
set +u
micromamba activate droid
set -u

exec python /workspace/droid/scripts/openpi_droid_main.py \
    --dry-run \
    --mock_robot_state \
    --mock_cameras \
    --mock_policy \
    --prompt "mock policy contract check" \
    --max_timesteps "${DROID_MOCK_ROLLOUT_STEPS:-3}" \
    --open_loop_horizon 2 \
    --camera_width 320 \
    --camera_height 240 \
    --save_preview /tmp/openpi_droid_mock_preview.png
