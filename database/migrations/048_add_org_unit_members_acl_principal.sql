BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 048',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Add the contextual org-unit-members ACL principal',true),
       set_config('app.event_metadata','{"migration":"048_add_org_unit_members_acl_principal"}',true);

ALTER TABLE roles
  ADD CONSTRAINT roles_org_unit_members_code_reserved
    CHECK (lower(btrim(code)) <> 'org_unit_members'),
  ADD CONSTRAINT roles_org_unit_members_name_reserved
    CHECK (lower(btrim(name)) <> 'all org unit members');

DO $$
DECLARE table_name text; constraint_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'aggregation_acl_grants',
    'aggregation_child_aggregation_acl_defaults',
    'aggregation_child_record_acl_defaults',
    'record_acl_grants'
  ] LOOP
    FOR constraint_name IN
      SELECT con.conname
      FROM pg_constraint con
      JOIN pg_class relation ON relation.oid=con.conrelid
      JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
      WHERE namespace.nspname=current_schema()
        AND relation.relname=table_name
        AND con.contype='c'
        AND pg_get_constraintdef(con.oid) LIKE '%principal_type%'
    LOOP
      EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I',table_name,constraint_name);
    END LOOP;
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK (principal_type IN (''role'',''everyone'',''org_unit_members''))',
      table_name,table_name || '_principal_type_valid'
    );
    EXECUTE format(
      'ALTER TABLE %I ADD CONSTRAINT %I CHECK ((principal_type=''role'' AND role_id IS NOT NULL) OR (principal_type IN (''everyone'',''org_unit_members'') AND role_id IS NULL))',
      table_name,table_name || '_principal_shape_valid'
    );
  END LOOP;
END;
$$;

CREATE UNIQUE INDEX aggregation_acl_org_unit_members_grant_unique
  ON aggregation_acl_grants(aggregation_id,permission_id)
  WHERE principal_type='org_unit_members';
CREATE UNIQUE INDEX child_aggregation_acl_org_unit_members_grant_unique
  ON aggregation_child_aggregation_acl_defaults(aggregation_id,permission_id)
  WHERE principal_type='org_unit_members';
CREATE UNIQUE INDEX child_record_acl_org_unit_members_grant_unique
  ON aggregation_child_record_acl_defaults(aggregation_id,permission_id)
  WHERE principal_type='org_unit_members';
CREATE UNIQUE INDEX record_acl_org_unit_members_grant_unique
  ON record_acl_grants(record_id,permission_id)
  WHERE principal_type='org_unit_members';

CREATE OR REPLACE FUNCTION user_has_aggregation_permission(
  p_user_id bigint, p_aggregation_id bigint, p_permission text
) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
DECLARE
  cursor_row aggregations%ROWTYPE;
  parent_row aggregations%ROWTYPE;
  source_id bigint;
  source_kind text;
  target_owner_id bigint;
BEGIN
  SELECT * INTO cursor_row FROM aggregations WHERE id=p_aggregation_id;
  IF NOT FOUND THEN RETURN false; END IF;
  target_owner_id := cursor_row.owning_org_unit_id;
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
        AND (grant_row.principal_type='everyone'
          OR (grant_row.principal_type='role' AND EXISTS (
            SELECT 1 FROM user_role_assignments assignment
            WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
              AND assignment.valid_from<=CURRENT_TIMESTAMP
              AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
              AND role_effectively_active(assignment.role_id)))
          OR (grant_row.principal_type='org_unit_members' AND EXISTS (
            SELECT 1 FROM user_role_assignments assignment
            JOIN roles role ON role.id=assignment.role_id
            WHERE assignment.user_id=p_user_id AND role.org_unit_id=target_owner_id
              AND assignment.valid_from<=CURRENT_TIMESTAMP
              AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
              AND role_effectively_active(role.id))))
    );
  END IF;
  RETURN EXISTS (
    SELECT 1 FROM aggregation_child_aggregation_acl_defaults grant_row
    JOIN permissions permission ON permission.id=grant_row.permission_id
    WHERE grant_row.aggregation_id=source_id AND permission.code=p_permission
      AND (grant_row.principal_type='everyone'
        OR (grant_row.principal_type='role' AND EXISTS (
          SELECT 1 FROM user_role_assignments assignment
          WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
            AND assignment.valid_from<=CURRENT_TIMESTAMP
            AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
            AND role_effectively_active(assignment.role_id)))
        OR (grant_row.principal_type='org_unit_members' AND EXISTS (
          SELECT 1 FROM user_role_assignments assignment
          JOIN roles role ON role.id=assignment.role_id
          WHERE assignment.user_id=p_user_id AND role.org_unit_id=target_owner_id
            AND assignment.valid_from<=CURRENT_TIMESTAMP
            AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
            AND role_effectively_active(role.id))))
  );
END $$;

CREATE OR REPLACE FUNCTION user_has_record_permission(
  p_user_id bigint, p_record_id bigint, p_permission text
) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM records resource
    JOIN permissions permission ON permission.code=p_permission
    JOIN record_acl_grants grant_row ON NOT resource.inherit_acl_from_parent
      AND grant_row.record_id=resource.id AND grant_row.permission_id=permission.id
    WHERE resource.id=p_record_id AND
      (grant_row.principal_type='everyone'
       OR (grant_row.principal_type='role' AND EXISTS (
         SELECT 1 FROM user_role_assignments assignment
         WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
           AND assignment.valid_from<=CURRENT_TIMESTAMP
           AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(assignment.role_id)))
       OR (grant_row.principal_type='org_unit_members' AND EXISTS (
         SELECT 1 FROM user_role_assignments assignment
         JOIN roles role ON role.id=assignment.role_id
         WHERE assignment.user_id=p_user_id AND role.org_unit_id=resource.owning_org_unit_id
           AND assignment.valid_from<=CURRENT_TIMESTAMP
           AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(role.id))))
  ) OR EXISTS (
    SELECT 1 FROM records resource
    JOIN permissions permission ON permission.code=p_permission
    JOIN aggregation_child_record_acl_defaults grant_row
      ON resource.inherit_acl_from_parent AND grant_row.aggregation_id=resource.aggregation_id
      AND grant_row.permission_id=permission.id
    WHERE resource.id=p_record_id AND
      (grant_row.principal_type='everyone'
       OR (grant_row.principal_type='role' AND EXISTS (
         SELECT 1 FROM user_role_assignments assignment
         WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
           AND assignment.valid_from<=CURRENT_TIMESTAMP
           AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(assignment.role_id)))
       OR (grant_row.principal_type='org_unit_members' AND EXISTS (
         SELECT 1 FROM user_role_assignments assignment
         JOIN roles role ON role.id=assignment.role_id
         WHERE assignment.user_id=p_user_id AND role.org_unit_id=resource.owning_org_unit_id
           AND assignment.valid_from<=CURRENT_TIMESTAMP
           AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(role.id))))
  )
$$;

CREATE OR REPLACE FUNCTION user_has_destination_record_permission(
  p_user_id bigint,p_aggregation_id bigint,p_permission text
) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT EXISTS(
    SELECT 1 FROM aggregations resource
    JOIN aggregation_child_record_acl_defaults grant_row
      ON grant_row.aggregation_id=resource.id
    JOIN permissions permission ON permission.id=grant_row.permission_id
    WHERE resource.id=p_aggregation_id AND permission.code=p_permission
      AND (grant_row.principal_type='everyone'
       OR (grant_row.principal_type='role' AND EXISTS(
         SELECT 1 FROM user_role_assignments assignment
         WHERE assignment.user_id=p_user_id AND assignment.role_id=grant_row.role_id
           AND assignment.valid_from<=CURRENT_TIMESTAMP
           AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(assignment.role_id)))
       OR (grant_row.principal_type='org_unit_members' AND EXISTS(
         SELECT 1 FROM user_role_assignments assignment
         JOIN roles role ON role.id=assignment.role_id
         WHERE assignment.user_id=p_user_id AND role.org_unit_id=resource.owning_org_unit_id
           AND assignment.valid_from<=CURRENT_TIMESTAMP
           AND (assignment.valid_until IS NULL OR assignment.valid_until>CURRENT_TIMESTAMP)
           AND role_effectively_active(role.id))))
  )
$$;

INSERT INTO schema_migrations(version)
VALUES ('048_add_org_unit_members_acl_principal');

COMMIT;
