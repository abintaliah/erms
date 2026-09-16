-- Preserve the human-readable actor identity on every audit event so history
-- remains understandable even if the live user row is later hard deleted.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE event_history
    ADD COLUMN actor_name text,
    ADD COLUMN actor_email text;

CREATE OR REPLACE FUNCTION populate_event_actor_snapshot()
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

DROP TRIGGER IF EXISTS event_history_populate_actor_snapshot ON event_history;
CREATE TRIGGER event_history_populate_actor_snapshot
BEFORE INSERT ON event_history
FOR EACH ROW EXECUTE FUNCTION populate_event_actor_snapshot();

DROP TRIGGER IF EXISTS event_history_reject_update_delete ON event_history;

UPDATE event_history AS event
SET actor_name = actor.name,
    actor_email = actor.email
FROM users AS actor
WHERE actor.id = event.actor_user_id
  AND (event.actor_name IS NULL OR event.actor_email IS DISTINCT FROM actor.email);

CREATE TRIGGER event_history_reject_update_delete
BEFORE UPDATE OR DELETE ON event_history
FOR EACH ROW EXECUTE FUNCTION reject_event_history_mutation();

INSERT INTO schema_migrations(version)
VALUES ('013_snapshot_event_actor_identity')
ON CONFLICT(version) DO NOTHING;
