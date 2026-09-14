CREATE TABLE IF NOT EXISTS org_units (
    id                 bigserial PRIMARY KEY,
    parent_org_unit_id bigint REFERENCES org_units (id) ON DELETE RESTRICT,
    code               text NOT NULL,
    name               text NOT NULL,
    description        text,
    status             text NOT NULL DEFAULT 'active',
    date_created       timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_closed        timestamptz,

    CONSTRAINT org_units_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT org_units_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT org_units_status_valid CHECK (status IN ('active', 'inactive')),
    CONSTRAINT org_units_not_own_parent
        CHECK (parent_org_unit_id IS NULL OR parent_org_unit_id <> id),
    CONSTRAINT org_units_dates_in_order
        CHECK (date_closed IS NULL OR date_closed >= date_created)
);

CREATE UNIQUE INDEX IF NOT EXISTS org_units_code_ci_unique
    ON org_units (lower(code));
CREATE UNIQUE INDEX IF NOT EXISTS org_units_name_ci_unique
    ON org_units (lower(name));
CREATE INDEX IF NOT EXISTS org_units_parent_org_unit_id_idx
    ON org_units (parent_org_unit_id);

CREATE TABLE IF NOT EXISTS users (
    id               bigserial PRIMARY KEY,
    name             text NOT NULL,
    email            text,
    external_id      text,
    status           text NOT NULL DEFAULT 'active',
    date_created     timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_deactivated timestamptz,

    CONSTRAINT users_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT users_email_not_blank CHECK (email IS NULL OR btrim(email) <> ''),
    CONSTRAINT users_external_id_not_blank
        CHECK (external_id IS NULL OR btrim(external_id) <> ''),
    CONSTRAINT users_status_valid
        CHECK (status IN ('active', 'inactive', 'suspended')),
    CONSTRAINT users_dates_in_order
        CHECK (date_deactivated IS NULL OR date_deactivated >= date_created)
);

CREATE UNIQUE INDEX IF NOT EXISTS users_email_ci_unique
    ON users (lower(email)) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS users_external_id_unique
    ON users (external_id) WHERE external_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS roles (
    id                 bigserial PRIMARY KEY,
    org_unit_id        bigint NOT NULL REFERENCES org_units (id) ON DELETE RESTRICT,
    supervisor_role_id bigint REFERENCES roles (id) ON DELETE RESTRICT,
    code               text NOT NULL,
    name               text NOT NULL,
    description        text,
    status             text NOT NULL DEFAULT 'active',
    date_created       timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_deactivated   timestamptz,

    CONSTRAINT roles_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT roles_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT roles_status_valid CHECK (status IN ('active', 'inactive')),
    CONSTRAINT roles_not_own_supervisor
        CHECK (supervisor_role_id IS NULL OR supervisor_role_id <> id),
    CONSTRAINT roles_dates_in_order
        CHECK (date_deactivated IS NULL OR date_deactivated >= date_created)
);

CREATE UNIQUE INDEX IF NOT EXISTS roles_code_ci_unique ON roles (lower(code));
CREATE UNIQUE INDEX IF NOT EXISTS roles_name_ci_unique ON roles (lower(name));
CREATE INDEX IF NOT EXISTS roles_org_unit_id_idx ON roles (org_unit_id);
CREATE INDEX IF NOT EXISTS roles_supervisor_role_id_idx ON roles (supervisor_role_id);

CREATE TABLE IF NOT EXISTS user_role_assignments (
    id            bigserial PRIMARY KEY,
    user_id       bigint NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    role_id       bigint NOT NULL REFERENCES roles (id) ON DELETE RESTRICT,
    assigned_by   bigint REFERENCES users (id) ON DELETE RESTRICT,
    date_assigned timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_from    timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_until   timestamptz,

    CONSTRAINT user_role_assignments_dates_in_order
        CHECK (valid_until IS NULL OR valid_until >= valid_from),
    CONSTRAINT user_role_assignments_period_unique
        UNIQUE (user_id, role_id, valid_from)
);

CREATE INDEX IF NOT EXISTS user_role_assignments_user_id_idx
    ON user_role_assignments (user_id);
CREATE INDEX IF NOT EXISTS user_role_assignments_role_id_idx
    ON user_role_assignments (role_id);
CREATE INDEX IF NOT EXISTS user_role_assignments_assigned_by_idx
    ON user_role_assignments (assigned_by) WHERE assigned_by IS NOT NULL;

CREATE OR REPLACE FUNCTION set_user_management_default_dates()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.date_created IS NULL THEN
        NEW.date_created := CURRENT_TIMESTAMP;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION set_assignment_default_dates()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.date_assigned IS NULL THEN
        NEW.date_assigned := CURRENT_TIMESTAMP;
    END IF;
    IF NEW.valid_from IS NULL THEN
        NEW.valid_from := NEW.date_assigned;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION prevent_org_unit_cycle()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.parent_org_unit_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF EXISTS (
        WITH RECURSIVE ancestors AS (
            SELECT id, parent_org_unit_id
            FROM org_units WHERE id = NEW.parent_org_unit_id
            UNION ALL
            SELECT parent.id, parent.parent_org_unit_id
            FROM org_units AS parent
            JOIN ancestors ON parent.id = ancestors.parent_org_unit_id
        )
        SELECT 1 FROM ancestors WHERE id = NEW.id
    ) THEN
        RAISE EXCEPTION 'organizational unit hierarchy cannot contain a cycle';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION prevent_role_supervision_cycle()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.supervisor_role_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF EXISTS (
        WITH RECURSIVE supervisors AS (
            SELECT id, supervisor_role_id
            FROM roles WHERE id = NEW.supervisor_role_id
            UNION ALL
            SELECT supervisor.id, supervisor.supervisor_role_id
            FROM roles AS supervisor
            JOIN supervisors ON supervisor.id = supervisors.supervisor_role_id
        )
        SELECT 1 FROM supervisors WHERE id = NEW.id
    ) THEN
        RAISE EXCEPTION 'role supervision hierarchy cannot contain a cycle';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS org_units_set_default_dates ON org_units;
CREATE TRIGGER org_units_set_default_dates
BEFORE INSERT ON org_units
FOR EACH ROW EXECUTE FUNCTION set_user_management_default_dates();

DROP TRIGGER IF EXISTS users_set_default_dates ON users;
CREATE TRIGGER users_set_default_dates
BEFORE INSERT ON users
FOR EACH ROW EXECUTE FUNCTION set_user_management_default_dates();

DROP TRIGGER IF EXISTS roles_set_default_dates ON roles;
CREATE TRIGGER roles_set_default_dates
BEFORE INSERT ON roles
FOR EACH ROW EXECUTE FUNCTION set_user_management_default_dates();

DROP TRIGGER IF EXISTS user_role_assignments_set_default_dates ON user_role_assignments;
CREATE TRIGGER user_role_assignments_set_default_dates
BEFORE INSERT ON user_role_assignments
FOR EACH ROW EXECUTE FUNCTION set_assignment_default_dates();

DROP TRIGGER IF EXISTS org_units_prevent_cycle ON org_units;
CREATE TRIGGER org_units_prevent_cycle
BEFORE INSERT OR UPDATE OF parent_org_unit_id ON org_units
FOR EACH ROW EXECUTE FUNCTION prevent_org_unit_cycle();

DROP TRIGGER IF EXISTS roles_prevent_supervision_cycle ON roles;
CREATE TRIGGER roles_prevent_supervision_cycle
BEFORE INSERT OR UPDATE OF supervisor_role_id ON roles
FOR EACH ROW EXECUTE FUNCTION prevent_role_supervision_cycle();

DROP TRIGGER IF EXISTS org_units_record_history ON org_units;
CREATE TRIGGER org_units_record_history
AFTER INSERT OR UPDATE OR DELETE ON org_units
FOR EACH ROW EXECUTE FUNCTION record_entity_history('org_unit');

DROP TRIGGER IF EXISTS users_record_history ON users;
CREATE TRIGGER users_record_history
AFTER INSERT OR UPDATE OR DELETE ON users
FOR EACH ROW EXECUTE FUNCTION record_entity_history('user');

DROP TRIGGER IF EXISTS roles_record_history ON roles;
CREATE TRIGGER roles_record_history
AFTER INSERT OR UPDATE OR DELETE ON roles
FOR EACH ROW EXECUTE FUNCTION record_entity_history('role');

DROP TRIGGER IF EXISTS user_role_assignments_record_history ON user_role_assignments;
CREATE TRIGGER user_role_assignments_record_history
AFTER INSERT OR UPDATE OR DELETE ON user_role_assignments
FOR EACH ROW EXECUTE FUNCTION record_entity_history('user_role_assignment');

INSERT INTO schema_migrations (version)
VALUES ('002_add_user_management')
ON CONFLICT (version) DO NOTHING;
