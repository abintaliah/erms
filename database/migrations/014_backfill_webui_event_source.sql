-- This development database was exclusively operated through NiceGUI for all
-- API-originated entity changes. Correct the coarse legacy `api` source while
-- preserving direct SQL events as `database`.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DROP TRIGGER IF EXISTS event_history_reject_update_delete ON event_history;

UPDATE event_history
SET source = 'web_ui',
    metadata = metadata || jsonb_build_object(
        'source_attribution_backfill',
        jsonb_build_object(
            'migration', '014_backfill_webui_event_source',
            'previous_source', 'api',
            'basis', 'development system was exclusively operated through NiceGUI'
        )
    )
WHERE source = 'api';

CREATE TRIGGER event_history_reject_update_delete
BEFORE UPDATE OR DELETE ON event_history
FOR EACH ROW EXECUTE FUNCTION reject_event_history_mutation();

INSERT INTO schema_migrations(version)
VALUES ('014_backfill_webui_event_source')
ON CONFLICT(version) DO NOTHING;
