BEGIN;

DO $$
DECLARE
    migration_name constant text := '030_remove_assignment_attribution_and_prepare_user_deletion';
BEGIN
    IF EXISTS (SELECT 1 FROM schema_migrations WHERE version = migration_name) THEN
        RETURN;
    END IF;

    DROP INDEX IF EXISTS user_role_assignments_assigned_by_idx;
    ALTER TABLE user_role_assignments
        DROP CONSTRAINT IF EXISTS user_role_assignments_assigned_by_fkey,
        DROP COLUMN IF EXISTS assigned_by;

    ALTER TABLE user_role_assignments
        DROP CONSTRAINT IF EXISTS user_role_assignments_user_id_fkey,
        ADD CONSTRAINT user_role_assignments_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        DROP CONSTRAINT IF EXISTS user_role_assignments_role_id_fkey,
        ADD CONSTRAINT user_role_assignments_role_id_fkey
            FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE;

    ALTER TABLE record_drafts
        DROP CONSTRAINT IF EXISTS record_drafts_owner_user_id_fkey,
        ADD CONSTRAINT record_drafts_owner_user_id_fkey
            FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE;

    CREATE INDEX IF NOT EXISTS login_sessions_revoked_cleanup_idx
        ON login_sessions (revoked_at, id)
        WHERE revoked_at IS NOT NULL;

    INSERT INTO schema_migrations(version) VALUES (migration_name);
END;
$$;

COMMIT;
