BEGIN;

CREATE INDEX IF NOT EXISTS service_account_credentials_history_cleanup_idx
    ON service_account_credentials((coalesce(date_revoked,expires_at)),id);

INSERT INTO schema_migrations(version)
VALUES ('017_add_service_credential_cleanup_index')
ON CONFLICT(version) DO NOTHING;

COMMIT;
