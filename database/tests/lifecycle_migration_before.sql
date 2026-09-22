CREATE TABLE schema_migrations (
    id bigserial PRIMARY KEY,
    version text NOT NULL UNIQUE,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE event_history (
    id bigserial PRIMARY KEY,
    entity_type text NOT NULL,
    entity_id bigint NOT NULL,
    operation text NOT NULL,
    actor_type text NOT NULL,
    actor_name text,
    source text NOT NULL,
    changed_fields text[] NOT NULL DEFAULT '{}',
    reason text,
    metadata jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE org_units (
    id bigserial PRIMARY KEY,
    parent_org_unit_id bigint REFERENCES org_units(id),
    code text NOT NULL,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_deactivated timestamptz,
    CONSTRAINT org_units_status_valid CHECK (status IN ('active', 'inactive')),
    CONSTRAINT org_units_lifecycle_consistent
        CHECK ((status = 'inactive') = (date_deactivated IS NOT NULL))
);

CREATE TABLE users (
    id bigserial PRIMARY KEY,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_deactivated timestamptz,
    CONSTRAINT users_status_valid CHECK (status IN ('active', 'inactive', 'suspended')),
    CONSTRAINT users_dates_in_order
        CHECK (date_deactivated IS NULL OR date_deactivated >= date_created),
    CONSTRAINT users_lifecycle_consistent
        CHECK ((status = 'inactive') = (date_deactivated IS NOT NULL))
);

CREATE TABLE roles (
    id bigserial PRIMARY KEY,
    org_unit_id bigint NOT NULL REFERENCES org_units(id),
    code text NOT NULL,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_deactivated timestamptz,
    CONSTRAINT roles_status_valid CHECK (status IN ('active', 'inactive')),
    CONSTRAINT roles_lifecycle_consistent
        CHECK ((status = 'inactive') = (date_deactivated IS NOT NULL))
);

CREATE TABLE user_role_assignments (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users(id),
    role_id bigint NOT NULL REFERENCES roles(id)
);

CREATE FUNCTION normalize_user_management_lifecycle()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END; $$;
CREATE TRIGGER org_units_normalize_lifecycle BEFORE INSERT OR UPDATE ON org_units
FOR EACH ROW EXECUTE FUNCTION normalize_user_management_lifecycle();
CREATE TRIGGER users_normalize_lifecycle BEFORE INSERT OR UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION normalize_user_management_lifecycle();
CREATE TRIGGER roles_normalize_lifecycle BEFORE INSERT OR UPDATE ON roles
FOR EACH ROW EXECUTE FUNCTION normalize_user_management_lifecycle();

CREATE FUNCTION validate_active_role_assignment()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END; $$;

INSERT INTO org_units (code, name, status, date_deactivated) VALUES
    ('ACTIVE', 'Active Unit', 'active', NULL),
    ('INACTIVE', 'Inactive Unit', 'inactive', CURRENT_TIMESTAMP - interval '1 day');
INSERT INTO users (name, status, date_created, date_deactivated) VALUES
    ('Active Person', 'active', CURRENT_TIMESTAMP - interval '2 days', NULL),
    ('Inactive Person', 'inactive', CURRENT_TIMESTAMP - interval '2 days', CURRENT_TIMESTAMP - interval '1 day'),
    ('Suspended Person', 'suspended', CURRENT_TIMESTAMP - interval '2 days', NULL);
INSERT INTO roles (org_unit_id, code, name, status, date_deactivated) VALUES
    (1, 'ACTIVE', 'Active Role', 'active', NULL),
    (1, 'INACTIVE', 'Inactive Role', 'inactive', CURRENT_TIMESTAMP - interval '1 day');
