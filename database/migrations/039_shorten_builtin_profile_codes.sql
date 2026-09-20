BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 039',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Shorten built-in profile codes for clearer administration',true),
       set_config('app.event_metadata','{"migration":"039_shorten_builtin_profile_codes"}',true);

DO $$
BEGIN
    IF (EXISTS (SELECT 1 FROM profiles WHERE code='ALL_PRIVILEGES')
        AND EXISTS (SELECT 1 FROM profiles WHERE code='ALL_PRIVS'))
       OR (EXISTS (SELECT 1 FROM profiles WHERE code='INFORMATION_GOVERNANCE_CUSTODIAN')
           AND EXISTS (SELECT 1 FROM profiles WHERE code='INFO_GOV'))
       OR (EXISTS (SELECT 1 FROM profiles WHERE code='SYSTEM_ADMINISTRATOR')
           AND EXISTS (SELECT 1 FROM profiles WHERE code='SYS_ADMIN')) THEN
        RAISE EXCEPTION 'a target built-in profile code is already in use';
    END IF;
END $$;

UPDATE profiles
SET code = CASE code
    WHEN 'ALL_PRIVILEGES' THEN 'ALL_PRIVS'
    WHEN 'INFORMATION_GOVERNANCE_CUSTODIAN' THEN 'INFO_GOV'
    WHEN 'SYSTEM_ADMINISTRATOR' THEN 'SYS_ADMIN'
END
WHERE code IN (
    'ALL_PRIVILEGES',
    'INFORMATION_GOVERNANCE_CUSTODIAN',
    'SYSTEM_ADMINISTRATOR'
);

CREATE OR REPLACE FUNCTION default_role_profile()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.profile_id IS NULL THEN
        SELECT id INTO NEW.profile_id FROM profiles WHERE code='ALL_PRIVS';
    END IF;
    RETURN NEW;
END;
$$;

INSERT INTO schema_migrations(version)
VALUES ('039_shorten_builtin_profile_codes')
ON CONFLICT (version) DO NOTHING;

COMMIT;
