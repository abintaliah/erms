#!/usr/bin/env bash
set -Eeuo pipefail

readonly PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly API_DIR="${PROJECT_DIR}/backend/services/api"
readonly REQUIREMENTS_FILE="${API_DIR}/requirements.txt"
readonly VENV_DIR="${ERMS_API_VENV:-${API_DIR}/.venv}"
readonly PYTHON_BOOTSTRAP="${PYTHON_BOOTSTRAP:-python3}"
readonly DEPENDENCY_STAMP="${VENV_DIR}/.requirements-checksum"

if ! command -v "${PYTHON_BOOTSTRAP}" >/dev/null 2>&1; then
    echo "Python 3.11 or newer is required." >&2
    exit 1
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    echo "Creating API virtual environment at ${VENV_DIR}"
    "${PYTHON_BOOTSTRAP}" -m venv "${VENV_DIR}"
fi

readonly CURRENT_CHECKSUM="$(cksum "${REQUIREMENTS_FILE}")"
INSTALLED_CHECKSUM=""
if [[ -f "${DEPENDENCY_STAMP}" ]]; then
    INSTALLED_CHECKSUM="$(<"${DEPENDENCY_STAMP}")"
fi

if [[ "${CURRENT_CHECKSUM}" != "${INSTALLED_CHECKSUM}" ]]; then
    echo "Installing API runtime dependencies"
    "${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check \
        --requirement "${REQUIREMENTS_FILE}"
    printf '%s\n' "${CURRENT_CHECKSUM}" >"${DEPENDENCY_STAMP}"
fi

cd "${PROJECT_DIR}"
exec "${VENV_DIR}/bin/python" -m backend.services.api.launcher
