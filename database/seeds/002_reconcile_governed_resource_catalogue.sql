BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Canonical catalogue reconciliation', true),
       set_config('app.event_source', 'seeding', true),
       set_config(
           'app.change_reason',
           'Reconcile canonical governed resource privileges after a data-only restore',
           true
       );

INSERT INTO privileges(code,name,description,category)
VALUES
 ('aggregation.vital_status.change','Change Aggregation Vital Status','Governed change of aggregation vital status.','aggregation'),
 ('record.vital_status.change','Change Record Vital Status','Governed change of record vital status.','record'),
 ('aggregation.location.change','Change Aggregation Location','Governed change of aggregation assigned or current location.','aggregation')
ON CONFLICT DO NOTHING;

INSERT INTO permissions(code,name,description,resource_type)
VALUES
 ('aggregation.vital_status.change','Change Aggregation Vital Status','Governed change of aggregation vital status.','aggregation'),
 ('record.vital_status.change','Change Record Vital Status','Governed change of record vital status.','record'),
 ('aggregation.location.change','Change Aggregation Location','Governed change of aggregation assigned or current location.','aggregation')
ON CONFLICT DO NOTHING;

INSERT INTO privilege_dependencies(privilege_id,required_privilege_id)
SELECT dependent.id,required.id
FROM privileges dependent
JOIN privileges required ON required.code=CASE
    WHEN dependent.code LIKE 'aggregation.%' THEN 'aggregation.view'
    ELSE 'record.view'
END
WHERE dependent.code IN (
    'aggregation.vital_status.change',
    'record.vital_status.change',
    'aggregation.location.change'
)
ON CONFLICT DO NOTHING;

INSERT INTO permission_dependencies(permission_id,required_permission_id)
SELECT dependent.id,required.id
FROM permissions dependent
JOIN permissions required ON required.code=CASE
    WHEN dependent.resource_type='aggregation' THEN 'aggregation.view'
    ELSE 'record.view'
END
WHERE dependent.code IN (
    'aggregation.vital_status.change',
    'record.vital_status.change',
    'aggregation.location.change'
)
ON CONFLICT DO NOTHING;

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id
FROM profiles profile CROSS JOIN privileges privilege
WHERE profile.code IN ('ALL_PRIVS','INFO_GOV_MGR','INFO_GOV_OFFICER')
  AND privilege.code IN (
      'aggregation.vital_status.change',
      'record.vital_status.change',
      'aggregation.location.change'
  )
ON CONFLICT DO NOTHING;

COMMIT;
