-- Enforce user-management lifecycle semantics and inherited organization activity.
CREATE TABLE IF NOT EXISTS schema_migrations (
    id bigserial PRIMARY KEY,
    version text NOT NULL UNIQUE,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT schema_migrations_version_not_blank CHECK (btrim(version) <> '')
);

CREATE OR REPLACE FUNCTION org_unit_effectively_active(p_org_unit_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    WITH RECURSIVE ancestors AS (
        SELECT id, parent_org_unit_id, status FROM org_units WHERE id = p_org_unit_id
        UNION ALL
        SELECT parent.id, parent.parent_org_unit_id, parent.status
        FROM org_units parent JOIN ancestors child ON parent.id = child.parent_org_unit_id
    )
    SELECT COALESCE(bool_and(status = 'active'), false) FROM ancestors;
$$;

CREATE OR REPLACE FUNCTION role_effectively_active(p_role_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT COALESCE(r.status = 'active' AND org_unit_effectively_active(r.org_unit_id), false)
    FROM roles r WHERE r.id = p_role_id;
$$;

CREATE OR REPLACE FUNCTION normalize_user_management_lifecycle()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'org_units' THEN
        IF NEW.status = 'inactive' THEN
            NEW.date_closed := COALESCE(NEW.date_closed, CURRENT_TIMESTAMP);
            IF NEW.date_closed > CURRENT_TIMESTAMP THEN
                RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='organization unit closure date cannot be in the future';
            END IF;
        ELSE
            NEW.date_closed := NULL;
        END IF;
    ELSIF TG_TABLE_NAME = 'users' THEN
        IF NEW.status = 'inactive' THEN
            NEW.date_deactivated := COALESCE(NEW.date_deactivated, CURRENT_TIMESTAMP);
            IF NEW.date_deactivated > CURRENT_TIMESTAMP THEN
                RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='user deactivation date cannot be in the future';
            END IF;
        ELSE
            NEW.date_deactivated := NULL;
        END IF;
    ELSE
        IF NEW.status = 'inactive' THEN
            NEW.date_deactivated := COALESCE(NEW.date_deactivated, CURRENT_TIMESTAMP);
            IF NEW.date_deactivated > CURRENT_TIMESTAMP THEN
                RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='role deactivation date cannot be in the future';
            END IF;
        ELSE
            NEW.date_deactivated := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validate_active_role_assignment()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.user_id AND status='active') THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='role assignments require an active user';
    END IF;
    IF NOT role_effectively_active(NEW.role_id) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='role assignments require an effectively active role and organization hierarchy';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS org_units_normalize_lifecycle ON org_units;
CREATE TRIGGER org_units_normalize_lifecycle
BEFORE INSERT OR UPDATE OF status, date_closed ON org_units
FOR EACH ROW EXECUTE FUNCTION normalize_user_management_lifecycle();

DROP TRIGGER IF EXISTS users_normalize_lifecycle ON users;
CREATE TRIGGER users_normalize_lifecycle
BEFORE INSERT OR UPDATE OF status, date_deactivated ON users
FOR EACH ROW EXECUTE FUNCTION normalize_user_management_lifecycle();

DROP TRIGGER IF EXISTS roles_normalize_lifecycle ON roles;
CREATE TRIGGER roles_normalize_lifecycle
BEFORE INSERT OR UPDATE OF status, date_deactivated ON roles
FOR EACH ROW EXECUTE FUNCTION normalize_user_management_lifecycle();

DROP TRIGGER IF EXISTS user_role_assignments_validate_active ON user_role_assignments;
CREATE TRIGGER user_role_assignments_validate_active
BEFORE INSERT OR UPDATE OF user_id, role_id ON user_role_assignments
FOR EACH ROW EXECUTE FUNCTION validate_active_role_assignment();


UPDATE org_units
SET date_closed = CASE WHEN status = 'inactive' THEN COALESCE(date_closed, CURRENT_TIMESTAMP) ELSE NULL END;
UPDATE users
SET date_deactivated = CASE WHEN status = 'inactive' THEN COALESCE(date_deactivated, CURRENT_TIMESTAMP) ELSE NULL END;
UPDATE roles
SET date_deactivated = CASE WHEN status = 'inactive' THEN COALESCE(date_deactivated, CURRENT_TIMESTAMP) ELSE NULL END;

ALTER TABLE org_units DROP CONSTRAINT IF EXISTS org_units_lifecycle_consistent;
ALTER TABLE org_units ADD CONSTRAINT org_units_lifecycle_consistent
    CHECK ((status = 'inactive') = (date_closed IS NOT NULL));
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_lifecycle_consistent;
ALTER TABLE users ADD CONSTRAINT users_lifecycle_consistent
    CHECK ((status = 'inactive') = (date_deactivated IS NOT NULL));
ALTER TABLE roles DROP CONSTRAINT IF EXISTS roles_lifecycle_consistent;
ALTER TABLE roles ADD CONSTRAINT roles_lifecycle_consistent
    CHECK ((status = 'inactive') = (date_deactivated IS NOT NULL));


INSERT INTO schema_migrations(version)
VALUES ('009_user_management_lifecycle')
ON CONFLICT(version) DO NOTHING;
