
BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Database migration 033', true),
       set_config('app.event_source', 'migration', true),
       set_config('app.change_reason', 'Install the Phase 2 privilege and profile model', true),
       set_config('app.event_metadata', '{"migration":"033_add_privileges_profiles_and_role_authorization"}', true);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE privileges (
    id bigserial PRIMARY KEY,
    code text NOT NULL,
    name text NOT NULL,
    description text NOT NULL,
    category text NOT NULL,
    is_reserved boolean NOT NULL DEFAULT false,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    CONSTRAINT privileges_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT privileges_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT privileges_category_valid CHECK (category IN ('administration','aggregation','record','component','exceptional'))
);
CREATE UNIQUE INDEX privileges_code_ci_unique ON privileges(lower(code));

CREATE TABLE profiles (
    id bigserial PRIMARY KEY,
    code text NOT NULL,
    name text NOT NULL,
    description text,
    is_system boolean NOT NULL DEFAULT false,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    CONSTRAINT profiles_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT profiles_name_not_blank CHECK (btrim(name) <> '')
);
CREATE UNIQUE INDEX profiles_code_ci_unique ON profiles(lower(code));
CREATE UNIQUE INDEX profiles_name_ci_unique ON profiles(lower(name));

CREATE TABLE profile_privileges (
    id bigserial PRIMARY KEY,
    profile_id bigint NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    privilege_id bigint NOT NULL REFERENCES privileges(id) ON DELETE RESTRICT,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    CONSTRAINT profile_privileges_unique UNIQUE(profile_id, privilege_id)
);
CREATE INDEX profile_privileges_privilege_id_idx ON profile_privileges(privilege_id, profile_id);

CREATE TABLE privilege_dependencies (
    privilege_id bigint NOT NULL REFERENCES privileges(id) ON DELETE CASCADE,
    required_privilege_id bigint NOT NULL REFERENCES privileges(id) ON DELETE RESTRICT,
    PRIMARY KEY(privilege_id, required_privilege_id),
    CONSTRAINT privilege_dependencies_not_self CHECK (privilege_id <> required_privilege_id)
);

WITH seed(code, category, reserved) AS (VALUES
 ('authorization.administer','administration',false), ('authorization.explain','administration',false),
 ('security_levels.administer','administration',false), ('identity.users.administer','administration',false),
 ('identity.sessions.administer','administration',false), ('organization.administer','administration',false),
 ('classifications.administer','administration',false), ('audit.view','administration',false),
 ('aggregation.view','aggregation',false), ('aggregation.create_root','aggregation',false),
 ('aggregation.create_child','aggregation',false), ('aggregation.modify','aggregation',false),
 ('aggregation.move','aggregation',false), ('aggregation.reclassify','aggregation',false),
 ('aggregation.close','aggregation',false), ('aggregation.reopen','aggregation',false),
 ('aggregation.delete','aggregation',false), ('aggregation.security_level.change','aggregation',false),
 ('aggregation.acl.manage','aggregation',false), ('record.view','record',false),
 ('record.create','record',false), ('record.modify','record',false), ('record.move','record',false),
 ('record.delete','record',false), ('record.security_level.change','record',false),
 ('record.acl.manage','record',false), ('record.component.view','component',false),
 ('record.component.download','component',false), ('record.component.add','component',false),
 ('record.component.replace','component',false), ('record.component.remove','component',false),
 ('record.component.reorder','component',false), ('record.component.share','component',true),
 ('record.component.print','component',true), ('security.resource.downgrade','exceptional',false),
 ('closure.correct_record_placement','exceptional',false), ('authorization.recovery','exceptional',true)
)
INSERT INTO privileges(code,name,description,category,is_reserved)
SELECT code, initcap(replace(replace(code,'.',' '),'_',' ')),
       'Global capability: ' || code, category, reserved FROM seed;

INSERT INTO profiles(code,name,description,is_system) VALUES
 ('ALL_PRIVS','All privileges','Migration and controlled compatibility profile',true),
 ('SYS_ADMIN','System Administrator','Platform administration without governed-content bypass',true),
 ('INFO_GOV_MGR','Information Governance Manager','Universal governed-information custody and classification administration, subject to privilege and clearance gates',true),
 ('INFO_GOV_OFFICER','Information Governance Officer','Universal governed-information custody and classification administration, subject to privilege and clearance gates',true);

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id, privilege.id FROM profiles profile CROSS JOIN privileges privilege
WHERE profile.code='ALL_PRIVS';

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id, privilege.id FROM profiles profile JOIN privileges privilege ON privilege.code IN (
 'authorization.administer','authorization.explain','security_levels.administer',
 'identity.users.administer','identity.sessions.administer','organization.administer',
 'classifications.administer','audit.view') WHERE profile.code='SYS_ADMIN';

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id, privilege.id FROM profiles profile JOIN privileges privilege ON
 privilege.code IN ('authorization.administer','authorization.explain','classifications.administer','security_levels.administer','audit.view',
 'aggregation.view','aggregation.create_root','aggregation.create_child','aggregation.modify',
 'aggregation.move','aggregation.reclassify','aggregation.close','aggregation.reopen',
 'aggregation.delete','aggregation.security_level.change','aggregation.acl.manage',
 'record.view','record.create','record.modify','record.move','record.delete',
 'record.security_level.change','record.acl.manage','record.component.view',
 'record.component.download','record.component.add','record.component.replace',
 'record.component.remove','record.component.reorder','record.component.share',
 'record.component.print','security.resource.downgrade','closure.correct_record_placement')
WHERE profile.code IN ('INFO_GOV_MGR','INFO_GOV_OFFICER');

INSERT INTO privilege_dependencies(privilege_id,required_privilege_id)
SELECT dependent.id, required.id FROM privileges dependent CROSS JOIN privileges required
WHERE required.code = CASE
 WHEN dependent.code LIKE 'aggregation.%' AND dependent.code <> 'aggregation.view' THEN 'aggregation.view'
 WHEN (dependent.code LIKE 'record.%' OR dependent.code LIKE 'record.component.%') AND dependent.code <> 'record.view' THEN 'record.view'
 END;

ALTER TABLE roles ADD COLUMN profile_id bigint;
ALTER TABLE roles ADD COLUMN is_information_governance boolean NOT NULL DEFAULT false;
UPDATE roles SET profile_id=(SELECT id FROM profiles WHERE code='ALL_PRIVS');
ALTER TABLE roles ALTER COLUMN profile_id SET NOT NULL;
ALTER TABLE roles ADD CONSTRAINT roles_profile_fk FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE RESTRICT;
CREATE INDEX roles_profile_id_idx ON roles(profile_id);
CREATE INDEX roles_governance_clearance_idx ON roles(is_information_governance,security_level_id) WHERE is_information_governance;

CREATE OR REPLACE FUNCTION default_role_profile()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.profile_id IS NULL THEN
        SELECT id INTO NEW.profile_id FROM profiles WHERE code='ALL_PRIVS';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER roles_default_profile BEFORE INSERT ON roles
FOR EACH ROW EXECUTE FUNCTION default_role_profile();

CREATE OR REPLACE FUNCTION touch_authorization_catalogue()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.date_updated := CURRENT_TIMESTAMP;
    NEW.version := OLD.version + 1;
    RETURN NEW;
END;
$$;
CREATE TRIGGER privileges_touch BEFORE UPDATE ON privileges FOR EACH ROW EXECUTE FUNCTION touch_authorization_catalogue();
CREATE TRIGGER profiles_touch BEFORE UPDATE ON profiles FOR EACH ROW EXECUTE FUNCTION touch_authorization_catalogue();

CREATE TRIGGER privileges_record_history AFTER INSERT OR UPDATE OR DELETE ON privileges
FOR EACH ROW EXECUTE FUNCTION record_entity_history('privilege');
CREATE TRIGGER profiles_record_history AFTER INSERT OR UPDATE OR DELETE ON profiles
FOR EACH ROW EXECUTE FUNCTION record_entity_history('profile');
CREATE TRIGGER profile_privileges_record_history AFTER INSERT OR UPDATE OR DELETE ON profile_privileges
FOR EACH ROW EXECUTE FUNCTION record_entity_history('profile_privilege');

SELECT append_domain_event(
    'profile', profile.id, 'ROLE_PROFILE_BACKFILL_COMPLETED',
    jsonb_build_object(
        'profile_code', profile.code,
        'role_count', (SELECT count(*) FROM roles),
        'privilege_count', (SELECT count(*) FROM privileges),
        'unassigned_role_count', (SELECT count(*) FROM roles WHERE profile_id IS NULL)
    ),
    'Assign the compatibility profile before enforcing the non-null role profile reference'
)
FROM profiles profile WHERE profile.code='ALL_PRIVS';

INSERT INTO schema_migrations(version) VALUES ('033_add_privileges_profiles_and_role_authorization');
COMMIT;
