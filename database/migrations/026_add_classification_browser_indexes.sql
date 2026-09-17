BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true);
SELECT set_config('app.actor_name', 'Database migration 026', true);
SELECT set_config('app.source', 'migration', true);
SELECT set_config(
    'app.change_reason',
    'Add stable ordering indexes for the paginated aggregation classification browser',
    true
);

CREATE INDEX IF NOT EXISTS aggregations_parent_number_browse_idx
    ON aggregations (parent_aggregation_id, aggregation_number COLLATE "C", id);
CREATE INDEX IF NOT EXISTS records_aggregation_number_browse_idx
    ON records (aggregation_id, record_number COLLATE "C", id);
CREATE INDEX IF NOT EXISTS classifications_parent_code_browse_idx
    ON classifications (
        classification_scheme_id, parent_classification_id, code COLLATE "C", id
    );
CREATE INDEX IF NOT EXISTS aggregations_classification_number_browse_idx
    ON aggregations (classification_id, aggregation_number COLLATE "C", id);

INSERT INTO schema_migrations (version)
VALUES ('026_add_classification_browser_indexes')
ON CONFLICT (version) DO NOTHING;

COMMIT;
