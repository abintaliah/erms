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
