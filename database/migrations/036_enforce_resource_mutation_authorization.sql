BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 036',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Install Phase 7 resource mutation predicates',true),
       set_config('app.event_metadata','{"migration":"036_enforce_resource_mutation_authorization"}',true);

CREATE FUNCTION user_has_governance_clearance(p_user_id bigint,p_security_level_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS(
    SELECT 1 FROM user_role_assignments assignment
    JOIN roles role ON role.id=assignment.role_id
    JOIN security_levels role_level ON role_level.id=role.security_level_id
    JOIN security_levels required ON required.id=p_security_level_id
    WHERE assignment.user_id=p_user_id AND role.is_information_governance
      AND assignment.valid_from<=CURRENT_TIMESTAMP
      AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
      AND role_effectively_active(role.id)
      AND role_level.level_number>=required.level_number)
$$;

CREATE FUNCTION user_can_aggregation_operation(
  p_user_id bigint,p_aggregation_id bigint,p_privilege text,p_permission text
) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT user_can_view_aggregation(p_user_id,p_aggregation_id)
     AND user_has_global_privilege(p_user_id,p_privilege)
     AND (user_has_aggregation_permission(p_user_id,p_aggregation_id,p_permission)
          OR EXISTS(SELECT 1 FROM aggregations resource
                    WHERE resource.id=p_aggregation_id
                      AND user_has_governance_clearance(p_user_id,resource.security_level_id)))
$$;

CREATE FUNCTION user_can_record_operation(
  p_user_id bigint,p_record_id bigint,p_privilege text,p_permission text
) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT user_can_view_record(p_user_id,p_record_id)
     AND user_has_global_privilege(p_user_id,p_privilege)
     AND (user_has_record_permission(p_user_id,p_record_id,p_permission)
          OR EXISTS(SELECT 1 FROM records resource
                    WHERE resource.id=p_record_id
                      AND user_has_governance_clearance(p_user_id,resource.security_level_id)))
$$;

CREATE FUNCTION current_user_can_aggregation_operation(bigint,text,text)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_id() IS NOT NULL
     AND user_can_aggregation_operation(current_user_id(),$1,$2,$3)
$$;
CREATE FUNCTION current_user_can_record_operation(bigint,text,text)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_id() IS NOT NULL
     AND user_can_record_operation(current_user_id(),$1,$2,$3)
$$;

INSERT INTO schema_migrations(version) VALUES ('036_enforce_resource_mutation_authorization');
COMMIT;
