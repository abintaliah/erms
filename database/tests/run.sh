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
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/004_add_record_drafts.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/005_add_authentication.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/006_enforce_closed_aggregations.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/007_freeze_closed_aggregation_metadata.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/008_cascade_record_digital_components.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/009_user_management_lifecycle.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/010_rename_org_unit_deactivation_date.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/011_normalize_org_unit_event_history.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/012_backfill_anonymous_event_actor.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/013_snapshot_event_actor_identity.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/014_backfill_webui_event_source.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/015_reclassify_lifecycle_normalization_events.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/016_snapshot_role_assignment_parties.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/017_rename_system_accounts_to_service.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/018_rename_system_actor_to_automated_process.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/019_add_classification_schemes.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --single-transaction \
    --file "${DATABASE_DIR}/migrations/022_govern_classification_scheme_deletion.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on \
    --file "${DATABASE_DIR}/migrations/023_govern_classification_lifecycle.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on \
    --file "${DATABASE_DIR}/migrations/026_add_classification_browser_indexes.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on \
    --file "${SCRIPT_DIR}/segmented_content_migration_before.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on \
    --file "${DATABASE_DIR}/migrations/027_segment_postgresql_content.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on \
    --file "${DATABASE_DIR}/migrations/028_add_user_favourites.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on \
    --file "${DATABASE_DIR}/migrations/030_remove_assignment_attribution_and_prepare_user_deletion.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on \
    --file "${SCRIPT_DIR}/segmented_content_migration_after.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --file "${SCRIPT_DIR}/core_records_management.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --file "${SCRIPT_DIR}/event_history.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --file "${SCRIPT_DIR}/user_management.sql"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on --file "${SCRIPT_DIR}/content_storage_and_concurrency.sql"
env DATABASE_URL="${DATABASE_URL}" PYTHONPATH="${PROJECT_DIR}" \
    "${API_VENV}/bin/python" -m pytest "${API_DIR}/tests"

"${API_VENV}/bin/python" "${DATABASE_DIR}/seeds/import_mutamathilah.py" \
    --database-url "${DATABASE_URL}"
psql "${DATABASE_URL}" --set ON_ERROR_STOP=on <<'SQL'
DO $$
DECLARE
    scheme_id bigint;
    correlation_count integer;
BEGIN
    SELECT id INTO STRICT scheme_id
      FROM classification_schemes
     WHERE code = 'USCR-SHJ'
       AND title = 'Unified Scheme for Common Records of the Emirate of Sharjah'
       AND description = 'النظام الموحد للوثائق المتماثلة لإمارة الشارقة'
       AND date_published IS NULL;

    IF (SELECT count(*) FROM classifications WHERE classification_scheme_id=scheme_id) <> 345 THEN
        RAISE EXCEPTION 'Mutamathilah import classification count mismatch';
    END IF;
    IF (SELECT count(*) FROM classifications WHERE classification_scheme_id=scheme_id AND is_terminal) <> 254 THEN
        RAISE EXCEPTION 'Mutamathilah import terminal count mismatch';
    END IF;
    IF EXISTS (
        SELECT 1 FROM classifications
        WHERE classification_scheme_id=scheme_id
          AND (description IS NULL OR btrim(description) = '')
    ) THEN
        RAISE EXCEPTION 'Mutamathilah Arabic description mapping is incomplete';
    END IF;
    SELECT count(DISTINCT correlation_id) INTO correlation_count
      FROM event_history
     WHERE metadata->>'migration' = '025_seed_mutamathilah_classification_scheme';
    IF correlation_count <> 1 THEN
        RAISE EXCEPTION 'Mutamathilah events do not share one correlation id';
    END IF;
    IF (
        SELECT count(*) FROM event_history
        WHERE metadata->>'migration' = '025_seed_mutamathilah_classification_scheme'
          AND source = 'migration'
          AND actor_type = 'automated_process'
    ) <> 600 THEN
        RAISE EXCEPTION 'Mutamathilah audit provenance count mismatch';
    END IF;
END;
$$;
SQL
"${API_VENV}/bin/python" "${DATABASE_DIR}/seeds/import_mutamathilah.py" \
    --database-url "${DATABASE_URL}"

echo "Core records management database and API tests passed."
