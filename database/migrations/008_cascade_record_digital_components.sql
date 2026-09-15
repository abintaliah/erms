-- Digital components are dependent parts of a record, not independent entities.
CREATE TABLE IF NOT EXISTS schema_migrations (
    id         bigserial PRIMARY KEY,
    version    text NOT NULL UNIQUE,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT schema_migrations_version_not_blank CHECK (btrim(version) <> '')
);

ALTER TABLE digital_components
    DROP CONSTRAINT digital_components_record_id_fkey,
    ADD CONSTRAINT digital_components_record_id_fkey
        FOREIGN KEY (record_id) REFERENCES records (id) ON DELETE CASCADE;

INSERT INTO schema_migrations (version)
VALUES ('008_cascade_record_digital_components')
ON CONFLICT (version) DO NOTHING;
