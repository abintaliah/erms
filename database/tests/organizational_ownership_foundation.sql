BEGIN;

DO $$
DECLARE
    test_org_unit_id bigint;
    snapshot jsonb;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'aggregations'
          AND column_name = 'owning_org_unit_id'
          AND data_type = 'bigint'
          AND is_nullable = 'YES'
    ) THEN
        RAISE EXCEPTION 'aggregations.owning_org_unit_id is missing or not nullable bigint';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'records'
          AND column_name = 'owning_org_unit_id'
          AND data_type = 'bigint'
          AND is_nullable = 'YES'
    ) THEN
        RAISE EXCEPTION 'records.owning_org_unit_id is missing or not nullable bigint';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'aggregations_owning_org_unit_fk'
          AND confdeltype = 'r'
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'records_owning_org_unit_fk'
          AND confdeltype = 'r'
    ) THEN
        RAISE EXCEPTION 'organizational ownership foreign keys are missing or not restrictive';
    END IF;

    IF to_regclass('public.aggregations_owner_parent_number_browse_idx') IS NULL
       OR to_regclass('public.records_owner_aggregation_number_browse_idx') IS NULL THEN
        RAISE EXCEPTION 'organizational ownership browse indexes are missing';
    END IF;

    IF to_regclass('public.organizational_ownership_diagnostics') IS NULL THEN
        RAISE EXCEPTION 'organizational ownership diagnostics view is missing';
    END IF;

    PERFORM count(*) FROM organizational_ownership_diagnostics;

    IF pg_get_viewdef('organizational_ownership_diagnostics'::regclass, true)
       NOT LIKE '%missing_owner%'
       OR pg_get_viewdef('organizational_ownership_diagnostics'::regclass, true)
          NOT LIKE '%owner_mismatch%' THEN
        RAISE EXCEPTION 'organizational ownership diagnostics do not cover missing and inconsistent owners';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM schema_migrations
        WHERE version = '044_add_organizational_ownership_foundation'
    ) THEN
        RAISE EXCEPTION 'organizational ownership migration is not recorded';
    END IF;

    INSERT INTO org_units (code, name)
    VALUES ('OWNERSHIP-FOUNDATION-TEST', 'Ownership Foundation Test')
    RETURNING id INTO test_org_unit_id;

    snapshot := event_state_reference_snapshots(
        jsonb_build_object('owning_org_unit_id', test_org_unit_id)
    );
    IF snapshot #>> '{owning_org_unit_id,code}' <> 'OWNERSHIP-FOUNDATION-TEST'
       OR snapshot #>> '{owning_org_unit_id,name}' <> 'Ownership Foundation Test' THEN
        RAISE EXCEPTION 'owning organization unit reference snapshot is incorrect';
    END IF;
END;
$$;

ROLLBACK;
