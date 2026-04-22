#!/usr/bin/env bash
set -euo pipefail

export MAMBA_ROOT_PREFIX="${MAMBA_ROOT_PREFIX:-/opt/micromamba}"
export PATH="/opt/micromamba/bin:${PATH}"
export PYTHONPATH="/workspace/droid:/workspace/openpi/packages/openpi-client/src:${PYTHONPATH:-}"

git config --global --add safe.directory /workspace/droid >/dev/null 2>&1 || true
git config --global --add safe.directory /workspace/droid/droid/fairo >/dev/null 2>&1 || true
git config --global --add safe.directory '*' >/dev/null 2>&1 || true

cd /workspace

if [[ "${DROID_RUNTIME_AUTO_BOOTSTRAP:-0}" == "1" ]]; then
    /workspace/runtime_scripts/bootstrap_envs.sh
fi

exec "$@"
