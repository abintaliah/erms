BEGIN;

DELETE FROM profile_privileges mapping
USING profiles profile, privileges privilege
WHERE mapping.profile_id=profile.id AND mapping.privilege_id=privilege.id
  AND profile.code IN ('INFO_GOV_MGR','INFO_GOV_OFFICER')
  AND privilege.code='holds.administer';

CREATE OR REPLACE FUNCTION prevent_nonempty_hold_deletion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM hold_aggregation_assignments WHERE hold_id=OLD.id)
       OR EXISTS (SELECT 1 FROM hold_record_assignments WHERE hold_id=OLD.id) THEN
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_not_empty';
    END IF;
    RETURN OLD;
END;
$$;
DROP TRIGGER IF EXISTS holds_prevent_nonempty_deletion ON holds;
CREATE TRIGGER holds_prevent_nonempty_deletion
BEFORE DELETE ON holds FOR EACH ROW EXECUTE FUNCTION prevent_nonempty_hold_deletion();

CREATE OR REPLACE FUNCTION protect_held_component_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE component_id bigint;
DECLARE held_record_id bigint;
DECLARE failure_code text;
BEGIN
    PERFORM lock_hold_policy_shared();
    IF TG_TABLE_NAME='digital_components' THEN
        held_record_id:=CASE WHEN TG_OP='DELETE' THEN OLD.record_id ELSE NEW.record_id END;
    ELSIF TG_TABLE_NAME='digital_component_content_sets' THEN
        component_id:=CASE WHEN TG_OP='DELETE' THEN OLD.digital_component_id ELSE NEW.digital_component_id END;
        SELECT record_id INTO held_record_id FROM digital_components WHERE id=component_id;
    ELSIF TG_TABLE_NAME='digital_component_blobs' THEN
        SELECT component.digital_component_id INTO component_id
        FROM digital_component_content_sets component
        WHERE component.id=CASE WHEN TG_OP='DELETE' THEN OLD.content_set_id ELSE NEW.content_set_id END;
        SELECT record_id INTO held_record_id FROM digital_components WHERE id=component_id;
    ELSE
        component_id:=CASE WHEN TG_OP='DELETE' THEN OLD.digital_component_id ELSE NEW.digital_component_id END;
        IF component_id IS NOT NULL THEN SELECT record_id INTO held_record_id FROM digital_components WHERE id=component_id; END IF;
    END IF;
    IF held_record_id IS NOT NULL AND resource_has_effective_hold('record',held_record_id) THEN
        failure_code:=CASE TG_OP WHEN 'INSERT' THEN 'effective_hold_prevents_component_addition'
          WHEN 'DELETE' THEN 'effective_hold_prevents_component_deletion'
          ELSE 'effective_hold_prevents_component_replacement' END;
        IF TG_TABLE_NAME='digital_components' AND TG_OP='UPDATE'
           AND NEW.component_order IS DISTINCT FROM OLD.component_order THEN
            failure_code:='effective_hold_prevents_component_reordering';
        END IF;
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE=failure_code;
    END IF;
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE OR REPLACE FUNCTION append_hold_definition_domain_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE entity_id bigint:=CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;
DECLARE operation_name text:=CASE TG_OP WHEN 'INSERT' THEN 'HOLD_CREATED' WHEN 'UPDATE' THEN 'HOLD_UPDATED' ELSE 'HOLD_DELETED' END;
DECLARE old_state jsonb:=CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) ELSE NULL END;
DECLARE new_state jsonb:=CASE WHEN TG_OP IN ('INSERT','UPDATE') THEN to_jsonb(NEW) ELSE NULL END;
BEGIN
    IF TG_OP='INSERT' THEN
        new_state:=new_state||jsonb_build_object(
            'contributor_user_ids',COALESCE(NULLIF(current_setting('app.hold_contributor_ids',true),'')::jsonb,'[]'::jsonb));
    END IF;
    PERFORM append_domain_event('hold',entity_id,operation_name,
        jsonb_strip_nulls(jsonb_build_object('before',old_state,'after',new_state)));
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE OR REPLACE FUNCTION append_hold_assignment_domain_events() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE state record;
DECLARE operation_name text:=CASE WHEN TG_OP='INSERT' THEN 'RESOURCE_ADDED_TO_HOLD' ELSE 'RESOURCE_REMOVED_FROM_HOLD' END;
DECLARE resource_type text:=CASE WHEN TG_TABLE_NAME='hold_aggregation_assignments' THEN 'aggregation' ELSE 'record' END;
DECLARE resource_id bigint;
DECLARE metadata jsonb;
BEGIN
    IF TG_OP='UPDATE' THEN RETURN NEW; END IF;
    IF TG_OP='DELETE' THEN state:=OLD; ELSE state:=NEW; END IF;
    IF resource_type='aggregation' THEN resource_id:=state.aggregation_id; ELSE resource_id:=state.record_id; END IF;
    metadata:=jsonb_build_object('hold_id',state.hold_id,'resource_type',resource_type,
                                 'resource_id',resource_id,'assignment_id',state.id);
    IF TG_OP='DELETE' THEN
        IF resource_type='aggregation' THEN
            metadata:=metadata||jsonb_build_object('remaining_effective_hold_ids',COALESCE((SELECT jsonb_agg(hold_id ORDER BY hold_id) FROM effective_holds_for_aggregation(resource_id)),'[]'::jsonb));
        ELSE
            metadata:=metadata||jsonb_build_object('remaining_effective_hold_ids',COALESCE((SELECT jsonb_agg(hold_id ORDER BY hold_id) FROM effective_holds_for_record(resource_id)),'[]'::jsonb));
        END IF;
    END IF;
    PERFORM append_domain_event('hold',state.hold_id,operation_name,metadata);
    PERFORM append_domain_event(resource_type,resource_id,operation_name,metadata);
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE OR REPLACE VIEW authorized_aggregations_for_search AS
SELECT resource.id,
       CASE WHEN resource.parent_aggregation_id IS NULL OR current_user_can_view_aggregation(resource.parent_aggregation_id)
            THEN resource.parent_aggregation_id END AS parent_aggregation_id,
       resource.classification_id,resource.aggregation_number,resource.title,resource.description,
       resource.date_created,resource.date_opened,resource.date_closed,resource.security_level_id,
       resource.inherit_acl_from_parent,resource.default_child_aggregation_acl_mode,
       resource.resource_acl_version,resource.child_aggregation_acl_version,resource.child_record_acl_version,
       resource.version,resource.owning_org_unit_id,resource.medium,resource.is_vital,
       resource.date_of_next_review,resource.assigned_location,resource.current_location,
       aggregation_effective_assigned_location(resource.id) AS effective_assigned_location,
       aggregation_effective_current_location(resource.id) AS effective_current_location,
       CASE WHEN current_user_can_view_aggregation(aggregation_effective_assigned_location_source_id(resource.id)) THEN aggregation_effective_assigned_location_source_id(resource.id) END AS effective_assigned_location_source_aggregation_id,
       CASE WHEN current_user_can_view_aggregation(aggregation_effective_current_location_source_id(resource.id)) THEN aggregation_effective_current_location_source_id(resource.id) END AS effective_current_location_source_aggregation_id,
       hold_state.effective_hold_count > 0 AS on_effective_hold,
       hold_state.resource_state_changes_blocked,hold_state.effective_hold_ids
FROM aggregations resource
CROSS JOIN LATERAL (
    SELECT count(*)::integer effective_hold_count,
           COALESCE(bool_or(effective.preserve_resource_state),false) resource_state_changes_blocked,
           COALESCE(array_agg(effective.hold_id ORDER BY effective.hold_id),'{}'::bigint[]) effective_hold_ids
    FROM effective_holds_for_aggregation(resource.id) effective
) hold_state;

CREATE OR REPLACE VIEW authorized_records_for_search AS
SELECT resource.id,
       CASE WHEN current_user_can_view_aggregation(resource.aggregation_id) THEN resource.aggregation_id END AS aggregation_id,
       resource.record_number,resource.title,resource.description,resource.date_created,resource.date_originated,
       resource.security_level_id,resource.inherit_acl_from_parent,resource.resource_acl_version,resource.version,
       resource.owning_org_unit_id,resource.medium,resource.is_vital,resource.date_of_next_review,
       aggregation_effective_assigned_location(resource.aggregation_id) AS effective_assigned_location,
       aggregation_effective_current_location(resource.aggregation_id) AS effective_current_location,
       CASE WHEN current_user_can_view_aggregation(aggregation_effective_assigned_location_source_id(resource.aggregation_id)) THEN aggregation_effective_assigned_location_source_id(resource.aggregation_id) END AS effective_assigned_location_source_aggregation_id,
       CASE WHEN current_user_can_view_aggregation(aggregation_effective_current_location_source_id(resource.aggregation_id)) THEN aggregation_effective_current_location_source_id(resource.aggregation_id) END AS effective_current_location_source_aggregation_id,
       hold_state.effective_hold_count > 0 AS on_effective_hold,
       hold_state.resource_state_changes_blocked,hold_state.effective_hold_ids
FROM records resource
CROSS JOIN LATERAL (
    SELECT count(*)::integer effective_hold_count,
           COALESCE(bool_or(effective.preserve_resource_state),false) resource_state_changes_blocked,
           COALESCE(array_agg(effective.hold_id ORDER BY effective.hold_id),'{}'::bigint[]) effective_hold_ids
    FROM effective_holds_for_record(resource.id) effective
) hold_state;

INSERT INTO schema_migrations(version)
VALUES ('006_correct_legal_hold_authorization')
ON CONFLICT (version) DO NOTHING;

COMMIT;
