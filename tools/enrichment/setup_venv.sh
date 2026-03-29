#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROFILE="${1:-captions}"

case "${PROFILE}" in
  captions)
    VENV_DIR="${ROOT_DIR}/.venv"
    REQUIREMENTS_FILE="${ROOT_DIR}/tools/enrichment/requirements.txt"
    ;;
  faces)
    VENV_DIR="${ROOT_DIR}/.venv-faces"
    REQUIREMENTS_FILE="${ROOT_DIR}/tools/enrichment/requirements-faces.txt"
    ;;
  *)
    echo "Unknown profile: ${PROFILE}" >&2
    echo "Usage: bash ./tools/enrichment/setup_venv.sh [captions|faces]" >&2
    exit 1
    ;;
esac

python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "${REQUIREMENTS_FILE}"

echo "Virtualenv ready at ${VENV_DIR}"
echo "Activate with: source ${VENV_DIR#${ROOT_DIR}/}/bin/activate"
