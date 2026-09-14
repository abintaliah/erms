#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DATABASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly CONTAINER_NAME="erms-postgres-test-$$"
readonly POSTGRES_IMAGE="${POSTGRES_TEST_IMAGE:-postgres:17-alpine}"
readonly POSTGRES_USER="erms_test"
readonly POSTGRES_PASSWORD="erms_test_password"
readonly POSTGRES_DB="erms_test"

cleanup() {
    docker rm --force "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

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
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --file "${SCRIPT_DIR}/core_records_management.sql"

echo "Core records management database tests passed."
