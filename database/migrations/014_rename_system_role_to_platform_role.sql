BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 014',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Rename the platform-owned role discriminator for clarity',true),
       set_config('app.event_metadata','{"migration":"014_rename_system_role_to_platform_role"}',true);

ALTER TABLE roles RENAME COLUMN is_system TO is_platform_role;

CREATE OR REPLACE FUNCTION role_effectively_active(p_role_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT COALESCE(
        role.date_deactivated IS NULL
        AND CASE
            WHEN role.is_platform_role THEN
                role.account_type_restriction='service' AND role.org_unit_id IS NULL
            ELSE org_unit_effectively_active(role.org_unit_id)
        END,
        false
    )
    FROM roles role WHERE role.id=p_role_id;
$$;

CREATE OR REPLACE FUNCTION validate_active_role_assignment()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    selected_account_type text;
    selected_role_restriction text;
    selected_role_is_platform boolean;
BEGIN
    SELECT account_type INTO selected_account_type
    FROM users
    WHERE id=NEW.user_id AND date_deactivated IS NULL AND date_suspended IS NULL;
    IF selected_account_type IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='role assignments require an active user';
    END IF;
    SELECT account_type_restriction,is_platform_role
      INTO selected_role_restriction,selected_role_is_platform
      FROM roles WHERE id=NEW.role_id;
    IF NOT role_effectively_active(NEW.role_id) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='role assignments require an effectively active role and organization hierarchy';
    END IF;
    IF selected_role_restriction IS NOT NULL
       AND selected_role_restriction<>selected_account_type THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='role account type restriction does not match user account type';
    END IF;
    IF selected_role_is_platform AND EXISTS (
        SELECT 1 FROM user_role_assignments existing
        WHERE existing.user_id=NEW.user_id AND existing.id<>COALESCE(NEW.id,0)
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='service platform role must be the account only role assignment';
    END IF;
    IF NOT selected_role_is_platform AND EXISTS (
        SELECT 1 FROM user_role_assignments existing
        JOIN roles existing_role ON existing_role.id=existing.role_id
        WHERE existing.user_id=NEW.user_id AND existing.id<>COALESCE(NEW.id,0)
          AND existing_role.is_platform_role AND existing_role.account_type_restriction='service'
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='service platform role must be the account only role assignment';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION protect_text_indexer_role()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.code='text-indexer-service' AND OLD.is_platform_role THEN
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE='text-indexer-service role is protected';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$;

INSERT INTO schema_migrations(version)
VALUES ('014_rename_system_role_to_platform_role')
ON CONFLICT(version) DO NOTHING;

COMMIT;
