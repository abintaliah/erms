#!/usr/bin/env bash
set -Eeuo pipefail

# Existing terminal sessions may predate Homebrew installation.
# Append standard macOS tool locations while preserving explicit PATH priority.
if [[ "$(uname -s)" == Darwin ]]; then
    for tool_directory in /opt/homebrew/bin /usr/local/bin; do
        if [[ -d "${tool_directory}" && ":${PATH}:" != *":${tool_directory}:"* ]]; then
            export PATH="${PATH}:${tool_directory}"
        fi
    done
    unset tool_directory
fi

readonly PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly ENVIRONMENT_DIR="${PROJECT_DIR}/.venv-text-indexer"
readonly REQUIREMENTS="${PROJECT_DIR}/backend/services/text_indexer/requirements.txt"

if [[ -f "${PROJECT_DIR}/.env" ]]; then
    INHERITED_EXPORTED_ENVIRONMENT="$(export -p)"
    ALLEXPORT_WAS_ENABLED=false
    if [[ "$-" == *a* ]]; then
        ALLEXPORT_WAS_ENABLED=true
    fi
    set -a
    # shellcheck disable=SC1091
    source "${PROJECT_DIR}/.env"
    if [[ "${ALLEXPORT_WAS_ENABLED}" == false ]]; then
        set +a
    fi
    eval "${INHERITED_EXPORTED_ENVIRONMENT}"
    unset INHERITED_EXPORTED_ENVIRONMENT ALLEXPORT_WAS_ENABLED
fi
for required in TEXT_INDEXER_API_URL TEXT_INDEXER_API_KEY TEXT_INDEXER_TIKA_HOME; do
    if [[ -z "${!required:-}" ]]; then
        echo "${required} is required." >&2
        exit 1
    fi
done
if [[ ! -x "${ENVIRONMENT_DIR}/bin/python" ]] || ! "${ENVIRONMENT_DIR}/bin/python" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    INDEXER_PYTHON="${PYTHON_BOOTSTRAP:-${ERMS_API_VENV:-${PROJECT_DIR}/backend/services/api/.venv}/bin/python}"
    if [[ ! -x "${INDEXER_PYTHON}" ]] && ! command -v "${INDEXER_PYTHON}" >/dev/null 2>&1; then
        INDEXER_PYTHON=python3
    fi
    if ! "${INDEXER_PYTHON}" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
        echo "The text indexer requires Python 3.11 or newer. Set PYTHON_BOOTSTRAP to a supported Python interpreter." >&2
        exit 1
    fi
    echo "Preparing text-indexer environment with ${INDEXER_PYTHON}."
    "${INDEXER_PYTHON}" -m venv --clear "${ENVIRONMENT_DIR}"
fi
"${ENVIRONMENT_DIR}/bin/python" -m pip install --disable-pip-version-check --quiet -r "${REQUIREMENTS}"
exec "${ENVIRONMENT_DIR}/bin/python" -m backend.services.text_indexer "$@"
