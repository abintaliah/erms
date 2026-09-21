BEGIN;

CREATE OR REPLACE FUNCTION aggregation_effective_assigned_location_source_id(p_aggregation_id bigint)
RETURNS bigint LANGUAGE sql STABLE AS $$
 WITH RECURSIVE ancestors AS (
  SELECT id,parent_aggregation_id,assigned_location,0 depth FROM aggregations WHERE id=p_aggregation_id
  UNION ALL SELECT p.id,p.parent_aggregation_id,p.assigned_location,a.depth+1 FROM ancestors a JOIN aggregations p ON p.id=a.parent_aggregation_id)
 SELECT id FROM ancestors WHERE assigned_location IS NOT NULL ORDER BY depth LIMIT 1
$$;
CREATE OR REPLACE FUNCTION aggregation_effective_current_location_source_id(p_aggregation_id bigint)
RETURNS bigint LANGUAGE sql STABLE AS $$
 WITH RECURSIVE ancestors AS (
  SELECT id,parent_aggregation_id,current_location,0 depth FROM aggregations WHERE id=p_aggregation_id
  UNION ALL SELECT p.id,p.parent_aggregation_id,p.current_location,a.depth+1 FROM ancestors a JOIN aggregations p ON p.id=a.parent_aggregation_id)
 SELECT id FROM ancestors WHERE current_location IS NOT NULL ORDER BY depth LIMIT 1
$$;

CREATE OR REPLACE VIEW authorized_aggregations_for_search AS
SELECT resource.id,CASE WHEN resource.parent_aggregation_id IS NULL OR current_user_can_view_aggregation(resource.parent_aggregation_id) THEN resource.parent_aggregation_id END parent_aggregation_id,
 resource.classification_id,resource.aggregation_number,resource.title,resource.description,resource.date_created,resource.date_opened,resource.date_closed,
 resource.security_level_id,resource.inherit_acl_from_parent,resource.default_child_aggregation_acl_mode,resource.resource_acl_version,resource.child_aggregation_acl_version,resource.child_record_acl_version,resource.version,
 resource.owning_org_unit_id,resource.medium,resource.is_vital,resource.date_of_next_review,resource.assigned_location,resource.current_location,
 aggregation_effective_assigned_location(resource.id) effective_assigned_location,aggregation_effective_current_location(resource.id) effective_current_location,
 CASE WHEN current_user_can_view_aggregation(aggregation_effective_assigned_location_source_id(resource.id)) THEN aggregation_effective_assigned_location_source_id(resource.id) END effective_assigned_location_source_aggregation_id,
 CASE WHEN current_user_can_view_aggregation(aggregation_effective_current_location_source_id(resource.id)) THEN aggregation_effective_current_location_source_id(resource.id) END effective_current_location_source_aggregation_id
FROM aggregations resource;
CREATE OR REPLACE VIEW authorized_records_for_search AS
SELECT resource.id,CASE WHEN current_user_can_view_aggregation(resource.aggregation_id) THEN resource.aggregation_id END aggregation_id,
 resource.record_number,resource.title,resource.description,resource.date_created,resource.date_originated,resource.security_level_id,resource.inherit_acl_from_parent,resource.resource_acl_version,resource.version,resource.owning_org_unit_id,
 resource.medium,resource.is_vital,resource.date_of_next_review,
 aggregation_effective_assigned_location(resource.aggregation_id) effective_assigned_location,aggregation_effective_current_location(resource.aggregation_id) effective_current_location,
 CASE WHEN current_user_can_view_aggregation(aggregation_effective_assigned_location_source_id(resource.aggregation_id)) THEN aggregation_effective_assigned_location_source_id(resource.aggregation_id) END effective_assigned_location_source_aggregation_id,
 CASE WHEN current_user_can_view_aggregation(aggregation_effective_current_location_source_id(resource.aggregation_id)) THEN aggregation_effective_current_location_source_id(resource.aggregation_id) END effective_current_location_source_aggregation_id
FROM records resource;

CREATE OR REPLACE FUNCTION record_entity_history() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE old_state jsonb; new_state jsonb; entity_key bigint; changed text[]; context_user_id text; context_metadata text;
BEGIN
 IF TG_OP='UPDATE' AND current_setting('app.suppress_ordinary_history',true)='authorized' THEN RETURN NEW; END IF;
 old_state:=CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) END;
 new_state:=CASE WHEN TG_OP IN ('INSERT','UPDATE') THEN to_jsonb(NEW) END;
 entity_key:=CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;
 SELECT coalesce(array_agg(key ORDER BY key),ARRAY[]::text[]) INTO changed FROM (
  SELECT key FROM jsonb_object_keys(coalesce(old_state,'{}'::jsonb)||coalesce(new_state,'{}'::jsonb)) key
  WHERE old_state->key IS DISTINCT FROM new_state->key) differences;
 context_user_id:=nullif(current_setting('app.user_id',true),''); context_metadata:=nullif(current_setting('app.event_metadata',true),'');
 INSERT INTO event_history(entity_type,entity_id,operation,actor_user_id,actor_type,source,request_id,correlation_id,before_state,after_state,changed_fields,reason,metadata)
 VALUES(TG_ARGV[0],entity_key,CASE TG_OP WHEN 'INSERT' THEN 'CREATE' ELSE TG_OP END,context_user_id::bigint,
  coalesce(nullif(current_setting('app.actor_type',true),''),'automated_process'),coalesce(nullif(current_setting('app.event_source',true),''),'database'),
  nullif(current_setting('app.request_id',true),'')::uuid,nullif(current_setting('app.correlation_id',true),'')::uuid,old_state,new_state,changed,
  nullif(current_setting('app.change_reason',true),''),coalesce(context_metadata::jsonb,'{}'::jsonb));
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END; $$;

COMMIT;
