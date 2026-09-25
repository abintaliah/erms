#!/usr/bin/env bash
set -Eeuo pipefail

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
if [[ ! -x "${ENVIRONMENT_DIR}/bin/python" ]]; then
    python3 -m venv "${ENVIRONMENT_DIR}"
fi
"${ENVIRONMENT_DIR}/bin/python" -m pip install --disable-pip-version-check --quiet -r "${REQUIREMENTS}"
exec "${ENVIRONMENT_DIR}/bin/python" -m backend.services.text_indexer "$@"
