
BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Database migration 035', true),
       set_config('app.event_source', 'migration', true),
       set_config('app.change_reason', 'Install Phase 6 governed-resource read predicates', true),
       set_config('app.event_metadata', '{"migration":"035_enforce_resource_read_authorization"}', true);

-- This is deliberately a database predicate: callers can compose it into the
-- query before count, sort, and pagination, avoiding both inference leaks and
-- per-row authorization queries.
CREATE FUNCTION user_has_global_privilege(p_user_id bigint, p_code text)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1
      FROM users account
      JOIN user_role_assignments assignment ON assignment.user_id=account.id
      JOIN roles role ON role.id=assignment.role_id
      JOIN profile_privileges membership ON membership.profile_id=role.profile_id
      JOIN privileges privilege ON privilege.id=membership.privilege_id
     WHERE account.id=p_user_id AND account.status='active'
       AND assignment.valid_from<=CURRENT_TIMESTAMP
       AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
       AND role_effectively_active(role.id)
       AND privilege.code=p_code
  )
$$;

CREATE FUNCTION user_has_aggregation_permission(
  p_user_id bigint, p_aggregation_id bigint, p_permission text
) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
DECLARE
  cursor_row aggregations%ROWTYPE;
  parent_row aggregations%ROWTYPE;
  source_id bigint;
  source_kind text;
BEGIN
  SELECT * INTO cursor_row FROM aggregations WHERE id=p_aggregation_id;
  IF NOT FOUND THEN RETURN false; END IF;
  IF NOT cursor_row.inherit_acl_from_parent OR cursor_row.parent_aggregation_id IS NULL THEN
    source_id := cursor_row.id; source_kind := 'resource';
  ELSE
    LOOP
      SELECT * INTO parent_row FROM aggregations WHERE id=cursor_row.parent_aggregation_id;
      IF NOT FOUND THEN RETURN false; END IF;
      IF parent_row.default_child_aggregation_acl_mode='custom' THEN
        source_id := parent_row.id; source_kind := 'child_default'; EXIT;
      ELSIF NOT parent_row.inherit_acl_from_parent OR parent_row.parent_aggregation_id IS NULL THEN
        source_id := parent_row.id; source_kind := 'resource'; EXIT;
      END IF;
      cursor_row := parent_row;
    END LOOP;
  END IF;

  IF source_kind='resource' THEN
    RETURN EXISTS (
      SELECT 1 FROM aggregation_acl_grants grant_row
      JOIN permissions permission ON permission.id=grant_row.permission_id
      WHERE grant_row.aggregation_id=source_id AND permission.code=p_permission
        AND (grant_row.principal_type='everyone' OR EXISTS (
          SELECT 1 FROM user_role_assignments assignment
          WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
            AND assignment.valid_from<=CURRENT_TIMESTAMP
            AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
            AND role_effectively_active(assignment.role_id)))
    );
  END IF;
  RETURN EXISTS (
    SELECT 1 FROM aggregation_child_aggregation_acl_defaults grant_row
    JOIN permissions permission ON permission.id=grant_row.permission_id
    WHERE grant_row.aggregation_id=source_id AND permission.code=p_permission
      AND (grant_row.principal_type='everyone' OR EXISTS (
        SELECT 1 FROM user_role_assignments assignment
        WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
          AND assignment.valid_from<=CURRENT_TIMESTAMP
          AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
          AND role_effectively_active(assignment.role_id)))
  );
END $$;

CREATE FUNCTION user_can_view_aggregation(p_user_id bigint, p_aggregation_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT user_has_global_privilege(p_user_id,'aggregation.view')
     AND EXISTS (SELECT 1 FROM user_role_assignments a
       JOIN roles r ON r.id=a.role_id JOIN security_levels rl ON rl.id=r.security_level_id
       JOIN aggregations resource ON resource.id=p_aggregation_id
       JOIN security_levels required ON required.id=resource.security_level_id
       WHERE a.user_id=p_user_id AND a.valid_from<=CURRENT_TIMESTAMP
         AND (a.valid_until IS NULL OR a.valid_until>CURRENT_TIMESTAMP)
         AND role_effectively_active(r.id) AND rl.level_number>=required.level_number)
     AND (
       user_has_aggregation_permission(p_user_id,p_aggregation_id,'aggregation.view')
       OR EXISTS (SELECT 1 FROM user_role_assignments a
         JOIN roles r ON r.id=a.role_id JOIN security_levels rl ON rl.id=r.security_level_id
         JOIN aggregations resource ON resource.id=p_aggregation_id
         JOIN security_levels required ON required.id=resource.security_level_id
         WHERE a.user_id=p_user_id AND r.is_information_governance
           AND a.valid_from<=CURRENT_TIMESTAMP
           AND (a.valid_until IS NULL OR a.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(r.id) AND rl.level_number>=required.level_number)
     )
$$;

CREATE FUNCTION user_has_record_permission(
  p_user_id bigint, p_record_id bigint, p_permission text
) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM records resource
    JOIN permissions permission ON permission.code=p_permission
    JOIN record_acl_grants grant_row ON NOT resource.inherit_acl_from_parent
      AND grant_row.record_id=resource.id AND grant_row.permission_id=permission.id
    WHERE resource.id=p_record_id AND
      (grant_row.principal_type='everyone' OR EXISTS (
        SELECT 1 FROM user_role_assignments assignment
        WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
          AND assignment.valid_from<=CURRENT_TIMESTAMP
          AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
          AND role_effectively_active(assignment.role_id)))
  ) OR EXISTS (
    SELECT 1 FROM records resource
    JOIN permissions permission ON permission.code=p_permission
    JOIN aggregation_child_record_acl_defaults grant_row
      ON resource.inherit_acl_from_parent AND grant_row.aggregation_id=resource.aggregation_id
      AND grant_row.permission_id=permission.id
    WHERE resource.id=p_record_id AND
      (grant_row.principal_type='everyone' OR EXISTS (
        SELECT 1 FROM user_role_assignments assignment
        WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
          AND assignment.valid_from<=CURRENT_TIMESTAMP
          AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
          AND role_effectively_active(assignment.role_id)))
  )
$$;

CREATE FUNCTION user_can_view_record(p_user_id bigint, p_record_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT user_has_global_privilege(p_user_id,'record.view')
     AND EXISTS (SELECT 1 FROM user_role_assignments a
       JOIN roles r ON r.id=a.role_id JOIN security_levels rl ON rl.id=r.security_level_id
       JOIN records resource ON resource.id=p_record_id
       JOIN security_levels required ON required.id=resource.security_level_id
       WHERE a.user_id=p_user_id AND a.valid_from<=CURRENT_TIMESTAMP
         AND (a.valid_until IS NULL OR a.valid_until>CURRENT_TIMESTAMP)
         AND role_effectively_active(r.id) AND rl.level_number>=required.level_number)
     AND (
       user_has_record_permission(p_user_id,p_record_id,'record.view')
       OR EXISTS (SELECT 1 FROM user_role_assignments a
         JOIN roles r ON r.id=a.role_id JOIN security_levels rl ON rl.id=r.security_level_id
         JOIN records resource ON resource.id=p_record_id
         JOIN security_levels required ON required.id=resource.security_level_id
         WHERE a.user_id=p_user_id AND r.is_information_governance
           AND a.valid_from<=CURRENT_TIMESTAMP
           AND (a.valid_until IS NULL OR a.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(r.id) AND rl.level_number>=required.level_number)
     )
$$;

CREATE FUNCTION current_user_id() RETURNS bigint LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.user_id',true),'')::bigint
$$;
CREATE FUNCTION current_user_can_view_aggregation(p_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_id() IS NOT NULL AND user_can_view_aggregation(current_user_id(),p_id)
$$;
CREATE FUNCTION current_user_can_view_record(p_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_id() IS NOT NULL AND user_can_view_record(current_user_id(),p_id)
$$;

CREATE FUNCTION current_user_can_list_record_components(p_record_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT current_user_can_view_record(p_record_id)
     AND user_has_global_privilege(current_user_id(),'record.component.view')
     AND (
       user_has_record_permission(current_user_id(),p_record_id,'record.component.list')
       OR EXISTS (SELECT 1 FROM user_role_assignments a
         JOIN roles r ON r.id=a.role_id JOIN security_levels rl ON rl.id=r.security_level_id
         JOIN records resource ON resource.id=p_record_id
         JOIN security_levels required ON required.id=resource.security_level_id
         WHERE a.user_id=current_user_id() AND r.is_information_governance
           AND a.valid_from<=CURRENT_TIMESTAMP
           AND (a.valid_until IS NULL OR a.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(r.id) AND rl.level_number>=required.level_number)
     )
$$;

CREATE FUNCTION current_user_can_view_event_resource(
  p_entity_type text, p_entity_id bigint, p_before jsonb, p_after jsonb
) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
DECLARE record_id bigint;
DECLARE historical_level_id bigint;
BEGIN
  IF p_entity_type='aggregation' THEN
    IF EXISTS (SELECT 1 FROM aggregations WHERE id=p_entity_id) THEN
      RETURN current_user_can_view_aggregation(p_entity_id);
    END IF;
    historical_level_id := COALESCE(
      CASE WHEN (p_before->>'security_level_id') ~ '^[0-9]+$' THEN (p_before->>'security_level_id')::bigint END,
      CASE WHEN (p_after->>'security_level_id') ~ '^[0-9]+$' THEN (p_after->>'security_level_id')::bigint END
    );
  ELSIF p_entity_type='record' THEN
    IF EXISTS (SELECT 1 FROM records WHERE id=p_entity_id) THEN
      RETURN current_user_can_view_record(p_entity_id);
    END IF;
    historical_level_id := COALESCE(
      CASE WHEN (p_before->>'security_level_id') ~ '^[0-9]+$' THEN (p_before->>'security_level_id')::bigint END,
      CASE WHEN (p_after->>'security_level_id') ~ '^[0-9]+$' THEN (p_after->>'security_level_id')::bigint END
    );
  ELSIF p_entity_type IN ('digital_component','record_component') THEN
    SELECT component.record_id INTO record_id FROM digital_components component WHERE component.id=p_entity_id;
    IF record_id IS NULL THEN
      record_id := COALESCE(
        CASE WHEN (p_after->>'record_id') ~ '^[0-9]+$' THEN (p_after->>'record_id')::bigint END,
        CASE WHEN (p_before->>'record_id') ~ '^[0-9]+$' THEN (p_before->>'record_id')::bigint END
      );
    END IF;
    RETURN record_id IS NOT NULL AND current_user_can_view_record(record_id);
  ELSE
    RETURN true;
  END IF;
  IF historical_level_id IS NOT NULL THEN
    RETURN user_has_global_privilege(current_user_id(),'audit.view') AND EXISTS (
      SELECT 1 FROM user_role_assignments assignment
      JOIN roles role ON role.id=assignment.role_id
      JOIN security_levels role_level ON role_level.id=role.security_level_id
      JOIN security_levels required ON required.id=historical_level_id
      WHERE assignment.user_id=current_user_id()
        AND assignment.valid_from<=CURRENT_TIMESTAMP
        AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
        AND role_effectively_active(role.id)
        AND role_level.level_number>=required.level_number
    );
  END IF;
  RETURN false;
END $$;

CREATE VIEW authorized_event_history AS
SELECT event.id,event.occurred_at,event.transaction_id,event.entity_type,event.entity_id,
       event.operation,event.actor_user_id,event.actor_name,event.actor_email,event.actor_type,
       event.source,event.request_id,event.correlation_id,
       CASE WHEN visible.allowed THEN event.before_state ELSE NULL END AS before_state,
       CASE WHEN visible.allowed THEN event.after_state ELSE NULL END AS after_state,
       CASE WHEN visible.allowed THEN event.changed_fields ELSE ARRAY[]::text[] END AS changed_fields,
       CASE WHEN visible.allowed THEN event.reason ELSE NULL END AS reason,
       CASE WHEN visible.allowed THEN event.metadata
            ELSE jsonb_build_object('redacted',true,'reason','resource_access_denied') END AS metadata
FROM event_history event
CROSS JOIN LATERAL (
  SELECT current_user_can_view_event_resource(
    event.entity_type,event.entity_id,event.before_state,event.after_state
  ) AS allowed
) visible;

CREATE VIEW authorized_aggregations_for_search AS
SELECT resource.id,
       CASE WHEN resource.parent_aggregation_id IS NULL
                  OR current_user_can_view_aggregation(resource.parent_aggregation_id)
            THEN resource.parent_aggregation_id END AS parent_aggregation_id,
       resource.classification_id,resource.aggregation_number,resource.title,
       resource.description,resource.date_created,resource.date_opened,resource.date_closed,
       resource.security_level_id,resource.inherit_acl_from_parent,
       resource.default_child_aggregation_acl_mode,resource.resource_acl_version,
       resource.child_aggregation_acl_version,resource.child_record_acl_version,resource.version
FROM aggregations resource;

CREATE VIEW authorized_records_for_search AS
SELECT resource.id,
       CASE WHEN current_user_can_view_aggregation(resource.aggregation_id)
            THEN resource.aggregation_id END AS aggregation_id,
       resource.record_number,resource.title,resource.description,resource.date_created,
       resource.date_originated,resource.security_level_id,resource.inherit_acl_from_parent,
       resource.resource_acl_version,resource.version
FROM records resource;

CREATE INDEX user_role_assignments_effective_lookup_idx
  ON user_role_assignments(user_id,role_id,valid_from,valid_until);

INSERT INTO schema_migrations(version) VALUES ('035_enforce_resource_read_authorization');
COMMIT;
