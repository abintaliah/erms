BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Phase 2 ownership test fixture', true),
       set_config('app.event_source', 'test', true),
       set_config('app.change_reason', 'Prepare deterministic ownership assignment fixture', true);

INSERT INTO org_units(code, name, description)
VALUES
    ('PHASE2-SEGMENT', 'Segment Operations', 'Maintains segment migration holdings'),
    ('PHASE2-OTHER', 'Other Operations', 'Unrelated operational unit');

INSERT INTO roles(org_unit_id, code, name, description)
SELECT id, 'phase2-segment-curator', 'Segment Migration Curator',
       'Responsible for segment migration records'
FROM org_units WHERE code = 'PHASE2-SEGMENT';
INSERT INTO roles(org_unit_id, code, name, description)
SELECT id, 'phase2-other-curator', 'Other Curator', 'Responsible for unrelated records'
FROM org_units WHERE code = 'PHASE2-OTHER';

INSERT INTO aggregations(parent_aggregation_id, aggregation_number, title)
SELECT id, 'SEG-MIG-CHILD', 'Segment migration child'
FROM aggregations WHERE aggregation_number = 'SEG-MIG-AGG';

INSERT INTO records(aggregation_id, record_number, title)
SELECT id, 'SEG-MIG-CHILD-REC', 'Segment migration child record'
FROM aggregations WHERE aggregation_number = 'SEG-MIG-CHILD';

COMMIT;
