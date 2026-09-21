BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Database migration 044', true),
       set_config('app.event_source', 'migration', true),
       set_config('app.change_reason', 'Add the organizational ownership schema foundation', true),
       set_config('app.event_metadata', '{"migration":"044_add_organizational_ownership_foundation"}', true);

ALTER TABLE aggregations
    ADD COLUMN owning_org_unit_id bigint,
    ADD CONSTRAINT aggregations_owning_org_unit_fk
        FOREIGN KEY (owning_org_unit_id) REFERENCES org_units (id) ON DELETE RESTRICT;

ALTER TABLE records
    ADD COLUMN owning_org_unit_id bigint,
    ADD CONSTRAINT records_owning_org_unit_fk
        FOREIGN KEY (owning_org_unit_id) REFERENCES org_units (id) ON DELETE RESTRICT;

CREATE INDEX aggregations_owner_parent_number_browse_idx
    ON aggregations (
        owning_org_unit_id,
        parent_aggregation_id,
        aggregation_number COLLATE "C",
        id
    );

CREATE INDEX records_owner_aggregation_number_browse_idx
    ON records (
        owning_org_unit_id,
        aggregation_id,
        record_number COLLATE "C",
        id
    );

CREATE VIEW organizational_ownership_diagnostics AS
SELECT
    'aggregation'::text AS resource_type,
    child.id AS resource_id,
    child.parent_aggregation_id AS parent_resource_id,
    child.owning_org_unit_id,
    parent.owning_org_unit_id AS expected_owning_org_unit_id,
    CASE WHEN child.owning_org_unit_id IS NULL THEN 'missing_owner' ELSE 'owner_mismatch' END AS issue
FROM aggregations AS child
LEFT JOIN aggregations AS parent ON parent.id = child.parent_aggregation_id
WHERE child.owning_org_unit_id IS NULL
   OR (child.parent_aggregation_id IS NOT NULL
       AND child.owning_org_unit_id IS DISTINCT FROM parent.owning_org_unit_id)
UNION ALL
SELECT
    'record'::text,
    record.id,
    record.aggregation_id,
    record.owning_org_unit_id,
    parent.owning_org_unit_id,
    CASE WHEN record.owning_org_unit_id IS NULL THEN 'missing_owner' ELSE 'owner_mismatch' END
FROM records AS record
JOIN aggregations AS parent ON parent.id = record.aggregation_id
WHERE record.owning_org_unit_id IS NULL
   OR record.owning_org_unit_id IS DISTINCT FROM parent.owning_org_unit_id;

CREATE OR REPLACE FUNCTION event_reference_identity(reference_field text, reference_id bigint)
RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE snapshot jsonb;
BEGIN
    CASE reference_field
        WHEN 'profile_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM profiles WHERE id=reference_id;
        WHEN 'old_profile_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM profiles WHERE id=reference_id;
        WHEN 'new_profile_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM profiles WHERE id=reference_id;
        WHEN 'security_level_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name,'level_number',level_number) INTO snapshot FROM security_levels WHERE id=reference_id;
        WHEN 'classification_id' THEN SELECT jsonb_build_object('id',id,'code',code,'title',title) INTO snapshot FROM classifications WHERE id=reference_id;
        WHEN 'parent_classification_id' THEN SELECT jsonb_build_object('id',id,'code',code,'title',title) INTO snapshot FROM classifications WHERE id=reference_id;
        WHEN 'classification_scheme_id' THEN SELECT jsonb_build_object('id',id,'code',code,'title',title) INTO snapshot FROM classification_schemes WHERE id=reference_id;
        WHEN 'aggregation_id' THEN SELECT jsonb_build_object('id',id,'code',aggregation_number,'title',title) INTO snapshot FROM aggregations WHERE id=reference_id;
        WHEN 'parent_aggregation_id' THEN SELECT jsonb_build_object('id',id,'code',aggregation_number,'title',title) INTO snapshot FROM aggregations WHERE id=reference_id;
        WHEN 'destination_aggregation_id' THEN SELECT jsonb_build_object('id',id,'code',aggregation_number,'title',title) INTO snapshot FROM aggregations WHERE id=reference_id;
        WHEN 'record_id' THEN SELECT jsonb_build_object('id',id,'code',record_number,'title',title) INTO snapshot FROM records WHERE id=reference_id;
        WHEN 'role_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM roles WHERE id=reference_id;
        WHEN 'supervisor_role_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM roles WHERE id=reference_id;
        WHEN 'user_id' THEN SELECT jsonb_build_object('id',id,'name',name,'email',email) INTO snapshot FROM users WHERE id=reference_id;
        WHEN 'owner_user_id' THEN SELECT jsonb_build_object('id',id,'name',name,'email',email) INTO snapshot FROM users WHERE id=reference_id;
        WHEN 'org_unit_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM org_units WHERE id=reference_id;
        WHEN 'parent_org_unit_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM org_units WHERE id=reference_id;
        WHEN 'owning_org_unit_id' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM org_units WHERE id=reference_id;
        ELSE snapshot := NULL;
    END CASE;
    RETURN snapshot;
END;
$$;

CREATE OR REPLACE FUNCTION event_state_reference_snapshots(event_state jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE reference_field text; reference_value text; snapshot jsonb; snapshots jsonb := '{}'::jsonb;
BEGIN
    IF event_state IS NULL OR jsonb_typeof(event_state) <> 'object' THEN RETURN snapshots; END IF;
    FOREACH reference_field IN ARRAY ARRAY[
        'profile_id','old_profile_id','new_profile_id','security_level_id',
        'classification_id','parent_classification_id','classification_scheme_id',
        'aggregation_id','parent_aggregation_id','destination_aggregation_id',
        'record_id','role_id','supervisor_role_id','user_id','owner_user_id',
        'org_unit_id','parent_org_unit_id','owning_org_unit_id'
    ] LOOP
        reference_value := event_state ->> reference_field;
        IF reference_value IS NOT NULL AND reference_value ~ '^[0-9]+$' THEN
            snapshot := event_reference_identity(reference_field,reference_value::bigint);
            IF snapshot IS NOT NULL THEN snapshots := snapshots || jsonb_build_object(reference_field,snapshot); END IF;
        END IF;
    END LOOP;
    RETURN snapshots;
END;
$$;

INSERT INTO schema_migrations(version)
VALUES ('044_add_organizational_ownership_foundation');

COMMIT;
