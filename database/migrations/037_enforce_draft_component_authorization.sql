BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 037',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Install Phase 8 draft, component, and placement-correction policy',true),
       set_config('app.event_metadata','{"migration":"037_enforce_draft_component_authorization"}',true);

CREATE FUNCTION user_has_destination_record_permission(
  p_user_id bigint,p_aggregation_id bigint,p_permission text
) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS(
    SELECT 1 FROM aggregation_child_record_acl_defaults grant_row
    JOIN permissions permission ON permission.id=grant_row.permission_id
    WHERE grant_row.aggregation_id=p_aggregation_id AND permission.code=p_permission
      AND (grant_row.principal_type='everyone' OR EXISTS(
        SELECT 1 FROM user_role_assignments assignment
        WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
          AND assignment.valid_from<=CURRENT_TIMESTAMP
          AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
          AND role_effectively_active(assignment.role_id)))
  )
$$;

CREATE FUNCTION current_user_can_record_component_operation(
  p_record_id bigint,p_privilege text,p_permission text
) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_can_view_record(p_record_id)
     AND user_has_global_privilege(current_user_id(),p_privilege)
     AND (user_has_record_permission(current_user_id(),p_record_id,p_permission)
          OR EXISTS(SELECT 1 FROM records resource
                    WHERE resource.id=p_record_id
                      AND user_has_governance_clearance(current_user_id(),resource.security_level_id)))
$$;

CREATE OR REPLACE FUNCTION current_user_can_list_record_components(p_record_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_can_view_record(p_record_id)
     AND (user_has_record_permission(current_user_id(),p_record_id,'record.component.list')
          OR EXISTS(SELECT 1 FROM records resource
                    WHERE resource.id=p_record_id
                      AND user_has_governance_clearance(current_user_id(),resource.security_level_id)))
$$;

CREATE FUNCTION current_user_owns_open_draft(p_draft_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_id() IS NOT NULL AND EXISTS(
    SELECT 1 FROM record_drafts draft
    JOIN users owner ON owner.id=draft.owner_user_id
    WHERE draft.id=p_draft_id AND draft.owner_user_id=current_user_id()
      AND draft.status='open' AND draft.expires_at>CURRENT_TIMESTAMP
      AND owner.status='active')
$$;

CREATE OR REPLACE FUNCTION protect_record_in_closed_aggregation()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE correction boolean := COALESCE(current_setting('app.closed_record_placement_correction',true)='authorized',false);
BEGIN
  IF TG_OP='INSERT' THEN
    IF NOT correction THEN PERFORM assert_aggregation_effectively_open(NEW.aggregation_id); END IF;
    RETURN NEW;
  ELSIF TG_OP='DELETE' THEN
    PERFORM assert_aggregation_effectively_open(OLD.aggregation_id); RETURN OLD;
  END IF;
  IF correction AND NEW.aggregation_id IS DISTINCT FROM OLD.aggregation_id
     AND NEW.record_number IS NOT DISTINCT FROM OLD.record_number
     AND NEW.title IS NOT DISTINCT FROM OLD.title
     AND NEW.description IS NOT DISTINCT FROM OLD.description
     AND NEW.date_originated IS NOT DISTINCT FROM OLD.date_originated
     AND NEW.security_level_id IS NOT DISTINCT FROM OLD.security_level_id THEN
    RETURN NEW;
  END IF;
  PERFORM assert_aggregation_effectively_open(OLD.aggregation_id);
  IF NEW.aggregation_id IS DISTINCT FROM OLD.aggregation_id THEN
    PERFORM assert_aggregation_effectively_open(NEW.aggregation_id);
  END IF;
  RETURN NEW;
END $$;

INSERT INTO schema_migrations(version) VALUES ('037_enforce_draft_component_authorization');
COMMIT;
