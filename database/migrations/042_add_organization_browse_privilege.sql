BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 042',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Add organization browsing as a distinct global privilege',true),
       set_config('app.event_metadata','{"migration":"042_add_organization_browse_privilege"}',true);

INSERT INTO privileges(code,name,description,category,is_reserved)
VALUES (
    'organization.browse',
    'Browse Organization Structure',
    'Browse the organization hierarchy and view concise organization-unit, role, and user summaries.',
    'administration',
    false
)
ON CONFLICT DO NOTHING;

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id
FROM profiles profile
CROSS JOIN privileges privilege
WHERE privilege.code='organization.browse'
ON CONFLICT (profile_id,privilege_id) DO NOTHING;

INSERT INTO schema_migrations(version)
VALUES ('042_add_organization_browse_privilege')
ON CONFLICT (version) DO NOTHING;

COMMIT;
