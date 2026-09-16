-- Standardize organizational-unit lifecycle terminology with users and roles.
-- PostgreSQL preserves every existing timestamp while renaming the column.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DROP TRIGGER IF EXISTS org_units_normalize_lifecycle ON org_units;

ALTER TABLE org_units
    RENAME COLUMN date_closed TO date_deactivated;

CREATE OR REPLACE FUNCTION normalize_user_management_lifecycle()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'org_units' THEN
        IF NEW.status = 'inactive' THEN
            NEW.date_deactivated := COALESCE(NEW.date_deactivated, CURRENT_TIMESTAMP);
            IF NEW.date_deactivated > CURRENT_TIMESTAMP THEN
                RAISE EXCEPTION USING
                    ERRCODE = 'P0001',
                    MESSAGE = 'organization unit deactivation date cannot be in the future';
            END IF;
        ELSE
            NEW.date_deactivated := NULL;
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

CREATE TRIGGER org_units_normalize_lifecycle
BEFORE INSERT OR UPDATE OF status, date_deactivated ON org_units
FOR EACH ROW EXECUTE FUNCTION normalize_user_management_lifecycle();

INSERT INTO schema_migrations(version)
VALUES ('010_rename_org_unit_deactivation_date')
ON CONFLICT(version) DO NOTHING;
