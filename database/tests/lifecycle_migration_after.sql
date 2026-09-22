DO $$
DECLARE
    failed boolean;
BEGIN
    IF (SELECT status FROM org_units WHERE code='INACTIVE') <> 'inactive'
       OR (SELECT status FROM roles WHERE code='INACTIVE') <> 'inactive' THEN
        RAISE EXCEPTION 'inactive organization lifecycle was not preserved';
    END IF;
    IF (SELECT status FROM users WHERE name='Suspended Person') <> 'suspended'
       OR (SELECT date_suspended FROM users WHERE name='Suspended Person') IS NULL
       OR (SELECT date_deactivated FROM users WHERE name='Suspended Person') IS NOT NULL THEN
        RAISE EXCEPTION 'suspended user was not migrated to date_suspended';
    END IF;
    IF (SELECT count(*) FROM pg_attribute
         WHERE attrelid IN ('org_units'::regclass, 'users'::regclass, 'roles'::regclass)
           AND attname='status' AND attgenerated='s') <> 3 THEN
        RAISE EXCEPTION 'status columns are not generated projections';
    END IF;

    failed := false;
    BEGIN
        UPDATE users SET status='active' WHERE name='Suspended Person';
    EXCEPTION WHEN generated_always THEN
        failed := true;
    END;
    IF NOT failed THEN
        RAISE EXCEPTION 'generated user status unexpectedly accepted a direct write';
    END IF;

    failed := false;
    BEGIN
        UPDATE users SET date_deactivated=clock_timestamp(), date_suspended=clock_timestamp()
         WHERE name='Active Person';
    EXCEPTION WHEN check_violation THEN
        failed := true;
    END;
    IF NOT failed THEN
        RAISE EXCEPTION 'user deactivation and suspension were allowed simultaneously';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM event_history
         WHERE operation='LIFECYCLE_STORAGE_NORMALIZED'
           AND source='migration'
           AND entity_id=(SELECT id FROM users WHERE name='Suspended Person')
    ) THEN
        RAISE EXCEPTION 'suspension migration provenance event is missing';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM schema_migrations
         WHERE version='004_normalize_user_management_lifecycle'
    ) THEN
        RAISE EXCEPTION 'migration version was not recorded';
    END IF;
END;
$$;
