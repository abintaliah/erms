BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Phase 3 ownership test', true),
       set_config('app.event_source', 'test', true);

INSERT INTO org_units(code,name) VALUES
('PHASE2-SEGMENT','Phase 2 Segment'),
('PHASE2-OTHER','Phase 2 Other');

INSERT INTO classification_schemes(code, title, date_published)
VALUES ('OWN-P3', 'Ownership Phase 3', CURRENT_TIMESTAMP);
INSERT INTO classifications(classification_scheme_id, code, title, is_terminal)
SELECT id, 'OWN-P3-01', 'Ownership Phase 3 destination', false
FROM classification_schemes WHERE code='OWN-P3';
INSERT INTO classification_retention_rules(
    classification_id, current_period_years, intermediate_period_years, final_disposition
)
SELECT id, 1, 0, 'destruction' FROM classifications WHERE code='OWN-P3-01';
UPDATE classifications SET is_terminal=true WHERE code='OWN-P3-01';

INSERT INTO aggregations(aggregation_number,title,classification_id,owning_org_unit_id)
SELECT 'SEG-MIG-AGG','Ownership source',classification.id,unit.id
FROM classifications classification CROSS JOIN org_units unit
WHERE classification.code='OWN-P3-01' AND unit.code='PHASE2-SEGMENT';

INSERT INTO aggregations(
    aggregation_number, title, classification_id, owning_org_unit_id
)
SELECT 'OWN-P3-DEST', 'Ownership destination', classification.id, unit.id
FROM classifications classification CROSS JOIN org_units unit
WHERE classification.code='OWN-P3-01' AND unit.code='PHASE2-OTHER';

INSERT INTO aggregations(parent_aggregation_id, aggregation_number, title, owning_org_unit_id)
SELECT source.id, 'OWN-P3-CHILD', 'Ownership child', wrong_unit.id
FROM aggregations source CROSS JOIN org_units wrong_unit
WHERE source.aggregation_number='SEG-MIG-AGG' AND wrong_unit.code='PHASE2-OTHER';
INSERT INTO aggregations(parent_aggregation_id, aggregation_number, title)
SELECT id, 'OWN-P3-GRANDCHILD', 'Ownership grandchild'
FROM aggregations WHERE aggregation_number='OWN-P3-CHILD';
INSERT INTO records(aggregation_id, record_number, title)
SELECT id, 'OWN-P3-SUBTREE-REC', 'Ownership subtree record'
FROM aggregations WHERE aggregation_number='OWN-P3-GRANDCHILD';
INSERT INTO records(aggregation_id, record_number, title)
SELECT id, 'OWN-P3-DIRECT-REC', 'Ownership direct record'
FROM aggregations WHERE aggregation_number='SEG-MIG-AGG';

DO $$
DECLARE
    source_unit bigint;
    destination_unit bigint;
    child_id bigint;
    destination_id bigint;
    direct_record_id bigint;
    rejected boolean;
BEGIN
    SELECT id INTO STRICT source_unit FROM org_units WHERE code='PHASE2-SEGMENT';
    SELECT id INTO STRICT destination_unit FROM org_units WHERE code='PHASE2-OTHER';
    SELECT id INTO STRICT child_id FROM aggregations WHERE aggregation_number='OWN-P3-CHILD';
    SELECT id INTO STRICT destination_id FROM aggregations WHERE aggregation_number='OWN-P3-DEST';
    SELECT id INTO STRICT direct_record_id FROM records WHERE record_number='OWN-P3-DIRECT-REC';

    IF EXISTS (
        SELECT 1 FROM aggregations
        WHERE aggregation_number IN ('OWN-P3-CHILD','OWN-P3-GRANDCHILD')
          AND owning_org_unit_id <> source_unit
    ) OR EXISTS (
        SELECT 1 FROM records WHERE record_number LIKE 'OWN-P3-%' AND owning_org_unit_id <> source_unit
    ) THEN
        RAISE EXCEPTION 'child or record ownership was not derived from its parent';
    END IF;

    rejected := false;
    BEGIN
        UPDATE aggregations SET owning_org_unit_id=destination_unit WHERE id=child_id;
    EXCEPTION WHEN SQLSTATE 'P0001' THEN rejected := true;
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'direct aggregation owner update unexpectedly succeeded'; END IF;

    rejected := false;
    BEGIN
        UPDATE aggregations SET parent_aggregation_id=destination_id WHERE id=child_id;
    EXCEPTION WHEN SQLSTATE 'P0001' THEN rejected := true;
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'unconfirmed ownership-changing aggregation move unexpectedly succeeded'; END IF;
    IF (SELECT parent_aggregation_id FROM aggregations WHERE id=child_id) = destination_id THEN
        RAISE EXCEPTION 'failed aggregation move did not roll back';
    END IF;

    PERFORM set_config('app.change_reason', 'Confirmed Phase 3 subtree move', true),
            set_config('app.ownership_move_confirmed', 'true', true);
    UPDATE aggregations SET parent_aggregation_id=destination_id WHERE id=child_id;
    IF EXISTS (
        SELECT 1 FROM aggregations
        WHERE aggregation_number IN ('OWN-P3-CHILD','OWN-P3-GRANDCHILD')
          AND owning_org_unit_id <> destination_unit
    ) OR EXISTS (
        SELECT 1 FROM records WHERE record_number='OWN-P3-SUBTREE-REC'
          AND owning_org_unit_id <> destination_unit
    ) THEN
        RAISE EXCEPTION 'aggregation subtree ownership was not propagated atomically';
    END IF;

    PERFORM set_config('app.change_reason', '', true),
            set_config('app.ownership_move_confirmed', 'false', true);
    rejected := false;
    BEGIN
        UPDATE records SET aggregation_id=destination_id WHERE id=direct_record_id;
    EXCEPTION WHEN SQLSTATE 'P0001' THEN rejected := true;
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'unconfirmed ownership-changing record move unexpectedly succeeded'; END IF;
    PERFORM set_config('app.change_reason', 'Confirmed Phase 3 record move', true),
            set_config('app.ownership_move_confirmed', 'true', true);
    UPDATE records SET aggregation_id=destination_id WHERE id=direct_record_id;
    IF (SELECT owning_org_unit_id FROM records WHERE id=direct_record_id) <> destination_unit THEN
        RAISE EXCEPTION 'record ownership did not follow its destination aggregation';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM event_history
        WHERE entity_type='aggregation' AND entity_id=child_id
          AND operation='UPDATE' AND 'owning_org_unit_id'=ANY(changed_fields)
          AND reason='Confirmed Phase 3 subtree move'
    ) OR NOT EXISTS (
        SELECT 1 FROM event_history
        WHERE entity_type='record' AND entity_id=direct_record_id
          AND operation='UPDATE' AND 'owning_org_unit_id'=ANY(changed_fields)
          AND reason='Confirmed Phase 3 record move'
    ) THEN
        RAISE EXCEPTION 'ownership-changing moves were not recorded in immutable history';
    END IF;
END;
$$;

ROLLBACK;
