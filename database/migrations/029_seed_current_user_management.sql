BEGIN;

-- TEST ENVIRONMENTS ONLY.
-- Every seeded user receives the shared password: pass12345678
-- Do not apply this migration to production or any security-sensitive system.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $$
DECLARE
    migration_name constant text := '028_seed_current_user_management';
    inserted_count integer;
BEGIN
    IF EXISTS (SELECT 1 FROM schema_migrations WHERE version = migration_name) THEN
        RETURN;
    END IF;

    PERFORM set_config('app.actor_type', 'automated_process', true),
            set_config('app.actor_name', 'Database migration 028', true),
            set_config('app.event_source', 'migration', true),
            set_config(
                'app.change_reason',
                'Seed organizational units, roles, users and role assignments exported from the ERMS development database on 17 September 2026',
                true
            ),
            set_config(
                'app.event_metadata',
                jsonb_build_object(
                    'migration', migration_name,
                    'operation', 'user_management_seed',
                    'source', 'postgres://localhost:5433/erms',
                    'exported_at', '2026-09-17',
                    'credentials_included', true,
                    'shared_test_password', true,
                    'login_sessions_included', false,
                    'existing_seed_user_sessions_revoked', true
                )::text,
                true
            );

    CREATE TEMP TABLE seed_org_units (
        parent_code text,
        code text PRIMARY KEY,
        name text NOT NULL,
        description text,
        status text NOT NULL,
        date_created timestamptz NOT NULL,
        date_deactivated timestamptz,
        version bigint NOT NULL
    ) ON COMMIT DROP;

    INSERT INTO seed_org_units VALUES
        (NULL,     'SYSTEM', 'Platform Administration',         NULL, 'active', '2026-09-17 20:14:20.094777+04', NULL, 1),
        (NULL,     'SA',     'Sharjah Archives',                NULL, 'active', '2026-09-17 20:17:06.808935+04', NULL, 1),
        ('GMO',    'RMD',    'Records Management Department',  NULL, 'active', '2026-09-17 20:17:30.133152+04', NULL, 2),
        ('SA',     'GMO',    'General Manager''s Office',       NULL, 'active', '2026-09-17 20:18:25.085270+04', NULL, 1),
        ('GMO',    'EAO',    'Experts and Advisors Office',     NULL, 'active', '2026-09-17 20:19:30.760204+04', NULL, 1),
        ('GMO',    'RECU',   'Records Unit',                    NULL, 'active', '2026-09-17 20:19:52.859498+04', NULL, 1),
        ('RMD',    'DRS',    'Digital Records Section',         NULL, 'active', '2026-09-17 20:20:14.159093+04', NULL, 1);

    IF EXISTS (
        SELECT 1
        FROM seed_org_units seed
        JOIN org_units existing
          ON lower(existing.code) = lower(seed.code)
          OR lower(existing.name) = lower(seed.name)
        WHERE lower(existing.code) <> lower(seed.code)
           OR lower(existing.name) <> lower(seed.name)
    ) THEN
        RAISE EXCEPTION
            'organizational-unit seed conflicts with an existing code or name';
    END IF;

    LOOP
        INSERT INTO org_units (
            parent_org_unit_id, code, name, description, status,
            date_created, date_deactivated, version
        )
        SELECT parent.id, seed.code, seed.name, seed.description, seed.status,
               seed.date_created, seed.date_deactivated, seed.version
        FROM seed_org_units seed
        LEFT JOIN org_units parent
          ON lower(parent.code) = lower(seed.parent_code)
        WHERE NOT EXISTS (
                  SELECT 1 FROM org_units existing
                  WHERE lower(existing.code) = lower(seed.code)
              )
          AND (seed.parent_code IS NULL OR parent.id IS NOT NULL);

        GET DIAGNOSTICS inserted_count = ROW_COUNT;
        EXIT WHEN NOT EXISTS (
            SELECT 1
            FROM seed_org_units seed
            WHERE NOT EXISTS (
                SELECT 1 FROM org_units existing
                WHERE lower(existing.code) = lower(seed.code)
            )
        );
        IF inserted_count = 0 THEN
            RAISE EXCEPTION
                'organizational-unit seed contains an unresolved parent or cycle';
        END IF;
    END LOOP;

    CREATE TEMP TABLE seed_roles (
        org_unit_code text NOT NULL,
        supervisor_role_code text,
        code text PRIMARY KEY,
        name text NOT NULL,
        description text,
        status text NOT NULL,
        date_created timestamptz NOT NULL,
        date_deactivated timestamptz,
        version bigint NOT NULL
    ) ON COMMIT DROP;

    INSERT INTO seed_roles VALUES
        ('SYSTEM', NULL,      'system-administrator', 'SYSTEM — System Administrator',                  'Reserved platform administration role', 'active', '2026-09-17 20:14:20.094777+04', NULL, 1),
        ('GMO',    NULL,      'GM',                   'General Manager',                                NULL,                                    'active', '2026-09-17 20:20:49.482405+04', NULL, 1),
        ('RMD',    'GM',      'RMD-DIR',              'Director (Records Management Department)',       NULL,                                    'active', '2026-09-17 20:21:35.968759+04', NULL, 1),
        ('RECU',   'GM',      'REC-MGR',              'Records Manager',                                NULL,                                    'active', '2026-09-17 20:22:20.632197+04', NULL, 1),
        ('DRS',    'RMD-DIR', 'DRS-HD',               'Head (Digital Records Section)',                 NULL,                                    'active', '2026-09-17 20:23:05.575448+04', NULL, 1),
        ('EAO',    'GM',      'EXP-ERM',              'Expert in Electronic Records Management',        NULL,                                    'active', '2026-09-17 20:23:37.684054+04', NULL, 1),
        ('EAO',    'GM',      'AV-RM',                'Advisor in Records Management',                   NULL,                                    'active', '2026-09-17 20:44:59.529521+04', NULL, 1);

    IF EXISTS (
        SELECT 1
        FROM seed_roles seed
        JOIN roles existing
          ON lower(existing.code) = lower(seed.code)
          OR lower(existing.name) = lower(seed.name)
        WHERE lower(existing.code) <> lower(seed.code)
           OR lower(existing.name) <> lower(seed.name)
    ) THEN
        RAISE EXCEPTION 'role seed conflicts with an existing code or name';
    END IF;

    LOOP
        INSERT INTO roles (
            org_unit_id, supervisor_role_id, code, name, description, status,
            date_created, date_deactivated, version
        )
        SELECT unit.id, supervisor.id, seed.code, seed.name, seed.description,
               seed.status, seed.date_created, seed.date_deactivated, seed.version
        FROM seed_roles seed
        JOIN org_units unit
          ON lower(unit.code) = lower(seed.org_unit_code)
        LEFT JOIN roles supervisor
          ON lower(supervisor.code) = lower(seed.supervisor_role_code)
        WHERE NOT EXISTS (
                  SELECT 1 FROM roles existing
                  WHERE lower(existing.code) = lower(seed.code)
              )
          AND (seed.supervisor_role_code IS NULL OR supervisor.id IS NOT NULL);

        GET DIAGNOSTICS inserted_count = ROW_COUNT;
        EXIT WHEN NOT EXISTS (
            SELECT 1
            FROM seed_roles seed
            WHERE NOT EXISTS (
                SELECT 1 FROM roles existing
                WHERE lower(existing.code) = lower(seed.code)
            )
        );
        IF inserted_count = 0 THEN
            RAISE EXCEPTION 'role seed contains an unresolved supervisor or cycle';
        END IF;
    END LOOP;

    CREATE TEMP TABLE seed_users (
        name text NOT NULL,
        email text PRIMARY KEY,
        external_id text,
        account_type text NOT NULL,
        status text NOT NULL,
        date_created timestamptz NOT NULL,
        date_deactivated timestamptz,
        version bigint NOT NULL
    ) ON COMMIT DROP;

    INSERT INTO seed_users VALUES
        ('Bootstrap Administrator',  'bootstrap@erms.local', 'SYSTEM-BOOTSTRAP', 'human', 'active', '2026-09-17 20:14:20.094777+04', NULL, 1),
        ('Salah Mahmoud',             'gm@sa.gov.ae',         NULL,               'human', 'active', '2026-09-17 20:25:02.419445+04', NULL, 1),
        ('Alya Al-Salman',            'aas@sa.gov.ae',        NULL,               'human', 'active', '2026-09-17 20:25:22.382205+04', NULL, 2),
        ('Fathiya Yousif Al-Mulla',   'fym@sa.gov.ae',        NULL,               'human', 'active', '2026-09-17 20:27:18.288719+04', NULL, 1),
        ('Ahmed BinTaliah',           'abt@sa.gov.ae',        NULL,               'human', 'active', '2026-09-17 20:27:46.264701+04', NULL, 1),
        ('Yahya Yai Abdullah',        'yya@sa.gov.ae',        NULL,               'human', 'active', '2026-09-17 20:28:04.649664+04', NULL, 1),
        ('Sami Mali Jibtou Jari',     'smjj@sa.gov.ae',       NULL,               'human', 'active', '2026-09-17 20:43:53.918232+04', NULL, 1);

    IF EXISTS (
        SELECT 1
        FROM seed_users seed
        JOIN users existing
          ON lower(existing.email) = lower(seed.email)
          OR (
              seed.external_id IS NOT NULL
              AND existing.external_id = seed.external_id
          )
        WHERE lower(existing.email) <> lower(seed.email)
           OR existing.name <> seed.name
           OR existing.external_id IS DISTINCT FROM seed.external_id
           OR existing.account_type <> seed.account_type
    ) THEN
        RAISE EXCEPTION
            'user seed conflicts with an existing email or external identifier';
    END IF;

    INSERT INTO users (
        name, email, external_id, account_type, status,
        date_created, date_deactivated, version
    )
    SELECT seed.name, seed.email, seed.external_id, seed.account_type,
           seed.status, seed.date_created, seed.date_deactivated, seed.version
    FROM seed_users seed
    WHERE NOT EXISTS (
        SELECT 1 FROM users existing
        WHERE lower(existing.email) = lower(seed.email)
    );

    -- This Argon2id hash is for the shared test password pass12345678. The
    -- migration intentionally replaces credentials for matching seeded users
    -- so its stated test login is deterministic on both empty and reused test
    -- databases.
    INSERT INTO user_credentials (
        user_id, password_hash, must_change_password, temporary_expires_at,
        password_changed_at, failed_attempt_count, last_failed_at, locked_until,
        last_authenticated_at, date_created, date_updated
    )
    SELECT seeded_user.id,
           '$argon2id$v=19$m=65536,t=3,p=4$+ld3FNFAz76i3+s0fmn7lQ$jMstAG4CIZY4ZtVQypnEUxBP5jaeqQ2E0VvKKlT+vVc',
           false, NULL, CURRENT_TIMESTAMP, 0, NULL, NULL, NULL,
           CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    FROM seed_users seed
    JOIN users seeded_user
      ON lower(seeded_user.email) = lower(seed.email)
    ON CONFLICT (user_id) DO UPDATE
    SET password_hash = EXCLUDED.password_hash,
        must_change_password = false,
        temporary_expires_at = NULL,
        password_changed_at = CURRENT_TIMESTAMP,
        failed_attempt_count = 0,
        last_failed_at = NULL,
        locked_until = NULL,
        last_authenticated_at = NULL,
        date_updated = CURRENT_TIMESTAMP;

    -- A password replacement invalidates any sessions copied or created in a
    -- reused test database. Sessions themselves are not seed data.
    DELETE FROM login_sessions session
    USING seed_users seed, users seeded_user
    WHERE lower(seeded_user.email) = lower(seed.email)
      AND session.user_id = seeded_user.id;

    CREATE TEMP TABLE seed_user_role_assignments (
        user_email text NOT NULL,
        role_code text NOT NULL,
        assigned_by_email text,
        date_assigned timestamptz NOT NULL,
        valid_from timestamptz NOT NULL,
        valid_until timestamptz,
        version bigint NOT NULL,
        PRIMARY KEY (user_email, role_code, valid_from)
    ) ON COMMIT DROP;

    INSERT INTO seed_user_role_assignments VALUES
        ('bootstrap@erms.local', 'system-administrator', NULL, '2026-09-17 20:14:20.094777+04', '2026-09-17 20:14:20.094777+04', NULL, 1),
        ('yya@sa.gov.ae',        'system-administrator', NULL, '2026-09-17 20:28:18.545482+04', '2026-09-17 20:28:18.545482+04', NULL, 1),
        ('yya@sa.gov.ae',        'EXP-ERM',              NULL, '2026-09-17 20:28:23.107250+04', '2026-09-17 20:28:23.107250+04', NULL, 1),
        ('abt@sa.gov.ae',        'DRS-HD',               NULL, '2026-09-17 20:28:33.669684+04', '2026-09-17 20:28:33.669684+04', NULL, 1),
        ('fym@sa.gov.ae',        'REC-MGR',              NULL, '2026-09-17 20:28:42.231302+04', '2026-09-17 20:28:42.231302+04', NULL, 1),
        ('aas@sa.gov.ae',        'RMD-DIR',              NULL, '2026-09-17 20:28:52.033240+04', '2026-09-17 20:28:52.033240+04', NULL, 1),
        ('gm@sa.gov.ae',         'GM',                   NULL, '2026-09-17 20:29:00.979964+04', '2026-09-17 20:29:00.979964+04', NULL, 1),
        ('smjj@sa.gov.ae',       'AV-RM',                NULL, '2026-09-17 20:45:07.726001+04', '2026-09-17 20:45:07.726001+04', NULL, 1);

    INSERT INTO user_role_assignments (
        user_id, role_id, assigned_by, date_assigned,
        valid_from, valid_until, version
    )
    SELECT assigned_user.id, assigned_role.id, assigning_user.id,
           seed.date_assigned, seed.valid_from, seed.valid_until, seed.version
    FROM seed_user_role_assignments seed
    JOIN users assigned_user
      ON lower(assigned_user.email) = lower(seed.user_email)
    JOIN roles assigned_role
      ON lower(assigned_role.code) = lower(seed.role_code)
    LEFT JOIN users assigning_user
      ON lower(assigning_user.email) = lower(seed.assigned_by_email)
    WHERE NOT EXISTS (
        SELECT 1
        FROM user_role_assignments existing
        WHERE existing.user_id = assigned_user.id
          AND existing.role_id = assigned_role.id
          AND (
              existing.valid_from = seed.valid_from
              OR (existing.valid_until IS NULL AND seed.valid_until IS NULL)
          )
    );

    INSERT INTO schema_migrations (version) VALUES (migration_name);
END;
$$;

COMMIT;
