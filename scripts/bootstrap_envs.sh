#!/usr/bin/env bash
set -euo pipefail

eval "$(micromamba shell hook --shell bash)"

echo "[bootstrap] Installing DROID runtime environment"
micromamba activate droid
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e /workspace/droid
python -m pip install -e /workspace/openpi/packages/openpi-client
python -m pip install pyrealsense2 tyro
micromamba deactivate

echo "[bootstrap] Installing OpenPI policy-server environment"
micromamba activate openpi
cd /workspace/openpi
uv sync
micromamba deactivate

echo "[bootstrap] DROID/OpenPI environments are ready."
echo "[bootstrap] For real Franka control, initialize droid/fairo and run:"
echo "[bootstrap]   /workspace/runtime_scripts/bootstrap_fairo_franka.sh"

echo "[bootstrap] Done"
