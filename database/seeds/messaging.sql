BEGIN;

-- Run separately after schema creation or migration 033.
SELECT set_config('app.actor_type','automated_process',true),
 set_config('app.actor_name','Messaging catalogue seed',true),
 set_config('app.event_source', 'seeding',true),
 set_config('app.change_reason','Seed approved messaging privileges',true);
INSERT INTO privileges(code,name,description,category,is_reserved,account_type_restriction) VALUES
 ('messaging.user_messages.exchange','Exchange messages','Send and receive human-authored messages.','administration',false,'person'),
 ('messaging.monitor','Monitor messaging','Read sanitized messaging operational health.','administration',false,'person'),
 ('messaging.notifications.administer','Administer notifications','Configure registered notification producers and controlled tests.','administration',false,'person')
ON CONFLICT DO NOTHING;
INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT p.id,v.id FROM profiles p CROSS JOIN privileges v
WHERE (p.code='ALL_PRIVS' AND v.code LIKE 'messaging.%')
 OR (p.code='SYS_ADMIN' AND v.code IN ('messaging.monitor','messaging.notifications.administer'))
ON CONFLICT DO NOTHING;

COMMIT;
