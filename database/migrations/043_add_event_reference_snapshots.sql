BEGIN;

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
        'org_unit_id','parent_org_unit_id'
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

CREATE OR REPLACE FUNCTION event_entity_identity_snapshot(event_entity_type text,event_entity_id bigint)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE snapshot jsonb;
BEGIN
    CASE event_entity_type
        WHEN 'aggregation' THEN SELECT jsonb_build_object('id',id,'code',aggregation_number,'title',title) INTO snapshot FROM aggregations WHERE id=event_entity_id;
        WHEN 'record' THEN SELECT jsonb_build_object('id',id,'code',record_number,'title',title) INTO snapshot FROM records WHERE id=event_entity_id;
        WHEN 'digital_component' THEN SELECT jsonb_build_object('id',id,'name',file_name) INTO snapshot FROM digital_components WHERE id=event_entity_id;
        WHEN 'classification_scheme' THEN SELECT jsonb_build_object('id',id,'code',code,'title',title) INTO snapshot FROM classification_schemes WHERE id=event_entity_id;
        WHEN 'classification' THEN SELECT jsonb_build_object('id',id,'code',code,'title',title) INTO snapshot FROM classifications WHERE id=event_entity_id;
        WHEN 'org_unit' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM org_units WHERE id=event_entity_id;
        WHEN 'role' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM roles WHERE id=event_entity_id;
        WHEN 'user' THEN SELECT jsonb_build_object('id',id,'name',name,'email',email) INTO snapshot FROM users WHERE id=event_entity_id;
        WHEN 'profile' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot FROM profiles WHERE id=event_entity_id;
        WHEN 'security_level' THEN SELECT jsonb_build_object('id',id,'code',code,'name',name,'level_number',level_number) INTO snapshot FROM security_levels WHERE id=event_entity_id;
        ELSE snapshot := NULL;
    END CASE;
    RETURN snapshot;
END;
$$;

CREATE OR REPLACE FUNCTION populate_event_reference_snapshots()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE snapshots jsonb := '{}'::jsonb; state_snapshot jsonb;
BEGIN
    state_snapshot := event_state_reference_snapshots(NEW.before_state);
    IF state_snapshot <> '{}'::jsonb THEN snapshots := snapshots || jsonb_build_object('before',state_snapshot); END IF;
    state_snapshot := event_state_reference_snapshots(NEW.after_state);
    IF state_snapshot <> '{}'::jsonb THEN snapshots := snapshots || jsonb_build_object('after',state_snapshot); END IF;
    state_snapshot := event_state_reference_snapshots(NEW.metadata);
    IF state_snapshot <> '{}'::jsonb THEN snapshots := snapshots || jsonb_build_object('metadata',state_snapshot); END IF;
    state_snapshot := event_entity_identity_snapshot(NEW.entity_type,NEW.entity_id);
    IF state_snapshot IS NOT NULL THEN snapshots := snapshots || jsonb_build_object('entity',state_snapshot); END IF;
    IF snapshots <> '{}'::jsonb THEN NEW.metadata := NEW.metadata || jsonb_build_object('reference_snapshots',snapshots); END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS event_history_populate_reference_snapshots ON event_history;
CREATE TRIGGER event_history_populate_reference_snapshots
BEFORE INSERT ON event_history
FOR EACH ROW EXECUTE FUNCTION populate_event_reference_snapshots();

INSERT INTO schema_migrations(version)
VALUES ('043_add_event_reference_snapshots')
ON CONFLICT (version) DO NOTHING;

COMMIT;
