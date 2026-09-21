BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 049',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Initialize approved organizational ACL defaults',true),
       set_config('app.event_metadata','{"migration":"049_initialize_organizational_acl_defaults"}',true);

CREATE OR REPLACE FUNCTION initialize_resource_acls() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE creator_role_id bigint := NULLIF(current_setting('app.creator_acl_role_id',true),'')::bigint;
BEGIN
  IF creator_role_id IS NULL THEN RETURN NEW; END IF;
  IF TG_TABLE_NAME='aggregations' THEN
    INSERT INTO aggregation_acl_grants(aggregation_id,principal_type,role_id,permission_id)
      SELECT NEW.id,'role',creator_role_id,id FROM permissions WHERE code=ANY(ARRAY[
        'aggregation.view','aggregation.modify_metadata','aggregation.add_child',
        'aggregation.add_record','aggregation.close','aggregation.acl.manage',
        'aggregation.history.view']);
    INSERT INTO aggregation_acl_grants(aggregation_id,principal_type,permission_id)
      SELECT NEW.id,'org_unit_members',id FROM permissions
      WHERE code=ANY(ARRAY['aggregation.view','aggregation.history.view']);
    INSERT INTO aggregation_child_aggregation_acl_defaults(aggregation_id,principal_type,role_id,permission_id)
      SELECT NEW.id,'role',creator_role_id,id FROM permissions WHERE code=ANY(ARRAY[
        'aggregation.view','aggregation.modify_metadata','aggregation.add_child',
        'aggregation.add_record','aggregation.close','aggregation.acl.manage',
        'aggregation.history.view']);
    INSERT INTO aggregation_child_aggregation_acl_defaults(aggregation_id,principal_type,permission_id)
      SELECT NEW.id,'org_unit_members',id FROM permissions
      WHERE code=ANY(ARRAY['aggregation.view','aggregation.history.view']);
    INSERT INTO aggregation_child_record_acl_defaults(aggregation_id,principal_type,role_id,permission_id)
      SELECT NEW.id,'role',creator_role_id,id FROM permissions WHERE code=ANY(ARRAY[
        'record.view','record.acl.manage','record.history.view','record.component.list',
        'record.component.view','record.component.download','record.component.share',
        'record.component.print']);
    INSERT INTO aggregation_child_record_acl_defaults(aggregation_id,principal_type,permission_id)
      SELECT NEW.id,'org_unit_members',id FROM permissions WHERE code=ANY(ARRAY[
        'record.view','record.component.list','record.component.view','record.component.download']);
  ELSE
    INSERT INTO record_acl_grants(record_id,principal_type,role_id,permission_id)
      SELECT NEW.id,'role',creator_role_id,id FROM permissions WHERE code=ANY(ARRAY[
        'record.view','record.acl.manage','record.history.view','record.component.list',
        'record.component.view','record.component.download','record.component.share',
        'record.component.print']);
    INSERT INTO record_acl_grants(record_id,principal_type,permission_id)
      SELECT NEW.id,'org_unit_members',id FROM permissions WHERE code=ANY(ARRAY[
        'record.view','record.component.list','record.component.view','record.component.download']);
  END IF;
  RETURN NEW;
END $$;

SET CONSTRAINTS ALL DEFERRED;
DELETE FROM aggregation_acl_grants;
DELETE FROM aggregation_child_aggregation_acl_defaults;
DELETE FROM aggregation_child_record_acl_defaults;
DELETE FROM record_acl_grants;

WITH RECURSIVE mapped AS (
  SELECT root.root_aggregation_id AS id,root.selected_role_id
  FROM organizational_ownership_root_assignments root
  UNION ALL
  SELECT child.id,parent.selected_role_id
  FROM mapped parent JOIN aggregations child ON child.parent_aggregation_id=parent.id
)
INSERT INTO aggregation_acl_grants(aggregation_id,principal_type,role_id,permission_id)
SELECT mapped.id,'role',mapped.selected_role_id,permission.id FROM mapped
CROSS JOIN permissions permission WHERE permission.code=ANY(ARRAY[
  'aggregation.view','aggregation.modify_metadata','aggregation.add_child','aggregation.add_record',
  'aggregation.close','aggregation.acl.manage','aggregation.history.view']);

WITH RECURSIVE mapped AS (
  SELECT root.root_aggregation_id AS id,root.selected_role_id FROM organizational_ownership_root_assignments root
  UNION ALL SELECT child.id,parent.selected_role_id FROM mapped parent JOIN aggregations child ON child.parent_aggregation_id=parent.id
)
INSERT INTO aggregation_acl_grants(aggregation_id,principal_type,permission_id)
SELECT mapped.id,'org_unit_members',permission.id FROM mapped CROSS JOIN permissions permission
WHERE permission.code=ANY(ARRAY['aggregation.view','aggregation.history.view']);

INSERT INTO aggregation_child_aggregation_acl_defaults
  (aggregation_id,principal_type,role_id,permission_id)
SELECT aggregation_id,principal_type,role_id,permission_id FROM aggregation_acl_grants;

WITH RECURSIVE mapped AS (
  SELECT root.root_aggregation_id AS id,root.selected_role_id FROM organizational_ownership_root_assignments root
  UNION ALL SELECT child.id,parent.selected_role_id FROM mapped parent JOIN aggregations child ON child.parent_aggregation_id=parent.id
)
INSERT INTO aggregation_child_record_acl_defaults(aggregation_id,principal_type,role_id,permission_id)
SELECT mapped.id,'role',mapped.selected_role_id,permission.id FROM mapped CROSS JOIN permissions permission
WHERE permission.code=ANY(ARRAY['record.view','record.acl.manage','record.history.view','record.component.list',
 'record.component.view','record.component.download','record.component.share','record.component.print']);
INSERT INTO aggregation_child_record_acl_defaults(aggregation_id,principal_type,permission_id)
SELECT aggregation.id,'org_unit_members',permission.id FROM aggregations aggregation CROSS JOIN permissions permission
WHERE permission.code=ANY(ARRAY['record.view','record.component.list','record.component.view','record.component.download']);

WITH RECURSIVE mapped AS (
  SELECT root.root_aggregation_id AS id,root.selected_role_id FROM organizational_ownership_root_assignments root
  UNION ALL SELECT child.id,parent.selected_role_id FROM mapped parent JOIN aggregations child ON child.parent_aggregation_id=parent.id
)
INSERT INTO record_acl_grants(record_id,principal_type,role_id,permission_id)
SELECT record.id,'role',mapped.selected_role_id,permission.id FROM records record JOIN mapped ON mapped.id=record.aggregation_id
CROSS JOIN permissions permission WHERE permission.code=ANY(ARRAY['record.view','record.acl.manage','record.history.view',
 'record.component.list','record.component.view','record.component.download','record.component.share','record.component.print']);
INSERT INTO record_acl_grants(record_id,principal_type,permission_id)
SELECT record.id,'org_unit_members',permission.id FROM records record CROSS JOIN permissions permission
WHERE permission.code=ANY(ARRAY['record.view','record.component.list','record.component.view','record.component.download']);

SET CONSTRAINTS ALL IMMEDIATE;
INSERT INTO schema_migrations(version) VALUES ('049_initialize_organizational_acl_defaults');
COMMIT;
