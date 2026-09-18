-- "Service" describes non-interactive software identities more clearly than
-- the earlier "system" account-type value. This does not rename the audit
-- actor_type "system", which identifies an automated process rather than a
-- user account category.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

SELECT set_config('app.actor_type', 'system', true),
       set_config('app.event_source', 'migration', true),
       set_config('app.change_reason', 'Rename non-interactive account type to service', true),
       set_config(
           'app.event_metadata',
           '{"migration":"017_rename_system_accounts_to_service","previous_account_type":"system"}',
           true
       );

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_account_type_valid;

UPDATE users
SET account_type = 'service'
WHERE account_type = 'system';

ALTER TABLE users
    ADD CONSTRAINT users_account_type_valid
    CHECK (account_type IN ('person', 'service'));

INSERT INTO schema_migrations(version)
VALUES ('017_rename_system_accounts_to_service')
ON CONFLICT(version) DO NOTHING;
