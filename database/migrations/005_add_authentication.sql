ALTER TABLE users ADD COLUMN IF NOT EXISTS account_type text NOT NULL DEFAULT 'person';
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_account_type_valid;
ALTER TABLE users ADD CONSTRAINT users_account_type_valid CHECK (account_type IN ('person', 'system'));

CREATE TABLE IF NOT EXISTS user_credentials (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL UNIQUE REFERENCES users (id) ON DELETE CASCADE,
    password_hash text NOT NULL CHECK (btrim(password_hash) <> ''),
    must_change_password boolean NOT NULL DEFAULT true,
    temporary_expires_at timestamptz,
    password_changed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    failed_attempt_count integer NOT NULL DEFAULT 0 CHECK (failed_attempt_count >= 0),
    last_failed_at timestamptz,
    locked_until timestamptz,
    last_authenticated_at timestamptz,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS login_sessions (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    session_token_hash bytea NOT NULL UNIQUE,
    csrf_token_hash bytea NOT NULL,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL,
    absolute_expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    revoked_by bigint REFERENCES users (id) ON DELETE SET NULL,
    client_ip inet,
    user_agent text,
    CONSTRAINT login_sessions_expiry_valid CHECK (expires_at > date_created),
    CONSTRAINT login_sessions_absolute_expiry_valid CHECK (absolute_expires_at >= expires_at)
);

CREATE INDEX IF NOT EXISTS login_sessions_user_id_idx ON login_sessions (user_id);
CREATE INDEX IF NOT EXISTS login_sessions_active_idx ON login_sessions (expires_at, absolute_expires_at) WHERE revoked_at IS NULL;

INSERT INTO schema_migrations (version) VALUES ('005_add_authentication') ON CONFLICT (version) DO NOTHING;
