CREATE TABLE IF NOT EXISTS schema_migrations (
    id         bigserial PRIMARY KEY,
    version    text NOT NULL UNIQUE,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),

    CONSTRAINT schema_migrations_version_not_blank
        CHECK (btrim(version) <> '')
);

CREATE TABLE IF NOT EXISTS event_history (
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

CREATE INDEX IF NOT EXISTS event_history_entity_timeline_idx
    ON event_history (entity_type, entity_id, occurred_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS event_history_actor_timeline_idx
    ON event_history (actor_user_id, occurred_at DESC)
    WHERE actor_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS event_history_request_id_idx
    ON event_history (request_id)
    WHERE request_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS event_history_correlation_id_idx
    ON event_history (correlation_id)
    WHERE correlation_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS event_history_occurred_at_idx
    ON event_history (occurred_at DESC);

CREATE OR REPLACE FUNCTION record_entity_history()
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

DROP TRIGGER IF EXISTS aggregations_record_history ON aggregations;
CREATE TRIGGER aggregations_record_history
AFTER INSERT OR UPDATE OR DELETE ON aggregations
FOR EACH ROW EXECUTE FUNCTION record_entity_history('aggregation');

DROP TRIGGER IF EXISTS records_record_history ON records;
CREATE TRIGGER records_record_history
AFTER INSERT OR UPDATE OR DELETE ON records
FOR EACH ROW EXECUTE FUNCTION record_entity_history('record');

DROP TRIGGER IF EXISTS digital_components_record_history ON digital_components;
CREATE TRIGGER digital_components_record_history
AFTER INSERT OR UPDATE OR DELETE ON digital_components
FOR EACH ROW EXECUTE FUNCTION record_entity_history('digital_component');

CREATE OR REPLACE FUNCTION reject_event_history_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'event history is immutable';
END;
$$;

DROP TRIGGER IF EXISTS event_history_reject_update_delete ON event_history;
CREATE TRIGGER event_history_reject_update_delete
BEFORE UPDATE OR DELETE ON event_history
FOR EACH ROW EXECUTE FUNCTION reject_event_history_mutation();

DROP TRIGGER IF EXISTS event_history_reject_truncate ON event_history;
CREATE TRIGGER event_history_reject_truncate
BEFORE TRUNCATE ON event_history
FOR EACH STATEMENT EXECUTE FUNCTION reject_event_history_mutation();

INSERT INTO schema_migrations (version)
VALUES ('001_add_event_history')
ON CONFLICT (version) DO NOTHING;
