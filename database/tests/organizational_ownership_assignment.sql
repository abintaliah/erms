BEGIN;

DO $$
DECLARE
    expected_unit_id bigint;
    expected_role_id bigint;
    run_record organizational_ownership_assignment_runs%ROWTYPE;
BEGIN
    SELECT id INTO STRICT expected_unit_id
    FROM org_units WHERE code = 'PHASE2-SEGMENT';
    SELECT id INTO STRICT expected_role_id
    FROM roles WHERE code = 'phase2-segment-curator';

    IF EXISTS (SELECT 1 FROM organizational_ownership_diagnostics) THEN
        RAISE EXCEPTION 'Phase 2 left missing or inconsistent ownership';
    END IF;

    IF (SELECT count(*) FROM aggregations WHERE owning_org_unit_id = expected_unit_id) <> 2
       OR (SELECT count(*) FROM records WHERE owning_org_unit_id = expected_unit_id) <> 2 THEN
        RAISE EXCEPTION 'Phase 2 did not propagate the root owner through the fixture hierarchy';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM organizational_ownership_root_assignments assignment
        JOIN aggregations root ON root.id = assignment.root_aggregation_id
        WHERE root.aggregation_number = 'SEG-MIG-AGG'
          AND assignment.selected_role_id = expected_role_id
          AND assignment.selected_role_code = 'phase2-segment-curator'
          AND assignment.selected_role_name = 'Segment Migration Curator'
          AND assignment.owning_org_unit_id = expected_unit_id
          AND assignment.owning_org_unit_code = 'PHASE2-SEGMENT'
          AND assignment.owning_org_unit_name = 'Segment Operations'
          AND assignment.match_score > 0
          AND assignment.assignment_method = 'text_match'
          AND assignment.root_title = 'Segment migration fixture'
    ) THEN
        RAISE EXCEPTION 'Phase 2 did not retain the expected scored root-role mapping';
    END IF;

    SELECT * INTO STRICT run_record
    FROM organizational_ownership_assignment_runs
    WHERE migration_version = '045_assign_existing_organizational_ownership';

    IF run_record.completed_at IS NULL
       OR run_record.root_count <> 1
       OR run_record.aggregation_count <> 2
       OR run_record.record_count <> 2
       OR run_record.before_counts_by_unit #>> '{unassigned,aggregations}' <> '2'
       OR run_record.before_counts_by_unit #>> '{unassigned,records}' <> '2'
       OR run_record.after_counts_by_unit #>> ARRAY[expected_unit_id::text, 'aggregations'] <> '2'
       OR run_record.after_counts_by_unit #>> ARRAY[expected_unit_id::text, 'records'] <> '2' THEN
        RAISE EXCEPTION 'Phase 2 reconciliation report is incomplete or incorrect';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM schema_migrations
        WHERE version = '045_assign_existing_organizational_ownership'
    ) THEN
        RAISE EXCEPTION 'Phase 2 migration is not recorded';
    END IF;
END;
$$;

DELETE FROM organizational_ownership_root_assignments;
DELETE FROM organizational_ownership_assignment_runs;
DELETE FROM records WHERE record_number = 'SEG-MIG-CHILD-REC';
DELETE FROM aggregations WHERE aggregation_number = 'SEG-MIG-CHILD';
DELETE FROM roles WHERE code IN ('phase2-segment-curator', 'phase2-other-curator');

COMMIT;
