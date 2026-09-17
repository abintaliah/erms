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
    record_id       bigint NOT NULL REFERENCES records (id) ON DELETE CASCADE,
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
    actor_name      text,
    actor_email     text,
    actor_type      text NOT NULL DEFAULT 'automated_process',
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
    CONSTRAINT event_history_actor_type_valid
        CHECK (actor_type IN ('user', 'anonymous', 'automated_process')),
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

CREATE FUNCTION populate_event_actor_snapshot()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    stored_name  text;
    stored_email text;
BEGIN
    IF NEW.actor_user_id IS NULL THEN
        RETURN NEW;
    END IF;

    IF NEW.actor_name IS NULL OR NEW.actor_email IS NULL THEN
        SELECT name, email INTO stored_name, stored_email
        FROM users
        WHERE id = NEW.actor_user_id;
    END IF;

    NEW.actor_name := COALESCE(
        NEW.actor_name,
        NULLIF(current_setting('app.actor_name', true), ''),
        stored_name
    );
    NEW.actor_email := COALESCE(
        NEW.actor_email,
        NULLIF(current_setting('app.actor_email', true), ''),
        stored_email
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER event_history_populate_actor_snapshot
BEFORE INSERT ON event_history
FOR EACH ROW EXECUTE FUNCTION populate_event_actor_snapshot();

CREATE FUNCTION populate_event_relationship_snapshot()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    assignment_state jsonb;
    user_snapshot     jsonb;
    role_snapshot     jsonb;
BEGIN
    IF NEW.entity_type <> 'user_role_assignment' THEN
        RETURN NEW;
    END IF;

    assignment_state := COALESCE(NEW.after_state, NEW.before_state);
    SELECT jsonb_build_object('id', id, 'name', name, 'email', email)
    INTO user_snapshot
    FROM users
    WHERE id = (assignment_state ->> 'user_id')::bigint;

    SELECT jsonb_build_object('id', id, 'code', code, 'name', name)
    INTO role_snapshot
    FROM roles
    WHERE id = (assignment_state ->> 'role_id')::bigint;

    NEW.metadata := NEW.metadata || jsonb_build_object(
        'assignment_parties',
        jsonb_build_object('user', user_snapshot, 'role', role_snapshot)
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER event_history_populate_relationship_snapshot
BEFORE INSERT ON event_history
FOR EACH ROW EXECUTE FUNCTION populate_event_relationship_snapshot();

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
        COALESCE(NULLIF(current_setting('app.actor_type', true), ''), 'automated_process'),
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
    date_deactivated   timestamptz,

    CONSTRAINT org_units_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT org_units_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT org_units_status_valid CHECK (status IN ('active', 'inactive')),
    CONSTRAINT org_units_not_own_parent
        CHECK (parent_org_unit_id IS NULL OR parent_org_unit_id <> id),
    CONSTRAINT org_units_dates_in_order
        CHECK (date_deactivated IS NULL OR date_deactivated >= date_created)
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
        CHECK (account_type IN ('human', 'service')),
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
        COALESCE(NULLIF(current_setting('app.actor_type', true), ''), 'automated_process'),
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

-- Enforce inherited aggregation closure across records, components and blobs.
CREATE OR REPLACE FUNCTION assert_aggregation_effectively_open(p_aggregation_id bigint)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    blocker record;
BEGIN
    IF p_aggregation_id IS NULL THEN
        RETURN;
    END IF;

    -- Lock every ancestor in a stable order. Closing or reparenting an ancestor
    -- must wait for in-flight content changes, and vice versa.
    PERFORM 1
    FROM aggregations AS locked
    WHERE locked.id IN (
        WITH RECURSIVE ancestors AS (
            SELECT id, parent_aggregation_id
            FROM aggregations
            WHERE id = p_aggregation_id
            UNION ALL
            SELECT parent.id, parent.parent_aggregation_id
            FROM aggregations AS parent
            JOIN ancestors ON parent.id = ancestors.parent_aggregation_id
        )
        SELECT id FROM ancestors
    )
    ORDER BY locked.id
    FOR SHARE;

    WITH RECURSIVE ancestors AS (
        SELECT id, parent_aggregation_id, aggregation_number, title, date_closed, 0 AS depth
        FROM aggregations
        WHERE id = p_aggregation_id
        UNION ALL
        SELECT parent.id, parent.parent_aggregation_id, parent.aggregation_number,
               parent.title, parent.date_closed, child.depth + 1
        FROM aggregations AS parent
        JOIN ancestors AS child ON parent.id = child.parent_aggregation_id
    )
    SELECT id, aggregation_number, title, date_closed
    INTO blocker
    FROM ancestors
    WHERE date_closed IS NOT NULL
    ORDER BY depth
    LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = format(
                'aggregation %s (%s) is closed by aggregation %s (%s); records and digital content in this subtree are immutable',
                p_aggregation_id,
                (SELECT aggregation_number FROM aggregations WHERE id = p_aggregation_id),
                blocker.id,
                blocker.aggregation_number
            );
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION validate_aggregation_closure_date()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.date_closed IS NOT NULL AND NEW.date_closed > CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'date_closed cannot be in the future';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION protect_closed_aggregation_hierarchy()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.parent_aggregation_id IS NOT NULL THEN
            PERFORM assert_aggregation_effectively_open(NEW.parent_aggregation_id);
        END IF;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM assert_aggregation_effectively_open(OLD.id);
        RETURN OLD;
    END IF;

    IF NEW.parent_aggregation_id IS DISTINCT FROM OLD.parent_aggregation_id THEN
        PERFORM assert_aggregation_effectively_open(OLD.id);
        IF NEW.parent_aggregation_id IS NOT NULL THEN
            PERFORM assert_aggregation_effectively_open(NEW.parent_aggregation_id);
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION protect_record_in_closed_aggregation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM assert_aggregation_effectively_open(NEW.aggregation_id);
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM assert_aggregation_effectively_open(OLD.aggregation_id);
        RETURN OLD;
    END IF;

    PERFORM assert_aggregation_effectively_open(OLD.aggregation_id);
    IF NEW.aggregation_id IS DISTINCT FROM OLD.aggregation_id THEN
        PERFORM assert_aggregation_effectively_open(NEW.aggregation_id);
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION assert_record_effectively_open(p_record_id bigint)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    aggregation_key bigint;
BEGIN
    SELECT aggregation_id
    INTO aggregation_key
    FROM records
    WHERE id = p_record_id
    FOR SHARE;

    IF aggregation_key IS NOT NULL THEN
        PERFORM assert_aggregation_effectively_open(aggregation_key);
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION protect_component_in_closed_aggregation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM assert_record_effectively_open(NEW.record_id);
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM assert_record_effectively_open(OLD.record_id);
        RETURN OLD;
    END IF;

    PERFORM assert_record_effectively_open(OLD.record_id);
    IF NEW.record_id IS DISTINCT FROM OLD.record_id THEN
        PERFORM assert_record_effectively_open(NEW.record_id);
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION protect_blob_in_closed_aggregation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM assert_record_effectively_open(
            (SELECT record_id FROM digital_components WHERE id = NEW.digital_component_id)
        );
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM assert_record_effectively_open(
            (SELECT record_id FROM digital_components WHERE id = OLD.digital_component_id)
        );
        RETURN OLD;
    END IF;

    PERFORM assert_record_effectively_open(
        (SELECT record_id FROM digital_components WHERE id = OLD.digital_component_id)
    );
    IF NEW.digital_component_id IS DISTINCT FROM OLD.digital_component_id THEN
        PERFORM assert_record_effectively_open(
            (SELECT record_id FROM digital_components WHERE id = NEW.digital_component_id)
        );
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS aggregations_validate_closure_date ON aggregations;
CREATE TRIGGER aggregations_validate_closure_date
BEFORE INSERT OR UPDATE OF date_closed ON aggregations
FOR EACH ROW EXECUTE FUNCTION validate_aggregation_closure_date();

DROP TRIGGER IF EXISTS aggregations_protect_closed_hierarchy ON aggregations;
CREATE TRIGGER aggregations_protect_closed_hierarchy
BEFORE INSERT OR UPDATE OF parent_aggregation_id OR DELETE ON aggregations
FOR EACH ROW EXECUTE FUNCTION protect_closed_aggregation_hierarchy();

DROP TRIGGER IF EXISTS records_protect_closed_aggregation ON records;
CREATE TRIGGER records_protect_closed_aggregation
BEFORE INSERT OR UPDATE OR DELETE ON records
FOR EACH ROW EXECUTE FUNCTION protect_record_in_closed_aggregation();

DROP TRIGGER IF EXISTS digital_components_protect_closed_aggregation ON digital_components;
CREATE TRIGGER digital_components_protect_closed_aggregation
BEFORE INSERT OR UPDATE OR DELETE ON digital_components
FOR EACH ROW EXECUTE FUNCTION protect_component_in_closed_aggregation();

DROP TRIGGER IF EXISTS digital_component_blobs_protect_closed_aggregation ON digital_component_blobs;
CREATE TRIGGER digital_component_blobs_protect_closed_aggregation
BEFORE INSERT OR UPDATE OR DELETE ON digital_component_blobs
FOR EACH ROW EXECUTE FUNCTION protect_blob_in_closed_aggregation();

INSERT INTO schema_migrations (version)
VALUES ('006_enforce_closed_aggregations')
ON CONFLICT (version) DO NOTHING;

-- Freeze aggregation metadata while allowing an explicit direct reopen.
CREATE OR REPLACE FUNCTION protect_closed_aggregation_hierarchy()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    closure_source_id bigint;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.parent_aggregation_id IS NOT NULL THEN
            PERFORM assert_aggregation_effectively_open(NEW.parent_aggregation_id);
        END IF;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM assert_aggregation_effectively_open(OLD.id);
        RETURN OLD;
    END IF;

    PERFORM 1
    FROM aggregations AS locked
    WHERE locked.id IN (
        WITH RECURSIVE ancestors AS (
            SELECT id, parent_aggregation_id FROM aggregations WHERE id = OLD.id
            UNION ALL
            SELECT parent.id, parent.parent_aggregation_id
            FROM aggregations AS parent
            JOIN ancestors ON parent.id = ancestors.parent_aggregation_id
        )
        SELECT id FROM ancestors
    )
    ORDER BY locked.id
    FOR SHARE;

    WITH RECURSIVE ancestors AS (
        SELECT id, parent_aggregation_id, date_closed, 0 AS depth
        FROM aggregations WHERE id = OLD.id
        UNION ALL
        SELECT parent.id, parent.parent_aggregation_id, parent.date_closed, child.depth + 1
        FROM aggregations AS parent
        JOIN ancestors AS child ON parent.id = child.parent_aggregation_id
    )
    SELECT id INTO closure_source_id
    FROM ancestors WHERE date_closed IS NOT NULL
    ORDER BY depth LIMIT 1;

    IF closure_source_id IS NOT NULL THEN
        IF closure_source_id = OLD.id
           AND OLD.date_closed IS NOT NULL AND NEW.date_closed IS NULL
           AND NEW.parent_aggregation_id IS NOT DISTINCT FROM OLD.parent_aggregation_id
           AND NEW.aggregation_number IS NOT DISTINCT FROM OLD.aggregation_number
           AND NEW.title IS NOT DISTINCT FROM OLD.title
           AND NEW.description IS NOT DISTINCT FROM OLD.description
           AND NEW.date_created IS NOT DISTINCT FROM OLD.date_created
           AND NEW.date_opened IS NOT DISTINCT FROM OLD.date_opened THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = format(
            'aggregation %s is closed by aggregation %s; closed aggregation metadata is immutable and only a direct closure may be cleared',
            OLD.id, closure_source_id
        );
    END IF;

    IF NEW.parent_aggregation_id IS DISTINCT FROM OLD.parent_aggregation_id
       AND NEW.parent_aggregation_id IS NOT NULL THEN
        PERFORM assert_aggregation_effectively_open(NEW.parent_aggregation_id);
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS aggregations_protect_closed_hierarchy ON aggregations;
CREATE TRIGGER aggregations_protect_closed_hierarchy
BEFORE INSERT OR UPDATE OR DELETE ON aggregations
FOR EACH ROW EXECUTE FUNCTION protect_closed_aggregation_hierarchy();

INSERT INTO schema_migrations (version)
VALUES ('007_freeze_closed_aggregation_metadata')
ON CONFLICT (version) DO NOTHING;


INSERT INTO schema_migrations(version)
VALUES ('008_cascade_record_digital_components')
ON CONFLICT(version) DO NOTHING;

-- Enforce user-management lifecycle semantics and inherited organization activity.
CREATE TABLE IF NOT EXISTS schema_migrations (
    id bigserial PRIMARY KEY,
    version text NOT NULL UNIQUE,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT schema_migrations_version_not_blank CHECK (btrim(version) <> '')
);

CREATE OR REPLACE FUNCTION org_unit_effectively_active(p_org_unit_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    WITH RECURSIVE ancestors AS (
        SELECT id, parent_org_unit_id, status FROM org_units WHERE id = p_org_unit_id
        UNION ALL
        SELECT parent.id, parent.parent_org_unit_id, parent.status
        FROM org_units parent JOIN ancestors child ON parent.id = child.parent_org_unit_id
    )
    SELECT COALESCE(bool_and(status = 'active'), false) FROM ancestors;
$$;

CREATE OR REPLACE FUNCTION role_effectively_active(p_role_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT COALESCE(r.status = 'active' AND org_unit_effectively_active(r.org_unit_id), false)
    FROM roles r WHERE r.id = p_role_id;
$$;

CREATE OR REPLACE FUNCTION normalize_user_management_lifecycle()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'org_units' THEN
        IF NEW.status = 'inactive' THEN
            NEW.date_deactivated := COALESCE(NEW.date_deactivated, CURRENT_TIMESTAMP);
            IF NEW.date_deactivated > CURRENT_TIMESTAMP THEN
                RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='organization unit deactivation date cannot be in the future';
            END IF;
        ELSE
            NEW.date_deactivated := NULL;
        END IF;
    ELSIF TG_TABLE_NAME = 'users' THEN
        IF NEW.status = 'inactive' THEN
            NEW.date_deactivated := COALESCE(NEW.date_deactivated, CURRENT_TIMESTAMP);
            IF NEW.date_deactivated > CURRENT_TIMESTAMP THEN
                RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='user deactivation date cannot be in the future';
            END IF;
        ELSE
            NEW.date_deactivated := NULL;
        END IF;
    ELSE
        IF NEW.status = 'inactive' THEN
            NEW.date_deactivated := COALESCE(NEW.date_deactivated, CURRENT_TIMESTAMP);
            IF NEW.date_deactivated > CURRENT_TIMESTAMP THEN
                RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='role deactivation date cannot be in the future';
            END IF;
        ELSE
            NEW.date_deactivated := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validate_active_role_assignment()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.user_id AND status='active') THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='role assignments require an active user';
    END IF;
    IF NOT role_effectively_active(NEW.role_id) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='role assignments require an effectively active role and organization hierarchy';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS org_units_normalize_lifecycle ON org_units;
CREATE TRIGGER org_units_normalize_lifecycle
BEFORE INSERT OR UPDATE OF status, date_deactivated ON org_units
FOR EACH ROW EXECUTE FUNCTION normalize_user_management_lifecycle();

DROP TRIGGER IF EXISTS users_normalize_lifecycle ON users;
CREATE TRIGGER users_normalize_lifecycle
BEFORE INSERT OR UPDATE OF status, date_deactivated ON users
FOR EACH ROW EXECUTE FUNCTION normalize_user_management_lifecycle();

DROP TRIGGER IF EXISTS roles_normalize_lifecycle ON roles;
CREATE TRIGGER roles_normalize_lifecycle
BEFORE INSERT OR UPDATE OF status, date_deactivated ON roles
FOR EACH ROW EXECUTE FUNCTION normalize_user_management_lifecycle();

DROP TRIGGER IF EXISTS user_role_assignments_validate_active ON user_role_assignments;
CREATE TRIGGER user_role_assignments_validate_active
BEFORE INSERT OR UPDATE OF user_id, role_id ON user_role_assignments
FOR EACH ROW EXECUTE FUNCTION validate_active_role_assignment();


UPDATE org_units
SET date_deactivated = CASE WHEN status = 'inactive' THEN COALESCE(date_deactivated, CURRENT_TIMESTAMP) ELSE NULL END;
UPDATE users
SET date_deactivated = CASE WHEN status = 'inactive' THEN COALESCE(date_deactivated, CURRENT_TIMESTAMP) ELSE NULL END;
UPDATE roles
SET date_deactivated = CASE WHEN status = 'inactive' THEN COALESCE(date_deactivated, CURRENT_TIMESTAMP) ELSE NULL END;

ALTER TABLE org_units DROP CONSTRAINT IF EXISTS org_units_lifecycle_consistent;
ALTER TABLE org_units ADD CONSTRAINT org_units_lifecycle_consistent
    CHECK ((status = 'inactive') = (date_deactivated IS NOT NULL));
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_lifecycle_consistent;
ALTER TABLE users ADD CONSTRAINT users_lifecycle_consistent
    CHECK ((status = 'inactive') = (date_deactivated IS NOT NULL));
ALTER TABLE roles DROP CONSTRAINT IF EXISTS roles_lifecycle_consistent;
ALTER TABLE roles ADD CONSTRAINT roles_lifecycle_consistent
    CHECK ((status = 'inactive') = (date_deactivated IS NOT NULL));


CREATE TABLE classification_schemes (
    id               bigserial PRIMARY KEY,
    code             text NOT NULL,
    title            text NOT NULL,
    description      text,
    authority        text,
    scope_note       text,
    edition          text,
    date_created     timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated     timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_published   timestamptz,
    date_deactivated timestamptz,
    date_first_used  timestamptz,
    version          bigint NOT NULL DEFAULT 1,
    CONSTRAINT classification_schemes_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT classification_schemes_title_not_blank CHECK (btrim(title) <> ''),
    CONSTRAINT classification_schemes_dates_in_order CHECK (
        date_deactivated IS NULL OR date_deactivated >= date_created
    ),
    CONSTRAINT classification_schemes_first_use_in_order CHECK (
        date_first_used IS NULL OR date_first_used >= date_created
    ),
    CONSTRAINT classification_schemes_version_positive CHECK (version > 0)
);
CREATE UNIQUE INDEX classification_schemes_code_ci_unique
    ON classification_schemes (lower(code));

CREATE TABLE classifications (
    id                       bigserial PRIMARY KEY,
    classification_scheme_id bigint NOT NULL
        REFERENCES classification_schemes(id) ON DELETE RESTRICT,
    parent_classification_id bigint REFERENCES classifications(id) ON DELETE RESTRICT,
    code                     text NOT NULL,
    title                    text NOT NULL,
    description              text,
    authority                text,
    scope_note               text,
    keywords                 text,
    is_terminal              boolean NOT NULL DEFAULT false,
    date_created             timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated             timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_deactivated         timestamptz,
    date_first_used          timestamptz,
    version                  bigint NOT NULL DEFAULT 1,
    CONSTRAINT classifications_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT classifications_title_not_blank CHECK (btrim(title) <> ''),
    CONSTRAINT classifications_not_own_parent CHECK (
        parent_classification_id IS NULL OR parent_classification_id <> id
    ),
    CONSTRAINT classifications_dates_in_order CHECK (
        date_deactivated IS NULL OR date_deactivated >= date_created
    ),
    CONSTRAINT classifications_first_use_in_order CHECK (
        date_first_used IS NULL OR date_first_used >= date_created
    ),
    CONSTRAINT classifications_version_positive CHECK (version > 0)
);
CREATE UNIQUE INDEX classifications_scheme_code_ci_unique
    ON classifications (classification_scheme_id, lower(code));
CREATE INDEX classifications_scheme_parent_idx
    ON classifications (classification_scheme_id, parent_classification_id);

CREATE TABLE classification_retention_rules (
    id                        bigserial PRIMARY KEY,
    classification_id         bigint NOT NULL UNIQUE
        REFERENCES classifications(id) ON DELETE CASCADE,
    current_period_years       integer NOT NULL CHECK (current_period_years >= 0),
    intermediate_period_years  integer NOT NULL CHECK (intermediate_period_years >= 0),
    final_disposition          text NOT NULL CHECK (final_disposition IN (
        'destruction', 'transfer_to_external_archive',
        'selective_preservation', 'retain_as_local_archives'
    )),
    instructions               text,
    date_created               timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated               timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version                    bigint NOT NULL DEFAULT 1 CHECK (version > 0)
);

ALTER TABLE aggregations
    ADD COLUMN classification_id bigint
        REFERENCES classifications(id) ON DELETE RESTRICT;
CREATE INDEX aggregations_classification_id_idx
    ON aggregations (classification_id);
ALTER TABLE aggregations
    ADD CONSTRAINT aggregations_root_classification_consistent
    CHECK (
        (parent_aggregation_id IS NULL AND classification_id IS NOT NULL)
        OR
        (parent_aggregation_id IS NOT NULL AND classification_id IS NULL)
    );

CREATE TABLE aggregation_retention_rules (
    id                        bigserial PRIMARY KEY,
    aggregation_id            bigint NOT NULL UNIQUE
        REFERENCES aggregations(id) ON DELETE CASCADE,
    current_period_years       integer NOT NULL CHECK (current_period_years >= 0),
    intermediate_period_years  integer NOT NULL CHECK (intermediate_period_years >= 0),
    final_disposition          text NOT NULL CHECK (final_disposition IN (
        'destruction', 'transfer_to_external_archive',
        'selective_preservation', 'retain_as_local_archives'
    )),
    instructions               text,
    justification              text NOT NULL CHECK (btrim(justification) <> ''),
    date_created               timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated               timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version                    bigint NOT NULL DEFAULT 1 CHECK (version > 0)
);

CREATE TABLE user_classification_selections (
    user_id           bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    classification_id bigint NOT NULL REFERENCES classifications(id) ON DELETE CASCADE,
    last_selected_at  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    selection_count   bigint NOT NULL DEFAULT 1 CHECK (selection_count > 0),
    PRIMARY KEY (user_id, classification_id)
);
CREATE INDEX user_classification_selections_recent_idx
    ON user_classification_selections (user_id, last_selected_at DESC);

CREATE OR REPLACE FUNCTION touch_classification_date_updated()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.date_updated := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validate_classification_scheme_dates()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.date_deactivated IS NOT NULL AND NEW.date_deactivated > CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION 'classification scheme date_deactivated cannot be in the future';
    END IF;
    IF NEW.date_deactivated IS NOT NULL AND NEW.date_deactivated < NEW.date_created THEN
        RAISE EXCEPTION 'classification scheme date_deactivated cannot precede date_created';
    END IF;
    IF TG_OP = 'UPDATE'
       AND OLD.date_first_used IS NOT NULL
       AND NEW.date_first_used IS DISTINCT FROM OLD.date_first_used THEN
        RAISE EXCEPTION 'classification scheme date_first_used is immutable once set';
    END IF;
    IF TG_OP = 'UPDATE'
       AND OLD.date_published IS NOT NULL
       AND NEW.date_published IS NULL THEN
        IF OLD.date_first_used IS NOT NULL THEN
            RAISE EXCEPTION 'a classification scheme that has governed an aggregation cannot be unpublished';
        END IF;
        IF NULLIF(current_setting('app.change_reason', true), '') IS NULL THEN
            RAISE EXCEPTION 'unpublishing a classification scheme requires a change reason';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION classification_scheme_is_eligible(p_scheme_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT COALESCE(
        date_deactivated IS NULL
        AND date_published IS NOT NULL
        AND date_published <= CURRENT_TIMESTAMP,
        false
    )
    FROM classification_schemes
    WHERE id = p_scheme_id;
$$;

CREATE OR REPLACE FUNCTION classification_is_effectively_active(p_classification_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    WITH RECURSIVE lineage AS (
        SELECT id, parent_classification_id, date_deactivated
        FROM classifications WHERE id = p_classification_id
        UNION ALL
        SELECT parent.id, parent.parent_classification_id, parent.date_deactivated
        FROM classifications AS parent
        JOIN lineage AS child ON parent.id = child.parent_classification_id
    )
    SELECT EXISTS (SELECT 1 FROM lineage)
       AND NOT EXISTS (SELECT 1 FROM lineage WHERE date_deactivated IS NOT NULL);
$$;

CREATE OR REPLACE FUNCTION validate_classification_dates()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.date_deactivated IS NOT NULL AND NEW.date_deactivated > CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION 'classification date_deactivated cannot be in the future';
    END IF;
    IF NEW.date_deactivated IS NOT NULL AND NEW.date_deactivated < NEW.date_created THEN
        RAISE EXCEPTION 'classification date_deactivated cannot precede date_created';
    END IF;
    IF TG_OP = 'UPDATE'
       AND OLD.date_first_used IS NOT NULL
       AND NEW.date_first_used IS DISTINCT FROM OLD.date_first_used THEN
        RAISE EXCEPTION 'classification date_first_used is immutable once set';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION record_classification_governance_first_use()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    scheme_id bigint;
    used_at timestamptz := CURRENT_TIMESTAMP;
BEGIN
    IF NEW.classification_id IS NULL
       OR (TG_OP = 'UPDATE' AND NEW.classification_id IS NOT DISTINCT FROM OLD.classification_id) THEN
        RETURN NEW;
    END IF;

    SELECT classification_scheme_id INTO scheme_id
    FROM classifications
    WHERE id = NEW.classification_id;

    WITH RECURSIVE lineage AS (
        SELECT id, parent_classification_id
        FROM classifications WHERE id = NEW.classification_id
        UNION ALL
        SELECT parent.id, parent.parent_classification_id
        FROM classifications AS parent
        JOIN lineage AS child ON parent.id = child.parent_classification_id
    )
    UPDATE classifications
    SET date_first_used = used_at
    WHERE id IN (SELECT id FROM lineage) AND date_first_used IS NULL;

    UPDATE classification_schemes
    SET date_first_used = used_at
    WHERE id = scheme_id AND date_first_used IS NULL;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION protect_classification_deletion()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    scheme_row classification_schemes%ROWTYPE;
BEGIN
    SELECT * INTO scheme_row FROM classification_schemes WHERE id = OLD.classification_scheme_id;
    IF scheme_row.date_deactivated IS NOT NULL THEN
        RAISE EXCEPTION 'classifications cannot be deleted while their scheme is deactivated';
    END IF;
    IF scheme_row.date_published IS NOT NULL THEN
        RAISE EXCEPTION 'classification scheme must be unpublished before deleting classifications';
    END IF;
    IF OLD.date_first_used IS NOT NULL THEN
        RAISE EXCEPTION 'a classification that has governed an aggregation cannot be deleted; deactivate it instead';
    END IF;
    IF EXISTS (SELECT 1 FROM classifications WHERE parent_classification_id = OLD.id) THEN
        RAISE EXCEPTION 'classification has children; delete its child classifications first';
    END IF;
    IF EXISTS (SELECT 1 FROM aggregations WHERE classification_id = OLD.id) THEN
        RAISE EXCEPTION 'classification is assigned to an aggregation and cannot be deleted';
    END IF;
    IF NULLIF(current_setting('app.change_reason', true), '') IS NULL THEN
        RAISE EXCEPTION 'deleting a classification requires a change reason';
    END IF;
    RETURN OLD;
END;
$$;

CREATE OR REPLACE FUNCTION delete_unused_classification_scheme()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    deleted_count integer;
BEGIN
    IF OLD.date_published IS NOT NULL THEN
        RAISE EXCEPTION 'published classification schemes must be unpublished before deletion';
    END IF;
    IF OLD.date_first_used IS NOT NULL THEN
        RAISE EXCEPTION 'a classification scheme that has governed an aggregation cannot be deleted';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM aggregations AS a
        JOIN classifications AS c ON c.id = a.classification_id
        WHERE c.classification_scheme_id = OLD.id
    ) THEN
        RAISE EXCEPTION 'classification scheme has classifications assigned to aggregations';
    END IF;

    LOOP
        DELETE FROM classifications AS candidate
        WHERE candidate.classification_scheme_id = OLD.id
          AND NOT EXISTS (
              SELECT 1 FROM classifications AS child
              WHERE child.parent_classification_id = candidate.id
          );
        GET DIAGNOSTICS deleted_count = ROW_COUNT;
        EXIT WHEN deleted_count = 0;
    END LOOP;

    IF EXISTS (SELECT 1 FROM classifications WHERE classification_scheme_id = OLD.id) THEN
        RAISE EXCEPTION 'classification scheme hierarchy could not be deleted safely';
    END IF;
    RETURN OLD;
END;
$$;

CREATE OR REPLACE FUNCTION validate_classification_structure()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parent_scheme bigint;
    parent_terminal boolean;
BEGIN
    IF TG_OP = 'UPDATE'
       AND NEW.classification_scheme_id IS DISTINCT FROM OLD.classification_scheme_id THEN
        RAISE EXCEPTION 'a classification cannot be moved to another scheme';
    END IF;

    IF NEW.parent_classification_id IS NOT NULL THEN
        SELECT classification_scheme_id, is_terminal
        INTO parent_scheme, parent_terminal
        FROM classifications
        WHERE id = NEW.parent_classification_id;
        IF parent_scheme IS NULL THEN
            RAISE EXCEPTION 'parent classification does not exist';
        END IF;
        IF parent_scheme <> NEW.classification_scheme_id THEN
            RAISE EXCEPTION 'parent classification must belong to the same scheme';
        END IF;
        IF parent_terminal THEN
            RAISE EXCEPTION 'terminal classifications cannot contain child classifications';
        END IF;
        IF EXISTS (
            WITH RECURSIVE descendants AS (
                SELECT id FROM classifications WHERE parent_classification_id = NEW.id
                UNION ALL
                SELECT child.id
                FROM classifications AS child
                JOIN descendants AS parent ON child.parent_classification_id = parent.id
            )
            SELECT 1 FROM descendants WHERE id = NEW.parent_classification_id
        ) THEN
            RAISE EXCEPTION 'classification hierarchy cannot contain a cycle';
        END IF;
    END IF;

    IF NEW.is_terminal AND EXISTS (
        SELECT 1 FROM classifications WHERE parent_classification_id = NEW.id
    ) THEN
        RAISE EXCEPTION 'a classification with children cannot be terminal';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.is_terminal AND NOT NEW.is_terminal
       AND EXISTS (SELECT 1 FROM aggregations WHERE classification_id = NEW.id) THEN
        RAISE EXCEPTION 'an assigned terminal classification cannot become a branch';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION effective_classification_retention_rule(p_classification_id bigint)
RETURNS TABLE (
    rule_id bigint,
    defined_by_classification_id bigint,
    inheritance_depth integer,
    current_period_years integer,
    intermediate_period_years integer,
    final_disposition text,
    instructions text
)
LANGUAGE sql STABLE AS $$
    WITH RECURSIVE ancestors AS (
        SELECT c.id, c.parent_classification_id, 0 AS depth
        FROM classifications AS c
        WHERE c.id = p_classification_id
        UNION ALL
        SELECT parent.id, parent.parent_classification_id, child.depth + 1
        FROM classifications AS parent
        JOIN ancestors AS child ON parent.id = child.parent_classification_id
    )
    SELECT rule.id, rule.classification_id, ancestors.depth,
           rule.current_period_years, rule.intermediate_period_years,
           rule.final_disposition, rule.instructions
    FROM ancestors
    JOIN classification_retention_rules AS rule
      ON rule.classification_id = ancestors.id
    ORDER BY ancestors.depth
    LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION validate_terminal_classification_rules()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE missing_code text;
BEGIN
    SELECT c.code INTO missing_code
    FROM classifications AS c
    WHERE c.is_terminal
      AND NOT EXISTS (
          SELECT 1 FROM effective_classification_retention_rule(c.id)
      )
    ORDER BY c.id LIMIT 1;
    IF missing_code IS NOT NULL THEN
        RAISE EXCEPTION 'terminal classification % has no effective retention rule', missing_code;
    END IF;
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION validate_aggregation_classification()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    classification_terminal boolean;
    scheme_id bigint;
BEGIN
    IF NEW.parent_aggregation_id IS NULL THEN
        IF NEW.classification_id IS NULL THEN
            RAISE EXCEPTION 'root aggregations must have a classification';
        END IF;
        SELECT is_terminal, classification_scheme_id
        INTO classification_terminal, scheme_id
        FROM classifications WHERE id = NEW.classification_id;
        IF NOT COALESCE(classification_terminal, false) THEN
            RAISE EXCEPTION 'root aggregations must use a terminal classification';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM effective_classification_retention_rule(NEW.classification_id)
        ) THEN
            RAISE EXCEPTION 'selected classification has no effective retention rule';
        END IF;
        IF TG_OP = 'INSERT'
           OR NEW.classification_id IS DISTINCT FROM OLD.classification_id
           OR NEW.parent_aggregation_id IS DISTINCT FROM OLD.parent_aggregation_id THEN
            IF NOT classification_scheme_is_eligible(scheme_id) THEN
                RAISE EXCEPTION 'selected classification scheme is not active and published';
            END IF;
            IF NOT classification_is_effectively_active(NEW.classification_id) THEN
                RAISE EXCEPTION 'selected classification or one of its ancestors is deactivated';
            END IF;
        END IF;
    ELSIF NEW.classification_id IS NOT NULL THEN
        RAISE EXCEPTION 'child aggregations cannot have a classification';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validate_root_aggregation_retention_rules()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE invalid_number text;
BEGIN
    SELECT a.aggregation_number INTO invalid_number
    FROM aggregation_retention_rules AS rule
    JOIN aggregations AS a ON a.id = rule.aggregation_id
    WHERE a.parent_aggregation_id IS NOT NULL
    ORDER BY a.id LIMIT 1;
    IF invalid_number IS NOT NULL THEN
        RAISE EXCEPTION 'child aggregation % cannot have a local retention rule', invalid_number;
    END IF;
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION aggregation_effective_retention_rule(p_aggregation_id bigint)
RETURNS TABLE (
    governing_root_aggregation_id bigint,
    classification_id bigint,
    rule_source text,
    rule_id bigint,
    defined_by_classification_id bigint,
    inheritance_depth integer,
    current_period_years integer,
    intermediate_period_years integer,
    final_disposition text,
    instructions text,
    justification text
)
LANGUAGE plpgsql STABLE AS $$
DECLARE root_row aggregations%ROWTYPE;
BEGIN
    WITH RECURSIVE lineage AS (
        SELECT a.*, 0 AS depth FROM aggregations AS a WHERE a.id = p_aggregation_id
        UNION ALL
        SELECT parent.*, child.depth + 1
        FROM aggregations AS parent
        JOIN lineage AS child ON parent.id = child.parent_aggregation_id
    )
    SELECT lineage.id, lineage.parent_aggregation_id, lineage.aggregation_number,
           lineage.title, lineage.description, lineage.date_created,
           lineage.date_opened, lineage.date_closed, lineage.version,
           lineage.classification_id
    INTO root_row
    FROM lineage WHERE lineage.parent_aggregation_id IS NULL LIMIT 1;

    IF root_row.id IS NULL THEN
        RETURN;
    END IF;
    IF EXISTS (
        SELECT 1 FROM aggregation_retention_rules WHERE aggregation_id = root_row.id
    ) THEN
        RETURN QUERY
        SELECT root_row.id, root_row.classification_id, 'aggregation'::text,
               r.id, NULL::bigint, 0,
               r.current_period_years, r.intermediate_period_years,
               r.final_disposition, r.instructions, r.justification
        FROM aggregation_retention_rules AS r
        WHERE r.aggregation_id = root_row.id;
        RETURN;
    END IF;
    RETURN QUERY
    SELECT root_row.id, root_row.classification_id, 'classification'::text,
           r.rule_id, r.defined_by_classification_id, r.inheritance_depth,
           r.current_period_years, r.intermediate_period_years,
           r.final_disposition, r.instructions, NULL::text
    FROM effective_classification_retention_rule(root_row.classification_id) AS r;
END;
$$;

CREATE OR REPLACE FUNCTION record_classification_selection()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE context_user_id text;
BEGIN
    context_user_id := NULLIF(current_setting('app.user_id', true), '');
    IF context_user_id IS NOT NULL
       AND NEW.parent_aggregation_id IS NULL
       AND NEW.classification_id IS NOT NULL
       AND (TG_OP = 'INSERT' OR NEW.classification_id IS DISTINCT FROM OLD.classification_id) THEN
        INSERT INTO user_classification_selections (
            user_id, classification_id, last_selected_at, selection_count
        ) VALUES (context_user_id::bigint, NEW.classification_id, CURRENT_TIMESTAMP, 1)
        ON CONFLICT (user_id, classification_id) DO UPDATE
        SET last_selected_at = EXCLUDED.last_selected_at,
            selection_count = user_classification_selections.selection_count + 1;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER classification_schemes_validate_dates
BEFORE INSERT OR UPDATE OF date_created, date_published, date_deactivated, date_first_used
ON classification_schemes
FOR EACH ROW EXECUTE FUNCTION validate_classification_scheme_dates();
CREATE TRIGGER classification_schemes_touch
BEFORE UPDATE ON classification_schemes
FOR EACH ROW EXECUTE FUNCTION touch_classification_date_updated();
CREATE TRIGGER classifications_touch
BEFORE UPDATE ON classifications
FOR EACH ROW EXECUTE FUNCTION touch_classification_date_updated();
CREATE TRIGGER classifications_validate_dates
BEFORE INSERT OR UPDATE OF date_created, date_deactivated, date_first_used ON classifications
FOR EACH ROW EXECUTE FUNCTION validate_classification_dates();
CREATE TRIGGER classification_retention_rules_touch
BEFORE UPDATE ON classification_retention_rules
FOR EACH ROW EXECUTE FUNCTION touch_classification_date_updated();
CREATE TRIGGER aggregation_retention_rules_touch
BEFORE UPDATE ON aggregation_retention_rules
FOR EACH ROW EXECUTE FUNCTION touch_classification_date_updated();

CREATE TRIGGER classifications_validate_structure
BEFORE INSERT OR UPDATE OF classification_scheme_id, parent_classification_id, is_terminal
ON classifications FOR EACH ROW EXECUTE FUNCTION validate_classification_structure();

CREATE CONSTRAINT TRIGGER classifications_validate_effective_rule
AFTER INSERT OR UPDATE ON classifications
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_terminal_classification_rules();
CREATE CONSTRAINT TRIGGER classification_rules_validate_effective_rule
AFTER INSERT OR UPDATE OR DELETE ON classification_retention_rules
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_terminal_classification_rules();

CREATE TRIGGER aggregations_validate_classification
BEFORE INSERT OR UPDATE OF parent_aggregation_id, classification_id ON aggregations
FOR EACH ROW EXECUTE FUNCTION validate_aggregation_classification();
CREATE CONSTRAINT TRIGGER aggregation_rules_validate_root
AFTER INSERT OR UPDATE ON aggregation_retention_rules
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_root_aggregation_retention_rules();
CREATE CONSTRAINT TRIGGER aggregations_validate_local_rule_root
AFTER UPDATE ON aggregations
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_root_aggregation_retention_rules();
CREATE TRIGGER aggregations_record_classification_selection
AFTER INSERT OR UPDATE OF classification_id ON aggregations
FOR EACH ROW EXECUTE FUNCTION record_classification_selection();
CREATE TRIGGER aggregations_record_classification_governance_first_use
AFTER INSERT OR UPDATE OF classification_id ON aggregations
FOR EACH ROW EXECUTE FUNCTION record_classification_governance_first_use();

CREATE TRIGGER classification_schemes_delete_unused
BEFORE DELETE ON classification_schemes
FOR EACH ROW EXECUTE FUNCTION delete_unused_classification_scheme();
CREATE TRIGGER classifications_protect_deletion
BEFORE DELETE ON classifications
FOR EACH ROW EXECUTE FUNCTION protect_classification_deletion();

CREATE TRIGGER classification_schemes_bump_version
BEFORE UPDATE ON classification_schemes
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();
CREATE TRIGGER classifications_bump_version
BEFORE UPDATE ON classifications
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();
CREATE TRIGGER classification_retention_rules_bump_version
BEFORE UPDATE ON classification_retention_rules
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();
CREATE TRIGGER aggregation_retention_rules_bump_version
BEFORE UPDATE ON aggregation_retention_rules
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();

CREATE TRIGGER classification_schemes_record_history
AFTER INSERT OR UPDATE OR DELETE ON classification_schemes
FOR EACH ROW EXECUTE FUNCTION record_entity_history('classification_scheme');
CREATE TRIGGER classifications_record_history
AFTER INSERT OR UPDATE OR DELETE ON classifications
FOR EACH ROW EXECUTE FUNCTION record_entity_history('classification');
CREATE TRIGGER classification_retention_rules_record_history
AFTER INSERT OR UPDATE OR DELETE ON classification_retention_rules
FOR EACH ROW EXECUTE FUNCTION record_entity_history('classification_retention_rule');
CREATE TRIGGER aggregation_retention_rules_record_history
AFTER INSERT OR UPDATE OR DELETE ON aggregation_retention_rules
FOR EACH ROW EXECUTE FUNCTION record_entity_history('aggregation_retention_rule');


INSERT INTO schema_migrations(version)
VALUES ('009_user_management_lifecycle')
ON CONFLICT(version) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('010_rename_org_unit_deactivation_date')
ON CONFLICT(version) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('011_normalize_org_unit_event_history')
ON CONFLICT(version) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('012_backfill_anonymous_event_actor')
ON CONFLICT(version) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('013_snapshot_event_actor_identity')
ON CONFLICT(version) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('014_backfill_webui_event_source')
ON CONFLICT(version) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('015_reclassify_lifecycle_normalization_events')
ON CONFLICT(version) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('016_snapshot_role_assignment_parties')
ON CONFLICT(version) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('017_rename_system_accounts_to_service')
ON CONFLICT(version) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('018_rename_system_actor_to_automated_process')
ON CONFLICT(version) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('019_add_classification_schemes')
ON CONFLICT(version) DO NOTHING;


COMMIT;
