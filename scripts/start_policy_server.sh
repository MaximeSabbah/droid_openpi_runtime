#!/usr/bin/env bash
set -euo pipefail

eval "$(micromamba shell hook --shell bash)"
micromamba activate openpi

cd /workspace/openpi

PORT="${OPENPI_PORT:-8000}"
POLICY_CONFIG="${OPENPI_POLICY_CONFIG:-pi05_droid}"
POLICY_DIR="${OPENPI_POLICY_DIR:-gs://openpi-assets/checkpoints/pi05_droid}"

exec uv run scripts/serve_policy.py \
    --port "$PORT" \
    policy:checkpoint \
    --policy.config "$POLICY_CONFIG" \
    --policy.dir "$POLICY_DIR"
