BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Database migration 031', true),
       set_config('app.event_source', 'migration', true),
       set_config('app.change_reason', 'Rename human account type to person', true),
       set_config(
           'app.event_metadata',
           '{"migration":"031_rename_human_accounts_to_person","previous_account_type":"human"}',
           true
       );

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_account_type_valid;
ALTER TABLE users ALTER COLUMN account_type SET DEFAULT 'person';

UPDATE users
SET account_type = 'person'
WHERE account_type = 'human';

ALTER TABLE users
    ADD CONSTRAINT users_account_type_valid
    CHECK (account_type IN ('person', 'service'));

INSERT INTO schema_migrations(version)
VALUES ('031_rename_human_accounts_to_person')
ON CONFLICT(version) DO NOTHING;

COMMIT;
