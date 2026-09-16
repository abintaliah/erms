-- Normalize the historical organizational-unit lifecycle field name after
-- migration 010 renamed the live table column. No event values or ordering are
-- changed; only the field name stored inside the audit payload is rewritten.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DROP TRIGGER IF EXISTS event_history_reject_update_delete ON event_history;

UPDATE event_history
SET before_state = CASE
        WHEN before_state ? 'date_closed'
            THEN (before_state - 'date_closed')
                 || jsonb_build_object('date_deactivated', before_state -> 'date_closed')
        ELSE before_state
    END,
    after_state = CASE
        WHEN after_state ? 'date_closed'
            THEN (after_state - 'date_closed')
                 || jsonb_build_object('date_deactivated', after_state -> 'date_closed')
        ELSE after_state
    END,
    changed_fields = ARRAY(
        SELECT CASE
            WHEN field_name = 'date_closed' THEN 'date_deactivated'
            ELSE field_name
        END
        FROM unnest(changed_fields) WITH ORDINALITY AS fields(field_name, position)
        ORDER BY position
    )
WHERE entity_type = 'org_unit'
  AND (
      before_state ? 'date_closed'
      OR after_state ? 'date_closed'
      OR 'date_closed' = ANY(changed_fields)
  );

CREATE TRIGGER event_history_reject_update_delete
BEFORE UPDATE OR DELETE ON event_history
FOR EACH ROW EXECUTE FUNCTION reject_event_history_mutation();

INSERT INTO schema_migrations(version)
VALUES ('011_normalize_org_unit_event_history')
ON CONFLICT(version) DO NOTHING;
