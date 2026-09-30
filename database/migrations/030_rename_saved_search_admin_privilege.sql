BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Database migration 030', true),
       set_config('app.event_source', 'migration', true),
       set_config('app.change_reason', 'Rename and align saved-search administration privilege', true);

UPDATE privileges
   SET code = 'search.saved_search.administer',
       name = 'Administer Saved Searches',
       description = 'Inspect and modify any saved search and manage any eligible role or organizational-unit audience.'
 WHERE code = 'search.saved_search.administrator';

INSERT INTO profile_privileges(profile_id, privilege_id)
SELECT profile.id, privilege.id
  FROM profiles profile
 CROSS JOIN privileges privilege
 WHERE profile.code IN ('ALL_PRIVS', 'SYS_ADMIN', 'INFO_GOV_MGR', 'INFO_GOV_OFFICER')
   AND privilege.code IN (
       'search.saved_search.save',
       'search.saved_search.administer',
       'search.saved_search.delete'
   )
ON CONFLICT DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('030_rename_saved_search_admin_privilege')
ON CONFLICT(version) DO NOTHING;

COMMIT;
