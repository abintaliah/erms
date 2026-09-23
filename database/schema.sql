BEGIN;

CREATE TABLE security_levels (
    id                   bigserial PRIMARY KEY,
    code                 text NOT NULL,
    name                 text NOT NULL,
    level_number         integer NOT NULL,
    prevents_disposition boolean NOT NULL DEFAULT false,
    date_created         timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated         timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version              integer NOT NULL DEFAULT 1,
    CONSTRAINT security_levels_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT security_levels_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT security_levels_number_nonnegative CHECK (level_number >= 0),
    CONSTRAINT security_levels_version_positive CHECK (version > 0),
    CONSTRAINT security_levels_level_number_unique UNIQUE (level_number)
);

CREATE UNIQUE INDEX security_levels_code_ci_unique ON security_levels (lower(code));
CREATE UNIQUE INDEX security_levels_name_ci_unique ON security_levels (lower(name));

INSERT INTO security_levels (code, name, level_number, prevents_disposition)
VALUES ('G','General',0,false), ('R','Restricted',50,false),
       ('S','Secret',75,false), ('TS','Top Secret',100,true);

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
CREATE INDEX aggregations_parent_number_browse_idx
    ON aggregations (parent_aggregation_id, aggregation_number COLLATE "C", id);

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
CREATE INDEX records_aggregation_number_browse_idx
    ON records (aggregation_id, record_number COLLATE "C", id);

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

CREATE INDEX event_history_security_operation_timeline_idx
    ON event_history (operation, occurred_at DESC)
    WHERE operation IN (
        'AUTHORIZATION_DENIED','AUTHENTICATION_FAILED','ACCOUNT_LOCKED',
        'INFORMATION_GOVERNANCE_BYPASS_USED','ACCESS_EXPLANATION_VIEWED',
        'SECURITY_LEVEL_CHANGED','SECURITY_LEVEL_UPGRADED','SECURITY_LEVEL_DOWNGRADED',
        'ACL_REPLACED','DEFAULT_CHILD_AGGREGATION_ACL_REPLACED',
        'DEFAULT_CHILD_RECORD_ACL_REPLACED','PROFILE_PRIVILEGES_REPLACED',
        'PROFILE_ASSIGNED','GOVERNANCE_ROLE_CHANGED'
    );

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

-- Preserve readable identities for entities referenced by newly-created audit
-- events.  These snapshots deliberately live alongside the numeric keys: the
-- key remains useful to developers while the snapshot remains meaningful to
-- auditors after the referenced row is renamed or deleted.
CREATE FUNCTION event_reference_identity(reference_field text, reference_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    snapshot jsonb;
BEGIN
    CASE reference_field
        WHEN 'profile_id' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'name', name)
            INTO snapshot FROM profiles WHERE id = reference_id;
        WHEN 'old_profile_id' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'name', name)
            INTO snapshot FROM profiles WHERE id = reference_id;
        WHEN 'new_profile_id' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'name', name)
            INTO snapshot FROM profiles WHERE id = reference_id;
        WHEN 'security_level_id' THEN
            SELECT jsonb_build_object(
                'id', id, 'code', code, 'name', name, 'level_number', level_number
            ) INTO snapshot FROM security_levels WHERE id = reference_id;
        WHEN 'classification_id' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'title', title)
            INTO snapshot FROM classifications WHERE id = reference_id;
        WHEN 'parent_classification_id' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'title', title)
            INTO snapshot FROM classifications WHERE id = reference_id;
        WHEN 'classification_scheme_id' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'title', title)
            INTO snapshot FROM classification_schemes WHERE id = reference_id;
        WHEN 'aggregation_id' THEN
            SELECT jsonb_build_object(
                'id', id, 'code', aggregation_number, 'title', title
            ) INTO snapshot FROM aggregations WHERE id = reference_id;
        WHEN 'parent_aggregation_id' THEN
            SELECT jsonb_build_object(
                'id', id, 'code', aggregation_number, 'title', title
            ) INTO snapshot FROM aggregations WHERE id = reference_id;
        WHEN 'destination_aggregation_id' THEN
            SELECT jsonb_build_object(
                'id', id, 'code', aggregation_number, 'title', title
            ) INTO snapshot FROM aggregations WHERE id = reference_id;
        WHEN 'record_id' THEN
            SELECT jsonb_build_object('id', id, 'code', record_number, 'title', title)
            INTO snapshot FROM records WHERE id = reference_id;
        WHEN 'role_id' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'name', name)
            INTO snapshot FROM roles WHERE id = reference_id;
        WHEN 'supervisor_role_id' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'name', name)
            INTO snapshot FROM roles WHERE id = reference_id;
        WHEN 'user_id' THEN
            SELECT jsonb_build_object('id', id, 'name', name, 'email', email)
            INTO snapshot FROM users WHERE id = reference_id;
        WHEN 'owner_user_id' THEN
            SELECT jsonb_build_object('id', id, 'name', name, 'email', email)
            INTO snapshot FROM users WHERE id = reference_id;
        WHEN 'org_unit_id' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'name', name)
            INTO snapshot FROM org_units WHERE id = reference_id;
        WHEN 'parent_org_unit_id' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'name', name)
            INTO snapshot FROM org_units WHERE id = reference_id;
        ELSE
            snapshot := NULL;
    END CASE;
    RETURN snapshot;
END;
$$;

CREATE FUNCTION event_state_reference_snapshots(event_state jsonb)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    reference_field text;
    reference_value text;
    snapshot        jsonb;
    snapshots       jsonb := '{}'::jsonb;
BEGIN
    IF event_state IS NULL OR jsonb_typeof(event_state) <> 'object' THEN
        RETURN snapshots;
    END IF;

    FOREACH reference_field IN ARRAY ARRAY[
        'profile_id', 'old_profile_id', 'new_profile_id', 'security_level_id',
        'classification_id', 'parent_classification_id', 'classification_scheme_id',
        'aggregation_id', 'parent_aggregation_id', 'destination_aggregation_id',
        'record_id', 'role_id', 'supervisor_role_id', 'user_id', 'owner_user_id',
        'org_unit_id', 'parent_org_unit_id'
    ] LOOP
        reference_value := event_state ->> reference_field;
        IF reference_value IS NOT NULL AND reference_value ~ '^[0-9]+$' THEN
            snapshot := event_reference_identity(reference_field, reference_value::bigint);
            IF snapshot IS NOT NULL THEN
                snapshots := snapshots || jsonb_build_object(reference_field, snapshot);
            END IF;
        END IF;
    END LOOP;
    RETURN snapshots;
END;
$$;

CREATE FUNCTION event_entity_identity_snapshot(event_entity_type text, event_entity_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    snapshot jsonb;
BEGIN
    CASE event_entity_type
        WHEN 'aggregation' THEN
            SELECT jsonb_build_object('id', id, 'code', aggregation_number, 'title', title)
            INTO snapshot FROM aggregations WHERE id = event_entity_id;
        WHEN 'record' THEN
            SELECT jsonb_build_object('id', id, 'code', record_number, 'title', title)
            INTO snapshot FROM records WHERE id = event_entity_id;
        WHEN 'digital_component' THEN
            SELECT jsonb_build_object('id', id, 'name', file_name)
            INTO snapshot FROM digital_components WHERE id = event_entity_id;
        WHEN 'classification_scheme' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'title', title)
            INTO snapshot FROM classification_schemes WHERE id = event_entity_id;
        WHEN 'classification' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'title', title)
            INTO snapshot FROM classifications WHERE id = event_entity_id;
        WHEN 'org_unit' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'name', name)
            INTO snapshot FROM org_units WHERE id = event_entity_id;
        WHEN 'role' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'name', name)
            INTO snapshot FROM roles WHERE id = event_entity_id;
        WHEN 'user' THEN
            SELECT jsonb_build_object('id', id, 'name', name, 'email', email)
            INTO snapshot FROM users WHERE id = event_entity_id;
        WHEN 'profile' THEN
            SELECT jsonb_build_object('id', id, 'code', code, 'name', name)
            INTO snapshot FROM profiles WHERE id = event_entity_id;
        WHEN 'security_level' THEN
            SELECT jsonb_build_object(
                'id', id, 'code', code, 'name', name, 'level_number', level_number
            ) INTO snapshot FROM security_levels WHERE id = event_entity_id;
        ELSE
            snapshot := NULL;
    END CASE;
    RETURN snapshot;
END;
$$;

CREATE FUNCTION populate_event_reference_snapshots()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    snapshots      jsonb := '{}'::jsonb;
    state_snapshot jsonb;
BEGIN
    state_snapshot := event_state_reference_snapshots(NEW.before_state);
    IF state_snapshot <> '{}'::jsonb THEN
        snapshots := snapshots || jsonb_build_object('before', state_snapshot);
    END IF;

    state_snapshot := event_state_reference_snapshots(NEW.after_state);
    IF state_snapshot <> '{}'::jsonb THEN
        snapshots := snapshots || jsonb_build_object('after', state_snapshot);
    END IF;

    state_snapshot := event_state_reference_snapshots(NEW.metadata);
    IF state_snapshot <> '{}'::jsonb THEN
        snapshots := snapshots || jsonb_build_object('metadata', state_snapshot);
    END IF;

    state_snapshot := event_entity_identity_snapshot(NEW.entity_type, NEW.entity_id);
    IF state_snapshot IS NOT NULL THEN
        snapshots := snapshots || jsonb_build_object('entity', state_snapshot);
    END IF;

    IF snapshots <> '{}'::jsonb THEN
        NEW.metadata := NEW.metadata || jsonb_build_object('reference_snapshots', snapshots);
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER event_history_populate_reference_snapshots
BEFORE INSERT ON event_history
FOR EACH ROW EXECUTE FUNCTION populate_event_reference_snapshots();

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
    IF TG_OP = 'UPDATE'
       AND current_setting('app.suppress_ordinary_history', true) = 'authorized' THEN
        RETURN NEW;
    END IF;
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


-- User management subsystem. The equivalent upgrade for existing databases is
-- database/migrations/002_add_user_management.sql.
CREATE TABLE org_units (
    id                 bigserial PRIMARY KEY,
    parent_org_unit_id bigint REFERENCES org_units (id) ON DELETE RESTRICT,
    code               text NOT NULL,
    name               text NOT NULL,
    description        text,
    date_created       timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_deactivated   timestamptz,
    status             text GENERATED ALWAYS AS (
        CASE WHEN date_deactivated IS NULL THEN 'active' ELSE 'inactive' END
    ) STORED,

    CONSTRAINT org_units_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT org_units_name_not_blank CHECK (btrim(name) <> ''),
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
    account_type     text NOT NULL DEFAULT 'person',
    date_created     timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_deactivated timestamptz,
    date_suspended   timestamptz,
    status           text GENERATED ALWAYS AS (
        CASE
            WHEN date_deactivated IS NOT NULL THEN 'inactive'
            WHEN date_suspended IS NOT NULL THEN 'suspended'
            ELSE 'active'
        END
    ) STORED,

    CONSTRAINT users_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT users_email_not_blank CHECK (email IS NULL OR btrim(email) <> ''),
    CONSTRAINT users_external_id_not_blank
        CHECK (external_id IS NULL OR btrim(external_id) <> ''),
    CONSTRAINT users_account_type_valid
        CHECK (account_type IN ('person', 'service')),
    CONSTRAINT users_dates_in_order
        CHECK (
            (date_deactivated IS NULL OR date_deactivated >= date_created)
            AND (date_suspended IS NULL OR date_suspended >= date_created)
        ),
    CONSTRAINT users_lifecycle_dates_exclusive
        CHECK (date_deactivated IS NULL OR date_suspended IS NULL)
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
    date_created       timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_deactivated   timestamptz,
    status             text GENERATED ALWAYS AS (
        CASE WHEN date_deactivated IS NULL THEN 'active' ELSE 'inactive' END
    ) STORED,

    CONSTRAINT roles_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT roles_name_not_blank CHECK (btrim(name) <> ''),
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
    user_id       bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role_id       bigint NOT NULL REFERENCES roles (id) ON DELETE CASCADE,
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
CREATE INDEX login_sessions_revoked_cleanup_idx
    ON login_sessions (revoked_at, id) WHERE revoked_at IS NOT NULL;

CREATE TABLE user_favourite_aggregations (
    user_id         bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    aggregation_id  bigint NOT NULL REFERENCES aggregations (id) ON DELETE CASCADE,
    date_created    timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, aggregation_id)
);

CREATE INDEX user_favourite_aggregations_aggregation_id_idx
    ON user_favourite_aggregations (aggregation_id);
CREATE INDEX user_favourite_aggregations_user_created_idx
    ON user_favourite_aggregations (user_id, date_created DESC, aggregation_id);

CREATE TABLE user_favourite_records (
    user_id      bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    record_id    bigint NOT NULL REFERENCES records (id) ON DELETE CASCADE,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, record_id)
);

CREATE INDEX user_favourite_records_record_id_idx
    ON user_favourite_records (record_id);
CREATE INDEX user_favourite_records_user_created_idx
    ON user_favourite_records (user_id, date_created DESC, record_id);

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


-- Open record drafts stage metadata and binary content until the user commits
-- the complete record package. The equivalent upgrade is migration 004.
CREATE TABLE IF NOT EXISTS record_drafts (
    id bigserial PRIMARY KEY,
    owner_user_id bigint REFERENCES users (id) ON DELETE CASCADE,
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
    content_status text NOT NULL DEFAULT 'uploading'
        CHECK (content_status IN ('uploading', 'interrupted', 'finalizing', 'available', 'failed', 'cancelled', 'expired')),
    segment_count integer CHECK (segment_count IS NULL OR segment_count >= 0),
    upload_completed_at timestamptz,
    CONSTRAINT record_draft_components_draft_order_unique
        UNIQUE (draft_id, component_order) DEFERRABLE INITIALLY IMMEDIATE
);
CREATE INDEX IF NOT EXISTS record_draft_components_draft_id_idx ON record_draft_components (draft_id);

CREATE TABLE IF NOT EXISTS record_draft_component_blobs (
    id bigserial PRIMARY KEY,
    record_draft_component_id bigint NOT NULL
        REFERENCES record_draft_components (id) ON DELETE CASCADE,
    segment_no integer NOT NULL CHECK (segment_no >= 0),
    segment_size integer NOT NULL CHECK (segment_size > 0),
    segment_checksum_algo text,
    segment_checksum_value text,
    content bytea NOT NULL,
    date_stored timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (record_draft_component_id, segment_no),
    CHECK (segment_size = octet_length(content))
);
CREATE INDEX IF NOT EXISTS record_draft_component_blobs_component_order_idx
    ON record_draft_component_blobs (record_draft_component_id, segment_no);

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
    ADD COLUMN IF NOT EXISTS content_status text NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS active_content_set_id bigint,
    ADD COLUMN IF NOT EXISTS upload_completed_at timestamptz;

ALTER TABLE digital_components DROP CONSTRAINT IF EXISTS digital_components_storage_backend_valid;
ALTER TABLE digital_components ADD CONSTRAINT digital_components_storage_backend_valid
    CHECK (storage_backend IN ('postgresql', 's3'));
ALTER TABLE digital_components DROP CONSTRAINT IF EXISTS digital_components_content_status_valid;
ALTER TABLE digital_components ADD CONSTRAINT digital_components_content_status_valid
    CHECK (content_status IN ('pending', 'uploading', 'available', 'failed', 'quarantined', 'deleted'));
ALTER TABLE digital_components DROP CONSTRAINT IF EXISTS digital_components_storage_location_valid;
ALTER TABLE digital_components ADD CONSTRAINT digital_components_storage_location_valid
    CHECK (
        (storage_backend = 'postgresql' AND storage_key IS NULL)
        OR (storage_backend = 's3' AND storage_key IS NOT NULL AND btrim(storage_key) <> '')
    );

CREATE TABLE IF NOT EXISTS digital_component_content_sets (
    id bigserial PRIMARY KEY,
    digital_component_id bigint NOT NULL REFERENCES digital_components (id) ON DELETE CASCADE,
    status text NOT NULL CHECK (status IN ('staged', 'active', 'superseded', 'failed')),
    size_in_bytes bigint CHECK (size_in_bytes IS NULL OR size_in_bytes >= 0),
    segment_count integer CHECK (segment_count IS NULL OR segment_count >= 0),
    checksum_algo text,
    checksum_value text,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_completed timestamptz,
    UNIQUE (digital_component_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS digital_component_one_active_content_set_idx
    ON digital_component_content_sets (digital_component_id) WHERE status = 'active';

ALTER TABLE digital_components DROP CONSTRAINT IF EXISTS digital_components_active_content_set_fk;
ALTER TABLE digital_components ADD CONSTRAINT digital_components_active_content_set_fk
    FOREIGN KEY (id, active_content_set_id)
    REFERENCES digital_component_content_sets (digital_component_id, id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE IF NOT EXISTS digital_component_blobs (
    id bigserial PRIMARY KEY,
    content_set_id bigint NOT NULL REFERENCES digital_component_content_sets (id) ON DELETE CASCADE,
    segment_no integer NOT NULL CHECK (segment_no >= 0),
    segment_size integer NOT NULL CHECK (segment_size > 0),
    segment_checksum_algo text,
    segment_checksum_value text,
    content bytea NOT NULL,
    date_stored timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (content_set_id, segment_no),
    CHECK (segment_size = octet_length(content))
);
CREATE INDEX IF NOT EXISTS digital_component_blobs_content_set_order_idx
    ON digital_component_blobs (content_set_id, segment_no);

CREATE TABLE IF NOT EXISTS content_upload_sessions (
    id bigserial PRIMARY KEY,
    digital_component_id bigint REFERENCES digital_components (id) ON DELETE CASCADE,
    draft_component_id bigint REFERENCES record_draft_components (id) ON DELETE CASCADE,
    content_set_id bigint REFERENCES digital_component_content_sets (id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'uploading'
        CHECK (status IN ('uploading', 'interrupted', 'finalizing', 'completed', 'failed', 'cancelled', 'expired')),
    next_segment_no integer NOT NULL DEFAULT 0 CHECK (next_segment_no >= 0),
    bytes_received bigint NOT NULL DEFAULT 0 CHECK (bytes_received >= 0),
    expected_size bigint CHECK (expected_size IS NULL OR expected_size >= 0),
    checksum_algo text NOT NULL DEFAULT 'sha256',
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL DEFAULT (CURRENT_TIMESTAMP + interval '1 day'),
    CHECK (((digital_component_id IS NOT NULL)::integer + (draft_component_id IS NOT NULL)::integer) = 1),
    CHECK ((digital_component_id IS NOT NULL AND content_set_id IS NOT NULL)
        OR (draft_component_id IS NOT NULL AND content_set_id IS NULL))
);
CREATE INDEX IF NOT EXISTS content_upload_sessions_cleanup_idx
    ON content_upload_sessions (status, expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS content_upload_sessions_open_component_idx
    ON content_upload_sessions (digital_component_id)
    WHERE status IN ('uploading', 'interrupted', 'finalizing');
CREATE UNIQUE INDEX IF NOT EXISTS content_upload_sessions_open_draft_component_idx
    ON content_upload_sessions (draft_component_id)
    WHERE status IN ('uploading', 'interrupted', 'finalizing');

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
CREATE OR REPLACE FUNCTION bump_digital_component_version()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (to_jsonb(NEW) - ARRAY['active_content_set_id', 'upload_completed_at'])
       IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY['active_content_set_id', 'upload_completed_at']) THEN
        NEW.version := OLD.version + 1;
    ELSE
        NEW.version := OLD.version;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER digital_components_bump_version
BEFORE UPDATE ON digital_components
FOR EACH ROW EXECUTE FUNCTION bump_digital_component_version();

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
DECLARE
    target_content_set_id bigint;
BEGIN
    target_content_set_id := CASE WHEN TG_OP = 'DELETE'
        THEN OLD.content_set_id ELSE NEW.content_set_id END;
    PERFORM assert_record_effectively_open(
        (SELECT dc.record_id
           FROM digital_component_content_sets content_set
           JOIN digital_components dc ON dc.id = content_set.digital_component_id
          WHERE content_set.id = target_content_set_id)
    );
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE OR REPLACE FUNCTION protect_content_set_in_closed_aggregation()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target_component_id bigint;
BEGIN
    target_component_id := CASE WHEN TG_OP = 'DELETE'
        THEN OLD.digital_component_id ELSE NEW.digital_component_id END;
    PERFORM assert_record_effectively_open(
        (SELECT record_id FROM digital_components WHERE id = target_component_id)
    );
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
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

DROP TRIGGER IF EXISTS digital_component_content_sets_protect_closed_aggregation ON digital_component_content_sets;
CREATE TRIGGER digital_component_content_sets_protect_closed_aggregation
BEFORE INSERT OR UPDATE OR DELETE ON digital_component_content_sets
FOR EACH ROW EXECUTE FUNCTION protect_content_set_in_closed_aggregation();


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
        SELECT id, parent_org_unit_id, date_deactivated FROM org_units WHERE id = p_org_unit_id
        UNION ALL
        SELECT parent.id, parent.parent_org_unit_id, parent.date_deactivated
        FROM org_units parent JOIN ancestors child ON parent.id = child.parent_org_unit_id
    )
    SELECT COALESCE(bool_and(date_deactivated IS NULL), false) FROM ancestors;
$$;

CREATE OR REPLACE FUNCTION role_effectively_active(p_role_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT COALESCE(r.date_deactivated IS NULL AND org_unit_effectively_active(r.org_unit_id), false)
    FROM roles r WHERE r.id = p_role_id;
$$;

CREATE OR REPLACE FUNCTION validate_user_management_lifecycle_dates()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.date_deactivated IS NOT NULL AND NEW.date_deactivated > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE=TG_TABLE_NAME || ' deactivation date cannot be in the future';
    END IF;
    IF TG_TABLE_NAME = 'users'
       AND NULLIF(to_jsonb(NEW)->>'date_suspended', '')::timestamptz > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='user suspension date cannot be in the future';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validate_active_role_assignment()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM users
        WHERE id=NEW.user_id
          AND date_deactivated IS NULL
          AND date_suspended IS NULL
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='role assignments require an active user';
    END IF;
    IF NOT role_effectively_active(NEW.role_id) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='role assignments require an effectively active role and organization hierarchy';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS org_units_normalize_lifecycle ON org_units;
CREATE TRIGGER org_units_validate_lifecycle_dates
BEFORE INSERT OR UPDATE OF date_deactivated ON org_units
FOR EACH ROW EXECUTE FUNCTION validate_user_management_lifecycle_dates();

DROP TRIGGER IF EXISTS users_normalize_lifecycle ON users;
CREATE TRIGGER users_validate_lifecycle_dates
BEFORE INSERT OR UPDATE OF date_deactivated, date_suspended ON users
FOR EACH ROW EXECUTE FUNCTION validate_user_management_lifecycle_dates();

DROP TRIGGER IF EXISTS roles_normalize_lifecycle ON roles;
CREATE TRIGGER roles_validate_lifecycle_dates
BEFORE INSERT OR UPDATE OF date_deactivated ON roles
FOR EACH ROW EXECUTE FUNCTION validate_user_management_lifecycle_dates();

DROP TRIGGER IF EXISTS user_role_assignments_validate_active ON user_role_assignments;
CREATE TRIGGER user_role_assignments_validate_active
BEFORE INSERT OR UPDATE OF user_id, role_id ON user_role_assignments
FOR EACH ROW EXECUTE FUNCTION validate_active_role_assignment();

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
CREATE INDEX classifications_parent_code_browse_idx
    ON classifications (classification_scheme_id, parent_classification_id, code COLLATE "C", id);

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
CREATE INDEX aggregations_classification_number_browse_idx
    ON aggregations (classification_id, aggregation_number COLLATE "C", id);
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
DECLARE root_row record;
BEGIN
    WITH RECURSIVE lineage AS (
        SELECT a.*, 0 AS depth FROM aggregations AS a WHERE a.id = p_aggregation_id
        UNION ALL
        SELECT parent.*, child.depth + 1
        FROM aggregations AS parent
        JOIN lineage AS child ON parent.id = child.parent_aggregation_id
    )
    SELECT lineage.*
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

ALTER TABLE aggregations ADD COLUMN security_level_id bigint NOT NULL;
ALTER TABLE aggregations ADD CONSTRAINT aggregations_security_level_fk
    FOREIGN KEY (security_level_id) REFERENCES security_levels (id) ON DELETE RESTRICT;
ALTER TABLE records ADD COLUMN security_level_id bigint NOT NULL;
ALTER TABLE records ADD CONSTRAINT records_security_level_fk
    FOREIGN KEY (security_level_id) REFERENCES security_levels (id) ON DELETE RESTRICT;
ALTER TABLE roles ADD COLUMN security_level_id bigint NOT NULL;
ALTER TABLE roles ADD CONSTRAINT roles_security_level_fk
    FOREIGN KEY (security_level_id) REFERENCES security_levels (id) ON DELETE RESTRICT;
ALTER TABLE record_drafts ADD COLUMN security_level_id bigint
    REFERENCES security_levels (id) ON DELETE RESTRICT;
CREATE INDEX aggregations_security_level_id_idx ON aggregations (security_level_id);
CREATE INDEX records_security_level_id_idx ON records (security_level_id);
CREATE INDEX roles_security_level_id_idx ON roles (security_level_id);
CREATE INDEX record_drafts_security_level_id_idx ON record_drafts (security_level_id);

CREATE FUNCTION lowest_security_level_id()
RETURNS bigint LANGUAGE sql STABLE AS $$
    SELECT id FROM security_levels ORDER BY level_number, id LIMIT 1
$$;

CREATE FUNCTION default_entity_security_level()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.security_level_id IS NOT NULL THEN RETURN NEW; END IF;
    IF TG_TABLE_NAME = 'aggregations'
       AND NULLIF(to_jsonb(NEW)->>'parent_aggregation_id', '') IS NOT NULL THEN
        SELECT security_level_id INTO NEW.security_level_id
        FROM aggregations
        WHERE id = (to_jsonb(NEW)->>'parent_aggregation_id')::bigint;
    END IF;
    NEW.security_level_id := COALESCE(NEW.security_level_id, lowest_security_level_id());
    IF NEW.security_level_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='no security level is configured';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER roles_default_security_level BEFORE INSERT ON roles
FOR EACH ROW EXECUTE FUNCTION default_entity_security_level();
CREATE TRIGGER aggregations_default_security_level BEFORE INSERT ON aggregations
FOR EACH ROW EXECUTE FUNCTION default_entity_security_level();
CREATE TRIGGER records_default_security_level BEFORE INSERT ON records
FOR EACH ROW EXECUTE FUNCTION default_entity_security_level();

CREATE FUNCTION enforce_resource_security_hierarchy()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    resource_level integer;
    parent_level integer;
    child_max integer;
BEGIN
    SELECT level_number INTO STRICT resource_level
    FROM security_levels WHERE id = NEW.security_level_id;
    IF TG_TABLE_NAME = 'records' THEN
        IF NEW.aggregation_id IS NULL THEN RETURN NEW; END IF;
        SELECT level.level_number INTO parent_level
        FROM aggregations parent JOIN security_levels level ON level.id=parent.security_level_id
        WHERE parent.id=NEW.aggregation_id;
        IF parent_level IS NULL THEN RETURN NEW; END IF;
        IF parent_level < resource_level THEN
            RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='security_hierarchy_violation',
                DETAIL=format('record level %s exceeds parent aggregation level %s',resource_level,parent_level);
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.parent_aggregation_id IS NOT NULL THEN
        SELECT level.level_number INTO parent_level
        FROM aggregations parent JOIN security_levels level ON level.id=parent.security_level_id
        WHERE parent.id=NEW.parent_aggregation_id;
        IF parent_level IS NULL THEN RETURN NEW; END IF;
        IF parent_level < resource_level THEN
            RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='security_hierarchy_violation',
                DETAIL=format('aggregation level %s exceeds parent aggregation level %s',resource_level,parent_level);
        END IF;
    END IF;
    SELECT max(level_number) INTO child_max FROM (
        SELECT level.level_number FROM aggregations child
        JOIN security_levels level ON level.id=child.security_level_id
        WHERE child.parent_aggregation_id=NEW.id
        UNION ALL
        SELECT level.level_number FROM records child
        JOIN security_levels level ON level.id=child.security_level_id
        WHERE child.aggregation_id=NEW.id
    ) children;
    IF child_max IS NOT NULL AND resource_level < child_max THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='security_hierarchy_violation',
            DETAIL=format('aggregation level %s is below contained resource level %s',resource_level,child_max);
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER aggregations_enforce_security_hierarchy
BEFORE INSERT OR UPDATE OF parent_aggregation_id, security_level_id ON aggregations
FOR EACH ROW EXECUTE FUNCTION enforce_resource_security_hierarchy();
CREATE TRIGGER records_enforce_security_hierarchy
BEFORE INSERT OR UPDATE OF aggregation_id, security_level_id ON records
FOR EACH ROW EXECUTE FUNCTION enforce_resource_security_hierarchy();

CREATE FUNCTION enforce_security_level_catalogue_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.level_number IS DISTINCT FROM OLD.level_number AND EXISTS (
        SELECT 1 FROM aggregations child
        JOIN aggregations parent ON parent.id=child.parent_aggregation_id
        JOIN security_levels child_level ON child_level.id=child.security_level_id
        JOIN security_levels parent_level ON parent_level.id=parent.security_level_id
        WHERE (CASE WHEN parent_level.id=NEW.id THEN NEW.level_number ELSE parent_level.level_number END)
            < (CASE WHEN child_level.id=NEW.id THEN NEW.level_number ELSE child_level.level_number END)
        UNION ALL
        SELECT 1 FROM records child
        JOIN aggregations parent ON parent.id=child.aggregation_id
        JOIN security_levels child_level ON child_level.id=child.security_level_id
        JOIN security_levels parent_level ON parent_level.id=parent.security_level_id
        WHERE (CASE WHEN parent_level.id=NEW.id THEN NEW.level_number ELSE parent_level.level_number END)
            < (CASE WHEN child_level.id=NEW.id THEN NEW.level_number ELSE child_level.level_number END)
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='security_hierarchy_violation',
            DETAIL='changing this catalogue number would invalidate a resource hierarchy';
    END IF;
    NEW.date_updated := CURRENT_TIMESTAMP;
    NEW.version := OLD.version + 1;
    RETURN NEW;
END;
$$;

CREATE TRIGGER security_levels_validate_update BEFORE UPDATE ON security_levels
FOR EACH ROW EXECUTE FUNCTION enforce_security_level_catalogue_change();
CREATE TRIGGER security_levels_record_history
AFTER INSERT OR UPDATE OR DELETE ON security_levels
FOR EACH ROW EXECUTE FUNCTION record_entity_history('security_level');

















-- The canonical schema repeats upgrade DDL here so a new database is created
-- from this file alone. Migration scripts remain independent upgrade paths for
-- existing databases and are never included or invoked by this file.

-- Canonical definitions corresponding to 033_add_privileges_profiles_and_role_authorization.sql

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Database migration 033', true),
       set_config('app.event_source', 'migration', true),
       set_config('app.change_reason', 'Install the Phase 2 privilege and profile model', true),
       set_config('app.event_metadata', '{"migration":"033_add_privileges_profiles_and_role_authorization"}', true);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE privileges (
    id bigserial PRIMARY KEY,
    code text NOT NULL,
    name text NOT NULL,
    description text NOT NULL,
    category text NOT NULL,
    is_reserved boolean NOT NULL DEFAULT false,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    CONSTRAINT privileges_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT privileges_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT privileges_category_valid CHECK (category IN ('administration','aggregation','record','component','exceptional'))
);
CREATE UNIQUE INDEX privileges_code_ci_unique ON privileges(lower(code));

CREATE TABLE profiles (
    id bigserial PRIMARY KEY,
    code text NOT NULL,
    name text NOT NULL,
    description text,
    is_system boolean NOT NULL DEFAULT false,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    CONSTRAINT profiles_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT profiles_name_not_blank CHECK (btrim(name) <> '')
);
CREATE UNIQUE INDEX profiles_code_ci_unique ON profiles(lower(code));
CREATE UNIQUE INDEX profiles_name_ci_unique ON profiles(lower(name));

CREATE TABLE profile_privileges (
    id bigserial PRIMARY KEY,
    profile_id bigint NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    privilege_id bigint NOT NULL REFERENCES privileges(id) ON DELETE RESTRICT,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    CONSTRAINT profile_privileges_unique UNIQUE(profile_id, privilege_id)
);
CREATE INDEX profile_privileges_privilege_id_idx ON profile_privileges(privilege_id, profile_id);

CREATE TABLE privilege_dependencies (
    privilege_id bigint NOT NULL REFERENCES privileges(id) ON DELETE CASCADE,
    required_privilege_id bigint NOT NULL REFERENCES privileges(id) ON DELETE RESTRICT,
    PRIMARY KEY(privilege_id, required_privilege_id),
    CONSTRAINT privilege_dependencies_not_self CHECK (privilege_id <> required_privilege_id)
);

WITH seed(code, category, reserved) AS (VALUES
 ('authorization.administer','administration',false), ('authorization.explain','administration',false),
 ('security_levels.administer','administration',false), ('identity.users.administer','administration',false),
 ('identity.sessions.administer','administration',false), ('organization.browse','administration',false),
 ('organization.administer','administration',false), ('organization.ownership.correct','exceptional',false),
 ('classifications.administer','administration',false), ('audit.view','administration',false),
 ('aggregation.view','aggregation',false), ('aggregation.create_root','aggregation',false),
 ('aggregation.create_child','aggregation',false), ('aggregation.modify','aggregation',false),
 ('aggregation.move','aggregation',false), ('aggregation.reclassify','aggregation',false),
 ('aggregation.close','aggregation',false), ('aggregation.reopen','aggregation',false),
 ('aggregation.delete','aggregation',false), ('aggregation.security_level.change','aggregation',false),
 ('aggregation.acl.manage','aggregation',false), ('record.view','record',false),
 ('record.create','record',false), ('record.modify','record',false), ('record.move','record',false),
 ('record.delete','record',false), ('record.security_level.change','record',false),
 ('record.acl.manage','record',false), ('record.component.view','component',false),
 ('record.component.download','component',false), ('record.component.add','component',false),
 ('record.component.replace','component',false), ('record.component.remove','component',false),
 ('record.component.reorder','component',false), ('record.component.share','component',true),
 ('record.component.print','component',true), ('security.resource.downgrade','exceptional',false),
 ('closure.correct_record_placement','exceptional',false), ('authorization.recovery','exceptional',true)
)
INSERT INTO privileges(code,name,description,category,is_reserved)
SELECT code, initcap(replace(replace(code,'.',' '),'_',' ')),
       'Global capability: ' || code, category, reserved FROM seed;

UPDATE privileges
SET name='Browse Organization Structure',
    description='Browse the organization hierarchy and view concise organization-unit, role, and user summaries.'
WHERE code='organization.browse';

INSERT INTO profiles(code,name,description,is_system) VALUES
 ('ALL_PRIVS','All privileges','Migration and controlled compatibility profile',true),
 ('SYS_ADMIN','System Administrator','Platform administration without governed-content bypass',true),
 ('INFO_GOV_MGR','Information Governance Manager','Universal governed-information custody and classification administration, subject to privilege and clearance gates',true),
 ('INFO_GOV_OFFICER','Information Governance Officer','Universal governed-information custody and classification administration, subject to privilege and clearance gates',true);

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id, privilege.id FROM profiles profile CROSS JOIN privileges privilege
WHERE profile.code='ALL_PRIVS';

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id, privilege.id FROM profiles profile JOIN privileges privilege ON privilege.code IN (
 'authorization.administer','authorization.explain','security_levels.administer',
 'identity.users.administer','identity.sessions.administer','organization.browse','organization.administer',
 'classifications.administer','audit.view') WHERE profile.code='SYS_ADMIN';

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id, privilege.id FROM profiles profile JOIN privileges privilege ON
 privilege.code IN ('authorization.administer','authorization.explain','classifications.administer','security_levels.administer','audit.view','organization.browse','organization.ownership.correct',
 'aggregation.view','aggregation.create_root','aggregation.create_child','aggregation.modify',
 'aggregation.move','aggregation.reclassify','aggregation.close','aggregation.reopen',
 'aggregation.delete','aggregation.security_level.change','aggregation.acl.manage',
 'record.view','record.create','record.modify','record.move','record.delete',
 'record.security_level.change','record.acl.manage','record.component.view',
 'record.component.download','record.component.add','record.component.replace',
 'record.component.remove','record.component.reorder','record.component.share',
 'record.component.print','security.resource.downgrade','closure.correct_record_placement')
WHERE profile.code IN ('INFO_GOV_MGR','INFO_GOV_OFFICER');

INSERT INTO privilege_dependencies(privilege_id,required_privilege_id)
SELECT dependent.id, required.id FROM privileges dependent CROSS JOIN privileges required
WHERE required.code = CASE
 WHEN dependent.code LIKE 'aggregation.%' AND dependent.code <> 'aggregation.view' THEN 'aggregation.view'
 WHEN (dependent.code LIKE 'record.%' OR dependent.code LIKE 'record.component.%') AND dependent.code <> 'record.view' THEN 'record.view'
 END;

ALTER TABLE roles ADD COLUMN profile_id bigint;
ALTER TABLE roles ADD COLUMN is_information_governance boolean NOT NULL DEFAULT false;
UPDATE roles SET profile_id=(SELECT id FROM profiles WHERE code='ALL_PRIVS');
ALTER TABLE roles ALTER COLUMN profile_id SET NOT NULL;
ALTER TABLE roles ADD CONSTRAINT roles_profile_fk FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE RESTRICT;
CREATE INDEX roles_profile_id_idx ON roles(profile_id);
CREATE INDEX roles_governance_clearance_idx ON roles(is_information_governance,security_level_id) WHERE is_information_governance;

CREATE OR REPLACE FUNCTION default_role_profile()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.profile_id IS NULL THEN
        SELECT id INTO NEW.profile_id FROM profiles WHERE code='ALL_PRIVS';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER roles_default_profile BEFORE INSERT ON roles
FOR EACH ROW EXECUTE FUNCTION default_role_profile();

CREATE OR REPLACE FUNCTION touch_authorization_catalogue()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.date_updated := CURRENT_TIMESTAMP;
    NEW.version := OLD.version + 1;
    RETURN NEW;
END;
$$;
CREATE TRIGGER privileges_touch BEFORE UPDATE ON privileges FOR EACH ROW EXECUTE FUNCTION touch_authorization_catalogue();
CREATE TRIGGER profiles_touch BEFORE UPDATE ON profiles FOR EACH ROW EXECUTE FUNCTION touch_authorization_catalogue();

CREATE TRIGGER privileges_record_history AFTER INSERT OR UPDATE OR DELETE ON privileges
FOR EACH ROW EXECUTE FUNCTION record_entity_history('privilege');
CREATE TRIGGER profiles_record_history AFTER INSERT OR UPDATE OR DELETE ON profiles
FOR EACH ROW EXECUTE FUNCTION record_entity_history('profile');
CREATE TRIGGER profile_privileges_record_history AFTER INSERT OR UPDATE OR DELETE ON profile_privileges
FOR EACH ROW EXECUTE FUNCTION record_entity_history('profile_privilege');

SELECT append_domain_event(
    'profile', profile.id, 'ROLE_PROFILE_BACKFILL_COMPLETED',
    jsonb_build_object(
        'profile_code', profile.code,
        'role_count', (SELECT count(*) FROM roles),
        'privilege_count', (SELECT count(*) FROM privileges),
        'unassigned_role_count', (SELECT count(*) FROM roles WHERE profile_id IS NULL)
    ),
    'Assign the compatibility profile before enforcing the non-null role profile reference'
)
FROM profiles profile WHERE profile.code='ALL_PRIVS';


-- Canonical definitions corresponding to 034_add_resource_acl_inheritance.sql

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Database migration 034', true),
       set_config('app.event_source', 'migration', true),
       set_config('app.change_reason', 'Install Phase 5 resource ACLs and live inheritance', true),
       set_config('app.event_metadata', '{"migration":"034_add_resource_acl_inheritance"}', true);

CREATE TABLE permissions (
    id bigserial PRIMARY KEY,
    code text NOT NULL,
    name text NOT NULL,
    description text NOT NULL,
    resource_type text NOT NULL CHECK (resource_type IN ('aggregation','record')),
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT permissions_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT permissions_name_not_blank CHECK (btrim(name) <> '')
);
CREATE UNIQUE INDEX permissions_code_ci_unique ON permissions(lower(code));

CREATE TABLE permission_dependencies (
    permission_id bigint NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    required_permission_id bigint NOT NULL REFERENCES permissions(id) ON DELETE RESTRICT,
    PRIMARY KEY(permission_id, required_permission_id),
    CHECK (permission_id <> required_permission_id)
);

WITH seed(code, resource_type) AS (VALUES
 ('aggregation.view','aggregation'), ('aggregation.modify_metadata','aggregation'),
 ('aggregation.delete','aggregation'), ('aggregation.close','aggregation'),
 ('aggregation.reopen','aggregation'), ('aggregation.add_child','aggregation'),
 ('aggregation.add_record','aggregation'), ('aggregation.move','aggregation'),
 ('aggregation.receive_child','aggregation'), ('aggregation.receive_record','aggregation'),
 ('aggregation.reclassify','aggregation'), ('aggregation.security_level.change','aggregation'),
 ('aggregation.acl.manage','aggregation'), ('aggregation.history.view','aggregation'),
 ('record.view','record'), ('record.modify_metadata','record'), ('record.delete','record'),
 ('record.move','record'), ('record.security_level.change','record'),
 ('record.acl.manage','record'), ('record.history.view','record'),
 ('record.component.list','record'), ('record.component.view','record'),
 ('record.component.download','record'), ('record.component.add','record'),
 ('record.component.replace','record'), ('record.component.remove','record'),
 ('record.component.reorder','record'), ('record.component.share','record'),
 ('record.component.print','record')
)
INSERT INTO permissions(code,name,description,resource_type)
SELECT code, initcap(replace(replace(code,'.',' '),'_',' ')),
       'Resource permission: ' || code, resource_type FROM seed;

INSERT INTO permission_dependencies(permission_id,required_permission_id)
SELECT dependent.id, required.id
FROM permissions dependent
JOIN permissions required ON required.code = CASE
  WHEN dependent.resource_type='aggregation' AND dependent.code<>'aggregation.view'
    THEN 'aggregation.view'
  WHEN dependent.code IN ('record.component.view','record.component.download','record.component.add',
                           'record.component.replace','record.component.remove','record.component.reorder')
    THEN 'record.component.list'
  WHEN dependent.code IN ('record.component.share','record.component.print')
    THEN 'record.component.view'
  WHEN dependent.resource_type='record' AND dependent.code<>'record.view'
    THEN 'record.view'
END
WHERE dependent.code NOT IN ('aggregation.view','record.view');

-- Materialize transitive dependencies so every storage boundary can validate
-- a complete permission set without relying on application recursion.
INSERT INTO permission_dependencies(permission_id,required_permission_id)
SELECT dependency.permission_id, root.id
FROM permission_dependencies dependency
JOIN permissions immediate ON immediate.id=dependency.required_permission_id
JOIN permissions root ON root.code=CASE
  WHEN immediate.resource_type='record' AND immediate.code<>'record.view' THEN 'record.view'
  ELSE immediate.code
END
ON CONFLICT DO NOTHING;

ALTER TABLE aggregations
  ADD COLUMN inherit_acl_from_parent boolean,
  ADD COLUMN default_child_aggregation_acl_mode text NOT NULL DEFAULT 'mirror_resource_acl',
  ADD COLUMN resource_acl_version integer NOT NULL DEFAULT 1,
  ADD COLUMN child_aggregation_acl_version integer NOT NULL DEFAULT 1,
  ADD COLUMN child_record_acl_version integer NOT NULL DEFAULT 1,
  ADD CONSTRAINT aggregations_child_acl_mode_valid
    CHECK (default_child_aggregation_acl_mode IN ('mirror_resource_acl','custom')),
  ADD CONSTRAINT aggregations_acl_versions_positive
    CHECK (resource_acl_version>0 AND child_aggregation_acl_version>0 AND child_record_acl_version>0);
UPDATE aggregations SET inherit_acl_from_parent=(parent_aggregation_id IS NOT NULL);
SET CONSTRAINTS ALL IMMEDIATE;
ALTER TABLE aggregations ALTER COLUMN inherit_acl_from_parent SET NOT NULL;
ALTER TABLE aggregations ALTER COLUMN inherit_acl_from_parent SET DEFAULT true;
ALTER TABLE aggregations ADD CONSTRAINT aggregations_root_acl_inheritance_valid
  CHECK ((parent_aggregation_id IS NULL AND NOT inherit_acl_from_parent)
      OR (parent_aggregation_id IS NOT NULL));

ALTER TABLE records
  ADD COLUMN inherit_acl_from_parent boolean NOT NULL DEFAULT true,
  ADD COLUMN resource_acl_version integer NOT NULL DEFAULT 1 CHECK (resource_acl_version>0);

ALTER TABLE roles ADD CONSTRAINT roles_everyone_code_reserved CHECK (lower(btrim(code)) <> 'everyone');
ALTER TABLE roles ADD CONSTRAINT roles_everyone_name_reserved CHECK (lower(btrim(name)) <> 'everyone');
ALTER TABLE roles ADD CONSTRAINT roles_org_unit_members_code_reserved CHECK (lower(btrim(code)) <> 'org_unit_members');
ALTER TABLE roles ADD CONSTRAINT roles_org_unit_members_name_reserved CHECK (lower(btrim(name)) <> 'all org unit members');

CREATE TABLE aggregation_acl_grants (
    id bigserial PRIMARY KEY,
    aggregation_id bigint NOT NULL REFERENCES aggregations(id) ON DELETE CASCADE,
    principal_type text NOT NULL CHECK (principal_type IN ('role','everyone','org_unit_members')),
    role_id bigint REFERENCES roles(id) ON DELETE RESTRICT,
    permission_id bigint NOT NULL REFERENCES permissions(id) ON DELETE RESTRICT,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version integer NOT NULL DEFAULT 1 CHECK (version>0),
    CHECK ((principal_type='role' AND role_id IS NOT NULL) OR
           (principal_type IN ('everyone','org_unit_members') AND role_id IS NULL))
);
CREATE UNIQUE INDEX aggregation_acl_role_grant_unique ON aggregation_acl_grants(aggregation_id,role_id,permission_id) WHERE principal_type='role';
CREATE UNIQUE INDEX aggregation_acl_everyone_grant_unique ON aggregation_acl_grants(aggregation_id,permission_id) WHERE principal_type='everyone';
CREATE UNIQUE INDEX aggregation_acl_org_unit_members_grant_unique ON aggregation_acl_grants(aggregation_id,permission_id) WHERE principal_type='org_unit_members';

CREATE TABLE aggregation_child_aggregation_acl_defaults (LIKE aggregation_acl_grants INCLUDING DEFAULTS INCLUDING GENERATED INCLUDING IDENTITY);
ALTER TABLE aggregation_child_aggregation_acl_defaults DROP COLUMN aggregation_id;
ALTER TABLE aggregation_child_aggregation_acl_defaults ADD COLUMN aggregation_id bigint NOT NULL REFERENCES aggregations(id) ON DELETE CASCADE;
ALTER TABLE aggregation_child_aggregation_acl_defaults ADD PRIMARY KEY(id);
ALTER TABLE aggregation_child_aggregation_acl_defaults ADD CHECK ((principal_type='role' AND role_id IS NOT NULL) OR (principal_type IN ('everyone','org_unit_members') AND role_id IS NULL));
ALTER TABLE aggregation_child_aggregation_acl_defaults ADD FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE RESTRICT;
ALTER TABLE aggregation_child_aggregation_acl_defaults ADD FOREIGN KEY(permission_id) REFERENCES permissions(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX child_aggregation_acl_role_grant_unique ON aggregation_child_aggregation_acl_defaults(aggregation_id,role_id,permission_id) WHERE principal_type='role';
CREATE UNIQUE INDEX child_aggregation_acl_everyone_grant_unique ON aggregation_child_aggregation_acl_defaults(aggregation_id,permission_id) WHERE principal_type='everyone';
CREATE UNIQUE INDEX child_aggregation_acl_org_unit_members_grant_unique ON aggregation_child_aggregation_acl_defaults(aggregation_id,permission_id) WHERE principal_type='org_unit_members';

CREATE TABLE aggregation_child_record_acl_defaults (LIKE aggregation_acl_grants INCLUDING DEFAULTS INCLUDING GENERATED INCLUDING IDENTITY);
ALTER TABLE aggregation_child_record_acl_defaults DROP COLUMN aggregation_id;
ALTER TABLE aggregation_child_record_acl_defaults ADD COLUMN aggregation_id bigint NOT NULL REFERENCES aggregations(id) ON DELETE CASCADE;
ALTER TABLE aggregation_child_record_acl_defaults ADD PRIMARY KEY(id);
ALTER TABLE aggregation_child_record_acl_defaults ADD CHECK ((principal_type='role' AND role_id IS NOT NULL) OR (principal_type IN ('everyone','org_unit_members') AND role_id IS NULL));
ALTER TABLE aggregation_child_record_acl_defaults ADD FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE RESTRICT;
ALTER TABLE aggregation_child_record_acl_defaults ADD FOREIGN KEY(permission_id) REFERENCES permissions(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX child_record_acl_role_grant_unique ON aggregation_child_record_acl_defaults(aggregation_id,role_id,permission_id) WHERE principal_type='role';
CREATE UNIQUE INDEX child_record_acl_everyone_grant_unique ON aggregation_child_record_acl_defaults(aggregation_id,permission_id) WHERE principal_type='everyone';
CREATE UNIQUE INDEX child_record_acl_org_unit_members_grant_unique ON aggregation_child_record_acl_defaults(aggregation_id,permission_id) WHERE principal_type='org_unit_members';

CREATE TABLE record_acl_grants (
    id bigserial PRIMARY KEY,
    record_id bigint NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    principal_type text NOT NULL CHECK (principal_type IN ('role','everyone','org_unit_members')),
    role_id bigint REFERENCES roles(id) ON DELETE RESTRICT,
    permission_id bigint NOT NULL REFERENCES permissions(id) ON DELETE RESTRICT,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version integer NOT NULL DEFAULT 1 CHECK (version>0),
    CHECK ((principal_type='role' AND role_id IS NOT NULL) OR
           (principal_type IN ('everyone','org_unit_members') AND role_id IS NULL))
);
CREATE UNIQUE INDEX record_acl_role_grant_unique ON record_acl_grants(record_id,role_id,permission_id) WHERE principal_type='role';
CREATE UNIQUE INDEX record_acl_everyone_grant_unique ON record_acl_grants(record_id,permission_id) WHERE principal_type='everyone';
CREATE UNIQUE INDEX record_acl_org_unit_members_grant_unique ON record_acl_grants(record_id,permission_id) WHERE principal_type='org_unit_members';

CREATE INDEX aggregation_acl_role_idx ON aggregation_acl_grants(role_id,aggregation_id,permission_id);
CREATE INDEX child_aggregation_acl_role_idx ON aggregation_child_aggregation_acl_defaults(role_id,aggregation_id,permission_id);
CREATE INDEX child_record_acl_role_idx ON aggregation_child_record_acl_defaults(role_id,aggregation_id,permission_id);
CREATE INDEX record_acl_role_idx ON record_acl_grants(role_id,record_id,permission_id);

-- Every local or custom ACL starts as Everyone/all. Inheritance determines
-- whether that local set is effective or dormant; no grants are copied later.
INSERT INTO aggregation_acl_grants(aggregation_id,principal_type,permission_id)
SELECT aggregation.id,'everyone',permission.id FROM aggregations aggregation CROSS JOIN permissions permission WHERE permission.resource_type='aggregation';
INSERT INTO aggregation_child_aggregation_acl_defaults(aggregation_id,principal_type,permission_id)
SELECT aggregation.id,'everyone',permission.id FROM aggregations aggregation CROSS JOIN permissions permission WHERE permission.resource_type='aggregation';
INSERT INTO aggregation_child_record_acl_defaults(aggregation_id,principal_type,permission_id)
SELECT aggregation.id,'everyone',permission.id FROM aggregations aggregation CROSS JOIN permissions permission WHERE permission.resource_type='record';
INSERT INTO record_acl_grants(record_id,principal_type,permission_id)
SELECT record.id,'everyone',permission.id FROM records record CROSS JOIN permissions permission WHERE permission.resource_type='record';

CREATE FUNCTION validate_acl_permission_type() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected text;
BEGIN
  expected := CASE WHEN TG_TABLE_NAME='aggregation_child_record_acl_defaults' OR TG_TABLE_NAME='record_acl_grants' THEN 'record' ELSE 'aggregation' END;
  IF NOT EXISTS (SELECT 1 FROM permissions WHERE id=NEW.permission_id AND resource_type=expected) THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='acl_permission_type_mismatch';
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION validate_acl_role_clearance() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_id bigint; sufficient boolean;
BEGIN
  IF NEW.principal_type <> 'role' THEN RETURN NEW; END IF;
  IF TG_TABLE_NAME='record_acl_grants' THEN
    SELECT role_level.level_number>=resource_level.level_number INTO sufficient
    FROM roles role JOIN security_levels role_level ON role_level.id=role.security_level_id
    JOIN records resource ON resource.id=NEW.record_id
    JOIN security_levels resource_level ON resource_level.id=resource.security_level_id
    WHERE role.id=NEW.role_id;
  ELSE
    SELECT role_level.level_number>=resource_level.level_number INTO sufficient
    FROM roles role JOIN security_levels role_level ON role_level.id=role.security_level_id
    JOIN aggregations resource ON resource.id=NEW.aggregation_id
    JOIN security_levels resource_level ON resource_level.id=resource.security_level_id
    WHERE role.id=NEW.role_id;
  END IF;
  IF NOT coalesce(sufficient,false) THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='role_clearance_below_resource';
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION validate_acl_dependencies() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_id bigint; owner_column text; missing boolean;
BEGIN
  owner_column := TG_ARGV[0];
  owner_id := CASE WHEN TG_OP='DELETE' THEN (to_jsonb(OLD)->>owner_column)::bigint ELSE (to_jsonb(NEW)->>owner_column)::bigint END;
  EXECUTE format($query$
    SELECT EXISTS(
      SELECT 1 FROM %I grant_row
      JOIN permission_dependencies dependency ON dependency.permission_id=grant_row.permission_id
      WHERE grant_row.%I=$1
        AND grant_row.principal_type=$2
        AND grant_row.role_id IS NOT DISTINCT FROM $3
        AND NOT EXISTS (
          SELECT 1 FROM %I required_grant
          WHERE required_grant.%I=grant_row.%I
            AND required_grant.principal_type=grant_row.principal_type
            AND required_grant.role_id IS NOT DISTINCT FROM grant_row.role_id
            AND required_grant.permission_id=dependency.required_permission_id))
  $query$,TG_TABLE_NAME,owner_column,TG_TABLE_NAME,owner_column,owner_column)
  INTO missing USING owner_id,
    CASE WHEN TG_OP='DELETE' THEN OLD.principal_type ELSE NEW.principal_type END,
    CASE WHEN TG_OP='DELETE' THEN OLD.role_id ELSE NEW.role_id END;
  IF missing THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='permission_dependency_violation';
  END IF;
  RETURN NULL;
END $$;

CREATE TRIGGER aggregation_acl_type BEFORE INSERT OR UPDATE ON aggregation_acl_grants FOR EACH ROW EXECUTE FUNCTION validate_acl_permission_type();
CREATE TRIGGER child_aggregation_acl_type BEFORE INSERT OR UPDATE ON aggregation_child_aggregation_acl_defaults FOR EACH ROW EXECUTE FUNCTION validate_acl_permission_type();
CREATE TRIGGER child_record_acl_type BEFORE INSERT OR UPDATE ON aggregation_child_record_acl_defaults FOR EACH ROW EXECUTE FUNCTION validate_acl_permission_type();
CREATE TRIGGER record_acl_type BEFORE INSERT OR UPDATE ON record_acl_grants FOR EACH ROW EXECUTE FUNCTION validate_acl_permission_type();
CREATE TRIGGER aggregation_acl_clearance BEFORE INSERT OR UPDATE ON aggregation_acl_grants FOR EACH ROW EXECUTE FUNCTION validate_acl_role_clearance();
CREATE TRIGGER child_aggregation_acl_clearance BEFORE INSERT OR UPDATE ON aggregation_child_aggregation_acl_defaults FOR EACH ROW EXECUTE FUNCTION validate_acl_role_clearance();
CREATE TRIGGER child_record_acl_clearance BEFORE INSERT OR UPDATE ON aggregation_child_record_acl_defaults FOR EACH ROW EXECUTE FUNCTION validate_acl_role_clearance();
CREATE TRIGGER record_acl_clearance BEFORE INSERT OR UPDATE ON record_acl_grants FOR EACH ROW EXECUTE FUNCTION validate_acl_role_clearance();
CREATE CONSTRAINT TRIGGER aggregation_acl_dependencies AFTER INSERT OR UPDATE OR DELETE ON aggregation_acl_grants DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_acl_dependencies('aggregation_id');
CREATE CONSTRAINT TRIGGER child_aggregation_acl_dependencies AFTER INSERT OR UPDATE OR DELETE ON aggregation_child_aggregation_acl_defaults DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_acl_dependencies('aggregation_id');
CREATE CONSTRAINT TRIGGER child_record_acl_dependencies AFTER INSERT OR UPDATE OR DELETE ON aggregation_child_record_acl_defaults DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_acl_dependencies('aggregation_id');
CREATE CONSTRAINT TRIGGER record_acl_dependencies AFTER INSERT OR UPDATE OR DELETE ON record_acl_grants DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_acl_dependencies('record_id');

CREATE FUNCTION initialize_resource_acls() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE creator_role_id bigint := NULLIF(current_setting('app.creator_acl_role_id',true),'')::bigint;
BEGIN
  IF creator_role_id IS NULL THEN RETURN NEW; END IF;
  IF TG_TABLE_NAME='aggregations' THEN
    INSERT INTO aggregation_acl_grants(aggregation_id,principal_type,role_id,permission_id)
      SELECT NEW.id,'role',creator_role_id,id FROM permissions WHERE code=ANY(ARRAY['aggregation.view','aggregation.modify_metadata','aggregation.add_child','aggregation.add_record','aggregation.close','aggregation.acl.manage','aggregation.history.view']);
    INSERT INTO aggregation_acl_grants(aggregation_id,principal_type,permission_id)
      SELECT NEW.id,'org_unit_members',id FROM permissions WHERE code=ANY(ARRAY['aggregation.view','aggregation.history.view']);
    INSERT INTO aggregation_child_aggregation_acl_defaults(aggregation_id,principal_type,role_id,permission_id)
      SELECT NEW.id,'role',creator_role_id,id FROM permissions WHERE code=ANY(ARRAY['aggregation.view','aggregation.modify_metadata','aggregation.add_child','aggregation.add_record','aggregation.close','aggregation.acl.manage','aggregation.history.view']);
    INSERT INTO aggregation_child_aggregation_acl_defaults(aggregation_id,principal_type,permission_id)
      SELECT NEW.id,'org_unit_members',id FROM permissions WHERE code=ANY(ARRAY['aggregation.view','aggregation.history.view']);
    INSERT INTO aggregation_child_record_acl_defaults(aggregation_id,principal_type,role_id,permission_id)
      SELECT NEW.id,'role',creator_role_id,id FROM permissions WHERE code=ANY(ARRAY['record.view','record.acl.manage','record.history.view','record.component.list','record.component.view','record.component.download','record.component.share','record.component.print']);
    INSERT INTO aggregation_child_record_acl_defaults(aggregation_id,principal_type,permission_id)
      SELECT NEW.id,'org_unit_members',id FROM permissions WHERE code=ANY(ARRAY['record.view','record.component.list','record.component.view','record.component.download']);
  ELSE
    INSERT INTO record_acl_grants(record_id,principal_type,role_id,permission_id)
      SELECT NEW.id,'role',creator_role_id,id FROM permissions WHERE code=ANY(ARRAY['record.view','record.acl.manage','record.history.view','record.component.list','record.component.view','record.component.download','record.component.share','record.component.print']);
    INSERT INTO record_acl_grants(record_id,principal_type,permission_id)
      SELECT NEW.id,'org_unit_members',id FROM permissions WHERE code=ANY(ARRAY['record.view','record.component.list','record.component.view','record.component.download']);
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION normalize_aggregation_acl_inheritance() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.parent_aggregation_id IS NULL THEN NEW.inherit_acl_from_parent := false; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER aggregations_normalize_acl_inheritance BEFORE INSERT OR UPDATE OF parent_aggregation_id ON aggregations FOR EACH ROW EXECUTE FUNCTION normalize_aggregation_acl_inheritance();
CREATE TRIGGER aggregations_initialize_acls AFTER INSERT ON aggregations FOR EACH ROW EXECUTE FUNCTION initialize_resource_acls();
CREATE TRIGGER records_initialize_acls AFTER INSERT ON records FOR EACH ROW EXECUTE FUNCTION initialize_resource_acls();

CREATE TRIGGER aggregation_acl_history AFTER INSERT OR UPDATE OR DELETE ON aggregation_acl_grants FOR EACH ROW EXECUTE FUNCTION record_entity_history('aggregation_acl_grant');
CREATE TRIGGER child_aggregation_acl_history AFTER INSERT OR UPDATE OR DELETE ON aggregation_child_aggregation_acl_defaults FOR EACH ROW EXECUTE FUNCTION record_entity_history('aggregation_child_aggregation_acl_default');
CREATE TRIGGER child_record_acl_history AFTER INSERT OR UPDATE OR DELETE ON aggregation_child_record_acl_defaults FOR EACH ROW EXECUTE FUNCTION record_entity_history('aggregation_child_record_acl_default');
CREATE TRIGGER record_acl_history AFTER INSERT OR UPDATE OR DELETE ON record_acl_grants FOR EACH ROW EXECUTE FUNCTION record_entity_history('record_acl_grant');


-- Canonical definitions corresponding to 035_enforce_resource_read_authorization.sql

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Database migration 035', true),
       set_config('app.event_source', 'migration', true),
       set_config('app.change_reason', 'Install Phase 6 governed-resource read predicates', true),
       set_config('app.event_metadata', '{"migration":"035_enforce_resource_read_authorization"}', true);

-- This is deliberately a database predicate: callers can compose it into the
-- query before count, sort, and pagination, avoiding both inference leaks and
-- per-row authorization queries.
CREATE FUNCTION user_has_global_privilege(p_user_id bigint, p_code text)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1
      FROM users account
      JOIN user_role_assignments assignment ON assignment.user_id=account.id
      JOIN roles role ON role.id=assignment.role_id
      JOIN profile_privileges membership ON membership.profile_id=role.profile_id
      JOIN privileges privilege ON privilege.id=membership.privilege_id
     WHERE account.id=p_user_id AND account.status='active'
       AND assignment.valid_from<=CURRENT_TIMESTAMP
       AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
       AND role_effectively_active(role.id)
       AND privilege.code=p_code
  )
$$;

CREATE FUNCTION user_has_aggregation_permission(
  p_user_id bigint, p_aggregation_id bigint, p_permission text
) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
DECLARE
  cursor_row aggregations%ROWTYPE;
  parent_row aggregations%ROWTYPE;
  source_id bigint;
  source_kind text;
BEGIN
  SELECT * INTO cursor_row FROM aggregations WHERE id=p_aggregation_id;
  IF NOT FOUND THEN RETURN false; END IF;
  IF NOT cursor_row.inherit_acl_from_parent OR cursor_row.parent_aggregation_id IS NULL THEN
    source_id := cursor_row.id; source_kind := 'resource';
  ELSE
    LOOP
      SELECT * INTO parent_row FROM aggregations WHERE id=cursor_row.parent_aggregation_id;
      IF NOT FOUND THEN RETURN false; END IF;
      IF parent_row.default_child_aggregation_acl_mode='custom' THEN
        source_id := parent_row.id; source_kind := 'child_default'; EXIT;
      ELSIF NOT parent_row.inherit_acl_from_parent OR parent_row.parent_aggregation_id IS NULL THEN
        source_id := parent_row.id; source_kind := 'resource'; EXIT;
      END IF;
      cursor_row := parent_row;
    END LOOP;
  END IF;

  IF source_kind='resource' THEN
    RETURN EXISTS (
      SELECT 1 FROM aggregation_acl_grants grant_row
      JOIN permissions permission ON permission.id=grant_row.permission_id
      WHERE grant_row.aggregation_id=source_id AND permission.code=p_permission
        AND (grant_row.principal_type='everyone' OR EXISTS (
          SELECT 1 FROM user_role_assignments assignment
          WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
            AND assignment.valid_from<=CURRENT_TIMESTAMP
            AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
            AND role_effectively_active(assignment.role_id)))
    );
  END IF;
  RETURN EXISTS (
    SELECT 1 FROM aggregation_child_aggregation_acl_defaults grant_row
    JOIN permissions permission ON permission.id=grant_row.permission_id
    WHERE grant_row.aggregation_id=source_id AND permission.code=p_permission
      AND (grant_row.principal_type='everyone' OR EXISTS (
        SELECT 1 FROM user_role_assignments assignment
        WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
          AND assignment.valid_from<=CURRENT_TIMESTAMP
          AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
          AND role_effectively_active(assignment.role_id)))
  );
END $$;

CREATE FUNCTION user_can_view_aggregation(p_user_id bigint, p_aggregation_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT user_has_global_privilege(p_user_id,'aggregation.view')
     AND EXISTS (SELECT 1 FROM user_role_assignments a
       JOIN roles r ON r.id=a.role_id JOIN security_levels rl ON rl.id=r.security_level_id
       JOIN aggregations resource ON resource.id=p_aggregation_id
       JOIN security_levels required ON required.id=resource.security_level_id
       WHERE a.user_id=p_user_id AND a.valid_from<=CURRENT_TIMESTAMP
         AND (a.valid_until IS NULL OR a.valid_until>CURRENT_TIMESTAMP)
         AND role_effectively_active(r.id) AND rl.level_number>=required.level_number)
     AND (
       user_has_aggregation_permission(p_user_id,p_aggregation_id,'aggregation.view')
       OR EXISTS (SELECT 1 FROM user_role_assignments a
         JOIN roles r ON r.id=a.role_id JOIN security_levels rl ON rl.id=r.security_level_id
         JOIN aggregations resource ON resource.id=p_aggregation_id
         JOIN security_levels required ON required.id=resource.security_level_id
         WHERE a.user_id=p_user_id AND r.is_information_governance
           AND a.valid_from<=CURRENT_TIMESTAMP
           AND (a.valid_until IS NULL OR a.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(r.id) AND rl.level_number>=required.level_number)
     )
$$;

CREATE FUNCTION user_has_record_permission(
  p_user_id bigint, p_record_id bigint, p_permission text
) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM records resource
    JOIN permissions permission ON permission.code=p_permission
    JOIN record_acl_grants grant_row ON NOT resource.inherit_acl_from_parent
      AND grant_row.record_id=resource.id AND grant_row.permission_id=permission.id
    WHERE resource.id=p_record_id AND
      (grant_row.principal_type='everyone' OR EXISTS (
        SELECT 1 FROM user_role_assignments assignment
        WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
          AND assignment.valid_from<=CURRENT_TIMESTAMP
          AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
          AND role_effectively_active(assignment.role_id)))
  ) OR EXISTS (
    SELECT 1 FROM records resource
    JOIN permissions permission ON permission.code=p_permission
    JOIN aggregation_child_record_acl_defaults grant_row
      ON resource.inherit_acl_from_parent AND grant_row.aggregation_id=resource.aggregation_id
      AND grant_row.permission_id=permission.id
    WHERE resource.id=p_record_id AND
      (grant_row.principal_type='everyone' OR EXISTS (
        SELECT 1 FROM user_role_assignments assignment
        WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
          AND assignment.valid_from<=CURRENT_TIMESTAMP
          AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
          AND role_effectively_active(assignment.role_id)))
  )
$$;

CREATE FUNCTION user_can_view_record(p_user_id bigint, p_record_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT user_has_global_privilege(p_user_id,'record.view')
     AND EXISTS (SELECT 1 FROM user_role_assignments a
       JOIN roles r ON r.id=a.role_id JOIN security_levels rl ON rl.id=r.security_level_id
       JOIN records resource ON resource.id=p_record_id
       JOIN security_levels required ON required.id=resource.security_level_id
       WHERE a.user_id=p_user_id AND a.valid_from<=CURRENT_TIMESTAMP
         AND (a.valid_until IS NULL OR a.valid_until>CURRENT_TIMESTAMP)
         AND role_effectively_active(r.id) AND rl.level_number>=required.level_number)
     AND (
       user_has_record_permission(p_user_id,p_record_id,'record.view')
       OR EXISTS (SELECT 1 FROM user_role_assignments a
         JOIN roles r ON r.id=a.role_id JOIN security_levels rl ON rl.id=r.security_level_id
         JOIN records resource ON resource.id=p_record_id
         JOIN security_levels required ON required.id=resource.security_level_id
         WHERE a.user_id=p_user_id AND r.is_information_governance
           AND a.valid_from<=CURRENT_TIMESTAMP
           AND (a.valid_until IS NULL OR a.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(r.id) AND rl.level_number>=required.level_number)
     )
$$;

CREATE FUNCTION current_user_id() RETURNS bigint LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.user_id',true),'')::bigint
$$;
CREATE FUNCTION current_user_can_view_aggregation(p_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_id() IS NOT NULL AND user_can_view_aggregation(current_user_id(),p_id)
$$;
CREATE FUNCTION current_user_can_view_record(p_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_id() IS NOT NULL AND user_can_view_record(current_user_id(),p_id)
$$;

CREATE FUNCTION current_user_can_list_record_components(p_record_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_can_view_record(p_record_id)
     AND user_has_global_privilege(current_user_id(),'record.component.view')
     AND (
       user_has_record_permission(current_user_id(),p_record_id,'record.component.list')
       OR EXISTS (SELECT 1 FROM user_role_assignments a
         JOIN roles r ON r.id=a.role_id JOIN security_levels rl ON rl.id=r.security_level_id
         JOIN records resource ON resource.id=p_record_id
         JOIN security_levels required ON required.id=resource.security_level_id
         WHERE a.user_id=current_user_id() AND r.is_information_governance
           AND a.valid_from<=CURRENT_TIMESTAMP
           AND (a.valid_until IS NULL OR a.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(r.id) AND rl.level_number>=required.level_number)
     )
$$;

CREATE FUNCTION current_user_can_view_event_resource(
  p_entity_type text, p_entity_id bigint, p_before jsonb, p_after jsonb
) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
DECLARE record_id bigint;
DECLARE historical_level_id bigint;
BEGIN
  IF p_entity_type='aggregation' THEN
    IF EXISTS (SELECT 1 FROM aggregations WHERE id=p_entity_id) THEN
      RETURN current_user_can_view_aggregation(p_entity_id);
    END IF;
    historical_level_id := COALESCE(
      CASE WHEN (p_before->>'security_level_id') ~ '^[0-9]+$' THEN (p_before->>'security_level_id')::bigint END,
      CASE WHEN (p_after->>'security_level_id') ~ '^[0-9]+$' THEN (p_after->>'security_level_id')::bigint END
    );
  ELSIF p_entity_type='record' THEN
    IF EXISTS (SELECT 1 FROM records WHERE id=p_entity_id) THEN
      RETURN current_user_can_view_record(p_entity_id);
    END IF;
    historical_level_id := COALESCE(
      CASE WHEN (p_before->>'security_level_id') ~ '^[0-9]+$' THEN (p_before->>'security_level_id')::bigint END,
      CASE WHEN (p_after->>'security_level_id') ~ '^[0-9]+$' THEN (p_after->>'security_level_id')::bigint END
    );
  ELSIF p_entity_type IN ('digital_component','record_component') THEN
    SELECT component.record_id INTO record_id FROM digital_components component WHERE component.id=p_entity_id;
    IF record_id IS NULL THEN
      record_id := COALESCE(
        CASE WHEN (p_after->>'record_id') ~ '^[0-9]+$' THEN (p_after->>'record_id')::bigint END,
        CASE WHEN (p_before->>'record_id') ~ '^[0-9]+$' THEN (p_before->>'record_id')::bigint END
      );
    END IF;
    RETURN record_id IS NOT NULL AND current_user_can_view_record(record_id);
  ELSE
    RETURN true;
  END IF;
  IF historical_level_id IS NOT NULL THEN
    RETURN user_has_global_privilege(current_user_id(),'audit.view') AND EXISTS (
      SELECT 1 FROM user_role_assignments assignment
      JOIN roles role ON role.id=assignment.role_id
      JOIN security_levels role_level ON role_level.id=role.security_level_id
      JOIN security_levels required ON required.id=historical_level_id
      WHERE assignment.user_id=current_user_id()
        AND assignment.valid_from<=CURRENT_TIMESTAMP
        AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
        AND role_effectively_active(role.id)
        AND role_level.level_number>=required.level_number
    );
  END IF;
  RETURN false;
END $$;

CREATE VIEW authorized_event_history AS
SELECT event.id,event.occurred_at,event.transaction_id,event.entity_type,event.entity_id,
       event.operation,event.actor_user_id,event.actor_name,event.actor_email,event.actor_type,
       event.source,event.request_id,event.correlation_id,
       CASE WHEN visible.allowed THEN event.before_state ELSE NULL END AS before_state,
       CASE WHEN visible.allowed THEN event.after_state ELSE NULL END AS after_state,
       CASE WHEN visible.allowed THEN event.changed_fields ELSE ARRAY[]::text[] END AS changed_fields,
       CASE WHEN visible.allowed THEN event.reason ELSE NULL END AS reason,
       CASE WHEN visible.allowed THEN event.metadata
            ELSE jsonb_build_object('redacted',true,'reason','resource_access_denied') END AS metadata
FROM event_history event
CROSS JOIN LATERAL (
  SELECT current_user_can_view_event_resource(
    event.entity_type,event.entity_id,event.before_state,event.after_state
  ) AS allowed
) visible;

CREATE VIEW authorized_aggregations_for_search AS
SELECT resource.id,
       CASE WHEN resource.parent_aggregation_id IS NULL
                  OR current_user_can_view_aggregation(resource.parent_aggregation_id)
            THEN resource.parent_aggregation_id END AS parent_aggregation_id,
       resource.classification_id,resource.aggregation_number,resource.title,
       resource.description,resource.date_created,resource.date_opened,resource.date_closed,
       resource.security_level_id,resource.inherit_acl_from_parent,
       resource.default_child_aggregation_acl_mode,resource.resource_acl_version,
       resource.child_aggregation_acl_version,resource.child_record_acl_version,resource.version
FROM aggregations resource;

CREATE VIEW authorized_records_for_search AS
SELECT resource.id,
       CASE WHEN current_user_can_view_aggregation(resource.aggregation_id)
            THEN resource.aggregation_id END AS aggregation_id,
       resource.record_number,resource.title,resource.description,resource.date_created,
       resource.date_originated,resource.security_level_id,resource.inherit_acl_from_parent,
       resource.resource_acl_version,resource.version
FROM records resource;

CREATE INDEX user_role_assignments_effective_lookup_idx
  ON user_role_assignments(user_id,role_id,valid_from,valid_until);


-- Canonical definitions corresponding to 036_enforce_resource_mutation_authorization.sql

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 036',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Install Phase 7 resource mutation predicates',true),
       set_config('app.event_metadata','{"migration":"036_enforce_resource_mutation_authorization"}',true);

CREATE FUNCTION user_has_governance_clearance(p_user_id bigint,p_security_level_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS(
    SELECT 1 FROM user_role_assignments assignment
    JOIN roles role ON role.id=assignment.role_id
    JOIN security_levels role_level ON role_level.id=role.security_level_id
    JOIN security_levels required ON required.id=p_security_level_id
    WHERE assignment.user_id=p_user_id AND role.is_information_governance
      AND assignment.valid_from<=CURRENT_TIMESTAMP
      AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
      AND role_effectively_active(role.id)
      AND role_level.level_number>=required.level_number)
$$;

CREATE FUNCTION user_can_aggregation_operation(
  p_user_id bigint,p_aggregation_id bigint,p_privilege text,p_permission text
) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT user_can_view_aggregation(p_user_id,p_aggregation_id)
     AND user_has_global_privilege(p_user_id,p_privilege)
     AND (user_has_aggregation_permission(p_user_id,p_aggregation_id,p_permission)
          OR EXISTS(SELECT 1 FROM aggregations resource
                    WHERE resource.id=p_aggregation_id
                      AND user_has_governance_clearance(p_user_id,resource.security_level_id)))
$$;

CREATE FUNCTION user_can_record_operation(
  p_user_id bigint,p_record_id bigint,p_privilege text,p_permission text
) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT user_can_view_record(p_user_id,p_record_id)
     AND user_has_global_privilege(p_user_id,p_privilege)
     AND (user_has_record_permission(p_user_id,p_record_id,p_permission)
          OR EXISTS(SELECT 1 FROM records resource
                    WHERE resource.id=p_record_id
                      AND user_has_governance_clearance(p_user_id,resource.security_level_id)))
$$;

CREATE FUNCTION current_user_can_aggregation_operation(bigint,text,text)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_id() IS NOT NULL
     AND user_can_aggregation_operation(current_user_id(),$1,$2,$3)
$$;
CREATE FUNCTION current_user_can_record_operation(bigint,text,text)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_id() IS NOT NULL
     AND user_can_record_operation(current_user_id(),$1,$2,$3)
$$;


-- Canonical definitions corresponding to 037_enforce_draft_component_authorization.sql

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 037',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Install Phase 8 draft, component, and placement-correction policy',true),
       set_config('app.event_metadata','{"migration":"037_enforce_draft_component_authorization"}',true);

CREATE FUNCTION user_has_destination_record_permission(
  p_user_id bigint,p_aggregation_id bigint,p_permission text
) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS(
    SELECT 1 FROM aggregation_child_record_acl_defaults grant_row
    JOIN permissions permission ON permission.id=grant_row.permission_id
    WHERE grant_row.aggregation_id=p_aggregation_id AND permission.code=p_permission
      AND (grant_row.principal_type='everyone' OR EXISTS(
        SELECT 1 FROM user_role_assignments assignment
        WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
          AND assignment.valid_from<=CURRENT_TIMESTAMP
          AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
          AND role_effectively_active(assignment.role_id)))
  )
$$;

CREATE FUNCTION current_user_can_record_component_operation(
  p_record_id bigint,p_privilege text,p_permission text
) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_can_view_record(p_record_id)
     AND user_has_global_privilege(current_user_id(),p_privilege)
     AND (user_has_record_permission(current_user_id(),p_record_id,p_permission)
          OR EXISTS(SELECT 1 FROM records resource
                    WHERE resource.id=p_record_id
                      AND user_has_governance_clearance(current_user_id(),resource.security_level_id)))
$$;

CREATE OR REPLACE FUNCTION current_user_can_list_record_components(p_record_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_can_view_record(p_record_id)
     AND (user_has_record_permission(current_user_id(),p_record_id,'record.component.list')
          OR EXISTS(SELECT 1 FROM records resource
                    WHERE resource.id=p_record_id
                      AND user_has_governance_clearance(current_user_id(),resource.security_level_id)))
$$;

CREATE FUNCTION current_user_owns_open_draft(p_draft_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_id() IS NOT NULL AND EXISTS(
    SELECT 1 FROM record_drafts draft
    JOIN users owner ON owner.id=draft.owner_user_id
    WHERE draft.id=p_draft_id AND draft.owner_user_id=current_user_id()
      AND draft.status='open' AND draft.expires_at>CURRENT_TIMESTAMP
      AND owner.status='active')
$$;

CREATE OR REPLACE FUNCTION protect_record_in_closed_aggregation()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE correction boolean := COALESCE(current_setting('app.closed_record_placement_correction',true)='authorized',false);
BEGIN
  IF TG_OP='INSERT' THEN
    IF NOT correction THEN PERFORM assert_aggregation_effectively_open(NEW.aggregation_id); END IF;
    RETURN NEW;
  ELSIF TG_OP='DELETE' THEN
    PERFORM assert_aggregation_effectively_open(OLD.aggregation_id); RETURN OLD;
  END IF;
  IF correction AND NEW.aggregation_id IS DISTINCT FROM OLD.aggregation_id
     AND NEW.record_number IS NOT DISTINCT FROM OLD.record_number
     AND NEW.title IS NOT DISTINCT FROM OLD.title
     AND NEW.description IS NOT DISTINCT FROM OLD.description
     AND NEW.date_originated IS NOT DISTINCT FROM OLD.date_originated
     AND NEW.security_level_id IS NOT DISTINCT FROM OLD.security_level_id THEN
    RETURN NEW;
  END IF;
  PERFORM assert_aggregation_effectively_open(OLD.aggregation_id);
  IF NEW.aggregation_id IS DISTINCT FROM OLD.aggregation_id THEN
    PERFORM assert_aggregation_effectively_open(NEW.aggregation_id);
  END IF;
  RETURN NEW;
END $$;








-- Canonical definitions corresponding to
-- 044_add_organizational_ownership_foundation.sql

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Database migration 044', true),
       set_config('app.event_source', 'migration', true),
       set_config('app.change_reason', 'Add the organizational ownership schema foundation', true),
       set_config('app.event_metadata', '{"migration":"044_add_organizational_ownership_foundation"}', true);

ALTER TABLE aggregations
    ADD COLUMN owning_org_unit_id bigint,
    ADD CONSTRAINT aggregations_owning_org_unit_fk
        FOREIGN KEY (owning_org_unit_id) REFERENCES org_units (id) ON DELETE RESTRICT;

ALTER TABLE records
    ADD COLUMN owning_org_unit_id bigint,
    ADD CONSTRAINT records_owning_org_unit_fk
        FOREIGN KEY (owning_org_unit_id) REFERENCES org_units (id) ON DELETE RESTRICT;

CREATE INDEX aggregations_owner_parent_number_browse_idx
    ON aggregations (
        owning_org_unit_id,
        parent_aggregation_id,
        aggregation_number COLLATE "C",
        id
    );

CREATE INDEX records_owner_aggregation_number_browse_idx
    ON records (
        owning_org_unit_id,
        aggregation_id,
        record_number COLLATE "C",
        id
    );

CREATE VIEW organizational_ownership_diagnostics AS
SELECT
    'aggregation'::text AS resource_type,
    child.id AS resource_id,
    child.parent_aggregation_id AS parent_resource_id,
    child.owning_org_unit_id,
    parent.owning_org_unit_id AS expected_owning_org_unit_id,
    CASE WHEN child.owning_org_unit_id IS NULL THEN 'missing_owner' ELSE 'owner_mismatch' END AS issue
FROM aggregations AS child
LEFT JOIN aggregations AS parent ON parent.id = child.parent_aggregation_id
WHERE child.owning_org_unit_id IS NULL
   OR (child.parent_aggregation_id IS NOT NULL
       AND child.owning_org_unit_id IS DISTINCT FROM parent.owning_org_unit_id)
UNION ALL
SELECT
    'record'::text,
    record.id,
    record.aggregation_id,
    record.owning_org_unit_id,
    parent.owning_org_unit_id,
    CASE WHEN record.owning_org_unit_id IS NULL THEN 'missing_owner' ELSE 'owner_mismatch' END
FROM records AS record
JOIN aggregations AS parent ON parent.id = record.aggregation_id
WHERE record.owning_org_unit_id IS NULL
   OR record.owning_org_unit_id IS DISTINCT FROM parent.owning_org_unit_id;

CREATE OR REPLACE FUNCTION event_reference_identity(reference_field text, reference_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE snapshot jsonb;
DECLARE existing_snapshots jsonb;
BEGIN
    CASE reference_field
        WHEN 'profile_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM profiles WHERE id=reference_id;
        WHEN 'old_profile_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM profiles WHERE id=reference_id;
        WHEN 'new_profile_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM profiles WHERE id=reference_id;
        WHEN 'security_level_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name,'level_number',level_number) INTO snapshot FROM security_levels WHERE id=reference_id;
        WHEN 'classification_id' THEN SELECT jsonb_build_object('id',id,'code',code,'title',title) INTO snapshot FROM classifications WHERE id=reference_id;
        WHEN 'parent_classification_id' THEN SELECT jsonb_build_object('id',id,'code',code,'title',title) INTO snapshot FROM classifications WHERE id=reference_id;
        WHEN 'classification_scheme_id' THEN SELECT jsonb_build_object('id',id,'code',code,'title',title) INTO snapshot FROM classification_schemes WHERE id=reference_id;
        WHEN 'aggregation_id' THEN SELECT jsonb_build_object('id',id,'code',aggregation_number,'title',title) INTO snapshot FROM aggregations WHERE id=reference_id;
        WHEN 'parent_aggregation_id' THEN SELECT jsonb_build_object('id',id,'code',aggregation_number,'title',title) INTO snapshot FROM aggregations WHERE id=reference_id;
        WHEN 'destination_aggregation_id' THEN SELECT jsonb_build_object('id',id,'code',aggregation_number,'title',title) INTO snapshot FROM aggregations WHERE id=reference_id;
        WHEN 'record_id' THEN SELECT jsonb_build_object('id',id,'code',record_number,'title',title) INTO snapshot FROM records WHERE id=reference_id;
        WHEN 'role_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM roles WHERE id=reference_id;
        WHEN 'supervisor_role_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM roles WHERE id=reference_id;
        WHEN 'user_id' THEN SELECT jsonb_build_object('id',id,'name',name,'email',email) INTO snapshot FROM users WHERE id=reference_id;
        WHEN 'owner_user_id' THEN SELECT jsonb_build_object('id',id,'name',name,'email',email) INTO snapshot FROM users WHERE id=reference_id;
        WHEN 'org_unit_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM org_units WHERE id=reference_id;
        WHEN 'parent_org_unit_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM org_units WHERE id=reference_id;
        WHEN 'owning_org_unit_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM org_units WHERE id=reference_id;
        ELSE snapshot := NULL;
    END CASE;
    RETURN snapshot;
END;
$$;

CREATE OR REPLACE FUNCTION event_state_reference_snapshots(event_state jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE reference_field text; reference_value text; snapshot jsonb; snapshots jsonb := '{}'::jsonb;
BEGIN
    IF event_state IS NULL OR jsonb_typeof(event_state) <> 'object' THEN RETURN snapshots; END IF;
    FOREACH reference_field IN ARRAY ARRAY[
        'profile_id','old_profile_id','new_profile_id','security_level_id',
        'classification_id','parent_classification_id','classification_scheme_id',
        'aggregation_id','parent_aggregation_id','destination_aggregation_id',
        'record_id','role_id','supervisor_role_id','user_id','owner_user_id',
        'org_unit_id','parent_org_unit_id','owning_org_unit_id'
    ] LOOP
        reference_value := event_state ->> reference_field;
        IF reference_value IS NOT NULL AND reference_value ~ '^[0-9]+$' THEN
            snapshot := event_reference_identity(reference_field,reference_value::bigint);
            IF snapshot IS NOT NULL THEN snapshots := snapshots || jsonb_build_object(reference_field,snapshot); END IF;
        END IF;
    END LOOP;
    RETURN snapshots;
END;
$$;


-- 045_assign_existing_organizational_ownership.sql
-- New databases contain no historical holdings to assign, but retain the
-- reporting structures used by the upgrade migration and later ACL work.
CREATE TABLE organizational_ownership_assignment_runs (
    id                    bigserial PRIMARY KEY,
    migration_version     text NOT NULL UNIQUE,
    started_at            timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at          timestamptz,
    root_count            bigint NOT NULL,
    aggregation_count     bigint NOT NULL,
    record_count          bigint NOT NULL,
    before_counts_by_unit jsonb NOT NULL,
    after_counts_by_unit  jsonb,
    CONSTRAINT ownership_assignment_run_version_not_blank
        CHECK (btrim(migration_version) <> ''),
    CONSTRAINT ownership_assignment_run_counts_nonnegative
        CHECK (root_count >= 0 AND aggregation_count >= 0 AND record_count >= 0),
    CONSTRAINT ownership_assignment_run_before_counts_object
        CHECK (jsonb_typeof(before_counts_by_unit) = 'object'),
    CONSTRAINT ownership_assignment_run_after_counts_object
        CHECK (after_counts_by_unit IS NULL OR jsonb_typeof(after_counts_by_unit) = 'object')
);

CREATE TABLE organizational_ownership_root_assignments (
    root_aggregation_id bigint PRIMARY KEY,
    run_id              bigint NOT NULL REFERENCES organizational_ownership_assignment_runs(id) ON DELETE RESTRICT,
    selected_role_id    bigint NOT NULL,
    selected_role_code  text NOT NULL,
    selected_role_name  text NOT NULL,
    owning_org_unit_id  bigint NOT NULL,
    owning_org_unit_code text NOT NULL,
    owning_org_unit_name text NOT NULL,
    match_score         integer NOT NULL CHECK (match_score >= 0),
    assignment_method   text NOT NULL CHECK (assignment_method IN (
        'text_match', 'score_tie_stable_distribution', 'no_text_match_stable_distribution'
    )),
    root_title          text NOT NULL,
    root_description    text,
    assigned_at         timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX organizational_ownership_root_assignments_role_idx
    ON organizational_ownership_root_assignments(selected_role_id, root_aggregation_id);
CREATE INDEX organizational_ownership_root_assignments_unit_idx
    ON organizational_ownership_root_assignments(owning_org_unit_id, root_aggregation_id);


-- 046_enforce_organizational_ownership.sql
ALTER TABLE aggregations ALTER COLUMN owning_org_unit_id SET NOT NULL;
ALTER TABLE records ALTER COLUMN owning_org_unit_id SET NOT NULL;

CREATE FUNCTION enforce_aggregation_ownership()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parent_owner bigint;
    target_owner bigint;
    confirmed boolean := COALESCE(NULLIF(current_setting('app.ownership_move_confirmed', true), '')::boolean, false);
    propagating boolean := current_setting('app.ownership_propagation', true) = 'authorized';
    correcting boolean := current_setting('app.ownership_correction_authorized', true) = 'authorized';
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.parent_aggregation_id IS NOT NULL THEN
            SELECT owning_org_unit_id INTO STRICT parent_owner
            FROM aggregations WHERE id = NEW.parent_aggregation_id FOR UPDATE;
            NEW.owning_org_unit_id := parent_owner;
        ELSIF NEW.owning_org_unit_id IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='23502', MESSAGE='root aggregation ownership is required';
        END IF;
        RETURN NEW;
    END IF;
    IF propagating THEN RETURN NEW; END IF;

    IF correcting THEN
        IF OLD.parent_aggregation_id IS NOT NULL OR NEW.parent_aggregation_id IS NOT NULL
           OR NEW.parent_aggregation_id IS DISTINCT FROM OLD.parent_aggregation_id
           OR NULLIF(btrim(current_setting('app.change_reason', true)), '') IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='ownership correction is restricted to root aggregations and requires a reason';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.parent_aggregation_id IS NOT DISTINCT FROM OLD.parent_aggregation_id THEN
        IF NEW.owning_org_unit_id IS DISTINCT FROM OLD.owning_org_unit_id THEN
            RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='owning_org_unit_id cannot be changed directly';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.parent_aggregation_id IS NULL THEN
        target_owner := OLD.owning_org_unit_id;
    ELSE
        SELECT owning_org_unit_id INTO STRICT target_owner
        FROM aggregations WHERE id = NEW.parent_aggregation_id FOR UPDATE;
    END IF;

    IF target_owner IS DISTINCT FROM OLD.owning_org_unit_id AND (
        NOT confirmed OR NULLIF(btrim(current_setting('app.change_reason', true)), '') IS NULL
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE='ownership-changing aggregation moves require a reason and explicit confirmation';
    END IF;
    NEW.owning_org_unit_id := target_owner;
    RETURN NEW;
END;
$$;

CREATE FUNCTION propagate_aggregation_ownership()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE previous_context text;
BEGIN
    IF NEW.owning_org_unit_id IS NOT DISTINCT FROM OLD.owning_org_unit_id
       OR current_setting('app.ownership_propagation', true) = 'authorized' THEN
        RETURN NEW;
    END IF;
    previous_context := current_setting('app.ownership_propagation', true);
    PERFORM set_config('app.ownership_propagation', 'authorized', true);
    WITH RECURSIVE descendants(id) AS (
        SELECT child.id FROM aggregations child WHERE child.parent_aggregation_id = NEW.id
        UNION ALL
        SELECT child.id FROM descendants parent
        JOIN aggregations child ON child.parent_aggregation_id = parent.id
    )
    UPDATE aggregations child SET owning_org_unit_id = NEW.owning_org_unit_id
    FROM descendants WHERE child.id = descendants.id
      AND child.owning_org_unit_id IS DISTINCT FROM NEW.owning_org_unit_id;
    WITH RECURSIVE subtree(id) AS (
        SELECT NEW.id
        UNION ALL
        SELECT child.id FROM subtree parent
        JOIN aggregations child ON child.parent_aggregation_id = parent.id
    )
    UPDATE records record SET owning_org_unit_id = NEW.owning_org_unit_id
    FROM subtree WHERE record.aggregation_id = subtree.id
      AND record.owning_org_unit_id IS DISTINCT FROM NEW.owning_org_unit_id;
    PERFORM set_config('app.ownership_propagation', COALESCE(previous_context, ''), true);
    RETURN NEW;
END;
$$;

CREATE FUNCTION enforce_record_ownership()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target_owner bigint;
    confirmed boolean := COALESCE(NULLIF(current_setting('app.ownership_move_confirmed', true), '')::boolean, false);
    propagating boolean := current_setting('app.ownership_propagation', true) = 'authorized';
BEGIN
    IF TG_OP = 'UPDATE' AND propagating THEN RETURN NEW; END IF;
    IF NEW.aggregation_id IS NULL THEN RETURN NEW; END IF;
    SELECT owning_org_unit_id INTO STRICT target_owner
    FROM aggregations WHERE id = NEW.aggregation_id FOR UPDATE;
    IF TG_OP = 'INSERT' THEN
        NEW.owning_org_unit_id := target_owner;
        RETURN NEW;
    END IF;
    IF NEW.aggregation_id IS NOT DISTINCT FROM OLD.aggregation_id THEN
        IF NEW.owning_org_unit_id IS DISTINCT FROM OLD.owning_org_unit_id THEN
            RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='owning_org_unit_id cannot be changed directly';
        END IF;
        RETURN NEW;
    END IF;
    IF target_owner IS DISTINCT FROM OLD.owning_org_unit_id AND (
        NOT confirmed OR NULLIF(btrim(current_setting('app.change_reason', true)), '') IS NULL
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE='ownership-changing record moves require a reason and explicit confirmation';
    END IF;
    NEW.owning_org_unit_id := target_owner;
    RETURN NEW;
END;
$$;

CREATE TRIGGER aggregations_enforce_ownership
BEFORE INSERT OR UPDATE OF parent_aggregation_id, owning_org_unit_id ON aggregations
FOR EACH ROW EXECUTE FUNCTION enforce_aggregation_ownership();
CREATE TRIGGER aggregations_propagate_ownership
AFTER UPDATE OF parent_aggregation_id, owning_org_unit_id ON aggregations
FOR EACH ROW EXECUTE FUNCTION propagate_aggregation_ownership();
CREATE TRIGGER records_enforce_ownership
BEFORE INSERT OR UPDATE OF aggregation_id, owning_org_unit_id ON records
FOR EACH ROW EXECUTE FUNCTION enforce_record_ownership();


-- 047_expose_organizational_ownership_in_search.sql
CREATE OR REPLACE VIEW authorized_aggregations_for_search AS
SELECT resource.id,
       CASE WHEN resource.parent_aggregation_id IS NULL
                  OR current_user_can_view_aggregation(resource.parent_aggregation_id)
            THEN resource.parent_aggregation_id END AS parent_aggregation_id,
       resource.classification_id,resource.aggregation_number,resource.title,
       resource.description,resource.date_created,resource.date_opened,resource.date_closed,
       resource.security_level_id,resource.inherit_acl_from_parent,
       resource.default_child_aggregation_acl_mode,resource.resource_acl_version,
       resource.child_aggregation_acl_version,resource.child_record_acl_version,resource.version,
       resource.owning_org_unit_id
FROM aggregations resource;

CREATE OR REPLACE VIEW authorized_records_for_search AS
SELECT resource.id,
       CASE WHEN current_user_can_view_aggregation(resource.aggregation_id)
            THEN resource.aggregation_id END AS aggregation_id,
       resource.record_number,resource.title,resource.description,resource.date_created,
       resource.date_originated,resource.security_level_id,resource.inherit_acl_from_parent,
       resource.resource_acl_version,resource.version,resource.owning_org_unit_id
FROM records resource;


-- 048_add_org_unit_members_acl_principal.sql
CREATE OR REPLACE FUNCTION user_has_aggregation_permission(
  p_user_id bigint, p_aggregation_id bigint, p_permission text
) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
DECLARE
  cursor_row aggregations%ROWTYPE;
  parent_row aggregations%ROWTYPE;
  source_id bigint;
  source_kind text;
  target_owner_id bigint;
BEGIN
  SELECT * INTO cursor_row FROM aggregations WHERE id=p_aggregation_id;
  IF NOT FOUND THEN RETURN false; END IF;
  target_owner_id := cursor_row.owning_org_unit_id;
  IF NOT cursor_row.inherit_acl_from_parent OR cursor_row.parent_aggregation_id IS NULL THEN
    source_id := cursor_row.id; source_kind := 'resource';
  ELSE
    LOOP
      SELECT * INTO parent_row FROM aggregations WHERE id=cursor_row.parent_aggregation_id;
      IF NOT FOUND THEN RETURN false; END IF;
      IF parent_row.default_child_aggregation_acl_mode='custom' THEN
        source_id := parent_row.id; source_kind := 'child_default'; EXIT;
      ELSIF NOT parent_row.inherit_acl_from_parent OR parent_row.parent_aggregation_id IS NULL THEN
        source_id := parent_row.id; source_kind := 'resource'; EXIT;
      END IF;
      cursor_row := parent_row;
    END LOOP;
  END IF;

  IF source_kind='resource' THEN
    RETURN EXISTS (
      SELECT 1 FROM aggregation_acl_grants grant_row
      JOIN permissions permission ON permission.id=grant_row.permission_id
      WHERE grant_row.aggregation_id=source_id AND permission.code=p_permission
        AND (grant_row.principal_type='everyone'
          OR (grant_row.principal_type='role' AND EXISTS (
            SELECT 1 FROM user_role_assignments assignment
            WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
              AND assignment.valid_from<=CURRENT_TIMESTAMP
              AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
              AND role_effectively_active(assignment.role_id)))
          OR (grant_row.principal_type='org_unit_members' AND EXISTS (
            SELECT 1 FROM user_role_assignments assignment
            JOIN roles role ON role.id=assignment.role_id
            WHERE assignment.user_id=p_user_id AND role.org_unit_id=target_owner_id
              AND assignment.valid_from<=CURRENT_TIMESTAMP
              AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
              AND role_effectively_active(role.id))))
    );
  END IF;
  RETURN EXISTS (
    SELECT 1 FROM aggregation_child_aggregation_acl_defaults grant_row
    JOIN permissions permission ON permission.id=grant_row.permission_id
    WHERE grant_row.aggregation_id=source_id AND permission.code=p_permission
      AND (grant_row.principal_type='everyone'
        OR (grant_row.principal_type='role' AND EXISTS (
          SELECT 1 FROM user_role_assignments assignment
          WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
            AND assignment.valid_from<=CURRENT_TIMESTAMP
            AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
            AND role_effectively_active(assignment.role_id)))
        OR (grant_row.principal_type='org_unit_members' AND EXISTS (
          SELECT 1 FROM user_role_assignments assignment
          JOIN roles role ON role.id=assignment.role_id
          WHERE assignment.user_id=p_user_id AND role.org_unit_id=target_owner_id
            AND assignment.valid_from<=CURRENT_TIMESTAMP
            AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
            AND role_effectively_active(role.id))))
  );
END $$;

CREATE OR REPLACE FUNCTION user_has_record_permission(
  p_user_id bigint, p_record_id bigint, p_permission text
) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM records resource
    JOIN permissions permission ON permission.code=p_permission
    JOIN record_acl_grants grant_row ON NOT resource.inherit_acl_from_parent
      AND grant_row.record_id=resource.id AND grant_row.permission_id=permission.id
    WHERE resource.id=p_record_id AND
      (grant_row.principal_type='everyone'
       OR (grant_row.principal_type='role' AND EXISTS (
         SELECT 1 FROM user_role_assignments assignment
         WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
           AND assignment.valid_from<=CURRENT_TIMESTAMP
           AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(assignment.role_id)))
       OR (grant_row.principal_type='org_unit_members' AND EXISTS (
         SELECT 1 FROM user_role_assignments assignment
         JOIN roles role ON role.id=assignment.role_id
         WHERE assignment.user_id=p_user_id AND role.org_unit_id=resource.owning_org_unit_id
           AND assignment.valid_from<=CURRENT_TIMESTAMP
           AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(role.id))))
  ) OR EXISTS (
    SELECT 1 FROM records resource
    JOIN permissions permission ON permission.code=p_permission
    JOIN aggregation_child_record_acl_defaults grant_row
      ON resource.inherit_acl_from_parent AND grant_row.aggregation_id=resource.aggregation_id
      AND grant_row.permission_id=permission.id
    WHERE resource.id=p_record_id AND
      (grant_row.principal_type='everyone'
       OR (grant_row.principal_type='role' AND EXISTS (
         SELECT 1 FROM user_role_assignments assignment
         WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
           AND assignment.valid_from<=CURRENT_TIMESTAMP
           AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(assignment.role_id)))
       OR (grant_row.principal_type='org_unit_members' AND EXISTS (
         SELECT 1 FROM user_role_assignments assignment
         JOIN roles role ON role.id=assignment.role_id
         WHERE assignment.user_id=p_user_id AND role.org_unit_id=resource.owning_org_unit_id
           AND assignment.valid_from<=CURRENT_TIMESTAMP
           AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(role.id))))
  )
$$;

CREATE OR REPLACE FUNCTION user_has_destination_record_permission(
  p_user_id bigint,p_aggregation_id bigint,p_permission text
) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS(
    SELECT 1 FROM aggregations resource
    JOIN aggregation_child_record_acl_defaults grant_row
      ON grant_row.aggregation_id=resource.id
    JOIN permissions permission ON permission.id=grant_row.permission_id
    WHERE resource.id=p_aggregation_id AND permission.code=p_permission
      AND (grant_row.principal_type='everyone'
       OR (grant_row.principal_type='role' AND EXISTS(
         SELECT 1 FROM user_role_assignments assignment
         WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
           AND assignment.valid_from<=CURRENT_TIMESTAMP
           AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(assignment.role_id)))
       OR (grant_row.principal_type='org_unit_members' AND EXISTS(
         SELECT 1 FROM user_role_assignments assignment
         JOIN roles role ON role.id=assignment.role_id
         WHERE assignment.user_id=p_user_id AND role.org_unit_id=resource.owning_org_unit_id
           AND assignment.valid_from<=CURRENT_TIMESTAMP
           AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(role.id))))
  )
$$;




ALTER TABLE aggregations
    ADD COLUMN medium text NOT NULL DEFAULT 'mixed',
    ADD COLUMN is_vital boolean NOT NULL DEFAULT false,
    ADD COLUMN date_of_next_review timestamptz,
    ADD COLUMN assigned_location text,
    ADD COLUMN current_location text,
    ADD CONSTRAINT aggregations_medium_valid CHECK (medium IN ('digital','physical','mixed')),
    ADD CONSTRAINT aggregations_assigned_location_valid CHECK (
        assigned_location IS NULL OR (
            assigned_location=btrim(assigned_location)
            AND assigned_location<>'' AND char_length(assigned_location)<=200
        )
    ),
    ADD CONSTRAINT aggregations_current_location_valid CHECK (
        current_location IS NULL OR (
            current_location=btrim(current_location)
            AND current_location<>'' AND char_length(current_location)<=200
        )
    );

ALTER TABLE records
    ADD COLUMN medium text NOT NULL DEFAULT 'mixed',
    ADD COLUMN is_vital boolean NOT NULL DEFAULT false,
    ADD COLUMN date_of_next_review timestamptz,
    ADD CONSTRAINT records_medium_valid CHECK (medium IN ('digital','physical','mixed'));

CREATE INDEX aggregations_medium_idx ON aggregations(medium,id);
CREATE INDEX aggregations_vital_idx ON aggregations(is_vital,id);
CREATE INDEX aggregations_next_review_idx
    ON aggregations(date_of_next_review,id) WHERE date_of_next_review IS NOT NULL;
CREATE INDEX records_medium_idx ON records(medium,id);
CREATE INDEX records_vital_idx ON records(is_vital,id);
CREATE INDEX records_next_review_idx
    ON records(date_of_next_review,id) WHERE date_of_next_review IS NOT NULL;

CREATE FUNCTION enforce_future_next_review_date()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.date_of_next_review IS NOT NULL
       AND (TG_OP='INSERT' OR NEW.date_of_next_review IS DISTINCT FROM OLD.date_of_next_review)
       AND NEW.date_of_next_review<=CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION USING ERRCODE='23514',
            MESSAGE='date_of_next_review must be in the future';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER aggregations_future_next_review
BEFORE INSERT OR UPDATE OF date_of_next_review ON aggregations
FOR EACH ROW EXECUTE FUNCTION enforce_future_next_review_date();

CREATE TRIGGER records_future_next_review
BEFORE INSERT OR UPDATE OF date_of_next_review ON records
FOR EACH ROW EXECUTE FUNCTION enforce_future_next_review_date();

CREATE FUNCTION aggregation_effective_assigned_location(p_aggregation_id bigint)
RETURNS text LANGUAGE sql STABLE AS $$
    WITH RECURSIVE ancestors AS (
        SELECT id,parent_aggregation_id,assigned_location,0 AS depth
        FROM aggregations WHERE id=p_aggregation_id
        UNION ALL
        SELECT parent.id,parent.parent_aggregation_id,parent.assigned_location,child.depth+1
        FROM ancestors child
        JOIN aggregations parent ON parent.id=child.parent_aggregation_id
    )
    SELECT assigned_location FROM ancestors
    WHERE assigned_location IS NOT NULL ORDER BY depth LIMIT 1
$$;

CREATE FUNCTION aggregation_effective_current_location(p_aggregation_id bigint)
RETURNS text LANGUAGE sql STABLE AS $$
    WITH RECURSIVE ancestors AS (
        SELECT id,parent_aggregation_id,current_location,0 AS depth
        FROM aggregations WHERE id=p_aggregation_id
        UNION ALL
        SELECT parent.id,parent.parent_aggregation_id,parent.current_location,child.depth+1
        FROM ancestors child
        JOIN aggregations parent ON parent.id=child.parent_aggregation_id
    )
    SELECT current_location FROM ancestors
    WHERE current_location IS NOT NULL ORDER BY depth LIMIT 1
$$;

CREATE FUNCTION aggregation_effective_assigned_location_source_id(p_aggregation_id bigint)
RETURNS bigint LANGUAGE sql STABLE AS $$
    WITH RECURSIVE ancestors AS (
        SELECT id,parent_aggregation_id,assigned_location,0 AS depth FROM aggregations WHERE id=p_aggregation_id
        UNION ALL
        SELECT parent.id,parent.parent_aggregation_id,parent.assigned_location,child.depth+1
        FROM ancestors child JOIN aggregations parent ON parent.id=child.parent_aggregation_id
    )
    SELECT id FROM ancestors WHERE assigned_location IS NOT NULL ORDER BY depth LIMIT 1
$$;

CREATE FUNCTION aggregation_effective_current_location_source_id(p_aggregation_id bigint)
RETURNS bigint LANGUAGE sql STABLE AS $$
    WITH RECURSIVE ancestors AS (
        SELECT id,parent_aggregation_id,current_location,0 AS depth FROM aggregations WHERE id=p_aggregation_id
        UNION ALL
        SELECT parent.id,parent.parent_aggregation_id,parent.current_location,child.depth+1
        FROM ancestors child JOIN aggregations parent ON parent.id=child.parent_aggregation_id
    )
    SELECT id FROM ancestors WHERE current_location IS NOT NULL ORDER BY depth LIMIT 1
$$;

CREATE OR REPLACE VIEW authorized_aggregations_for_search AS
SELECT resource.id,
       CASE WHEN resource.parent_aggregation_id IS NULL
                  OR current_user_can_view_aggregation(resource.parent_aggregation_id)
            THEN resource.parent_aggregation_id END AS parent_aggregation_id,
       resource.classification_id,resource.aggregation_number,resource.title,
       resource.description,resource.date_created,resource.date_opened,resource.date_closed,
       resource.security_level_id,resource.inherit_acl_from_parent,
       resource.default_child_aggregation_acl_mode,resource.resource_acl_version,
       resource.child_aggregation_acl_version,resource.child_record_acl_version,resource.version,
       resource.owning_org_unit_id,resource.medium,resource.is_vital,
       resource.date_of_next_review,resource.assigned_location,resource.current_location,
       aggregation_effective_assigned_location(resource.id) AS effective_assigned_location,
       aggregation_effective_current_location(resource.id) AS effective_current_location
       ,CASE WHEN current_user_can_view_aggregation(aggregation_effective_assigned_location_source_id(resource.id)) THEN aggregation_effective_assigned_location_source_id(resource.id) END AS effective_assigned_location_source_aggregation_id
       ,CASE WHEN current_user_can_view_aggregation(aggregation_effective_current_location_source_id(resource.id)) THEN aggregation_effective_current_location_source_id(resource.id) END AS effective_current_location_source_aggregation_id
FROM aggregations resource;

CREATE OR REPLACE VIEW authorized_records_for_search AS
SELECT resource.id,
       CASE WHEN current_user_can_view_aggregation(resource.aggregation_id)
            THEN resource.aggregation_id END AS aggregation_id,
       resource.record_number,resource.title,resource.description,resource.date_created,
       resource.date_originated,resource.security_level_id,resource.inherit_acl_from_parent,
       resource.resource_acl_version,resource.version,resource.owning_org_unit_id,
       resource.medium,resource.is_vital,resource.date_of_next_review,
       aggregation_effective_assigned_location(resource.aggregation_id) AS effective_assigned_location,
       aggregation_effective_current_location(resource.aggregation_id) AS effective_current_location
       ,CASE WHEN current_user_can_view_aggregation(aggregation_effective_assigned_location_source_id(resource.aggregation_id)) THEN aggregation_effective_assigned_location_source_id(resource.aggregation_id) END AS effective_assigned_location_source_aggregation_id
       ,CASE WHEN current_user_can_view_aggregation(aggregation_effective_current_location_source_id(resource.aggregation_id)) THEN aggregation_effective_current_location_source_id(resource.aggregation_id) END AS effective_current_location_source_aggregation_id
FROM records resource;


COMMIT;

-- Legal holds: persistence and non-bypassable policy enforcement.
BEGIN;

CREATE TABLE holds (
    id                      bigserial PRIMARY KEY,
    code                    text NOT NULL,
    name                    text NOT NULL,
    description             text,
    valid_from              timestamptz NOT NULL,
    valid_to                timestamptz,
    owner_user_id           bigint NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    preserve_resource_state boolean NOT NULL DEFAULT false,
    date_created            timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated            timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version                 bigint NOT NULL DEFAULT 1,
    CONSTRAINT holds_code_valid CHECK (code=btrim(code) AND code<>'' AND char_length(code)<=100),
    CONSTRAINT holds_name_valid CHECK (name=btrim(name) AND name<>'' AND char_length(name)<=300),
    CONSTRAINT holds_description_length CHECK (description IS NULL OR char_length(description)<=4000),
    CONSTRAINT holds_dates_in_order CHECK (valid_to IS NULL OR valid_to>valid_from),
    CONSTRAINT holds_version_positive CHECK (version>0)
);
CREATE UNIQUE INDEX holds_code_ci_unique ON holds(lower(code));
CREATE INDEX holds_effective_period_idx ON holds(valid_from,valid_to,id);
CREATE INDEX holds_owner_idx ON holds(owner_user_id,id);

CREATE TABLE hold_contributors (
    id           bigserial PRIMARY KEY,
    hold_id      bigint NOT NULL REFERENCES holds(id) ON DELETE CASCADE,
    user_id      bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version      bigint NOT NULL DEFAULT 1 CHECK (version>0),
    CONSTRAINT hold_contributors_unique UNIQUE(hold_id,user_id)
);
CREATE INDEX hold_contributors_user_idx ON hold_contributors(user_id,hold_id);

CREATE TABLE hold_aggregation_assignments (
    id                  bigserial PRIMARY KEY,
    hold_id             bigint NOT NULL REFERENCES holds(id) ON DELETE RESTRICT,
    aggregation_id      bigint NOT NULL REFERENCES aggregations(id) ON DELETE CASCADE,
    assigned_at         timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by_user_id bigint REFERENCES users(id) ON DELETE SET NULL,
    version             bigint NOT NULL DEFAULT 1 CHECK (version>0),
    CONSTRAINT hold_aggregation_assignments_unique UNIQUE(hold_id,aggregation_id)
);
CREATE INDEX hold_aggregation_assignments_resource_idx
    ON hold_aggregation_assignments(aggregation_id,hold_id);

CREATE TABLE hold_record_assignments (
    id                  bigserial PRIMARY KEY,
    hold_id             bigint NOT NULL REFERENCES holds(id) ON DELETE RESTRICT,
    record_id           bigint NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    assigned_at         timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by_user_id bigint REFERENCES users(id) ON DELETE SET NULL,
    version             bigint NOT NULL DEFAULT 1 CHECK (version>0),
    CONSTRAINT hold_record_assignments_unique UNIQUE(hold_id,record_id)
);
CREATE INDEX hold_record_assignments_resource_idx
    ON hold_record_assignments(record_id,hold_id);

INSERT INTO privileges(code,name,description,category,is_reserved)
VALUES ('holds.administer','Administer Legal Holds',
        'Create, update, and delete legal holds and manage their owners and contributors.',
        'administration',false),
       ('holds.membership.manage_all','Manage All Legal Hold Memberships',
        'Add or remove resources from any legal hold.',
        'administration',false)
ON CONFLICT DO NOTHING;
INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id
FROM profiles profile CROSS JOIN privileges privilege
WHERE (profile.code='ALL_PRIVS' AND privilege.code IN ('holds.administer','holds.membership.manage_all'))
   OR (profile.code IN ('INFO_GOV_MGR','INFO_GOV_OFFICER')
       AND privilege.code='holds.membership.manage_all')
ON CONFLICT DO NOTHING;

CREATE FUNCTION hold_is_effective(p_hold_id bigint,p_at_time timestamptz DEFAULT statement_timestamp())
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT COALESCE(
        (hold.valid_from<=p_at_time AND (hold.valid_to IS NULL OR p_at_time<hold.valid_to)),
        false
    ) FROM holds hold WHERE hold.id=p_hold_id
$$;

CREATE FUNCTION effective_holds_for_aggregation(
    p_aggregation_id bigint,p_at_time timestamptz DEFAULT statement_timestamp()
) RETURNS TABLE(
    hold_id bigint,code text,name text,preserve_resource_state boolean,
    is_direct boolean,is_inherited boolean,nearest_assigned_aggregation_id bigint
) LANGUAGE sql STABLE AS $$
    WITH RECURSIVE ancestry AS (
        SELECT aggregation.id,aggregation.parent_aggregation_id,0 AS depth
        FROM aggregations aggregation WHERE aggregation.id=p_aggregation_id
        UNION ALL
        SELECT parent.id,parent.parent_aggregation_id,child.depth+1
        FROM aggregations parent JOIN ancestry child ON child.parent_aggregation_id=parent.id
    ), matched AS (
        SELECT assignment.hold_id,ancestry.id AS assigned_aggregation_id,ancestry.depth
        FROM ancestry
        JOIN hold_aggregation_assignments assignment ON assignment.aggregation_id=ancestry.id
    )
    SELECT hold.id,hold.code,hold.name,hold.preserve_resource_state,
           bool_or(matched.depth=0),bool_or(matched.depth>0),
           (array_agg(matched.assigned_aggregation_id ORDER BY matched.depth))[1]
    FROM matched JOIN holds hold ON hold.id=matched.hold_id
    WHERE hold.valid_from<=p_at_time AND (hold.valid_to IS NULL OR p_at_time<hold.valid_to)
    GROUP BY hold.id,hold.code,hold.name,hold.preserve_resource_state
$$;

CREATE FUNCTION effective_holds_for_record(
    p_record_id bigint,p_at_time timestamptz DEFAULT statement_timestamp()
) RETURNS TABLE(
    hold_id bigint,code text,name text,preserve_resource_state boolean,
    is_direct boolean,is_inherited boolean,nearest_assigned_aggregation_id bigint
) LANGUAGE sql STABLE AS $$
    WITH RECURSIVE record_row AS (
        SELECT id,aggregation_id FROM records WHERE id=p_record_id
    ), ancestry AS (
        SELECT aggregation.id,aggregation.parent_aggregation_id,0 AS depth
        FROM aggregations aggregation JOIN record_row ON record_row.aggregation_id=aggregation.id
        UNION ALL
        SELECT parent.id,parent.parent_aggregation_id,child.depth+1
        FROM aggregations parent JOIN ancestry child ON child.parent_aggregation_id=parent.id
    ), matched AS (
        SELECT assignment.hold_id,true AS direct,false AS inherited,
               NULL::bigint AS assigned_aggregation_id,NULL::integer AS depth
        FROM record_row JOIN hold_record_assignments assignment ON assignment.record_id=record_row.id
        UNION ALL
        SELECT assignment.hold_id,false,true,ancestry.id,ancestry.depth
        FROM ancestry
        JOIN hold_aggregation_assignments assignment ON assignment.aggregation_id=ancestry.id
    )
    SELECT hold.id,hold.code,hold.name,hold.preserve_resource_state,
           bool_or(matched.direct),bool_or(matched.inherited),
           (array_agg(matched.assigned_aggregation_id ORDER BY matched.depth NULLS LAST)
             FILTER (WHERE matched.assigned_aggregation_id IS NOT NULL))[1]
    FROM matched JOIN holds hold ON hold.id=matched.hold_id
    WHERE hold.valid_from<=p_at_time AND (hold.valid_to IS NULL OR p_at_time<hold.valid_to)
    GROUP BY hold.id,hold.code,hold.name,hold.preserve_resource_state
$$;

CREATE FUNCTION resource_has_effective_hold(
    p_resource_type text,p_resource_id bigint,p_at_time timestamptz DEFAULT statement_timestamp()
) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
BEGIN
    IF p_resource_type='aggregation' THEN
        RETURN EXISTS(SELECT 1 FROM effective_holds_for_aggregation(p_resource_id,p_at_time));
    ELSIF p_resource_type='record' THEN
        RETURN EXISTS(SELECT 1 FROM effective_holds_for_record(p_resource_id,p_at_time));
    END IF;
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='unknown hold resource type';
END;
$$;

CREATE FUNCTION resource_state_changes_blocked(
    p_resource_type text,p_resource_id bigint,p_at_time timestamptz DEFAULT statement_timestamp()
) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
BEGIN
    IF p_resource_type='aggregation' THEN
        RETURN EXISTS(SELECT 1 FROM effective_holds_for_aggregation(p_resource_id,p_at_time)
                      WHERE preserve_resource_state);
    ELSIF p_resource_type='record' THEN
        RETURN EXISTS(SELECT 1 FROM effective_holds_for_record(p_resource_id,p_at_time)
                      WHERE preserve_resource_state);
    END IF;
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='unknown hold resource type';
END;
$$;

CREATE FUNCTION current_hold_actor_is_manager(p_hold_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS(
        SELECT 1 FROM holds hold JOIN users actor ON actor.id=NULLIF(current_setting('app.user_id',true),'')::bigint
        WHERE hold.id=p_hold_id AND actor.account_type='person'
          AND actor.date_deactivated IS NULL AND actor.date_suspended IS NULL
          AND (user_has_global_privilege(actor.id,'holds.administer')
               OR user_has_global_privilege(actor.id,'holds.membership.manage_all')
               OR hold.owner_user_id=actor.id OR EXISTS(
              SELECT 1 FROM hold_contributors contributor
              WHERE contributor.hold_id=hold.id AND contributor.user_id=actor.id))
    )
$$;

CREATE FUNCTION lock_hold_policy_shared() RETURNS void LANGUAGE plpgsql AS $$
BEGIN PERFORM pg_advisory_xact_lock_shared(7246,1); END;
$$;
CREATE FUNCTION lock_hold_policy_exclusive() RETURNS void LANGUAGE plpgsql AS $$
BEGIN PERFORM pg_advisory_xact_lock(7246,1); END;
$$;

CREATE FUNCTION validate_hold_person_reference() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE selected_user_id bigint;
BEGIN
    IF TG_TABLE_NAME='holds' THEN
        selected_user_id:=NEW.owner_user_id;
    ELSE
        selected_user_id:=NEW.user_id;
    END IF;
    IF NOT EXISTS(SELECT 1 FROM users WHERE id=selected_user_id AND account_type='person'
                  AND date_deactivated IS NULL AND date_suspended IS NULL) THEN
        RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='hold_owner_or_contributor_must_be_active_person';
    END IF;
    IF TG_TABLE_NAME='hold_contributors' THEN
        IF EXISTS(SELECT 1 FROM holds WHERE id=NEW.hold_id AND owner_user_id=NEW.user_id) THEN
            RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='hold_owner_cannot_be_contributor';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER holds_validate_owner BEFORE INSERT OR UPDATE OF owner_user_id ON holds
FOR EACH ROW EXECUTE FUNCTION validate_hold_person_reference();
CREATE TRIGGER hold_contributors_validate_user BEFORE INSERT OR UPDATE OF hold_id,user_id ON hold_contributors
FOR EACH ROW EXECUTE FUNCTION validate_hold_person_reference();

CREATE FUNCTION enforce_hold_change_reason() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE hold_created_in_transaction boolean:=false;
BEGIN
    PERFORM lock_hold_policy_exclusive();
    IF TG_TABLE_NAME='hold_contributors' AND TG_OP='DELETE' AND pg_trigger_depth()>1 THEN
        RETURN OLD;
    END IF;
    IF TG_TABLE_NAME='hold_contributors' AND TG_OP='INSERT' THEN
        SELECT xmin::text=pg_current_xact_id()::text INTO hold_created_in_transaction
        FROM holds WHERE id=NEW.hold_id;
    END IF;
    IF NOT hold_created_in_transaction
       AND NULLIF(btrim(current_setting('app.change_reason',true)),'') IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_change_reason_required';
    END IF;
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER holds_require_change_reason
BEFORE UPDATE OR DELETE ON holds FOR EACH ROW EXECUTE FUNCTION enforce_hold_change_reason();
CREATE TRIGGER hold_contributors_require_change_reason
BEFORE INSERT OR UPDATE OR DELETE ON hold_contributors FOR EACH ROW EXECUTE FUNCTION enforce_hold_change_reason();

CREATE FUNCTION enforce_hold_assignment_policy() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_hold_id bigint:=CASE WHEN TG_OP='DELETE' THEN OLD.hold_id ELSE NEW.hold_id END;
BEGIN
    PERFORM lock_hold_policy_exclusive();
    IF NULLIF(btrim(current_setting('app.change_reason',true)),'') IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_change_reason_required';
    END IF;
    IF NOT current_hold_actor_is_manager(target_hold_id) THEN
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_membership_manager_required';
    END IF;
    IF TG_OP='INSERT' AND NEW.assigned_by_user_id IS NULL THEN
        NEW.assigned_by_user_id:=NULLIF(current_setting('app.user_id',true),'')::bigint;
    END IF;
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER hold_aggregation_assignments_policy
BEFORE INSERT OR UPDATE OR DELETE ON hold_aggregation_assignments
FOR EACH ROW EXECUTE FUNCTION enforce_hold_assignment_policy();
CREATE TRIGGER hold_record_assignments_policy
BEFORE INSERT OR UPDATE OR DELETE ON hold_record_assignments
FOR EACH ROW EXECUTE FUNCTION enforce_hold_assignment_policy();

CREATE FUNCTION protect_held_resource() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE blocked boolean;
DECLARE allowed_old jsonb;
DECLARE allowed_new jsonb;
BEGIN
    PERFORM lock_hold_policy_shared();
    IF TG_OP='DELETE' THEN
        IF TG_TABLE_NAME='aggregations' THEN
            WITH RECURSIVE subtree AS (
                SELECT OLD.id AS id UNION ALL
                SELECT child.id FROM aggregations child JOIN subtree parent ON child.parent_aggregation_id=parent.id
            )
            SELECT EXISTS(
                SELECT 1 FROM subtree WHERE resource_has_effective_hold('aggregation',subtree.id)
                UNION ALL
                SELECT 1 FROM records record JOIN subtree ON subtree.id=record.aggregation_id
                WHERE resource_has_effective_hold('record',record.id)
            ) INTO blocked;
        ELSE
            blocked:=resource_has_effective_hold('record',OLD.id);
        END IF;
        IF blocked THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='effective_hold_prevents_deletion'; END IF;
        RETURN OLD;
    END IF;

    IF TG_TABLE_NAME='aggregations' THEN
        blocked:=resource_state_changes_blocked('aggregation',OLD.id);
        IF NEW.parent_aggregation_id IS DISTINCT FROM OLD.parent_aggregation_id THEN
            IF blocked OR (NEW.parent_aggregation_id IS NOT NULL AND EXISTS(
                SELECT 1 FROM effective_holds_for_aggregation(NEW.parent_aggregation_id) WHERE preserve_resource_state
            )) THEN
                RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='effective_hold_prevents_metadata_change';
            END IF;
            IF EXISTS(
                WITH old_holds AS (SELECT hold_id FROM effective_holds_for_aggregation(OLD.id)),
                     new_ancestor_holds AS (
                         SELECT hold_id FROM effective_holds_for_aggregation(NEW.parent_aggregation_id)
                         UNION SELECT hold_id FROM hold_aggregation_assignments WHERE aggregation_id=OLD.id AND hold_is_effective(hold_id)
                     ), changed AS ((SELECT * FROM old_holds EXCEPT SELECT * FROM new_ancestor_holds)
                                    UNION (SELECT * FROM new_ancestor_holds EXCEPT SELECT * FROM old_holds))
                SELECT 1 FROM changed WHERE NOT current_hold_actor_is_manager(changed.hold_id)
            ) THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_membership_required_for_held_move'; END IF;
        END IF;
        IF blocked THEN
            allowed_old:=to_jsonb(OLD)-ARRAY['security_level_id','owning_org_unit_id','assigned_location','current_location',
                'inherit_acl_from_parent','resource_acl_version','child_aggregation_acl_version','child_record_acl_version','version'];
            allowed_new:=to_jsonb(NEW)-ARRAY['security_level_id','owning_org_unit_id','assigned_location','current_location',
                'inherit_acl_from_parent','resource_acl_version','child_aggregation_acl_version','child_record_acl_version','version'];
            IF allowed_old IS DISTINCT FROM allowed_new THEN
                RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='effective_hold_prevents_metadata_change';
            END IF;
        END IF;
    ELSE
        blocked:=resource_state_changes_blocked('record',OLD.id);
        IF NEW.aggregation_id IS DISTINCT FROM OLD.aggregation_id THEN
            IF blocked OR EXISTS(SELECT 1 FROM effective_holds_for_aggregation(NEW.aggregation_id)
                                 WHERE preserve_resource_state) THEN
                RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='effective_hold_prevents_metadata_change';
            END IF;
            IF EXISTS(
                WITH old_holds AS (SELECT hold_id FROM effective_holds_for_record(OLD.id)),
                     new_holds AS (
                         SELECT hold_id FROM effective_holds_for_aggregation(NEW.aggregation_id)
                         UNION SELECT hold_id FROM hold_record_assignments WHERE record_id=OLD.id AND hold_is_effective(hold_id)
                     ), changed AS ((SELECT * FROM old_holds EXCEPT SELECT * FROM new_holds)
                                    UNION (SELECT * FROM new_holds EXCEPT SELECT * FROM old_holds))
                SELECT 1 FROM changed WHERE NOT current_hold_actor_is_manager(changed.hold_id)
            ) THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_membership_required_for_held_move'; END IF;
        END IF;
        IF blocked THEN
            allowed_old:=to_jsonb(OLD)-ARRAY['security_level_id','owning_org_unit_id','inherit_acl_from_parent',
                'resource_acl_version','version'];
            allowed_new:=to_jsonb(NEW)-ARRAY['security_level_id','owning_org_unit_id','inherit_acl_from_parent',
                'resource_acl_version','version'];
            IF allowed_old IS DISTINCT FROM allowed_new THEN
                RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='effective_hold_prevents_metadata_change';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER aggregations_protect_effective_holds
BEFORE UPDATE OR DELETE ON aggregations FOR EACH ROW EXECUTE FUNCTION protect_held_resource();
CREATE TRIGGER records_protect_effective_holds
BEFORE UPDATE OR DELETE ON records FOR EACH ROW EXECUTE FUNCTION protect_held_resource();

CREATE FUNCTION protect_held_component_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE component_id bigint;
DECLARE held_record_id bigint;
DECLARE failure_code text;
BEGIN
    PERFORM lock_hold_policy_shared();
    IF TG_TABLE_NAME='digital_components' THEN
        held_record_id:=CASE WHEN TG_OP='DELETE' THEN OLD.record_id ELSE NEW.record_id END;
    ELSIF TG_TABLE_NAME='digital_component_content_sets' THEN
        component_id:=CASE WHEN TG_OP='DELETE' THEN OLD.digital_component_id ELSE NEW.digital_component_id END;
        SELECT record_id INTO held_record_id FROM digital_components WHERE id=component_id;
    ELSIF TG_TABLE_NAME='digital_component_blobs' THEN
        SELECT component.digital_component_id INTO component_id
        FROM digital_component_content_sets component
        WHERE component.id=CASE WHEN TG_OP='DELETE' THEN OLD.content_set_id ELSE NEW.content_set_id END;
        SELECT record_id INTO held_record_id FROM digital_components WHERE id=component_id;
    ELSE
        component_id:=CASE WHEN TG_OP='DELETE' THEN OLD.digital_component_id ELSE NEW.digital_component_id END;
        IF component_id IS NOT NULL THEN SELECT record_id INTO held_record_id FROM digital_components WHERE id=component_id; END IF;
    END IF;
    IF held_record_id IS NOT NULL AND resource_has_effective_hold('record',held_record_id) THEN
        failure_code:=CASE TG_OP WHEN 'INSERT' THEN 'effective_hold_prevents_component_addition'
          WHEN 'DELETE' THEN 'effective_hold_prevents_component_deletion'
          ELSE 'effective_hold_prevents_component_replacement' END;
        IF TG_TABLE_NAME='digital_components' AND TG_OP='UPDATE'
           AND NEW.component_order IS DISTINCT FROM OLD.component_order THEN
            failure_code:='effective_hold_prevents_component_reordering';
        END IF;
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE=failure_code;
    END IF;
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER digital_components_protect_effective_holds
BEFORE INSERT OR UPDATE OR DELETE ON digital_components FOR EACH ROW EXECUTE FUNCTION protect_held_component_mutation();
CREATE TRIGGER digital_component_content_sets_protect_effective_holds
BEFORE INSERT OR UPDATE OR DELETE ON digital_component_content_sets FOR EACH ROW EXECUTE FUNCTION protect_held_component_mutation();
CREATE TRIGGER digital_component_blobs_protect_effective_holds
BEFORE INSERT OR UPDATE OR DELETE ON digital_component_blobs FOR EACH ROW EXECUTE FUNCTION protect_held_component_mutation();
CREATE TRIGGER content_upload_sessions_protect_effective_holds
BEFORE INSERT OR UPDATE OR DELETE ON content_upload_sessions FOR EACH ROW EXECUTE FUNCTION protect_held_component_mutation();

CREATE FUNCTION prevent_nonempty_hold_deletion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM hold_aggregation_assignments WHERE hold_id=OLD.id)
       OR EXISTS (SELECT 1 FROM hold_record_assignments WHERE hold_id=OLD.id) THEN
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_not_empty';
    END IF;
    RETURN OLD;
END;
$$;
CREATE TRIGGER holds_prevent_nonempty_deletion
BEFORE DELETE ON holds FOR EACH ROW EXECUTE FUNCTION prevent_nonempty_hold_deletion();

CREATE FUNCTION touch_hold() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.version:=OLD.version+1; NEW.date_updated:=CURRENT_TIMESTAMP; RETURN NEW; END;
$$;
CREATE TRIGGER holds_bump_version BEFORE UPDATE ON holds
FOR EACH ROW EXECUTE FUNCTION touch_hold();
CREATE TRIGGER hold_contributors_bump_version BEFORE UPDATE ON hold_contributors
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();
CREATE TRIGGER hold_aggregation_assignments_bump_version BEFORE UPDATE ON hold_aggregation_assignments
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();
CREATE TRIGGER hold_record_assignments_bump_version BEFORE UPDATE ON hold_record_assignments
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();

CREATE TRIGGER holds_record_history AFTER INSERT OR UPDATE OR DELETE ON holds
FOR EACH ROW EXECUTE FUNCTION record_entity_history('hold');
CREATE TRIGGER hold_contributors_record_history AFTER INSERT OR UPDATE OR DELETE ON hold_contributors
FOR EACH ROW EXECUTE FUNCTION record_entity_history('hold_contributor');
CREATE TRIGGER hold_aggregation_assignments_record_history AFTER INSERT OR UPDATE OR DELETE ON hold_aggregation_assignments
FOR EACH ROW EXECUTE FUNCTION record_entity_history('hold_aggregation_assignment');
CREATE TRIGGER hold_record_assignments_record_history AFTER INSERT OR UPDATE OR DELETE ON hold_record_assignments
FOR EACH ROW EXECUTE FUNCTION record_entity_history('hold_record_assignment');

CREATE FUNCTION populate_hold_event_reference_snapshots() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE state jsonb:=COALESCE(NEW.after_state,NEW.before_state,'{}'::jsonb);
DECLARE snapshots jsonb:='{}'::jsonb;
DECLARE reference_id bigint;
DECLARE snapshot jsonb;
DECLARE existing_snapshots jsonb;
BEGIN
    IF NEW.entity_type='hold' THEN
        snapshots:=jsonb_build_object('hold',jsonb_strip_nulls(jsonb_build_object(
            'id',NEW.entity_id,'code',state->>'code','name',state->>'name')));
    ELSIF NEW.entity_type IN ('hold_contributor','hold_aggregation_assignment','hold_record_assignment') THEN
        reference_id:=NULLIF(state->>'hold_id','')::bigint;
        SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot
        FROM holds WHERE id=reference_id;
        IF snapshot IS NOT NULL THEN snapshots:=snapshots||jsonb_build_object('hold',snapshot); END IF;
        IF NEW.entity_type='hold_contributor' THEN
            reference_id:=NULLIF(state->>'user_id','')::bigint;
            SELECT jsonb_strip_nulls(jsonb_build_object('id',id,'name',name,'email',email)) INTO snapshot
            FROM users WHERE id=reference_id;
            IF snapshot IS NOT NULL THEN snapshots:=snapshots||jsonb_build_object('user',snapshot); END IF;
        ELSIF NEW.entity_type='hold_aggregation_assignment' THEN
            reference_id:=NULLIF(state->>'aggregation_id','')::bigint;
            SELECT jsonb_build_object('id',id,'number',aggregation_number,'title',title) INTO snapshot
            FROM aggregations WHERE id=reference_id;
            IF snapshot IS NOT NULL THEN snapshots:=snapshots||jsonb_build_object('aggregation',snapshot); END IF;
        ELSE
            reference_id:=NULLIF(state->>'record_id','')::bigint;
            SELECT jsonb_build_object('id',id,'number',record_number,'title',title) INTO snapshot
            FROM records WHERE id=reference_id;
            IF snapshot IS NOT NULL THEN snapshots:=snapshots||jsonb_build_object('record',snapshot); END IF;
        END IF;
    ELSE
        IF NEW.metadata ? 'hold_id' THEN
            reference_id:=NULLIF(NEW.metadata->>'hold_id','')::bigint;
            SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot
            FROM holds WHERE id=reference_id;
            IF snapshot IS NOT NULL THEN snapshots:=snapshots||jsonb_build_object('hold',snapshot); END IF;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    IF snapshots<>'{}'::jsonb THEN
        existing_snapshots:=COALESCE(NEW.metadata->'reference_snapshots','{}'::jsonb);
        NEW.metadata:=NEW.metadata||jsonb_build_object(
            'reference_snapshots',existing_snapshots||snapshots);
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER event_history_z_hold_reference_snapshots
BEFORE INSERT ON event_history FOR EACH ROW EXECUTE FUNCTION populate_hold_event_reference_snapshots();

CREATE FUNCTION append_hold_definition_domain_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE entity_id bigint:=CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;
DECLARE operation_name text:=CASE TG_OP WHEN 'INSERT' THEN 'HOLD_CREATED' WHEN 'UPDATE' THEN 'HOLD_UPDATED' ELSE 'HOLD_DELETED' END;
DECLARE old_state jsonb:=CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) ELSE NULL END;
DECLARE new_state jsonb:=CASE WHEN TG_OP IN ('INSERT','UPDATE') THEN to_jsonb(NEW) ELSE NULL END;
BEGIN
    IF TG_OP='INSERT' THEN
        new_state:=new_state||jsonb_build_object(
            'contributor_user_ids',COALESCE(NULLIF(current_setting('app.hold_contributor_ids',true),'')::jsonb,'[]'::jsonb));
    END IF;
    PERFORM append_domain_event('hold',entity_id,operation_name,
        jsonb_strip_nulls(jsonb_build_object('before',old_state,'after',new_state)));
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER holds_domain_events AFTER INSERT OR UPDATE OR DELETE ON holds
FOR EACH ROW EXECUTE FUNCTION append_hold_definition_domain_event();

CREATE FUNCTION append_hold_assignment_domain_events() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE state record;
DECLARE operation_name text:=CASE WHEN TG_OP='INSERT' THEN 'RESOURCE_ADDED_TO_HOLD' ELSE 'RESOURCE_REMOVED_FROM_HOLD' END;
DECLARE resource_type text:=CASE WHEN TG_TABLE_NAME='hold_aggregation_assignments' THEN 'aggregation' ELSE 'record' END;
DECLARE resource_id bigint;
DECLARE metadata jsonb;
BEGIN
    IF TG_OP='UPDATE' THEN RETURN NEW; END IF;
    IF TG_OP='DELETE' THEN state:=OLD; ELSE state:=NEW; END IF;
    IF resource_type='aggregation' THEN resource_id:=state.aggregation_id; ELSE resource_id:=state.record_id; END IF;
    metadata:=jsonb_build_object('hold_id',state.hold_id,'resource_type',resource_type,
                                 'resource_id',resource_id,'assignment_id',state.id);
    IF TG_OP='DELETE' THEN
        IF resource_type='aggregation' THEN
            metadata:=metadata||jsonb_build_object('remaining_effective_hold_ids',
                COALESCE((SELECT jsonb_agg(hold_id ORDER BY hold_id) FROM effective_holds_for_aggregation(resource_id)),'[]'::jsonb));
        ELSE
            metadata:=metadata||jsonb_build_object('remaining_effective_hold_ids',
                COALESCE((SELECT jsonb_agg(hold_id ORDER BY hold_id) FROM effective_holds_for_record(resource_id)),'[]'::jsonb));
        END IF;
    END IF;
    PERFORM append_domain_event('hold',state.hold_id,operation_name,metadata);
    PERFORM append_domain_event(resource_type,resource_id,operation_name,metadata);
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER hold_aggregation_assignments_domain_events
AFTER INSERT OR DELETE ON hold_aggregation_assignments
FOR EACH ROW EXECUTE FUNCTION append_hold_assignment_domain_events();
CREATE TRIGGER hold_record_assignments_domain_events
AFTER INSERT OR DELETE ON hold_record_assignments
FOR EACH ROW EXECUTE FUNCTION append_hold_assignment_domain_events();

CREATE OR REPLACE VIEW authorized_aggregations_for_search AS
SELECT resource.id,
       CASE WHEN resource.parent_aggregation_id IS NULL OR current_user_can_view_aggregation(resource.parent_aggregation_id)
            THEN resource.parent_aggregation_id END AS parent_aggregation_id,
       resource.classification_id,resource.aggregation_number,resource.title,resource.description,
       resource.date_created,resource.date_opened,resource.date_closed,resource.security_level_id,
       resource.inherit_acl_from_parent,resource.default_child_aggregation_acl_mode,
       resource.resource_acl_version,resource.child_aggregation_acl_version,resource.child_record_acl_version,
       resource.version,resource.owning_org_unit_id,resource.medium,resource.is_vital,
       resource.date_of_next_review,resource.assigned_location,resource.current_location,
       aggregation_effective_assigned_location(resource.id) AS effective_assigned_location,
       aggregation_effective_current_location(resource.id) AS effective_current_location,
       CASE WHEN current_user_can_view_aggregation(aggregation_effective_assigned_location_source_id(resource.id))
            THEN aggregation_effective_assigned_location_source_id(resource.id) END AS effective_assigned_location_source_aggregation_id,
       CASE WHEN current_user_can_view_aggregation(aggregation_effective_current_location_source_id(resource.id))
            THEN aggregation_effective_current_location_source_id(resource.id) END AS effective_current_location_source_aggregation_id,
       hold_state.effective_hold_count > 0 AS on_effective_hold,
       hold_state.resource_state_changes_blocked,
       hold_state.effective_hold_ids
FROM aggregations resource
CROSS JOIN LATERAL (
    SELECT count(*)::integer effective_hold_count,
           COALESCE(bool_or(effective.preserve_resource_state),false) resource_state_changes_blocked,
           COALESCE(array_agg(effective.hold_id ORDER BY effective.hold_id),'{}'::bigint[]) effective_hold_ids
    FROM effective_holds_for_aggregation(resource.id) effective
) hold_state;

CREATE OR REPLACE VIEW authorized_records_for_search AS
SELECT resource.id,
       CASE WHEN current_user_can_view_aggregation(resource.aggregation_id) THEN resource.aggregation_id END AS aggregation_id,
       resource.record_number,resource.title,resource.description,resource.date_created,resource.date_originated,
       resource.security_level_id,resource.inherit_acl_from_parent,resource.resource_acl_version,resource.version,
       resource.owning_org_unit_id,resource.medium,resource.is_vital,resource.date_of_next_review,
       aggregation_effective_assigned_location(resource.aggregation_id) AS effective_assigned_location,
       aggregation_effective_current_location(resource.aggregation_id) AS effective_current_location,
       CASE WHEN current_user_can_view_aggregation(aggregation_effective_assigned_location_source_id(resource.aggregation_id))
            THEN aggregation_effective_assigned_location_source_id(resource.aggregation_id) END AS effective_assigned_location_source_aggregation_id,
       CASE WHEN current_user_can_view_aggregation(aggregation_effective_current_location_source_id(resource.aggregation_id))
            THEN aggregation_effective_current_location_source_id(resource.aggregation_id) END AS effective_current_location_source_aggregation_id,
       hold_state.effective_hold_count > 0 AS on_effective_hold,
       hold_state.resource_state_changes_blocked,
       hold_state.effective_hold_ids
FROM records resource
CROSS JOIN LATERAL (
    SELECT count(*)::integer effective_hold_count,
           COALESCE(bool_or(effective.preserve_resource_state),false) resource_state_changes_blocked,
           COALESCE(array_agg(effective.hold_id ORDER BY effective.hold_id),'{}'::bigint[]) effective_hold_ids
    FROM effective_holds_for_record(resource.id) effective
) hold_state;

COMMIT;

-- Resource-medium hierarchy enforcement. Equivalent upgrade: migration 052.
BEGIN;
ALTER TABLE record_drafts ADD COLUMN IF NOT EXISTS medium text;
ALTER TABLE record_drafts ADD COLUMN IF NOT EXISTS is_vital boolean NOT NULL DEFAULT false;
ALTER TABLE record_drafts ADD COLUMN IF NOT EXISTS date_of_next_review timestamptz;
ALTER TABLE record_drafts
    DROP CONSTRAINT IF EXISTS record_drafts_medium_valid,
    ADD CONSTRAINT record_drafts_medium_valid
        CHECK (medium IS NULL OR medium IN ('digital','physical','mixed'));

CREATE OR REPLACE FUNCTION enforce_aggregation_medium_hierarchy()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_medium text;
BEGIN
    IF NEW.parent_aggregation_id IS NOT NULL THEN
        SELECT medium INTO parent_medium FROM aggregations
         WHERE id=NEW.parent_aggregation_id FOR UPDATE;
        IF parent_medium IS NULL OR NEW.medium IS DISTINCT FROM parent_medium THEN
            RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='aggregation_medium_mismatch',
                MESSAGE='aggregation_medium_mismatch: a child aggregation must use its parent medium';
        END IF;
    END IF;
    IF TG_OP='UPDATE' AND NEW.medium IS DISTINCT FROM OLD.medium AND (
        EXISTS (SELECT 1 FROM aggregations WHERE parent_aggregation_id=OLD.id)
        OR EXISTS (SELECT 1 FROM records WHERE aggregation_id=OLD.id)) THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='medium_change_requires_empty_aggregation',
            MESSAGE='medium_change_requires_empty_aggregation: an aggregation must be empty before changing medium';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS aggregations_enforce_medium_hierarchy ON aggregations;
CREATE TRIGGER aggregations_enforce_medium_hierarchy
BEFORE INSERT OR UPDATE OF parent_aggregation_id,medium ON aggregations
FOR EACH ROW EXECUTE FUNCTION enforce_aggregation_medium_hierarchy();

CREATE OR REPLACE FUNCTION enforce_record_medium_hierarchy()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_medium text;
BEGIN
    IF NEW.aggregation_id IS NULL THEN RETURN NEW; END IF;
    SELECT medium INTO parent_medium FROM aggregations WHERE id=NEW.aggregation_id FOR UPDATE;
    IF parent_medium IS NULL OR (parent_medium<>'mixed' AND NEW.medium IS DISTINCT FROM parent_medium) THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='record_medium_not_allowed_by_parent',
            MESSAGE='record_medium_not_allowed_by_parent: record medium is incompatible with its parent aggregation';
    END IF;
    IF TG_OP='UPDATE' AND NEW.medium='physical' AND NEW.medium IS DISTINCT FROM OLD.medium
       AND EXISTS (SELECT 1 FROM digital_components WHERE record_id=OLD.id) THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='physical_record_has_digital_components',
            MESSAGE='physical_record_has_digital_components: a record with digital components cannot become physical';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS records_enforce_medium_hierarchy ON records;
CREATE TRIGGER records_enforce_medium_hierarchy
BEFORE INSERT OR UPDATE OF aggregation_id,medium ON records
FOR EACH ROW EXECUTE FUNCTION enforce_record_medium_hierarchy();

CREATE OR REPLACE FUNCTION enforce_record_draft_medium_hierarchy()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_medium text;
BEGIN
    IF NEW.aggregation_id IS NULL THEN RETURN NEW; END IF;
    SELECT medium INTO parent_medium FROM aggregations WHERE id=NEW.aggregation_id FOR UPDATE;
    IF NEW.medium IS NULL THEN
        NEW.medium:=parent_medium;
    ELSIF parent_medium IS NULL OR (parent_medium<>'mixed' AND NEW.medium IS DISTINCT FROM parent_medium) THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='record_medium_not_allowed_by_parent',
            MESSAGE='record_medium_not_allowed_by_parent: draft medium is incompatible with its parent aggregation';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS record_drafts_enforce_medium_hierarchy ON record_drafts;
CREATE TRIGGER record_drafts_enforce_medium_hierarchy
BEFORE INSERT OR UPDATE OF aggregation_id,medium ON record_drafts
FOR EACH ROW EXECUTE FUNCTION enforce_record_draft_medium_hierarchy();
COMMIT;

-- Physical records cannot carry digital components. Equivalent upgrade: migration 053.
BEGIN;
CREATE OR REPLACE FUNCTION enforce_digital_component_record_medium()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE record_medium text;
BEGIN
    SELECT medium INTO record_medium FROM records WHERE id=NEW.record_id FOR UPDATE;
    IF record_medium='physical' THEN
        RAISE EXCEPTION USING ERRCODE='23514',
            CONSTRAINT='physical_record_disallows_digital_components',
            MESSAGE='physical_record_disallows_digital_components: physical records cannot have digital components';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS digital_components_enforce_record_medium ON digital_components;
CREATE TRIGGER digital_components_enforce_record_medium
BEFORE INSERT OR UPDATE OF record_id ON digital_components
FOR EACH ROW EXECUTE FUNCTION enforce_digital_component_record_medium();

CREATE OR REPLACE FUNCTION enforce_record_draft_medium_hierarchy()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_medium text;
BEGIN
    IF NEW.aggregation_id IS NULL THEN RETURN NEW; END IF;
    SELECT medium INTO parent_medium FROM aggregations WHERE id=NEW.aggregation_id FOR UPDATE;
    IF NEW.medium IS NULL THEN
        NEW.medium:=parent_medium;
    ELSIF parent_medium IS NULL OR (parent_medium<>'mixed' AND NEW.medium IS DISTINCT FROM parent_medium) THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='record_medium_not_allowed_by_parent',
            MESSAGE='record_medium_not_allowed_by_parent: draft medium is incompatible with its parent aggregation';
    END IF;
    IF NEW.medium='physical' AND (TG_OP='INSERT' OR OLD.medium IS DISTINCT FROM NEW.medium)
       AND EXISTS (SELECT 1 FROM record_draft_components WHERE draft_id=NEW.id) THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='physical_record_has_staged_components',
            MESSAGE='physical_record_has_staged_components: remove staged components before changing the draft medium';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION enforce_draft_component_record_medium()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE draft_medium text;
BEGIN
    SELECT medium INTO draft_medium FROM record_drafts WHERE id=NEW.draft_id FOR UPDATE;
    IF draft_medium IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='record_medium_required_before_components',
            MESSAGE='record_medium_required_before_components: select a record medium before adding digital components';
    ELSIF draft_medium='physical' THEN
        RAISE EXCEPTION USING ERRCODE='23514', CONSTRAINT='physical_record_disallows_digital_components',
            MESSAGE='physical_record_disallows_digital_components: physical record drafts cannot have digital components';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS record_draft_components_enforce_record_medium ON record_draft_components;
CREATE TRIGGER record_draft_components_enforce_record_medium
BEFORE INSERT OR UPDATE OF draft_id ON record_draft_components
FOR EACH ROW EXECUTE FUNCTION enforce_draft_component_record_medium();
COMMIT;

-- Governed vital status and immutable deletion protection. Equivalent upgrade: migration 054.
BEGIN;
INSERT INTO privileges(code,name,description,category,is_reserved) VALUES
 ('aggregation.vital_status.change','Change Aggregation Vital Status','Governed change of aggregation vital status.','aggregation',false),
 ('record.vital_status.change','Change Record Vital Status','Governed change of record vital status.','record',false) ON CONFLICT DO NOTHING;
INSERT INTO permissions(code,name,description,resource_type) VALUES
 ('aggregation.vital_status.change','Change Aggregation Vital Status','Governed change of aggregation vital status.','aggregation'),
 ('record.vital_status.change','Change Record Vital Status','Governed change of record vital status.','record') ON CONFLICT DO NOTHING;
INSERT INTO privilege_dependencies(privilege_id,required_privilege_id)
SELECT dependent.id,required.id FROM privileges dependent JOIN privileges required ON required.code=CASE WHEN dependent.code LIKE 'aggregation.%' THEN 'aggregation.view' ELSE 'record.view' END WHERE dependent.code IN ('aggregation.vital_status.change','record.vital_status.change') ON CONFLICT DO NOTHING;
INSERT INTO permission_dependencies(permission_id,required_permission_id)
SELECT dependent.id,required.id FROM permissions dependent JOIN permissions required ON required.code=CASE WHEN dependent.resource_type='aggregation' THEN 'aggregation.view' ELSE 'record.view' END WHERE dependent.code IN ('aggregation.vital_status.change','record.vital_status.change') ON CONFLICT DO NOTHING;
INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id FROM profiles profile CROSS JOIN privileges privilege WHERE profile.code IN ('ALL_PRIVS','INFO_GOV_MGR','INFO_GOV_OFFICER') AND privilege.code IN ('aggregation.vital_status.change','record.vital_status.change') ON CONFLICT DO NOTHING;
CREATE OR REPLACE FUNCTION aggregation_has_vital_descendants(p_id bigint) RETURNS boolean LANGUAGE sql STABLE AS $$
 WITH RECURSIVE subtree AS (
   SELECT p_id AS id
   UNION ALL
   SELECT child.id FROM aggregations child JOIN subtree parent ON child.parent_aggregation_id=parent.id
 )
 SELECT EXISTS(SELECT 1 FROM aggregations WHERE id IN (SELECT id FROM subtree) AND id<>p_id AND is_vital)
     OR EXISTS(SELECT 1 FROM records WHERE aggregation_id IN (SELECT id FROM subtree) AND is_vital)$$;
CREATE OR REPLACE FUNCTION protect_vital_resource_deletion() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE vital_count integer;
BEGIN
 IF TG_TABLE_NAME='records' THEN IF OLD.is_vital THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='vital_resource_deletion_blocked'; END IF; RETURN OLD; END IF;
 PERFORM 1 FROM aggregations WHERE id=OLD.id FOR UPDATE;
 IF OLD.is_vital THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='vital_resource_deletion_blocked'; END IF;
 WITH RECURSIVE subtree AS (
   SELECT OLD.id AS id
   UNION ALL
   SELECT child.id FROM aggregations child JOIN subtree parent ON child.parent_aggregation_id=parent.id
 )
 SELECT count(*) INTO vital_count FROM (
   SELECT id FROM aggregations WHERE id IN (SELECT id FROM subtree) AND id<>OLD.id AND is_vital
   UNION ALL
   SELECT id FROM records WHERE aggregation_id IN (SELECT id FROM subtree) AND is_vital
 ) vital;
 IF vital_count>0 THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='vital_descendant_deletion_blocked'; END IF; RETURN OLD;
END; $$;
CREATE TRIGGER aggregations_protect_vital_deletion BEFORE DELETE ON aggregations FOR EACH ROW EXECUTE FUNCTION protect_vital_resource_deletion();
CREATE TRIGGER records_protect_vital_deletion BEFORE DELETE ON records FOR EACH ROW EXECUTE FUNCTION protect_vital_resource_deletion();
CREATE OR REPLACE FUNCTION allow_governed_vital_status_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF NEW.is_vital IS DISTINCT FROM OLD.is_vital AND (current_setting('app.vital_status_change_authorized',true)<>'authorized' OR NULLIF(btrim(current_setting('app.change_reason',true)), '') IS NULL) THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='vital_status_change_requires_governed_authorization_and_reason'; END IF; RETURN NEW; END; $$;
CREATE TRIGGER aggregations_govern_vital_status BEFORE UPDATE OF is_vital ON aggregations FOR EACH ROW EXECUTE FUNCTION allow_governed_vital_status_change();
CREATE TRIGGER records_govern_vital_status BEFORE UPDATE OF is_vital ON records FOR EACH ROW EXECUTE FUNCTION allow_governed_vital_status_change();
CREATE OR REPLACE FUNCTION protect_closed_aggregation_hierarchy() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE closure_source_id bigint;
BEGIN
 IF TG_OP='INSERT' THEN IF NEW.parent_aggregation_id IS NOT NULL THEN PERFORM assert_aggregation_effectively_open(NEW.parent_aggregation_id); END IF; RETURN NEW; END IF;
 IF TG_OP='DELETE' THEN PERFORM assert_aggregation_effectively_open(OLD.id); RETURN OLD; END IF;
 WITH RECURSIVE ancestors AS (SELECT id,parent_aggregation_id,date_closed,0 depth FROM aggregations WHERE id=OLD.id UNION ALL SELECT parent.id,parent.parent_aggregation_id,parent.date_closed,child.depth+1 FROM aggregations parent JOIN ancestors child ON parent.id=child.parent_aggregation_id) SELECT id INTO closure_source_id FROM ancestors WHERE date_closed IS NOT NULL ORDER BY depth LIMIT 1;
 IF closure_source_id IS NOT NULL THEN
  IF current_setting('app.vital_status_change_authorized',true)='authorized' AND NEW.is_vital IS DISTINCT FROM OLD.is_vital AND (to_jsonb(NEW)-'is_vital'-'version')=(to_jsonb(OLD)-'is_vital'-'version') THEN RETURN NEW; END IF;
  IF closure_source_id=OLD.id AND OLD.date_closed IS NOT NULL AND NEW.date_closed IS NULL AND (to_jsonb(NEW)-'date_closed'-'version')=(to_jsonb(OLD)-'date_closed'-'version') THEN RETURN NEW; END IF;
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='closed aggregation metadata is immutable';
 END IF; RETURN NEW;
END; $$;
CREATE OR REPLACE FUNCTION protect_record_in_closed_aggregation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN PERFORM assert_aggregation_effectively_open(NEW.aggregation_id); RETURN NEW; END IF;
 IF TG_OP='DELETE' THEN PERFORM assert_aggregation_effectively_open(OLD.aggregation_id); RETURN OLD; END IF;
 IF current_setting('app.vital_status_change_authorized',true)='authorized' AND NEW.is_vital IS DISTINCT FROM OLD.is_vital AND (to_jsonb(NEW)-'is_vital'-'version')=(to_jsonb(OLD)-'is_vital'-'version') THEN RETURN NEW; END IF;
 IF current_setting('app.review_date_change_authorized',true)='authorized' AND NEW.date_of_next_review IS DISTINCT FROM OLD.date_of_next_review AND (to_jsonb(NEW)-'date_of_next_review'-'version')=(to_jsonb(OLD)-'date_of_next_review'-'version') THEN RETURN NEW; END IF;
 PERFORM assert_aggregation_effectively_open(OLD.aggregation_id); RETURN NEW;
END; $$;
INSERT INTO privileges(code,name,description,category) VALUES ('aggregation.location.change','Change Aggregation Location','Governed change of aggregation assigned or current location.','aggregation') ON CONFLICT DO NOTHING;
INSERT INTO permissions(code,name,description,resource_type) VALUES ('aggregation.location.change','Change Aggregation Location','Governed change of aggregation assigned or current location.','aggregation') ON CONFLICT DO NOTHING;
INSERT INTO privilege_dependencies(privilege_id,required_privilege_id) SELECT dependent.id,required.id FROM privileges dependent JOIN privileges required ON required.code='aggregation.view' WHERE dependent.code='aggregation.location.change' ON CONFLICT DO NOTHING;
INSERT INTO permission_dependencies(permission_id,required_permission_id) SELECT dependent.id,required.id FROM permissions dependent JOIN permissions required ON required.code='aggregation.view' WHERE dependent.code='aggregation.location.change' ON CONFLICT DO NOTHING;
INSERT INTO profile_privileges(profile_id,privilege_id) SELECT profile.id,privilege.id FROM profiles profile CROSS JOIN privileges privilege WHERE profile.code IN ('ALL_PRIVS','INFO_GOV_MGR','INFO_GOV_OFFICER') AND privilege.code='aggregation.location.change' ON CONFLICT DO NOTHING;
INSERT INTO privileges(code,name,description,category,is_reserved) VALUES ('aggregation.review_date.change','Change Aggregation Review Date','Governed scheduling or clearing of an aggregation review date.','aggregation',false),('record.review_date.change','Change Record Review Date','Governed scheduling or clearing of a record review date.','record',false) ON CONFLICT DO NOTHING;
INSERT INTO permissions(code,name,description,resource_type) VALUES ('aggregation.review_date.change','Change Aggregation Review Date','Governed scheduling or clearing of an aggregation review date.','aggregation'),('record.review_date.change','Change Record Review Date','Governed scheduling or clearing of a record review date.','record') ON CONFLICT DO NOTHING;
INSERT INTO privilege_dependencies(privilege_id,required_privilege_id) SELECT d.id,r.id FROM privileges d JOIN privileges r ON r.code=CASE WHEN d.code LIKE 'aggregation.%' THEN 'aggregation.view' ELSE 'record.view' END WHERE d.code IN ('aggregation.review_date.change','record.review_date.change') ON CONFLICT DO NOTHING;
INSERT INTO permission_dependencies(permission_id,required_permission_id) SELECT d.id,r.id FROM permissions d JOIN permissions r ON r.code=CASE WHEN d.resource_type='aggregation' THEN 'aggregation.view' ELSE 'record.view' END WHERE d.code IN ('aggregation.review_date.change','record.review_date.change') ON CONFLICT DO NOTHING;
INSERT INTO profile_privileges(profile_id,privilege_id) SELECT p.id,v.id FROM profiles p CROSS JOIN privileges v WHERE p.code IN ('ALL_PRIVS','INFO_GOV_MGR','INFO_GOV_OFFICER') AND v.code IN ('aggregation.review_date.change','record.review_date.change') ON CONFLICT DO NOTHING;
CREATE OR REPLACE FUNCTION enforce_future_review_date() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.date_of_next_review IS NOT NULL AND (TG_OP='INSERT' OR NEW.date_of_next_review IS DISTINCT FROM OLD.date_of_next_review) AND NEW.date_of_next_review <= CURRENT_TIMESTAMP THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='date_of_next_review_must_be_future'; END IF; RETURN NEW; END; $$;
CREATE TRIGGER aggregations_enforce_future_review_date BEFORE INSERT OR UPDATE OF date_of_next_review ON aggregations FOR EACH ROW EXECUTE FUNCTION enforce_future_review_date();
CREATE TRIGGER records_enforce_future_review_date BEFORE INSERT OR UPDATE OF date_of_next_review ON records FOR EACH ROW EXECUTE FUNCTION enforce_future_review_date();
CREATE TRIGGER record_drafts_enforce_future_review_date BEFORE INSERT OR UPDATE OF date_of_next_review ON record_drafts FOR EACH ROW EXECUTE FUNCTION enforce_future_review_date();
CREATE OR REPLACE FUNCTION allow_governed_review_date_change() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.date_of_next_review IS DISTINCT FROM OLD.date_of_next_review AND (current_setting('app.review_date_change_authorized',true)<>'authorized' OR NULLIF(btrim(current_setting('app.change_reason',true)), '') IS NULL) THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='review_date_change_requires_governed_authorization_and_reason'; END IF; RETURN NEW; END; $$;
CREATE TRIGGER aggregations_govern_review_date BEFORE UPDATE OF date_of_next_review ON aggregations FOR EACH ROW EXECUTE FUNCTION allow_governed_review_date_change();
CREATE TRIGGER records_govern_review_date BEFORE UPDATE OF date_of_next_review ON records FOR EACH ROW EXECUTE FUNCTION allow_governed_review_date_change();
CREATE OR REPLACE FUNCTION allow_governed_aggregation_location_change() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF (NEW.assigned_location IS DISTINCT FROM OLD.assigned_location OR NEW.current_location IS DISTINCT FROM OLD.current_location) AND (current_setting('app.location_change_authorized',true)<>'authorized' OR NULLIF(btrim(current_setting('app.change_reason',true)), '') IS NULL) THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='location_change_requires_governed_authorization_and_reason'; END IF; RETURN NEW; END; $$;
CREATE TRIGGER aggregations_govern_location_change BEFORE UPDATE OF assigned_location,current_location ON aggregations FOR EACH ROW EXECUTE FUNCTION allow_governed_aggregation_location_change();
CREATE OR REPLACE FUNCTION protect_closed_aggregation_hierarchy()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE closure_source_id bigint;
BEGIN
 IF TG_OP='INSERT' THEN
   IF NEW.parent_aggregation_id IS NOT NULL THEN
     PERFORM assert_aggregation_effectively_open(NEW.parent_aggregation_id);
   END IF;
   RETURN NEW;
 END IF;
 IF TG_OP='DELETE' THEN
   PERFORM assert_aggregation_effectively_open(OLD.id);
   RETURN OLD;
 END IF;
 WITH RECURSIVE ancestors AS (
   SELECT id,parent_aggregation_id,date_closed,0 depth FROM aggregations WHERE id=OLD.id
   UNION ALL
   SELECT parent.id,parent.parent_aggregation_id,parent.date_closed,child.depth+1
   FROM aggregations parent JOIN ancestors child ON parent.id=child.parent_aggregation_id
 )
 SELECT id INTO closure_source_id FROM ancestors
 WHERE date_closed IS NOT NULL ORDER BY depth LIMIT 1;
 IF closure_source_id IS NOT NULL THEN
   IF current_setting('app.vital_status_change_authorized',true)='authorized'
      AND NEW.is_vital IS DISTINCT FROM OLD.is_vital
      AND (to_jsonb(NEW)-'is_vital'-'version')=(to_jsonb(OLD)-'is_vital'-'version') THEN
     RETURN NEW;
   END IF;
   IF current_setting('app.location_change_authorized',true)='authorized'
      AND (NEW.assigned_location IS DISTINCT FROM OLD.assigned_location
           OR NEW.current_location IS DISTINCT FROM OLD.current_location)
      AND (to_jsonb(NEW)-'assigned_location'-'current_location'-'version')
          =(to_jsonb(OLD)-'assigned_location'-'current_location'-'version') THEN
     RETURN NEW;
   END IF;
   IF current_setting('app.review_date_change_authorized',true)='authorized'
      AND NEW.date_of_next_review IS DISTINCT FROM OLD.date_of_next_review
      AND (to_jsonb(NEW)-'date_of_next_review'-'version')=(to_jsonb(OLD)-'date_of_next_review'-'version') THEN
     RETURN NEW;
   END IF;
   IF closure_source_id=OLD.id AND OLD.date_closed IS NOT NULL
      AND NEW.date_closed IS NULL
      AND (to_jsonb(NEW)-'date_closed'-'version')=(to_jsonb(OLD)-'date_closed'-'version') THEN
     RETURN NEW;
   END IF;
   RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='closed aggregation metadata is immutable';
 END IF;
 RETURN NEW;
END;
$$;
CREATE INDEX aggregations_review_due_idx ON aggregations (date_of_next_review,id) WHERE date_of_next_review IS NOT NULL;
CREATE INDEX records_review_due_idx ON records (date_of_next_review,id) WHERE date_of_next_review IS NOT NULL;
CREATE INDEX aggregations_owner_review_due_idx ON aggregations (owning_org_unit_id,date_of_next_review,id) WHERE date_of_next_review IS NOT NULL;
CREATE INDEX records_owner_review_due_idx ON records (owning_org_unit_id,date_of_next_review,id) WHERE date_of_next_review IS NOT NULL;
COMMIT;
