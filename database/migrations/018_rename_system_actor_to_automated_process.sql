-- Distinguish an automated event producer with no stored account identity from
-- a service account stored in users. The old actor value "system" becomes the
-- clearer "automated_process" throughout existing and future audit history.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DROP TRIGGER IF EXISTS event_history_reject_update_delete ON event_history;

UPDATE event_history
SET actor_type = 'automated_process',
    metadata = metadata || jsonb_build_object(
        'actor_type_terminology_migration',
        jsonb_build_object(
            'migration', '018_rename_system_actor_to_automated_process',
            'previous_value', 'system'
        )
    )
WHERE actor_type = 'system';

ALTER TABLE event_history
    ALTER COLUMN actor_type SET DEFAULT 'automated_process';
ALTER TABLE event_history
    DROP CONSTRAINT IF EXISTS event_history_actor_type_valid;
ALTER TABLE event_history
    ADD CONSTRAINT event_history_actor_type_valid
    CHECK (actor_type IN ('user', 'anonymous', 'automated_process'));

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
        entity_type, entity_id, operation, actor_user_id, actor_type, source,
        request_id, correlation_id, before_state, after_state, changed_fields,
        reason, metadata
    )
    VALUES (
        TG_ARGV[0],
        entity_key,
        CASE TG_OP WHEN 'INSERT' THEN 'CREATE' ELSE TG_OP END,
        context_user_id::bigint,
        COALESCE(
            NULLIF(current_setting('app.actor_type', true), ''),
            'automated_process'
        ),
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
        entity_type, entity_id, operation, actor_user_id, actor_type, source,
        request_id, correlation_id, reason, metadata
    )
    VALUES (
        event_entity_type,
        event_entity_id,
        event_operation,
        context_user_id::bigint,
        COALESCE(
            NULLIF(current_setting('app.actor_type', true), ''),
            'automated_process'
        ),
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

CREATE TRIGGER event_history_reject_update_delete
BEFORE UPDATE OR DELETE ON event_history
FOR EACH ROW EXECUTE FUNCTION reject_event_history_mutation();

INSERT INTO schema_migrations(version)
VALUES ('018_rename_system_actor_to_automated_process')
ON CONFLICT(version) DO NOTHING;
