#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DATABASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly PROJECT_DIR="$(cd "${DATABASE_DIR}/.." && pwd)"
readonly API_DIR="${PROJECT_DIR}/backend/services/api"
readonly API_VENV="${ERMS_API_VENV:-${API_DIR}/.venv}"
readonly TEST_REQUIREMENTS="${API_DIR}/requirements-test.txt"
readonly TEST_DEPENDENCY_STAMP="${API_VENV}/.test-requirements-checksum"
readonly CONTAINER_NAME="erms-postgres-test-$$"
readonly POSTGRES_IMAGE="${POSTGRES_TEST_IMAGE:-postgres:17-alpine}"
readonly POSTGRES_USER="erms_test"
readonly POSTGRES_PASSWORD="erms_test_password"
readonly POSTGRES_DB="erms_test"

cleanup() {
    local exit_code=$?
    trap - EXIT INT TERM
    docker rm --force "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    exit "${exit_code}"
}
trap cleanup EXIT INT TERM

if [[ ! -x "${API_VENV}/bin/python" ]]; then
    python3 -m venv "${API_VENV}"
fi

readonly CURRENT_TEST_CHECKSUM="$(cksum "${API_DIR}/requirements.txt" "${TEST_REQUIREMENTS}")"
INSTALLED_TEST_CHECKSUM=""
if [[ -f "${TEST_DEPENDENCY_STAMP}" ]]; then
    INSTALLED_TEST_CHECKSUM="$(<"${TEST_DEPENDENCY_STAMP}")"
fi

if [[ "${CURRENT_TEST_CHECKSUM}" != "${INSTALLED_TEST_CHECKSUM}" ]]; then
    "${API_VENV}/bin/python" -m pip install --disable-pip-version-check \
        --requirement "${TEST_REQUIREMENTS}"
    printf '%s\n' "${CURRENT_TEST_CHECKSUM}" >"${TEST_DEPENDENCY_STAMP}"
fi

docker run \
    --detach \
    --rm \
    --name "${CONTAINER_NAME}" \
    --env POSTGRES_USER="${POSTGRES_USER}" \
    --env POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
    --env POSTGRES_DB="${POSTGRES_DB}" \
    --publish 127.0.0.1::5432 \
    "${POSTGRES_IMAGE}" >/dev/null

for attempt in $(seq 1 30); do
    if docker exec "${CONTAINER_NAME}" \
        pg_isready --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" >/dev/null 2>&1; then
        break
    fi

    if [[ "${attempt}" -eq 30 ]]; then
        docker logs "${CONTAINER_NAME}"
        echo "PostgreSQL did not become ready in time" >&2
        exit 1
    fi

    sleep 1
done

readonly HOST_PORT="$(docker port "${CONTAINER_NAME}" 5432/tcp | sed 's/.*://')"
readonly DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${HOST_PORT}/${POSTGRES_DB}"

psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --file "${DATABASE_DIR}/schema.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on \
    --file "${SCRIPT_DIR}/reset_to_pre_event_history.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/001_add_event_history.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/002_add_user_management.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/003_add_content_storage_and_entity_versions.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --file "${SCRIPT_DIR}/core_records_management.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --file "${SCRIPT_DIR}/event_history.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --file "${SCRIPT_DIR}/user_management.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --file "${SCRIPT_DIR}/content_storage_and_concurrency.sql"
env DATABASE_URL="${DATABASE_URL}" PYTHONPATH="${PROJECT_DIR}" \
    "${API_VENV}/bin/python" -m pytest "${API_DIR}/tests"

echo "Core records management database and API tests passed."
