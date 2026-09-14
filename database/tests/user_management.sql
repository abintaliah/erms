\set ON_ERROR_STOP on

BEGIN;

INSERT INTO org_units (code, name)
VALUES ('CORP', 'Corporate Services')
RETURNING id AS root_unit_id \gset

INSERT INTO org_units (parent_org_unit_id, code, name)
VALUES (:root_unit_id, 'LEGAL', 'Legal Affairs')
RETURNING id AS legal_unit_id \gset

INSERT INTO org_units (parent_org_unit_id, code, name)
VALUES (:root_unit_id, 'FIN', 'Finance')
RETURNING id AS finance_unit_id \gset

INSERT INTO roles (org_unit_id, code, name)
VALUES (:legal_unit_id, 'LEGAL-DIRECTOR', 'Legal Affairs Director')
RETURNING id AS director_role_id \gset

-- Cross-unit supervision is intentionally allowed.
INSERT INTO roles (org_unit_id, supervisor_role_id, code, name)
VALUES (:finance_unit_id, :director_role_id, 'FIN-MANAGER', 'Finance Manager')
RETURNING id AS manager_role_id \gset

INSERT INTO users (name, email, external_id)
VALUES ('محمد علي', 'person@example.test', 'HR-1001')
RETURNING id AS user_id \gset

INSERT INTO user_role_assignments (user_id, role_id, valid_from)
VALUES (:user_id, :manager_role_id, NULL)
RETURNING id AS assignment_id \gset

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM user_role_assignments
        WHERE date_assigned = valid_from
    ) THEN
        RAISE EXCEPTION 'assignment valid_from default is incorrect';
    END IF;

    BEGIN
        INSERT INTO roles (org_unit_id, code, name)
        VALUES (
            (SELECT id FROM org_units WHERE code = 'LEGAL'),
            'legal-director-copy',
            'legal affairs director'
        );
        RAISE EXCEPTION 'case-insensitive duplicate role name was accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;

    BEGIN
        UPDATE org_units
        SET parent_org_unit_id = (SELECT id FROM org_units WHERE code = 'LEGAL')
        WHERE code = 'CORP';
        RAISE EXCEPTION 'organizational unit cycle was accepted';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM <> 'organizational unit hierarchy cannot contain a cycle' THEN
            RAISE;
        END IF;
    END;

    BEGIN
        UPDATE roles
        SET supervisor_role_id = (SELECT id FROM roles WHERE code = 'FIN-MANAGER')
        WHERE code = 'LEGAL-DIRECTOR';
        RAISE EXCEPTION 'role supervision cycle was accepted';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM <> 'role supervision hierarchy cannot contain a cycle' THEN
            RAISE;
        END IF;
    END;

    IF NOT EXISTS (
        SELECT 1 FROM event_history
        WHERE entity_type = 'user_role_assignment'
          AND entity_id = (SELECT id FROM user_role_assignments LIMIT 1)
          AND operation = 'CREATE'
    ) THEN
        RAISE EXCEPTION 'role assignment was not audited';
    END IF;
END;
$$;

ROLLBACK;
