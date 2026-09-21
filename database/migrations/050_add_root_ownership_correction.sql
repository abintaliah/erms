BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 050',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Add governed root ownership correction',true),
       set_config('app.event_metadata','{"migration":"050_add_root_ownership_correction"}',true);

INSERT INTO privileges(code,name,description,category,is_reserved)
VALUES (
  'organization.ownership.correct',
  'Correct Organizational Ownership',
  'Correct a mistaken root aggregation owner and propagate the correction through its holdings.',
  'exceptional',false
);

INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id FROM profiles profile CROSS JOIN privileges privilege
WHERE profile.code IN ('ALL_PRIVS','INFO_GOV_MGR','INFO_GOV_OFFICER')
  AND privilege.code='organization.ownership.correct'
ON CONFLICT (profile_id,privilege_id) DO NOTHING;

CREATE OR REPLACE FUNCTION enforce_aggregation_ownership()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parent_owner bigint;
    target_owner bigint;
    confirmed boolean := COALESCE(NULLIF(current_setting('app.ownership_move_confirmed', true), '')::boolean, false);
    propagating boolean := current_setting('app.ownership_propagation', true) = 'authorized';
    correcting boolean := current_setting('app.ownership_correction_authorized', true) = 'authorized';
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.parent_aggregation_id IS NOT NULL THEN
            SELECT owning_org_unit_id INTO STRICT parent_owner
            FROM aggregations WHERE id = NEW.parent_aggregation_id FOR UPDATE;
            NEW.owning_org_unit_id := parent_owner;
        ELSIF NEW.owning_org_unit_id IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='23502', MESSAGE='root aggregation ownership is required';
        END IF;
        RETURN NEW;
    END IF;
    IF propagating THEN RETURN NEW; END IF;

    IF correcting THEN
        IF OLD.parent_aggregation_id IS NOT NULL OR NEW.parent_aggregation_id IS NOT NULL
           OR NEW.parent_aggregation_id IS DISTINCT FROM OLD.parent_aggregation_id
           OR NULLIF(btrim(current_setting('app.change_reason', true)), '') IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='ownership correction is restricted to root aggregations and requires a reason';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.parent_aggregation_id IS NOT DISTINCT FROM OLD.parent_aggregation_id THEN
        IF NEW.owning_org_unit_id IS DISTINCT FROM OLD.owning_org_unit_id THEN
            RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='owning_org_unit_id cannot be changed directly';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.parent_aggregation_id IS NULL THEN
        target_owner := OLD.owning_org_unit_id;
    ELSE
        SELECT owning_org_unit_id INTO STRICT target_owner
        FROM aggregations WHERE id = NEW.parent_aggregation_id FOR UPDATE;
    END IF;

    IF target_owner IS DISTINCT FROM OLD.owning_org_unit_id AND (
        NOT confirmed OR NULLIF(btrim(current_setting('app.change_reason', true)), '') IS NULL
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE='ownership-changing aggregation moves require a reason and explicit confirmation';
    END IF;
    NEW.owning_org_unit_id := target_owner;
    RETURN NEW;
END;
$$;

INSERT INTO schema_migrations(version) VALUES ('050_add_root_ownership_correction');
COMMIT;
