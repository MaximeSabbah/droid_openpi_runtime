#!/usr/bin/env bash
set -euo pipefail

DROID_ROOT="${DROID_ROOT:-/workspace/droid}"
OPENPI_ROOT="${OPENPI_ROOT:-/workspace/openpi}"
FAIRO_DIR="${DROID_FAIRO_DIR:-${DROID_ROOT}/droid/fairo}"
FAIRO_GIT_URL="${DROID_FAIRO_GIT_URL:-https://github.com/facebookresearch/fairo.git}"
POLYMETIS_DIR="${DROID_POLYMETIS_DIR:-${FAIRO_DIR}/polymetis}"
ROBOT_TYPE="${DROID_ROBOT_TYPE:-panda}"
POLYMETIS_ENV="${DROID_ROBOT_RUNTIME_ENV:-${DROID_POLYMETIS_CONDA_ENV:-polymetis-local}}"
POLYMETIS_CONFIG_OVERLAY="${DROID_POLYMETIS_CONFIG_DIR:-/workspace/runtime_config/polymetis}"
ROBOT_CLIENT_CONFIG="${DROID_ROBOT_CLIENT_CONFIG:-droid_franka_hardware}"
ROBOT_MODEL_CONFIG="${DROID_ROBOT_MODEL_CONFIG:-droid_franka_panda}"
BUILD_TESTS="${DROID_POLYMETIS_BUILD_TESTS:-OFF}"
BUILD_DOCS="${DROID_POLYMETIS_BUILD_DOCS:-OFF}"
BUILD_JOBS="${DROID_FRANKA_BUILD_JOBS:-$(nproc)}"

case "${ROBOT_TYPE}" in
    panda)
        DEFAULT_LIBFRANKA_VERSION="0.9.0"
        ;;
    fr3)
        DEFAULT_LIBFRANKA_VERSION="0.10.0"
        ;;
    *)
        echo "Unsupported DROID_ROBOT_TYPE='${ROBOT_TYPE}'. Expected panda or fr3." >&2
        exit 2
        ;;
esac

LIBFRANKA_VERSION="${DROID_LIBFRANKA_VERSION:-${LIBFRANKA_VERSION:-${DEFAULT_LIBFRANKA_VERSION}}}"

if [[ ! -d "${FAIRO_DIR}" ]]; then
    if [[ "${DROID_BOOTSTRAP_FAIRO_SUBMODULE:-0}" == "1" ]]; then
        if git -C "${DROID_ROOT}" ls-files -s droid/fairo | grep -q '^160000 '; then
            echo "[franka] Initializing registered FAIRO submodule at ${FAIRO_DIR}"
            git -C "${DROID_ROOT}" submodule update --init --recursive droid/fairo
        else
            echo "[franka] droid/fairo is listed in .gitmodules but is not registered as a gitlink in this checkout."
            echo "[franka] Cloning FAIRO directly into ${FAIRO_DIR}"
            git clone --recursive "${FAIRO_GIT_URL}" "${FAIRO_DIR}"
        fi
    else
        cat >&2 <<EOF
FAIRO submodule is missing at ${FAIRO_DIR}.

Initialize or clone it first, then rerun this script:

  git -C ${DROID_ROOT} submodule update --init --recursive droid/fairo

If that fails with "pathspec did not match", this checkout has .gitmodules
metadata but no registered gitlink. In that case use:

  git clone --recursive ${FAIRO_GIT_URL} ${FAIRO_DIR}

Or rerun this script with DROID_BOOTSTRAP_FAIRO_SUBMODULE=1 to let the
container initialize the registered submodule or clone FAIRO as a fallback.
EOF
        exit 2
    fi
fi

if [[ ! -d "${POLYMETIS_DIR}/polymetis" ]]; then
    echo "Missing Polymetis sources at ${POLYMETIS_DIR}/polymetis." >&2
    echo "The DROID code expects the Polymetis runtime from the FAIRO repo." >&2
    exit 2
fi

git config --global --add safe.directory "${DROID_ROOT}" || true
git config --global --add safe.directory "${FAIRO_DIR}" || true
git config --global --add safe.directory '*' || true

echo "[franka] Updating required FAIRO/Polymetis submodules"
git -C "${FAIRO_DIR}" submodule update --init --recursive \
    polymetis/polymetis/src/clients/franka_panda_client/third_party/libfranka
if [[ "${BUILD_TESTS}" == "ON" ]]; then
    git -C "${FAIRO_DIR}" submodule update --init --recursive \
        polymetis/polymetis/tests/cpp/fake_clock
fi

eval "$(micromamba shell hook --shell bash)"

if micromamba env list | awk '{print $1}' | grep -Fxq "${POLYMETIS_ENV}"; then
    echo "[franka] Reusing micromamba env ${POLYMETIS_ENV}"
else
    echo "[franka] Creating micromamba env ${POLYMETIS_ENV} from FAIRO Polymetis environment.yml"
    POLYMETIS_ENV_FILE="${POLYMETIS_DIR}/polymetis/environment.yml"
    if [[ "${DROID_USE_CONDA_DEFAULTS:-0}" == "1" ]]; then
        micromamba env create -y -n "${POLYMETIS_ENV}" -f "${POLYMETIS_ENV_FILE}"
    else
        FILTERED_ENV_FILE="/tmp/polymetis-environment-no-defaults.yml"
        awk '$0 !~ /^[[:space:]]*-[[:space:]]*defaults[[:space:]]*$/' "${POLYMETIS_ENV_FILE}" > "${FILTERED_ENV_FILE}"
        micromamba env create -y -n "${POLYMETIS_ENV}" \
            --override-channels \
            -c pytorch \
            -c fair-robotics \
            -c aihabitat \
            -c conda-forge \
            -f "${FILTERED_ENV_FILE}"
    fi
fi

set +u
micromamba activate "${POLYMETIS_ENV}"
set -u

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e "${POLYMETIS_DIR}/polymetis"
python -m pip install -e "${DROID_ROOT}"
python -m pip install dm-robotics-moma==0.5.0 --no-deps
python -m pip install dm-robotics-transformations==0.5.0 --no-deps
python -m pip install dm-robotics-agentflow==0.5.0 --no-deps
python -m pip install dm-robotics-geometry==0.5.0 --no-deps
python -m pip install dm-robotics-manipulation==0.5.0 --no-deps
python -m pip install dm-robotics-controllers==0.5.0 --no-deps
python -m pip install -e "${OPENPI_ROOT}/packages/openpi-client"
python -m pip install pyrealsense2 tyro

export CMAKE_PREFIX_PATH="${CONDA_PREFIX}:${CMAKE_PREFIX_PATH:-}"
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${LD_LIBRARY_PATH:-}"
export PREFIX="${CONDA_PREFIX}"

echo "[franka] Building libfranka ${LIBFRANKA_VERSION}"
cd "${POLYMETIS_DIR}"
./scripts/build_libfranka.sh "${LIBFRANKA_VERSION}"

echo "[franka] Building Polymetis with Franka support"
mkdir -p "${POLYMETIS_DIR}/polymetis/build"
cd "${POLYMETIS_DIR}/polymetis/build"
cmake .. \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_FRANKA=ON \
    -DBUILD_TESTS="${BUILD_TESTS}" \
    -DBUILD_DOCS="${BUILD_DOCS}"
cmake --build . --parallel "${BUILD_JOBS}"

CONFIG_SRC="${DROID_ROOT}/config/${ROBOT_TYPE}"
if [[ ! -f "${CONFIG_SRC}/franka_hardware.yaml" || ! -f "${CONFIG_SRC}/franka_panda.yaml" ]]; then
    echo "Missing DROID Franka config files in ${CONFIG_SRC}." >&2
    exit 2
fi

echo "[franka] Installing DROID Franka configs into runtime Polymetis overlay: ${POLYMETIS_CONFIG_OVERLAY}"
mkdir -p "${POLYMETIS_CONFIG_OVERLAY}/robot_client" "${POLYMETIS_CONFIG_OVERLAY}/robot_model"
{
    echo "# @package _global_"
    cat "${CONFIG_SRC}/franka_hardware.yaml"
} > "${POLYMETIS_CONFIG_OVERLAY}/robot_client/${ROBOT_CLIENT_CONFIG}.yaml"
cp "${CONFIG_SRC}/franka_panda.yaml" "${POLYMETIS_CONFIG_OVERLAY}/robot_model/${ROBOT_MODEL_CONFIG}.yaml"

if [[ -n "${DROID_ROBOT_IP:-}" && "${DROID_ROBOT_IP}" != SET_* ]]; then
    python - "${POLYMETIS_CONFIG_OVERLAY}/robot_client/${ROBOT_CLIENT_CONFIG}.yaml" "${DROID_ROBOT_IP}" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
robot_ip = sys.argv[2]
text = path.read_text()
updated = re.sub(r'robot_ip:\s*"[^"]*"', f'robot_ip: "{robot_ip}"', text, count=1)
if updated == text:
    raise SystemExit(f"Could not find robot_ip field in {path}")
path.write_text(updated)
PY
else
    echo "[franka] DROID_ROBOT_IP is unset or still a placeholder; leaving robot_ip from ${CONFIG_SRC}/franka_hardware.yaml"
fi

cat <<EOF
[franka] DROID Polymetis launch config:
  robot_client=${ROBOT_CLIENT_CONFIG}
  robot_model=${ROBOT_MODEL_CONFIG}
  --config-dir ${POLYMETIS_CONFIG_OVERLAY}
EOF

echo "[franka] Running low-level availability check"
/workspace/runtime_scripts/test_polymetis.sh

echo "[franka] FAIRO/Polymetis Franka bootstrap complete"
