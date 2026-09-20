BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 040',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Add distinct information-governance manager and officer profiles',true),
       set_config('app.event_metadata','{"migration":"040_add_information_governance_profiles"}',true);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM profiles WHERE code='INFO_GOV')
       AND EXISTS (SELECT 1 FROM profiles WHERE code='INFO_GOV_MGR') THEN
        RAISE EXCEPTION 'both the former and replacement manager profile codes exist';
    END IF;
END $$;

UPDATE profiles
SET code='INFO_GOV_MGR',
    name='Information Governance Manager',
    description='Universal governed-information custody and classification administration, subject to privilege and clearance gates',
    is_system=true
WHERE code='INFO_GOV';

UPDATE profiles
SET name='Information Governance Manager',
    description='Universal governed-information custody and classification administration, subject to privilege and clearance gates',
    is_system=true
WHERE code='INFO_GOV_MGR';

INSERT INTO profiles(code,name,description,is_system)
VALUES (
    'INFO_GOV_OFFICER',
    'Information Governance Officer',
    'Universal governed-information custody and classification administration, subject to privilege and clearance gates',
    true
)
ON CONFLICT (lower(code)) DO UPDATE
SET name=EXCLUDED.name,
    description=EXCLUDED.description,
    is_system=true;

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT officer.id,membership.privilege_id
FROM profiles officer
JOIN profiles manager ON manager.code='INFO_GOV_MGR'
JOIN profile_privileges membership ON membership.profile_id=manager.id
WHERE officer.code='INFO_GOV_OFFICER'
ON CONFLICT (profile_id,privilege_id) DO NOTHING;

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id
FROM profiles profile
CROSS JOIN privileges privilege
WHERE profile.code IN ('INFO_GOV_MGR','INFO_GOV_OFFICER')
  AND privilege.code IN ('classifications.administer','security_levels.administer')
ON CONFLICT (profile_id,privilege_id) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('040_add_information_governance_profiles')
ON CONFLICT (version) DO NOTHING;

COMMIT;
