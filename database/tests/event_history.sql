\set ON_ERROR_STOP on

BEGIN;

INSERT INTO aggregations (aggregation_number, title)
VALUES ('AUDIT-AGG-001', 'Audited aggregation')
RETURNING id AS audited_aggregation_id \gset

UPDATE aggregations
SET title = 'Updated audited aggregation'
WHERE id = :audited_aggregation_id;

DO $$
DECLARE
    create_event event_history%ROWTYPE;
    update_event event_history%ROWTYPE;
BEGIN
    SELECT * INTO STRICT create_event
    FROM event_history
    WHERE entity_type = 'aggregation' AND operation = 'CREATE';

    IF create_event.before_state IS NOT NULL
       OR create_event.after_state ->> 'title' <> 'Audited aggregation'
       OR create_event.source <> 'database'
       OR create_event.actor_type <> 'automated_process' THEN
        RAISE EXCEPTION 'CREATE history event is incorrect';
    END IF;

    SELECT * INTO STRICT update_event
    FROM event_history
    WHERE entity_type = 'aggregation' AND operation = 'UPDATE';

    IF update_event.before_state ->> 'title' <> 'Audited aggregation'
       OR update_event.after_state ->> 'title' <> 'Updated audited aggregation'
       OR update_event.changed_fields <> ARRAY['title'] THEN
        RAISE EXCEPTION 'UPDATE history event is incorrect';
    END IF;
END;
$$;

SAVEPOINT before_rolled_back_change;
INSERT INTO aggregations (aggregation_number, title)
VALUES ('AUDIT-ROLLBACK', 'This change will roll back');
ROLLBACK TO SAVEPOINT before_rolled_back_change;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM event_history
        WHERE after_state ->> 'aggregation_number' = 'AUDIT-ROLLBACK'
    ) THEN
        RAISE EXCEPTION 'history survived a rolled-back entity change';
    END IF;

    BEGIN
        UPDATE event_history
        SET reason = 'tampered'
        WHERE id = (SELECT min(id) FROM event_history);
        RAISE EXCEPTION 'event history UPDATE was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM <> 'event history is immutable' THEN
                RAISE;
            END IF;
    END;

    BEGIN
        DELETE FROM event_history
        WHERE id = (SELECT min(id) FROM event_history);
        RAISE EXCEPTION 'event history DELETE was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM <> 'event history is immutable' THEN
                RAISE;
            END IF;
    END;

    BEGIN
        TRUNCATE event_history;
        RAISE EXCEPTION 'event history TRUNCATE was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM <> 'event history is immutable' THEN
                RAISE;
            END IF;
    END;
END;
$$;

DELETE FROM aggregations WHERE id = :audited_aggregation_id;

DO $$
DECLARE
    delete_event event_history%ROWTYPE;
BEGIN
    SELECT * INTO STRICT delete_event
    FROM event_history
    WHERE entity_type = 'aggregation' AND operation = 'DELETE';

    IF delete_event.before_state ->> 'title' <> 'Updated audited aggregation'
       OR delete_event.after_state IS NOT NULL THEN
        RAISE EXCEPTION 'DELETE history event is incorrect';
    END IF;
END;
$$;

ROLLBACK;
