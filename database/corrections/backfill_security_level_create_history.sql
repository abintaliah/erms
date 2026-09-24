BEGIN;

INSERT INTO event_history (
    occurred_at,
    entity_type,
    entity_id,
    operation,
    actor_type,
    actor_name,
    actor_email,
    source,
    after_state,
    changed_fields,
    reason,
    metadata
)
SELECT
    level.date_created,
    'security_level',
    level.id,
    'CREATE',
    'automated_process',
    'Security-level history correction',
    'system@erms.local',
    'administrative_tool',
    to_jsonb(level),
    ARRAY[
        'code', 'date_created', 'date_updated', 'id', 'level_number',
        'name', 'prevents_disposition'
    ]::text[],
    'Baseline CREATE event backfilled for an existing security level.',
    jsonb_build_object(
        'backfilled', true,
        'correction', 'backfill_security_level_create_history',
        'original_source', 'seeding'
    )
FROM security_levels level
WHERE NOT EXISTS (
    SELECT 1
    FROM event_history event
    WHERE event.entity_type = 'security_level'
      AND event.entity_id = level.id
      AND event.operation = 'CREATE'
);

COMMIT;
