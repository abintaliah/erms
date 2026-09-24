#!/usr/bin/env bash
set -Eeuo pipefail

readonly PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ENV_FILE="${PROJECT_DIR}/.env"

# Load project-local defaults before resolving the stack configuration. Keep
# values explicitly exported by the invoking environment authoritative, which
# matches the override=False behavior used by the API and web UI.
if [[ -f "${PROJECT_ENV_FILE}" ]]; then
    INHERITED_EXPORTED_ENVIRONMENT="$(export -p)"
    ALLEXPORT_WAS_ENABLED=false
    if [[ "$-" == *a* ]]; then
        ALLEXPORT_WAS_ENABLED=true
    fi
    set -a
    # shellcheck disable=SC1090
    source "${PROJECT_ENV_FILE}"
    if [[ "${ALLEXPORT_WAS_ENABLED}" == false ]]; then
        set +a
    fi
    eval "${INHERITED_EXPORTED_ENVIRONMENT}"
    unset INHERITED_EXPORTED_ENVIRONMENT ALLEXPORT_WAS_ENABLED
fi

readonly STACK_DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@127.0.0.1:5433/erms}"
readonly STACK_DB_CONTAINER="${ERMS_LOCAL_DB_CONTAINER:-erms-postgres-local}"
readonly STACK_DB_VOLUME="${ERMS_LOCAL_DB_VOLUME:-erms-postgres-local-data}"
readonly STACK_DB_IMAGE="${ERMS_LOCAL_DB_IMAGE:-postgres:17-alpine}"
readonly STACK_DB_PORT="${ERMS_LOCAL_DB_PORT:-5433}"
readonly STACK_API_URL="${WEBUI_API_URL:-http://127.0.0.1:8000}"
readonly STACK_UI_URL="${ERMS_LOCAL_UI_URL:-http://127.0.0.1:8080}"

API_PID=""
UI_PID=""
MANAGED_DATABASE=false

cleanup() {
    local exit_code=$?
    trap - EXIT INT TERM

    if [[ -n "${UI_PID}" ]] && kill -0 "${UI_PID}" 2>/dev/null; then
        kill "${UI_PID}" 2>/dev/null || true
        wait "${UI_PID}" 2>/dev/null || true
    fi
    if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
        kill "${API_PID}" 2>/dev/null || true
        wait "${API_PID}" 2>/dev/null || true
    fi
    if [[ "${MANAGED_DATABASE}" == true ]]; then
        echo "Stopping local PostgreSQL container (data remains in ${STACK_DB_VOLUME})"
        docker stop "${STACK_DB_CONTAINER}" >/dev/null 2>&1 || true
    fi
    exit "${exit_code}"
}
trap cleanup EXIT INT TERM

for command_name in docker curl psql; do
    if ! command -v "${command_name}" >/dev/null 2>&1; then
        echo "${command_name} is required to run the local stack." >&2
        exit 1
    fi
done

database_ready() {
    psql "${STACK_DATABASE_URL}" -v ON_ERROR_STOP=1 -Atc "SELECT 1" >/dev/null 2>&1
}

http_ready() {
    curl --fail --silent --max-time 2 "$1" >/dev/null 2>&1
}

wait_for_database() {
    local attempt
    for attempt in $(seq 1 45); do
        if database_ready; then
            return 0
        fi
        sleep 1
    done
    echo "PostgreSQL did not become ready within 45 seconds." >&2
    return 1
}

wait_for_http() {
    local name="$1"
    local url="$2"
    local attempt
    for attempt in $(seq 1 60); do
        if http_ready "${url}"; then
            return 0
        fi
        sleep 1
    done
    echo "${name} did not become ready at ${url} within 60 seconds." >&2
    return 1
}

start_database() {
    if database_ready; then
        echo "Using PostgreSQL already available through DATABASE_URL."
        return
    fi

    readonly DEFAULT_LOCAL_URL="postgresql://postgres:postgres@127.0.0.1:${STACK_DB_PORT}/erms"
    if [[ "${STACK_DATABASE_URL}" != "${DEFAULT_LOCAL_URL}" ]]; then
        echo "DATABASE_URL is not reachable: ${STACK_DATABASE_URL}" >&2
        echo "Automatic PostgreSQL startup is limited to the default local-stack URL." >&2
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        echo "Docker is not running and PostgreSQL is not reachable." >&2
        exit 1
    fi

    if docker container inspect "${STACK_DB_CONTAINER}" >/dev/null 2>&1; then
        echo "Starting existing local PostgreSQL container."
        docker start "${STACK_DB_CONTAINER}" >/dev/null
    else
        echo "Creating local PostgreSQL container and persistent volume."
        docker run --detach \
            --name "${STACK_DB_CONTAINER}" \
            --env POSTGRES_USER=postgres \
            --env POSTGRES_PASSWORD=postgres \
            --env POSTGRES_DB=erms \
            --publish "127.0.0.1:${STACK_DB_PORT}:5432" \
            --volume "${STACK_DB_VOLUME}:/var/lib/postgresql/data" \
            --volume "${PROJECT_DIR}/database/schema.sql:/docker-entrypoint-initdb.d/001-schema.sql:ro" \
            "${STACK_DB_IMAGE}" >/dev/null
    fi
    MANAGED_DATABASE=true
    wait_for_database
}

export DATABASE_URL="${STACK_DATABASE_URL}"
export WEBUI_API_URL="${STACK_API_URL}"

start_database

if http_ready "${STACK_API_URL}/health"; then
    echo "Using API already running at ${STACK_API_URL}."
else
    echo "Starting FastAPI service."
    "${PROJECT_DIR}/run-api.sh" &
    API_PID=$!
    wait_for_http "API" "${STACK_API_URL}/health"
fi

if http_ready "${STACK_UI_URL}"; then
    echo "Using web UI already running at ${STACK_UI_URL}."
else
    echo "Starting NiceGUI web frontend."
    "${PROJECT_DIR}/run-webui.sh" &
    UI_PID=$!
    wait_for_http "Web UI" "${STACK_UI_URL}"
fi

echo
echo "ERMS local stack is ready:"
echo "  Web UI:  ${STACK_UI_URL}"
echo "  API:     ${STACK_API_URL}"
echo "  API docs:${STACK_API_URL}/docs"
echo "Press Ctrl-C to stop services started by this script."

while true; do
    if [[ -n "${API_PID}" ]] && ! kill -0 "${API_PID}" 2>/dev/null; then
        wait "${API_PID}" || true
        echo "The API process stopped unexpectedly." >&2
        exit 1
    fi
    if [[ -n "${UI_PID}" ]] && ! kill -0 "${UI_PID}" 2>/dev/null; then
        wait "${UI_PID}" || true
        echo "The web UI process stopped unexpectedly." >&2
        exit 1
    fi
    sleep 1
done
