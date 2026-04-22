#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.singlepc.yml"

cd "${SCRIPT_DIR}"

echo "[install] Building OpenPI + DROID runtime image"
docker compose -f "${COMPOSE_FILE}" build openpi-droid

echo "[install] Installing DROID/OpenPI Python environments"
docker compose -f "${COMPOSE_FILE}" run --rm openpi-droid \
    /workspace/runtime_scripts/bootstrap_envs.sh

echo "[install] Installing FAIRO/Polymetis/libfranka robot-control environment"
docker compose -f "${COMPOSE_FILE}" run --rm openpi-droid \
    /workspace/runtime_scripts/bootstrap_fairo_franka.sh

echo "[install] Verifying robot-control environment"
docker compose -f "${COMPOSE_FILE}" run --rm openpi-droid \
    /workspace/runtime_scripts/test_polymetis.sh

echo "[install] Done"
