BEGIN;

CREATE TABLE aggregations (
    id                    bigserial PRIMARY KEY,
    parent_aggregation_id bigint REFERENCES aggregations (id) ON DELETE RESTRICT,
    aggregation_number    text NOT NULL UNIQUE,
    title                 text NOT NULL,
    description           text,
    date_created          timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_opened           timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_closed           timestamptz,

    CONSTRAINT aggregations_number_not_blank
        CHECK (btrim(aggregation_number) <> ''),
    CONSTRAINT aggregations_title_not_blank
        CHECK (btrim(title) <> ''),
    CONSTRAINT aggregations_not_own_parent
        CHECK (parent_aggregation_id IS NULL OR parent_aggregation_id <> id),
    CONSTRAINT aggregations_dates_in_order
        CHECK (date_closed IS NULL OR date_closed >= date_opened)
);

CREATE INDEX aggregations_parent_aggregation_id_idx
    ON aggregations (parent_aggregation_id);

CREATE TABLE records (
    id              bigserial PRIMARY KEY,
    aggregation_id  bigint NOT NULL REFERENCES aggregations (id) ON DELETE RESTRICT,
    record_number   text NOT NULL UNIQUE,
    title           text NOT NULL,
    description     text,
    date_created    timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_originated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT records_number_not_blank
        CHECK (btrim(record_number) <> ''),
    CONSTRAINT records_title_not_blank
        CHECK (btrim(title) <> '')
);

CREATE INDEX records_aggregation_id_idx
    ON records (aggregation_id);

CREATE TABLE digital_components (
    id              bigserial PRIMARY KEY,
    record_id       bigint NOT NULL REFERENCES records (id) ON DELETE RESTRICT,
    component_order integer NOT NULL,
    file_name       text NOT NULL,
    date_created    timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_originated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    mime_type       text NOT NULL,
    size_in_bytes   bigint NOT NULL,
    checksum_algo   text NOT NULL,
    checksum_value  text NOT NULL,

    CONSTRAINT digital_components_file_name_not_blank
        CHECK (btrim(file_name) <> ''),
    CONSTRAINT digital_components_order_positive
        CHECK (component_order > 0),
    CONSTRAINT digital_components_mime_type_not_blank
        CHECK (btrim(mime_type) <> ''),
    CONSTRAINT digital_components_size_nonnegative
        CHECK (size_in_bytes >= 0),
    CONSTRAINT digital_components_checksum_algo_not_blank
        CHECK (btrim(checksum_algo) <> ''),
    CONSTRAINT digital_components_checksum_value_not_blank
        CHECK (btrim(checksum_value) <> ''),
    CONSTRAINT digital_components_record_order_unique
        UNIQUE (record_id, component_order)
        DEFERRABLE INITIALLY IMMEDIATE
);

CREATE INDEX digital_components_record_id_idx
    ON digital_components (record_id);

-- DEFAULT applies when a column is omitted, while this trigger also handles an
-- explicitly supplied NULL as requested by the domain rules.
CREATE FUNCTION set_aggregation_default_dates()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.date_created IS NULL THEN
        NEW.date_created := CURRENT_TIMESTAMP;
    END IF;

    IF NEW.date_opened IS NULL THEN
        NEW.date_opened := NEW.date_created;
    END IF;

    RETURN NEW;
END;
$$;

CREATE FUNCTION set_originated_default_dates()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.date_created IS NULL THEN
        NEW.date_created := CURRENT_TIMESTAMP;
    END IF;

    IF NEW.date_originated IS NULL THEN
        NEW.date_originated := NEW.date_created;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER aggregations_set_default_dates
BEFORE INSERT ON aggregations
FOR EACH ROW EXECUTE FUNCTION set_aggregation_default_dates();

CREATE TRIGGER records_set_default_dates
BEFORE INSERT ON records
FOR EACH ROW EXECUTE FUNCTION set_originated_default_dates();

CREATE TRIGGER digital_components_set_default_dates
BEFORE INSERT ON digital_components
FOR EACH ROW EXECUTE FUNCTION set_originated_default_dates();

-- A self-referencing foreign key prevents missing parents but not longer
-- cycles. This trigger preserves a genuine containment hierarchy.
CREATE FUNCTION prevent_aggregation_cycle()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.parent_aggregation_id IS NULL THEN
        RETURN NEW;
    END IF;

    IF EXISTS (
        WITH RECURSIVE ancestors AS (
            SELECT id, parent_aggregation_id
            FROM aggregations
            WHERE id = NEW.parent_aggregation_id

            UNION ALL

            SELECT aggregation.id, aggregation.parent_aggregation_id
            FROM aggregations AS aggregation
            JOIN ancestors ON aggregation.id = ancestors.parent_aggregation_id
        )
        SELECT 1 FROM ancestors WHERE id = NEW.id
    ) THEN
        RAISE EXCEPTION 'aggregation hierarchy cannot contain a cycle';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER aggregations_prevent_cycle
BEFORE INSERT OR UPDATE OF parent_aggregation_id ON aggregations
FOR EACH ROW EXECUTE FUNCTION prevent_aggregation_cycle();

-- The current event-history schema is repeated here intentionally. New
-- databases need only this standard SQL file; existing databases use the
-- numbered migration containing the equivalent upgrade.
CREATE TABLE schema_migrations (
    id         bigserial PRIMARY KEY,
    version    text NOT NULL UNIQUE,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),

    CONSTRAINT schema_migrations_version_not_blank
        CHECK (btrim(version) <> '')
);

CREATE TABLE event_history (
    id              bigserial PRIMARY KEY,
    occurred_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
    transaction_id  bigint NOT NULL DEFAULT (pg_current_xact_id()::text::bigint),
    entity_type     text NOT NULL,
    entity_id       bigint NOT NULL,
    operation       text NOT NULL,
    actor_user_id   bigint,
    actor_type      text NOT NULL DEFAULT 'system',
    source          text NOT NULL DEFAULT 'database',
    request_id      uuid,
    correlation_id  uuid,
    before_state    jsonb,
    after_state     jsonb,
    changed_fields  text[] NOT NULL DEFAULT ARRAY[]::text[],
    reason          text,
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT event_history_entity_type_not_blank
        CHECK (btrim(entity_type) <> ''),
    CONSTRAINT event_history_operation_not_blank
        CHECK (btrim(operation) <> ''),
    CONSTRAINT event_history_actor_type_not_blank
        CHECK (btrim(actor_type) <> ''),
    CONSTRAINT event_history_source_not_blank
        CHECK (btrim(source) <> ''),
    CONSTRAINT event_history_metadata_is_object
        CHECK (jsonb_typeof(metadata) = 'object'),
    CONSTRAINT event_history_row_change_states_valid
        CHECK (
            (operation = 'CREATE' AND before_state IS NULL AND after_state IS NOT NULL)
            OR (operation = 'UPDATE' AND before_state IS NOT NULL AND after_state IS NOT NULL)
            OR (operation = 'DELETE' AND before_state IS NOT NULL AND after_state IS NULL)
            OR operation NOT IN ('CREATE', 'UPDATE', 'DELETE')
        )
);

CREATE INDEX event_history_entity_timeline_idx
    ON event_history (entity_type, entity_id, occurred_at DESC, id DESC);

CREATE INDEX event_history_actor_timeline_idx
    ON event_history (actor_user_id, occurred_at DESC)
    WHERE actor_user_id IS NOT NULL;

CREATE INDEX event_history_request_id_idx
    ON event_history (request_id)
    WHERE request_id IS NOT NULL;

CREATE INDEX event_history_correlation_id_idx
    ON event_history (correlation_id)
    WHERE correlation_id IS NOT NULL;

CREATE INDEX event_history_occurred_at_idx
    ON event_history (occurred_at DESC);

CREATE FUNCTION record_entity_history()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    old_state        jsonb;
    new_state        jsonb;
    entity_key       bigint;
    changed          text[];
    context_user_id  text;
    context_metadata text;
BEGIN
    old_state := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END;
    new_state := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END;
    entity_key := CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END;

    SELECT COALESCE(array_agg(key ORDER BY key), ARRAY[]::text[])
    INTO changed
    FROM (
        SELECT key
        FROM jsonb_object_keys(COALESCE(old_state, '{}'::jsonb) || COALESCE(new_state, '{}'::jsonb)) AS key
        WHERE old_state -> key IS DISTINCT FROM new_state -> key
    ) AS differences;

    context_user_id := NULLIF(current_setting('app.user_id', true), '');
    context_metadata := NULLIF(current_setting('app.event_metadata', true), '');

    INSERT INTO event_history (
        entity_type,
        entity_id,
        operation,
        actor_user_id,
        actor_type,
        source,
        request_id,
        correlation_id,
        before_state,
        after_state,
        changed_fields,
        reason,
        metadata
    )
    VALUES (
        TG_ARGV[0],
        entity_key,
        CASE TG_OP WHEN 'INSERT' THEN 'CREATE' ELSE TG_OP END,
        context_user_id::bigint,
        COALESCE(NULLIF(current_setting('app.actor_type', true), ''), 'system'),
        COALESCE(NULLIF(current_setting('app.event_source', true), ''), 'database'),
        NULLIF(current_setting('app.request_id', true), '')::uuid,
        NULLIF(current_setting('app.correlation_id', true), '')::uuid,
        old_state,
        new_state,
        changed,
        NULLIF(current_setting('app.change_reason', true), ''),
        COALESCE(context_metadata::jsonb, '{}'::jsonb)
    );

    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER aggregations_record_history
AFTER INSERT OR UPDATE OR DELETE ON aggregations
FOR EACH ROW EXECUTE FUNCTION record_entity_history('aggregation');

CREATE TRIGGER records_record_history
AFTER INSERT OR UPDATE OR DELETE ON records
FOR EACH ROW EXECUTE FUNCTION record_entity_history('record');

CREATE TRIGGER digital_components_record_history
AFTER INSERT OR UPDATE OR DELETE ON digital_components
FOR EACH ROW EXECUTE FUNCTION record_entity_history('digital_component');

CREATE FUNCTION reject_event_history_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'event history is immutable';
END;
$$;

CREATE TRIGGER event_history_reject_update_delete
BEFORE UPDATE OR DELETE ON event_history
FOR EACH ROW EXECUTE FUNCTION reject_event_history_mutation();

CREATE TRIGGER event_history_reject_truncate
BEFORE TRUNCATE ON event_history
FOR EACH STATEMENT EXECUTE FUNCTION reject_event_history_mutation();

INSERT INTO schema_migrations (version)
VALUES ('001_add_event_history')
ON CONFLICT (version) DO NOTHING;

-- User management subsystem. The equivalent upgrade for existing databases is
-- database/migrations/002_add_user_management.sql.
CREATE TABLE org_units (
    id                 bigserial PRIMARY KEY,
    parent_org_unit_id bigint REFERENCES org_units (id) ON DELETE RESTRICT,
    code               text NOT NULL,
    name               text NOT NULL,
    description        text,
    status             text NOT NULL DEFAULT 'active',
    date_created       timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_closed        timestamptz,

    CONSTRAINT org_units_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT org_units_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT org_units_status_valid CHECK (status IN ('active', 'inactive')),
    CONSTRAINT org_units_not_own_parent
        CHECK (parent_org_unit_id IS NULL OR parent_org_unit_id <> id),
    CONSTRAINT org_units_dates_in_order
        CHECK (date_closed IS NULL OR date_closed >= date_created)
);

CREATE UNIQUE INDEX org_units_code_ci_unique
    ON org_units (lower(code));
CREATE UNIQUE INDEX org_units_name_ci_unique
    ON org_units (lower(name));
CREATE INDEX org_units_parent_org_unit_id_idx
    ON org_units (parent_org_unit_id);

CREATE TABLE users (
    id               bigserial PRIMARY KEY,
    name             text NOT NULL,
    email            text,
    external_id      text,
    account_type     text NOT NULL DEFAULT 'human',
    status           text NOT NULL DEFAULT 'active',
    date_created     timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_deactivated timestamptz,

    CONSTRAINT users_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT users_email_not_blank CHECK (email IS NULL OR btrim(email) <> ''),
    CONSTRAINT users_external_id_not_blank
        CHECK (external_id IS NULL OR btrim(external_id) <> ''),
    CONSTRAINT users_account_type_valid
        CHECK (account_type IN ('human', 'system')),
    CONSTRAINT users_status_valid
        CHECK (status IN ('active', 'inactive', 'suspended')),
    CONSTRAINT users_dates_in_order
        CHECK (date_deactivated IS NULL OR date_deactivated >= date_created)
);

CREATE UNIQUE INDEX users_email_ci_unique
    ON users (lower(email)) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX users_external_id_unique
    ON users (external_id) WHERE external_id IS NOT NULL;

CREATE TABLE roles (
    id                 bigserial PRIMARY KEY,
    org_unit_id        bigint NOT NULL REFERENCES org_units (id) ON DELETE RESTRICT,
    supervisor_role_id bigint REFERENCES roles (id) ON DELETE RESTRICT,
    code               text NOT NULL,
    name               text NOT NULL,
    description        text,
    status             text NOT NULL DEFAULT 'active',
    date_created       timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_deactivated   timestamptz,

    CONSTRAINT roles_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT roles_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT roles_status_valid CHECK (status IN ('active', 'inactive')),
    CONSTRAINT roles_not_own_supervisor
        CHECK (supervisor_role_id IS NULL OR supervisor_role_id <> id),
    CONSTRAINT roles_dates_in_order
        CHECK (date_deactivated IS NULL OR date_deactivated >= date_created)
);

CREATE UNIQUE INDEX roles_code_ci_unique ON roles (lower(code));
CREATE UNIQUE INDEX roles_name_ci_unique ON roles (lower(name));
CREATE INDEX roles_org_unit_id_idx ON roles (org_unit_id);
CREATE INDEX roles_supervisor_role_id_idx ON roles (supervisor_role_id);

CREATE TABLE user_role_assignments (
    id            bigserial PRIMARY KEY,
    user_id       bigint NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    role_id       bigint NOT NULL REFERENCES roles (id) ON DELETE RESTRICT,
    assigned_by   bigint REFERENCES users (id) ON DELETE RESTRICT,
    date_assigned timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_from    timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_until   timestamptz,

    CONSTRAINT user_role_assignments_dates_in_order
        CHECK (valid_until IS NULL OR valid_until >= valid_from),
    CONSTRAINT user_role_assignments_period_unique
        UNIQUE (user_id, role_id, valid_from)
);

CREATE INDEX user_role_assignments_user_id_idx
    ON user_role_assignments (user_id);
CREATE INDEX user_role_assignments_role_id_idx
    ON user_role_assignments (role_id);
CREATE INDEX user_role_assignments_assigned_by_idx
    ON user_role_assignments (assigned_by) WHERE assigned_by IS NOT NULL;

CREATE TABLE user_credentials (
    id                   bigserial PRIMARY KEY,
    user_id              bigint NOT NULL UNIQUE REFERENCES users (id) ON DELETE CASCADE,
    password_hash        text NOT NULL,
    must_change_password boolean NOT NULL DEFAULT true,
    temporary_expires_at timestamptz,
    password_changed_at  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    failed_attempt_count integer NOT NULL DEFAULT 0,
    last_failed_at       timestamptz,
    locked_until         timestamptz,
    last_authenticated_at timestamptz,
    date_created         timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated         timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT user_credentials_password_hash_not_blank CHECK (btrim(password_hash) <> ''),
    CONSTRAINT user_credentials_failed_attempts_nonnegative CHECK (failed_attempt_count >= 0)
);

CREATE TABLE login_sessions (
    id                  bigserial PRIMARY KEY,
    user_id             bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    session_token_hash  bytea NOT NULL UNIQUE,
    csrf_token_hash     bytea NOT NULL,
    date_created        timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at        timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at          timestamptz NOT NULL,
    absolute_expires_at timestamptz NOT NULL,
    revoked_at          timestamptz,
    revoked_by          bigint REFERENCES users (id) ON DELETE SET NULL,
    client_ip           inet,
    user_agent          text,

    CONSTRAINT login_sessions_expiry_valid CHECK (expires_at > date_created),
    CONSTRAINT login_sessions_absolute_expiry_valid CHECK (absolute_expires_at >= expires_at)
);

CREATE INDEX login_sessions_user_id_idx ON login_sessions (user_id);
CREATE INDEX login_sessions_active_idx
    ON login_sessions (expires_at, absolute_expires_at) WHERE revoked_at IS NULL;

CREATE FUNCTION set_user_management_default_dates()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.date_created IS NULL THEN
        NEW.date_created := CURRENT_TIMESTAMP;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION set_assignment_default_dates()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.date_assigned IS NULL THEN
        NEW.date_assigned := CURRENT_TIMESTAMP;
    END IF;
    IF NEW.valid_from IS NULL THEN
        NEW.valid_from := NEW.date_assigned;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION prevent_org_unit_cycle()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.parent_org_unit_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF EXISTS (
        WITH RECURSIVE ancestors AS (
            SELECT id, parent_org_unit_id
            FROM org_units WHERE id = NEW.parent_org_unit_id
            UNION ALL
            SELECT parent.id, parent.parent_org_unit_id
            FROM org_units AS parent
            JOIN ancestors ON parent.id = ancestors.parent_org_unit_id
        )
        SELECT 1 FROM ancestors WHERE id = NEW.id
    ) THEN
        RAISE EXCEPTION 'organizational unit hierarchy cannot contain a cycle';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION prevent_role_supervision_cycle()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.supervisor_role_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF EXISTS (
        WITH RECURSIVE supervisors AS (
            SELECT id, supervisor_role_id
            FROM roles WHERE id = NEW.supervisor_role_id
            UNION ALL
            SELECT supervisor.id, supervisor.supervisor_role_id
            FROM roles AS supervisor
            JOIN supervisors ON supervisor.id = supervisors.supervisor_role_id
        )
        SELECT 1 FROM supervisors WHERE id = NEW.id
    ) THEN
        RAISE EXCEPTION 'role supervision hierarchy cannot contain a cycle';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER org_units_set_default_dates
BEFORE INSERT ON org_units
FOR EACH ROW EXECUTE FUNCTION set_user_management_default_dates();

CREATE TRIGGER users_set_default_dates
BEFORE INSERT ON users
FOR EACH ROW EXECUTE FUNCTION set_user_management_default_dates();

CREATE TRIGGER roles_set_default_dates
BEFORE INSERT ON roles
FOR EACH ROW EXECUTE FUNCTION set_user_management_default_dates();

CREATE TRIGGER user_role_assignments_set_default_dates
BEFORE INSERT ON user_role_assignments
FOR EACH ROW EXECUTE FUNCTION set_assignment_default_dates();

CREATE TRIGGER org_units_prevent_cycle
BEFORE INSERT OR UPDATE OF parent_org_unit_id ON org_units
FOR EACH ROW EXECUTE FUNCTION prevent_org_unit_cycle();

CREATE TRIGGER roles_prevent_supervision_cycle
BEFORE INSERT OR UPDATE OF supervisor_role_id ON roles
FOR EACH ROW EXECUTE FUNCTION prevent_role_supervision_cycle();

CREATE TRIGGER org_units_record_history
AFTER INSERT OR UPDATE OR DELETE ON org_units
FOR EACH ROW EXECUTE FUNCTION record_entity_history('org_unit');

CREATE TRIGGER users_record_history
AFTER INSERT OR UPDATE OR DELETE ON users
FOR EACH ROW EXECUTE FUNCTION record_entity_history('user');

CREATE TRIGGER roles_record_history
AFTER INSERT OR UPDATE OR DELETE ON roles
FOR EACH ROW EXECUTE FUNCTION record_entity_history('role');

CREATE TRIGGER user_role_assignments_record_history
AFTER INSERT OR UPDATE OR DELETE ON user_role_assignments
FOR EACH ROW EXECUTE FUNCTION record_entity_history('user_role_assignment');

INSERT INTO schema_migrations (version)
VALUES ('002_add_user_management')
ON CONFLICT (version) DO NOTHING;

-- Open record drafts stage metadata and binary content until the user commits
-- the complete record package. The equivalent upgrade is migration 004.
CREATE TABLE IF NOT EXISTS record_drafts (
    id bigserial PRIMARY KEY,
    owner_user_id bigint REFERENCES users (id) ON DELETE RESTRICT,
    aggregation_id bigint REFERENCES aggregations (id) ON DELETE RESTRICT,
    record_number text,
    title text,
    description text,
    date_originated timestamptz,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL DEFAULT (CURRENT_TIMESTAMP + interval '7 days'),
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'committed')),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0)
);
CREATE INDEX IF NOT EXISTS record_drafts_owner_user_id_idx ON record_drafts (owner_user_id);
CREATE INDEX IF NOT EXISTS record_drafts_expires_at_idx ON record_drafts (expires_at);

CREATE TABLE IF NOT EXISTS record_draft_components (
    id bigserial PRIMARY KEY,
    draft_id bigint NOT NULL REFERENCES record_drafts (id) ON DELETE CASCADE,
    component_order integer NOT NULL CHECK (component_order > 0),
    file_name text NOT NULL CHECK (btrim(file_name) <> ''),
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_originated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    mime_type text NOT NULL,
    size_in_bytes bigint NOT NULL CHECK (size_in_bytes >= 0),
    checksum_algo text NOT NULL,
    checksum_value text NOT NULL,
    content bytea NOT NULL,
    CONSTRAINT record_draft_components_draft_order_unique
        UNIQUE (draft_id, component_order) DEFERRABLE INITIALLY IMMEDIATE
);
CREATE INDEX IF NOT EXISTS record_draft_components_draft_id_idx ON record_draft_components (draft_id);

CREATE OR REPLACE FUNCTION touch_record_draft() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.date_updated := CURRENT_TIMESTAMP;
    NEW.version := OLD.version + 1;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS record_drafts_touch ON record_drafts;
CREATE TRIGGER record_drafts_touch BEFORE UPDATE ON record_drafts
FOR EACH ROW EXECUTE FUNCTION touch_record_draft();

INSERT INTO schema_migrations (version) VALUES ('004_add_record_drafts')
ON CONFLICT (version) DO NOTHING;

-- Binary content storage and optimistic concurrency. The equivalent upgrade
-- for existing databases is migration 003.
ALTER TABLE aggregations ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 1;
ALTER TABLE records ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 1;
ALTER TABLE digital_components ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 1;
ALTER TABLE org_units ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 1;
ALTER TABLE roles ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 1;
ALTER TABLE user_role_assignments ADD COLUMN IF NOT EXISTS version bigint NOT NULL DEFAULT 1;

ALTER TABLE aggregations DROP CONSTRAINT IF EXISTS aggregations_version_positive;
ALTER TABLE aggregations ADD CONSTRAINT aggregations_version_positive CHECK (version > 0);
ALTER TABLE records DROP CONSTRAINT IF EXISTS records_version_positive;
ALTER TABLE records ADD CONSTRAINT records_version_positive CHECK (version > 0);
ALTER TABLE digital_components DROP CONSTRAINT IF EXISTS digital_components_version_positive;
ALTER TABLE digital_components ADD CONSTRAINT digital_components_version_positive CHECK (version > 0);
ALTER TABLE org_units DROP CONSTRAINT IF EXISTS org_units_version_positive;
ALTER TABLE org_units ADD CONSTRAINT org_units_version_positive CHECK (version > 0);
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_version_positive;
ALTER TABLE users ADD CONSTRAINT users_version_positive CHECK (version > 0);
ALTER TABLE roles DROP CONSTRAINT IF EXISTS roles_version_positive;
ALTER TABLE roles ADD CONSTRAINT roles_version_positive CHECK (version > 0);
ALTER TABLE user_role_assignments DROP CONSTRAINT IF EXISTS user_role_assignments_version_positive;
ALTER TABLE user_role_assignments ADD CONSTRAINT user_role_assignments_version_positive CHECK (version > 0);

ALTER TABLE digital_components
    ADD COLUMN IF NOT EXISTS storage_backend text NOT NULL DEFAULT 'postgresql',
    ADD COLUMN IF NOT EXISTS storage_key text,
    ADD COLUMN IF NOT EXISTS content_status text NOT NULL DEFAULT 'pending';

ALTER TABLE digital_components DROP CONSTRAINT IF EXISTS digital_components_storage_backend_valid;
ALTER TABLE digital_components ADD CONSTRAINT digital_components_storage_backend_valid
    CHECK (storage_backend IN ('postgresql', 's3'));
ALTER TABLE digital_components DROP CONSTRAINT IF EXISTS digital_components_content_status_valid;
ALTER TABLE digital_components ADD CONSTRAINT digital_components_content_status_valid
    CHECK (content_status IN ('pending', 'available', 'failed', 'quarantined', 'deleted'));
ALTER TABLE digital_components DROP CONSTRAINT IF EXISTS digital_components_storage_location_valid;
ALTER TABLE digital_components ADD CONSTRAINT digital_components_storage_location_valid
    CHECK (
        (storage_backend = 'postgresql' AND storage_key IS NULL)
        OR (storage_backend = 's3' AND storage_key IS NOT NULL AND btrim(storage_key) <> '')
    );

CREATE TABLE IF NOT EXISTS digital_component_blobs (
    digital_component_id bigint PRIMARY KEY
        REFERENCES digital_components (id) ON DELETE CASCADE,
    content              bytea NOT NULL,
    date_stored          timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE FUNCTION bump_entity_version()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.version := OLD.version + 1;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS aggregations_bump_version ON aggregations;
CREATE TRIGGER aggregations_bump_version
BEFORE UPDATE ON aggregations
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();

DROP TRIGGER IF EXISTS records_bump_version ON records;
CREATE TRIGGER records_bump_version
BEFORE UPDATE ON records
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();

DROP TRIGGER IF EXISTS digital_components_bump_version ON digital_components;
CREATE TRIGGER digital_components_bump_version
BEFORE UPDATE ON digital_components
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();

DROP TRIGGER IF EXISTS org_units_bump_version ON org_units;
CREATE TRIGGER org_units_bump_version
BEFORE UPDATE ON org_units
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();

DROP TRIGGER IF EXISTS users_bump_version ON users;
CREATE TRIGGER users_bump_version
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();

DROP TRIGGER IF EXISTS roles_bump_version ON roles;
CREATE TRIGGER roles_bump_version
BEFORE UPDATE ON roles
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();

DROP TRIGGER IF EXISTS user_role_assignments_bump_version ON user_role_assignments;
CREATE TRIGGER user_role_assignments_bump_version
BEFORE UPDATE ON user_role_assignments
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();

CREATE OR REPLACE FUNCTION remove_internal_audit_fields()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.changed_fields := array_remove(NEW.changed_fields, 'version');
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS event_history_remove_internal_fields ON event_history;
CREATE TRIGGER event_history_remove_internal_fields
BEFORE INSERT ON event_history
FOR EACH ROW EXECUTE FUNCTION remove_internal_audit_fields();

CREATE OR REPLACE FUNCTION append_domain_event(
    event_entity_type text,
    event_entity_id bigint,
    event_operation text,
    event_metadata jsonb DEFAULT '{}'::jsonb,
    event_reason text DEFAULT NULL
)
RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    event_id         bigint;
    context_user_id text;
BEGIN
    IF btrim(event_entity_type) = '' OR btrim(event_operation) = '' THEN
        RAISE EXCEPTION 'domain event entity type and operation cannot be blank';
    END IF;
    IF jsonb_typeof(event_metadata) <> 'object' THEN
        RAISE EXCEPTION 'domain event metadata must be a JSON object';
    END IF;

    context_user_id := NULLIF(current_setting('app.user_id', true), '');
    INSERT INTO event_history (
        entity_type,
        entity_id,
        operation,
        actor_user_id,
        actor_type,
        source,
        request_id,
        correlation_id,
        reason,
        metadata
    )
    VALUES (
        event_entity_type,
        event_entity_id,
        event_operation,
        context_user_id::bigint,
        COALESCE(NULLIF(current_setting('app.actor_type', true), ''), 'system'),
        COALESCE(NULLIF(current_setting('app.event_source', true), ''), 'database'),
        NULLIF(current_setting('app.request_id', true), '')::uuid,
        NULLIF(current_setting('app.correlation_id', true), '')::uuid,
        COALESCE(event_reason, NULLIF(current_setting('app.change_reason', true), '')),
        event_metadata
    )
    RETURNING id INTO event_id;
    RETURN event_id;
END;
$$;

INSERT INTO schema_migrations (version)
VALUES ('003_add_content_storage_and_entity_versions')
ON CONFLICT (version) DO NOTHING;

INSERT INTO schema_migrations (version)
VALUES ('005_add_authentication')
ON CONFLICT (version) DO NOTHING;

COMMIT;
