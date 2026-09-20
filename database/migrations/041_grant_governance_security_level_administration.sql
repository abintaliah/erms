BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 041',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Grant security-level administration to built-in information-governance profiles',true),
       set_config('app.event_metadata','{"migration":"041_grant_governance_security_level_administration"}',true);

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id
FROM profiles profile
CROSS JOIN privileges privilege
WHERE profile.code IN ('INFO_GOV_MGR','INFO_GOV_OFFICER')
  AND privilege.code='security_levels.administer'
ON CONFLICT (profile_id,privilege_id) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('041_grant_governance_security_level_administration')
ON CONFLICT (version) DO NOTHING;

COMMIT;
