-- Attribute legacy events, created before authentication existed, to the
-- administrator identified by the agreed stable email address. The metadata
-- marker makes the retrospective nature of this attribution explicit.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $$
DECLARE
    matching_users integer;
    anonymous_events bigint;
BEGIN
    SELECT count(*) INTO matching_users
    FROM users
    WHERE lower(email) = lower('y.abdullah@sa.gov.ae');

    SELECT count(*) INTO anonymous_events
    FROM event_history
    WHERE actor_type = 'anonymous';

    IF anonymous_events > 0 AND matching_users <> 1 THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = format(
                'cannot backfill %s anonymous events: expected exactly one user with email y.abdullah@sa.gov.ae, found %s',
                anonymous_events,
                matching_users
            );
    END IF;
END;
$$;

DROP TRIGGER IF EXISTS event_history_reject_update_delete ON event_history;

UPDATE event_history AS event
SET actor_user_id = target_user.id,
    actor_type = 'user',
    metadata = event.metadata || jsonb_build_object(
        'actor_attribution_backfill',
        jsonb_build_object(
            'migration', '012_backfill_anonymous_event_actor',
            'basis', 'legacy activity predates authentication',
            'user_email', 'y.abdullah@sa.gov.ae'
        )
    )
FROM users AS target_user
WHERE lower(target_user.email) = lower('y.abdullah@sa.gov.ae')
  AND event.actor_type = 'anonymous';

CREATE TRIGGER event_history_reject_update_delete
BEFORE UPDATE OR DELETE ON event_history
FOR EACH ROW EXECUTE FUNCTION reject_event_history_mutation();

INSERT INTO schema_migrations(version)
VALUES ('012_backfill_anonymous_event_actor')
ON CONFLICT(version) DO NOTHING;
