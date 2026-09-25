BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 016',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Add dedicated Text Indexers administration privilege',true),
       set_config('app.event_metadata','{"migration":"016_add_text_indexer_administration_privilege"}',true);

INSERT INTO privileges(code,name,description,category,is_reserved,account_type_restriction)
VALUES ('identity.text_indexers.administer','Administer Text Indexers',
        'Create and manage non-interactive text-indexer identities and their API credentials.',
        'administration',false,'person')
ON CONFLICT DO NOTHING;

UPDATE privileges
SET name='Administer Text Indexers',
    description='Create and manage non-interactive text-indexer identities and their API credentials.',
    category='administration',
    is_reserved=false,
    account_type_restriction='person'
WHERE lower(code)=lower('identity.text_indexers.administer');

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id
FROM profiles profile CROSS JOIN privileges privilege
WHERE profile.code IN ('ALL_PRIVS','SYS_ADMIN')
  AND privilege.code='identity.text_indexers.administer'
ON CONFLICT DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('016_add_text_indexer_administration_privilege')
ON CONFLICT(version) DO NOTHING;

COMMIT;
