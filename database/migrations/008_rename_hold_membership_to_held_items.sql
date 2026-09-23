BEGIN;

UPDATE privileges
SET code='holds.held_items.manage_all',
    name='Manage All Legal Hold Items',
    description='Add or remove held items from any legal hold.'
WHERE code='holds.membership.manage_all';

CREATE OR REPLACE FUNCTION current_hold_actor_is_manager(p_hold_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS(
        SELECT 1
        FROM holds hold
        JOIN users actor
          ON actor.id=NULLIF(current_setting('app.user_id',true),'')::bigint
        WHERE hold.id=p_hold_id
          AND actor.account_type='person'
          AND actor.date_deactivated IS NULL
          AND actor.date_suspended IS NULL
          AND (
              user_has_global_privilege(actor.id,'holds.administer')
              OR user_has_global_privilege(actor.id,'holds.held_items.manage_all')
              OR hold.owner_user_id=actor.id
              OR EXISTS (
                  SELECT 1
                  FROM hold_contributors contributor
                  WHERE contributor.hold_id=hold.id
                    AND contributor.user_id=actor.id
              )
          )
    )
$$;

CREATE OR REPLACE FUNCTION enforce_hold_assignment_policy() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_hold_id bigint:=CASE WHEN TG_OP='DELETE' THEN OLD.hold_id ELSE NEW.hold_id END;
BEGIN
    PERFORM lock_hold_policy_exclusive();
    IF NULLIF(btrim(current_setting('app.change_reason',true)),'') IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_change_reason_required';
    END IF;
    IF NOT current_hold_actor_is_manager(target_hold_id) THEN
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_held_item_manager_required';
    END IF;
    IF TG_OP='INSERT' AND NEW.assigned_by_user_id IS NULL THEN
        NEW.assigned_by_user_id:=NULLIF(current_setting('app.user_id',true),'')::bigint;
    END IF;
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;

INSERT INTO schema_migrations(version)
VALUES ('008_rename_hold_membership_to_held_items')
ON CONFLICT (version) DO NOTHING;

COMMIT;
