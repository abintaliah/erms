BEGIN;
SELECT set_config('app.event_source', 'seeding',true);
-- Feature catalogue only; activation is a separately attributed administrator operation.
INSERT INTO system_notification_producers(producer_code,feature_code,event_type,required_for_business_commit,contract_version,contract_definition) VALUES
('holds.responsibility_assigned','holds','responsibility_assigned',false,1,'{"audience_modes": ["newly_assigned_person"], "resource_link_kinds": [], "resource_configuration": null, "placeholders": {"hold_id": {"type": "integer", "max_length": 1000}, "user_id": {"type": "integer", "max_length": 1000}}}'::jsonb),
('holds.approaching_end','holds','approaching_end',false,1,'{"audience_modes": ["current_responsible_people"], "resource_link_kinds": [], "resource_configuration": null, "placeholders": {"hold_id": {"type": "integer", "max_length": 1000}, "end_date": {"type": "datetime", "max_length": 1000}}}'::jsonb)
ON CONFLICT (producer_code) DO NOTHING;
-- Fill missing metadata only; preserve existing local wording and configuration.
UPDATE system_notification_producers p SET name=COALESCE(p.name,n.name),
 translations=COALESCE(p.translations,'{}'::jsonb) ||
 CASE WHEN EXISTS(SELECT 1 FROM supported_languages WHERE language_tag='ar' AND is_enabled)
 THEN jsonb_build_object('ar', jsonb_build_object('name',n.ar_name) || COALESCE(p.translations->'ar','{}'::jsonb))
 ELSE '{}'::jsonb END
FROM (VALUES
 ('holds.approaching_end','Legal hold approaching expiry','اقتراب انتهاء تعليق قنوني'),
 ('holds.responsibility_assigned','Legal hold responsibility assigned','إسناد مسؤولية بشأن تعليق قنوني')
) AS n(code,name,ar_name)
WHERE p.producer_code=n.code AND (p.name IS NULL OR (
 EXISTS(SELECT 1 FROM supported_languages WHERE language_tag='ar' AND is_enabled)
 AND p.translations->'ar'->>'name' IS NULL));
COMMIT;
