BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true);
SELECT set_config('app.actor_name', 'Database migration 004', true);
SELECT set_config('app.event_source', 'migration', true);
SELECT set_config('app.change_reason',
    'Make lifecycle timestamps authoritative and separate suspension from deactivation', true);
SELECT set_config('app.suppress_ordinary_history', 'authorized', true);

DROP TRIGGER IF EXISTS org_units_normalize_lifecycle ON org_units;
DROP TRIGGER IF EXISTS users_normalize_lifecycle ON users;
DROP TRIGGER IF EXISTS roles_normalize_lifecycle ON roles;
DROP FUNCTION IF EXISTS normalize_user_management_lifecycle();

ALTER TABLE org_units DROP CONSTRAINT IF EXISTS org_units_lifecycle_consistent;
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_lifecycle_consistent;
ALTER TABLE roles DROP CONSTRAINT IF EXISTS roles_lifecycle_consistent;
ALTER TABLE org_units DROP CONSTRAINT IF EXISTS org_units_status_valid;
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_status_valid;
ALTER TABLE roles DROP CONSTRAINT IF EXISTS roles_status_valid;

ALTER TABLE org_units RENAME COLUMN status TO legacy_status;
ALTER TABLE users RENAME COLUMN status TO legacy_status;
ALTER TABLE roles RENAME COLUMN status TO legacy_status;

ALTER TABLE users ADD COLUMN date_suspended timestamptz;

UPDATE org_units
   SET date_deactivated = CASE
       WHEN legacy_status = 'inactive' THEN COALESCE(date_deactivated, CURRENT_TIMESTAMP)
       ELSE NULL
   END;
UPDATE roles
   SET date_deactivated = CASE
       WHEN legacy_status = 'inactive' THEN COALESCE(date_deactivated, CURRENT_TIMESTAMP)
       ELSE NULL
   END;
UPDATE users
   SET date_deactivated = CASE
           WHEN legacy_status = 'inactive' THEN COALESCE(date_deactivated, CURRENT_TIMESTAMP)
           ELSE NULL
       END,
       date_suspended = CASE
           WHEN legacy_status = 'suspended' THEN CURRENT_TIMESTAMP
           ELSE NULL
       END;

ALTER TABLE org_units ADD COLUMN status text GENERATED ALWAYS AS (
    CASE WHEN date_deactivated IS NULL THEN 'active' ELSE 'inactive' END
) STORED;
ALTER TABLE roles ADD COLUMN status text GENERATED ALWAYS AS (
    CASE WHEN date_deactivated IS NULL THEN 'active' ELSE 'inactive' END
) STORED;
ALTER TABLE users ADD COLUMN status text GENERATED ALWAYS AS (
    CASE
        WHEN date_deactivated IS NOT NULL THEN 'inactive'
        WHEN date_suspended IS NOT NULL THEN 'suspended'
        ELSE 'active'
    END
) STORED;

ALTER TABLE org_units DROP COLUMN legacy_status;
ALTER TABLE roles DROP COLUMN legacy_status;
ALTER TABLE users DROP COLUMN legacy_status;

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_dates_in_order;
ALTER TABLE users ADD CONSTRAINT users_dates_in_order CHECK (
    (date_deactivated IS NULL OR date_deactivated >= date_created)
    AND (date_suspended IS NULL OR date_suspended >= date_created)
);
ALTER TABLE users ADD CONSTRAINT users_lifecycle_dates_exclusive CHECK (
    date_deactivated IS NULL OR date_suspended IS NULL
);

CREATE OR REPLACE FUNCTION org_unit_effectively_active(p_org_unit_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    WITH RECURSIVE ancestors AS (
        SELECT id, parent_org_unit_id, date_deactivated
          FROM org_units WHERE id = p_org_unit_id
        UNION ALL
        SELECT parent.id, parent.parent_org_unit_id, parent.date_deactivated
          FROM org_units parent
          JOIN ancestors child ON parent.id = child.parent_org_unit_id
    )
    SELECT COALESCE(bool_and(date_deactivated IS NULL), false) FROM ancestors;
$$;

CREATE OR REPLACE FUNCTION role_effectively_active(p_role_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT COALESCE(
        role.date_deactivated IS NULL
        AND org_unit_effectively_active(role.org_unit_id),
        false
    )
      FROM roles role WHERE role.id = p_role_id;
$$;

CREATE OR REPLACE FUNCTION validate_user_management_lifecycle_dates()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.date_deactivated IS NOT NULL AND NEW.date_deactivated > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE=TG_TABLE_NAME || ' deactivation date cannot be in the future';
    END IF;
    IF TG_TABLE_NAME = 'users'
       AND NULLIF(to_jsonb(NEW)->>'date_suspended', '')::timestamptz > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE='user suspension date cannot be in the future';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER org_units_validate_lifecycle_dates
BEFORE INSERT OR UPDATE OF date_deactivated ON org_units
FOR EACH ROW EXECUTE FUNCTION validate_user_management_lifecycle_dates();

CREATE TRIGGER users_validate_lifecycle_dates
BEFORE INSERT OR UPDATE OF date_deactivated, date_suspended ON users
FOR EACH ROW EXECUTE FUNCTION validate_user_management_lifecycle_dates();

CREATE TRIGGER roles_validate_lifecycle_dates
BEFORE INSERT OR UPDATE OF date_deactivated ON roles
FOR EACH ROW EXECUTE FUNCTION validate_user_management_lifecycle_dates();

CREATE OR REPLACE FUNCTION validate_active_role_assignment()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM users
         WHERE id = NEW.user_id
           AND date_deactivated IS NULL
           AND date_suspended IS NULL
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE='role assignments require an active user';
    END IF;
    IF NOT role_effectively_active(NEW.role_id) THEN
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE='role assignments require an effectively active role and organization hierarchy';
    END IF;
    RETURN NEW;
END;
$$;

INSERT INTO event_history (
    entity_type, entity_id, operation, actor_type, actor_name,
    source, changed_fields, reason, metadata
)
SELECT
    'user', id, 'LIFECYCLE_STORAGE_NORMALIZED', 'automated_process',
    'Database migration 004', 'migration', ARRAY['date_suspended'],
    'Preserve temporary suspension as state distinct from deactivation',
    jsonb_build_object('migration', '004_normalize_user_management_lifecycle')
FROM users
WHERE date_suspended IS NOT NULL;

INSERT INTO schema_migrations (version)
VALUES ('004_normalize_user_management_lifecycle')
ON CONFLICT (version) DO NOTHING;

COMMIT;
