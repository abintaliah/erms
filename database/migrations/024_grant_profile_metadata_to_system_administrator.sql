BEGIN;

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id
  FROM profiles profile
  JOIN privileges privilege ON privilege.code='profile.modify_metadata'
 WHERE profile.code='SYS_ADMIN'
ON CONFLICT DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('024_grant_profile_metadata_to_system_administrator')
ON CONFLICT DO NOTHING;

COMMIT;
