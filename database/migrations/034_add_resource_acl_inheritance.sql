
BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Database migration 034', true),
       set_config('app.event_source', 'migration', true),
       set_config('app.change_reason', 'Install Phase 5 resource ACLs and live inheritance', true),
       set_config('app.event_metadata', '{"migration":"034_add_resource_acl_inheritance"}', true);

CREATE TABLE permissions (
    id bigserial PRIMARY KEY,
    code text NOT NULL,
    name text NOT NULL,
    description text NOT NULL,
    resource_type text NOT NULL CHECK (resource_type IN ('aggregation','record')),
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT permissions_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT permissions_name_not_blank CHECK (btrim(name) <> '')
);
CREATE UNIQUE INDEX permissions_code_ci_unique ON permissions(lower(code));

CREATE TABLE permission_dependencies (
    permission_id bigint NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    required_permission_id bigint NOT NULL REFERENCES permissions(id) ON DELETE RESTRICT,
    PRIMARY KEY(permission_id, required_permission_id),
    CHECK (permission_id <> required_permission_id)
);

WITH seed(code, resource_type) AS (VALUES
 ('aggregation.view','aggregation'), ('aggregation.modify_metadata','aggregation'),
 ('aggregation.delete','aggregation'), ('aggregation.close','aggregation'),
 ('aggregation.reopen','aggregation'), ('aggregation.add_child','aggregation'),
 ('aggregation.add_record','aggregation'), ('aggregation.move','aggregation'),
 ('aggregation.receive_child','aggregation'), ('aggregation.receive_record','aggregation'),
 ('aggregation.reclassify','aggregation'), ('aggregation.security_level.change','aggregation'),
 ('aggregation.acl.manage','aggregation'), ('aggregation.history.view','aggregation'),
 ('record.view','record'), ('record.modify_metadata','record'), ('record.delete','record'),
 ('record.move','record'), ('record.security_level.change','record'),
 ('record.acl.manage','record'), ('record.history.view','record'),
 ('record.component.list','record'), ('record.component.view','record'),
 ('record.component.download','record'), ('record.component.add','record'),
 ('record.component.replace','record'), ('record.component.remove','record'),
 ('record.component.reorder','record'), ('record.component.share','record'),
 ('record.component.print','record')
)
INSERT INTO permissions(code,name,description,resource_type)
SELECT code, initcap(replace(replace(code,'.',' '),'_',' ')),
       'Resource permission: ' || code, resource_type FROM seed;

INSERT INTO permission_dependencies(permission_id,required_permission_id)
SELECT dependent.id, required.id
FROM permissions dependent
JOIN permissions required ON required.code = CASE
  WHEN dependent.resource_type='aggregation' AND dependent.code<>'aggregation.view'
    THEN 'aggregation.view'
  WHEN dependent.code IN ('record.component.view','record.component.download','record.component.add',
                           'record.component.replace','record.component.remove','record.component.reorder')
    THEN 'record.component.list'
  WHEN dependent.code IN ('record.component.share','record.component.print')
    THEN 'record.component.view'
  WHEN dependent.resource_type='record' AND dependent.code<>'record.view'
    THEN 'record.view'
END
WHERE dependent.code NOT IN ('aggregation.view','record.view');

-- Materialize transitive dependencies so every storage boundary can validate
-- a complete permission set without relying on application recursion.
INSERT INTO permission_dependencies(permission_id,required_permission_id)
SELECT dependency.permission_id, root.id
FROM permission_dependencies dependency
JOIN permissions immediate ON immediate.id=dependency.required_permission_id
JOIN permissions root ON root.code=CASE
  WHEN immediate.resource_type='record' AND immediate.code<>'record.view' THEN 'record.view'
  ELSE immediate.code
END
ON CONFLICT DO NOTHING;

ALTER TABLE aggregations
  ADD COLUMN inherit_acl_from_parent boolean,
  ADD COLUMN default_child_aggregation_acl_mode text NOT NULL DEFAULT 'mirror_resource_acl',
  ADD COLUMN resource_acl_version integer NOT NULL DEFAULT 1,
  ADD COLUMN child_aggregation_acl_version integer NOT NULL DEFAULT 1,
  ADD COLUMN child_record_acl_version integer NOT NULL DEFAULT 1,
  ADD CONSTRAINT aggregations_child_acl_mode_valid
    CHECK (default_child_aggregation_acl_mode IN ('mirror_resource_acl','custom')),
  ADD CONSTRAINT aggregations_acl_versions_positive
    CHECK (resource_acl_version>0 AND child_aggregation_acl_version>0 AND child_record_acl_version>0);
UPDATE aggregations SET inherit_acl_from_parent=(parent_aggregation_id IS NOT NULL);
SET CONSTRAINTS ALL IMMEDIATE;
ALTER TABLE aggregations ALTER COLUMN inherit_acl_from_parent SET NOT NULL;
ALTER TABLE aggregations ALTER COLUMN inherit_acl_from_parent SET DEFAULT true;
ALTER TABLE aggregations ADD CONSTRAINT aggregations_root_acl_inheritance_valid
  CHECK ((parent_aggregation_id IS NULL AND NOT inherit_acl_from_parent)
      OR (parent_aggregation_id IS NOT NULL));

ALTER TABLE records
  ADD COLUMN inherit_acl_from_parent boolean NOT NULL DEFAULT true,
  ADD COLUMN resource_acl_version integer NOT NULL DEFAULT 1 CHECK (resource_acl_version>0);

ALTER TABLE roles ADD CONSTRAINT roles_everyone_code_reserved CHECK (lower(btrim(code)) <> 'everyone');
ALTER TABLE roles ADD CONSTRAINT roles_everyone_name_reserved CHECK (lower(btrim(name)) <> 'everyone');

CREATE TABLE aggregation_acl_grants (
    id bigserial PRIMARY KEY,
    aggregation_id bigint NOT NULL REFERENCES aggregations(id) ON DELETE CASCADE,
    principal_type text NOT NULL CHECK (principal_type IN ('role','everyone')),
    role_id bigint REFERENCES roles(id) ON DELETE RESTRICT,
    permission_id bigint NOT NULL REFERENCES permissions(id) ON DELETE RESTRICT,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version integer NOT NULL DEFAULT 1 CHECK (version>0),
    CHECK ((principal_type='role' AND role_id IS NOT NULL) OR
           (principal_type='everyone' AND role_id IS NULL))
);
CREATE UNIQUE INDEX aggregation_acl_role_grant_unique ON aggregation_acl_grants(aggregation_id,role_id,permission_id) WHERE principal_type='role';
CREATE UNIQUE INDEX aggregation_acl_everyone_grant_unique ON aggregation_acl_grants(aggregation_id,permission_id) WHERE principal_type='everyone';

CREATE TABLE aggregation_child_aggregation_acl_defaults (LIKE aggregation_acl_grants INCLUDING DEFAULTS INCLUDING GENERATED INCLUDING IDENTITY);
ALTER TABLE aggregation_child_aggregation_acl_defaults DROP COLUMN aggregation_id;
ALTER TABLE aggregation_child_aggregation_acl_defaults ADD COLUMN aggregation_id bigint NOT NULL REFERENCES aggregations(id) ON DELETE CASCADE;
ALTER TABLE aggregation_child_aggregation_acl_defaults ADD PRIMARY KEY(id);
ALTER TABLE aggregation_child_aggregation_acl_defaults ADD CHECK ((principal_type='role' AND role_id IS NOT NULL) OR (principal_type='everyone' AND role_id IS NULL));
ALTER TABLE aggregation_child_aggregation_acl_defaults ADD FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE RESTRICT;
ALTER TABLE aggregation_child_aggregation_acl_defaults ADD FOREIGN KEY(permission_id) REFERENCES permissions(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX child_aggregation_acl_role_grant_unique ON aggregation_child_aggregation_acl_defaults(aggregation_id,role_id,permission_id) WHERE principal_type='role';
CREATE UNIQUE INDEX child_aggregation_acl_everyone_grant_unique ON aggregation_child_aggregation_acl_defaults(aggregation_id,permission_id) WHERE principal_type='everyone';

CREATE TABLE aggregation_child_record_acl_defaults (LIKE aggregation_acl_grants INCLUDING DEFAULTS INCLUDING GENERATED INCLUDING IDENTITY);
ALTER TABLE aggregation_child_record_acl_defaults DROP COLUMN aggregation_id;
ALTER TABLE aggregation_child_record_acl_defaults ADD COLUMN aggregation_id bigint NOT NULL REFERENCES aggregations(id) ON DELETE CASCADE;
ALTER TABLE aggregation_child_record_acl_defaults ADD PRIMARY KEY(id);
ALTER TABLE aggregation_child_record_acl_defaults ADD CHECK ((principal_type='role' AND role_id IS NOT NULL) OR (principal_type='everyone' AND role_id IS NULL));
ALTER TABLE aggregation_child_record_acl_defaults ADD FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE RESTRICT;
ALTER TABLE aggregation_child_record_acl_defaults ADD FOREIGN KEY(permission_id) REFERENCES permissions(id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX child_record_acl_role_grant_unique ON aggregation_child_record_acl_defaults(aggregation_id,role_id,permission_id) WHERE principal_type='role';
CREATE UNIQUE INDEX child_record_acl_everyone_grant_unique ON aggregation_child_record_acl_defaults(aggregation_id,permission_id) WHERE principal_type='everyone';

CREATE TABLE record_acl_grants (
    id bigserial PRIMARY KEY,
    record_id bigint NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    principal_type text NOT NULL CHECK (principal_type IN ('role','everyone')),
    role_id bigint REFERENCES roles(id) ON DELETE RESTRICT,
    permission_id bigint NOT NULL REFERENCES permissions(id) ON DELETE RESTRICT,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version integer NOT NULL DEFAULT 1 CHECK (version>0),
    CHECK ((principal_type='role' AND role_id IS NOT NULL) OR
           (principal_type='everyone' AND role_id IS NULL))
);
CREATE UNIQUE INDEX record_acl_role_grant_unique ON record_acl_grants(record_id,role_id,permission_id) WHERE principal_type='role';
CREATE UNIQUE INDEX record_acl_everyone_grant_unique ON record_acl_grants(record_id,permission_id) WHERE principal_type='everyone';

CREATE INDEX aggregation_acl_role_idx ON aggregation_acl_grants(role_id,aggregation_id,permission_id);
CREATE INDEX child_aggregation_acl_role_idx ON aggregation_child_aggregation_acl_defaults(role_id,aggregation_id,permission_id);
CREATE INDEX child_record_acl_role_idx ON aggregation_child_record_acl_defaults(role_id,aggregation_id,permission_id);
CREATE INDEX record_acl_role_idx ON record_acl_grants(role_id,record_id,permission_id);

-- Every local or custom ACL starts as Everyone/all. Inheritance determines
-- whether that local set is effective or dormant; no grants are copied later.
INSERT INTO aggregation_acl_grants(aggregation_id,principal_type,permission_id)
SELECT aggregation.id,'everyone',permission.id FROM aggregations aggregation CROSS JOIN permissions permission WHERE permission.resource_type='aggregation';
INSERT INTO aggregation_child_aggregation_acl_defaults(aggregation_id,principal_type,permission_id)
SELECT aggregation.id,'everyone',permission.id FROM aggregations aggregation CROSS JOIN permissions permission WHERE permission.resource_type='aggregation';
INSERT INTO aggregation_child_record_acl_defaults(aggregation_id,principal_type,permission_id)
SELECT aggregation.id,'everyone',permission.id FROM aggregations aggregation CROSS JOIN permissions permission WHERE permission.resource_type='record';
INSERT INTO record_acl_grants(record_id,principal_type,permission_id)
SELECT record.id,'everyone',permission.id FROM records record CROSS JOIN permissions permission WHERE permission.resource_type='record';

CREATE FUNCTION validate_acl_permission_type() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected text;
BEGIN
  expected := CASE WHEN TG_TABLE_NAME='aggregation_child_record_acl_defaults' OR TG_TABLE_NAME='record_acl_grants' THEN 'record' ELSE 'aggregation' END;
  IF NOT EXISTS (SELECT 1 FROM permissions WHERE id=NEW.permission_id AND resource_type=expected) THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='acl_permission_type_mismatch';
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION validate_acl_role_clearance() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_id bigint; sufficient boolean;
BEGIN
  IF NEW.principal_type <> 'role' THEN RETURN NEW; END IF;
  IF TG_TABLE_NAME='record_acl_grants' THEN
    SELECT role_level.level_number>=resource_level.level_number INTO sufficient
    FROM roles role JOIN security_levels role_level ON role_level.id=role.security_level_id
    JOIN records resource ON resource.id=NEW.record_id
    JOIN security_levels resource_level ON resource_level.id=resource.security_level_id
    WHERE role.id=NEW.role_id;
  ELSE
    SELECT role_level.level_number>=resource_level.level_number INTO sufficient
    FROM roles role JOIN security_levels role_level ON role_level.id=role.security_level_id
    JOIN aggregations resource ON resource.id=NEW.aggregation_id
    JOIN security_levels resource_level ON resource_level.id=resource.security_level_id
    WHERE role.id=NEW.role_id;
  END IF;
  IF NOT coalesce(sufficient,false) THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='role_clearance_below_resource';
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION validate_acl_dependencies() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE owner_id bigint; owner_column text; missing boolean;
BEGIN
  owner_column := TG_ARGV[0];
  owner_id := CASE WHEN TG_OP='DELETE' THEN (to_jsonb(OLD)->>owner_column)::bigint ELSE (to_jsonb(NEW)->>owner_column)::bigint END;
  EXECUTE format($query$
    SELECT EXISTS(
      SELECT 1 FROM %I grant_row
      JOIN permission_dependencies dependency ON dependency.permission_id=grant_row.permission_id
      WHERE grant_row.%I=$1
        AND grant_row.principal_type=$2
        AND grant_row.role_id IS NOT DISTINCT FROM $3
        AND NOT EXISTS (
          SELECT 1 FROM %I required_grant
          WHERE required_grant.%I=grant_row.%I
            AND required_grant.principal_type=grant_row.principal_type
            AND required_grant.role_id IS NOT DISTINCT FROM grant_row.role_id
            AND required_grant.permission_id=dependency.required_permission_id))
  $query$,TG_TABLE_NAME,owner_column,TG_TABLE_NAME,owner_column,owner_column)
  INTO missing USING owner_id,
    CASE WHEN TG_OP='DELETE' THEN OLD.principal_type ELSE NEW.principal_type END,
    CASE WHEN TG_OP='DELETE' THEN OLD.role_id ELSE NEW.role_id END;
  IF missing THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='permission_dependency_violation';
  END IF;
  RETURN NULL;
END $$;

CREATE TRIGGER aggregation_acl_type BEFORE INSERT OR UPDATE ON aggregation_acl_grants FOR EACH ROW EXECUTE FUNCTION validate_acl_permission_type();
CREATE TRIGGER child_aggregation_acl_type BEFORE INSERT OR UPDATE ON aggregation_child_aggregation_acl_defaults FOR EACH ROW EXECUTE FUNCTION validate_acl_permission_type();
CREATE TRIGGER child_record_acl_type BEFORE INSERT OR UPDATE ON aggregation_child_record_acl_defaults FOR EACH ROW EXECUTE FUNCTION validate_acl_permission_type();
CREATE TRIGGER record_acl_type BEFORE INSERT OR UPDATE ON record_acl_grants FOR EACH ROW EXECUTE FUNCTION validate_acl_permission_type();
CREATE TRIGGER aggregation_acl_clearance BEFORE INSERT OR UPDATE ON aggregation_acl_grants FOR EACH ROW EXECUTE FUNCTION validate_acl_role_clearance();
CREATE TRIGGER child_aggregation_acl_clearance BEFORE INSERT OR UPDATE ON aggregation_child_aggregation_acl_defaults FOR EACH ROW EXECUTE FUNCTION validate_acl_role_clearance();
CREATE TRIGGER child_record_acl_clearance BEFORE INSERT OR UPDATE ON aggregation_child_record_acl_defaults FOR EACH ROW EXECUTE FUNCTION validate_acl_role_clearance();
CREATE TRIGGER record_acl_clearance BEFORE INSERT OR UPDATE ON record_acl_grants FOR EACH ROW EXECUTE FUNCTION validate_acl_role_clearance();
CREATE CONSTRAINT TRIGGER aggregation_acl_dependencies AFTER INSERT OR UPDATE OR DELETE ON aggregation_acl_grants DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_acl_dependencies('aggregation_id');
CREATE CONSTRAINT TRIGGER child_aggregation_acl_dependencies AFTER INSERT OR UPDATE OR DELETE ON aggregation_child_aggregation_acl_defaults DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_acl_dependencies('aggregation_id');
CREATE CONSTRAINT TRIGGER child_record_acl_dependencies AFTER INSERT OR UPDATE OR DELETE ON aggregation_child_record_acl_defaults DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_acl_dependencies('aggregation_id');
CREATE CONSTRAINT TRIGGER record_acl_dependencies AFTER INSERT OR UPDATE OR DELETE ON record_acl_grants DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION validate_acl_dependencies('record_id');

CREATE FUNCTION initialize_resource_acls() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_TABLE_NAME='aggregations' THEN
    INSERT INTO aggregation_acl_grants(aggregation_id,principal_type,permission_id)
      SELECT NEW.id,'everyone',id FROM permissions WHERE resource_type='aggregation';
    INSERT INTO aggregation_child_aggregation_acl_defaults(aggregation_id,principal_type,permission_id)
      SELECT NEW.id,'everyone',id FROM permissions WHERE resource_type='aggregation';
    INSERT INTO aggregation_child_record_acl_defaults(aggregation_id,principal_type,permission_id)
      SELECT NEW.id,'everyone',id FROM permissions WHERE resource_type='record';
  ELSE
    INSERT INTO record_acl_grants(record_id,principal_type,permission_id)
      SELECT NEW.id,'everyone',id FROM permissions WHERE resource_type='record';
  END IF;
  RETURN NEW;
END $$;
CREATE FUNCTION normalize_aggregation_acl_inheritance() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.parent_aggregation_id IS NULL THEN NEW.inherit_acl_from_parent := false; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER aggregations_normalize_acl_inheritance BEFORE INSERT OR UPDATE OF parent_aggregation_id ON aggregations FOR EACH ROW EXECUTE FUNCTION normalize_aggregation_acl_inheritance();
CREATE TRIGGER aggregations_initialize_acls AFTER INSERT ON aggregations FOR EACH ROW EXECUTE FUNCTION initialize_resource_acls();
CREATE TRIGGER records_initialize_acls AFTER INSERT ON records FOR EACH ROW EXECUTE FUNCTION initialize_resource_acls();

CREATE TRIGGER aggregation_acl_history AFTER INSERT OR UPDATE OR DELETE ON aggregation_acl_grants FOR EACH ROW EXECUTE FUNCTION record_entity_history('aggregation_acl_grant');
CREATE TRIGGER child_aggregation_acl_history AFTER INSERT OR UPDATE OR DELETE ON aggregation_child_aggregation_acl_defaults FOR EACH ROW EXECUTE FUNCTION record_entity_history('aggregation_child_aggregation_acl_default');
CREATE TRIGGER child_record_acl_history AFTER INSERT OR UPDATE OR DELETE ON aggregation_child_record_acl_defaults FOR EACH ROW EXECUTE FUNCTION record_entity_history('aggregation_child_record_acl_default');
CREATE TRIGGER record_acl_history AFTER INSERT OR UPDATE OR DELETE ON record_acl_grants FOR EACH ROW EXECUTE FUNCTION record_entity_history('record_acl_grant');

INSERT INTO schema_migrations(version) VALUES ('034_add_resource_acl_inheritance');
COMMIT;
