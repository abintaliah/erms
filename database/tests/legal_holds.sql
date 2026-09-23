BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Legal hold database test',true),
       set_config('app.event_source','test',true);

DO $$
DECLARE
    unit_id bigint;
    scheme_id bigint;
    classification_id bigint;
    owner_id bigint;
    contributor_id bigint;
    global_manager_id bigint;
    global_manager_role_id bigint;
    outsider_id bigint;
    root_id bigint;
    child_id bigint;
    free_root_id bigint;
    record_id bigint;
    expired_record_id bigint;
    component_id bigint;
    active_hold_id bigint;
    preserving_hold_id bigint;
    scheduled_hold_id bigint;
    expired_hold_id bigint;
    rejected boolean;
BEGIN
    INSERT INTO org_units(code,name) VALUES ('HOLD-TEST','Legal Hold Test') RETURNING id INTO unit_id;
    INSERT INTO classification_schemes(code,title,date_published)
    VALUES ('HOLD-TEST','Legal Hold Test',CURRENT_TIMESTAMP) RETURNING id INTO scheme_id;
    INSERT INTO classifications(classification_scheme_id,code,title,is_terminal)
    VALUES (scheme_id,'HOLD-01','Legal Hold Test',true) RETURNING id INTO classification_id;
    INSERT INTO classification_retention_rules(
        classification_id,current_period_years,intermediate_period_years,final_disposition
    ) VALUES (classification_id,1,0,'destruction');

    INSERT INTO users(name,email) VALUES ('Hold Owner','hold-owner@test.invalid') RETURNING id INTO owner_id;
    INSERT INTO users(name,email) VALUES ('Hold Contributor','hold-contributor@test.invalid') RETURNING id INTO contributor_id;
    INSERT INTO users(name,email) VALUES ('Global Hold Membership Manager','hold-global-manager@test.invalid') RETURNING id INTO global_manager_id;
    INSERT INTO users(name,email) VALUES ('Hold Outsider','hold-outsider@test.invalid') RETURNING id INTO outsider_id;
    INSERT INTO roles(org_unit_id,code,name,profile_id,is_information_governance)
    VALUES (unit_id,'HOLD-GLOBAL-MANAGER','Global Hold Membership Manager',
            (SELECT id FROM profiles WHERE code='INFO_GOV_OFFICER'),true)
    RETURNING id INTO global_manager_role_id;
    INSERT INTO user_role_assignments(user_id,role_id)
    VALUES (global_manager_id,global_manager_role_id);

    IF NOT EXISTS (
        SELECT 1
        FROM profile_privileges mapping
        JOIN profiles profile ON profile.id=mapping.profile_id
        JOIN privileges privilege ON privilege.id=mapping.privilege_id
        WHERE profile.code IN ('INFO_GOV_MGR','INFO_GOV_OFFICER')
          AND privilege.code='holds.membership.manage_all'
        GROUP BY privilege.code
        HAVING count(*)=2
    ) THEN
        RAISE EXCEPTION 'built-in information-governance profiles lack global hold membership authority';
    END IF;

    INSERT INTO aggregations(aggregation_number,title,classification_id,owning_org_unit_id)
    VALUES ('HOLD-ROOT','Held root',classification_id,unit_id) RETURNING id INTO root_id;
    INSERT INTO aggregations(parent_aggregation_id,aggregation_number,title)
    VALUES (root_id,'HOLD-CHILD','Held child') RETURNING id INTO child_id;
    INSERT INTO aggregations(aggregation_number,title,classification_id,owning_org_unit_id)
    VALUES ('HOLD-FREE','Free root',classification_id,unit_id) RETURNING id INTO free_root_id;
    INSERT INTO records(aggregation_id,record_number,title)
    VALUES (child_id,'HOLD-REC','Held record') RETURNING id INTO record_id;
    INSERT INTO records(aggregation_id,record_number,title)
    VALUES (free_root_id,'HOLD-EXPIRED-REC','Expired hold record') RETURNING id INTO expired_record_id;
    INSERT INTO digital_components(
        record_id,component_order,file_name,mime_type,size_in_bytes,checksum_algo,checksum_value
    ) VALUES (record_id,1,'held.pdf','application/pdf',1,'SHA-256',repeat('a',64))
    RETURNING id INTO component_id;

    INSERT INTO holds(code,name,valid_from,owner_user_id)
    VALUES ('ACTIVE','Active hold',CURRENT_TIMESTAMP-interval '1 day',owner_id)
    RETURNING id INTO active_hold_id;
    INSERT INTO holds(code,name,valid_from,owner_user_id,preserve_resource_state)
    VALUES ('PRESERVE','Preserving hold',CURRENT_TIMESTAMP-interval '1 day',owner_id,true)
    RETURNING id INTO preserving_hold_id;
    INSERT INTO holds(code,name,valid_from,valid_to,owner_user_id)
    VALUES ('SCHEDULED','Scheduled hold',CURRENT_TIMESTAMP+interval '1 day',CURRENT_TIMESTAMP+interval '2 days',owner_id)
    RETURNING id INTO scheduled_hold_id;
    INSERT INTO holds(code,name,valid_from,valid_to,owner_user_id)
    VALUES ('EXPIRED','Expired hold',CURRENT_TIMESTAMP-interval '2 days',CURRENT_TIMESTAMP-interval '1 day',owner_id)
    RETURNING id INTO expired_hold_id;

    IF NOT hold_is_effective(active_hold_id,CURRENT_TIMESTAMP)
       OR hold_is_effective(scheduled_hold_id,CURRENT_TIMESTAMP)
       OR hold_is_effective(expired_hold_id,CURRENT_TIMESTAMP)
       OR NOT hold_is_effective(scheduled_hold_id,(SELECT valid_from FROM holds WHERE id=scheduled_hold_id))
       OR hold_is_effective(scheduled_hold_id,(SELECT valid_to FROM holds WHERE id=scheduled_hold_id)) THEN
        RAISE EXCEPTION 'hold effective-period boundary semantics are incorrect';
    END IF;

    PERFORM set_config('app.user_id',owner_id::text,true);
    PERFORM set_config('app.change_reason','Apply test hold',true);
    INSERT INTO hold_aggregation_assignments(hold_id,aggregation_id)
    VALUES (active_hold_id,root_id);
    INSERT INTO hold_record_assignments(hold_id,record_id)
    VALUES (expired_hold_id,expired_record_id);

    IF NOT resource_has_effective_hold('aggregation',child_id)
       OR NOT resource_has_effective_hold('record',record_id)
       OR resource_has_effective_hold('record',expired_record_id) THEN
        RAISE EXCEPTION 'direct, inherited, or expired effective hold calculation is incorrect';
    END IF;
    IF (SELECT count(*) FROM effective_holds_for_record(record_id))<>1 THEN
        RAISE EXCEPTION 'effective hold result was not deduplicated';
    END IF;

    rejected:=false;
    BEGIN DELETE FROM records WHERE id=record_id;
    EXCEPTION WHEN SQLSTATE 'P0001' THEN
        rejected:=SQLERRM='effective_hold_prevents_deletion';
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'effective hold did not block record deletion'; END IF;

    rejected:=false;
    BEGIN
        INSERT INTO digital_components(
            record_id,component_order,file_name,mime_type,size_in_bytes,checksum_algo,checksum_value
        ) VALUES (record_id,2,'new.pdf','application/pdf',1,'SHA-256',repeat('b',64));
    EXCEPTION WHEN SQLSTATE 'P0001' THEN
        rejected:=SQLERRM='effective_hold_prevents_component_addition';
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'effective hold did not block component addition'; END IF;

    rejected:=false;
    BEGIN UPDATE digital_components SET component_order=2 WHERE id=component_id;
    EXCEPTION WHEN SQLSTATE 'P0001' THEN rejected:=SQLERRM='effective_hold_prevents_component_reordering';
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'effective hold did not block component mutation'; END IF;

    PERFORM set_config('app.change_reason','Delete expired resource',true);
    DELETE FROM records WHERE id=expired_record_id;
    IF EXISTS(SELECT 1 FROM hold_record_assignments assignment
              WHERE assignment.record_id=expired_record_id) THEN
        RAISE EXCEPTION 'expired assignment did not cascade after permitted resource deletion';
    END IF;

    PERFORM set_config('app.change_reason','Add contributor',true);
    INSERT INTO hold_contributors(hold_id,user_id) VALUES (active_hold_id,contributor_id);
    PERFORM set_config('app.user_id',contributor_id::text,true);
    IF NOT current_hold_actor_is_manager(active_hold_id) THEN
        RAISE EXCEPTION 'active contributor lacks hold membership authority';
    END IF;
    PERFORM set_config('app.user_id',global_manager_id::text,true);
    IF NOT current_hold_actor_is_manager(active_hold_id) THEN
        RAISE EXCEPTION 'global hold membership manager lacks hold membership authority';
    END IF;
    PERFORM set_config('app.user_id',owner_id::text,true);
    DELETE FROM users WHERE id=contributor_id;
    IF EXISTS(SELECT 1 FROM hold_contributors WHERE user_id=contributor_id) THEN
        RAISE EXCEPTION 'contributor user deletion did not cascade';
    END IF;
    rejected:=false;
    BEGIN DELETE FROM users WHERE id=owner_id;
    EXCEPTION WHEN foreign_key_violation THEN rejected:=true;
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'hold owner deletion was not restricted'; END IF;

    PERFORM set_config('app.user_id',outsider_id::text,true);
    rejected:=false;
    BEGIN UPDATE aggregations SET parent_aggregation_id=free_root_id WHERE id=child_id;
    EXCEPTION WHEN SQLSTATE 'P0001' THEN
        rejected:=SQLERRM='hold_membership_required_for_held_move';
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'unrelated user moved a resource out of held coverage'; END IF;

    PERFORM set_config('app.user_id',owner_id::text,true);
    UPDATE aggregations SET parent_aggregation_id=free_root_id WHERE id=child_id;
    UPDATE aggregations SET parent_aggregation_id=root_id WHERE id=child_id;

    PERFORM set_config('app.change_reason','Apply state preservation',true);
    INSERT INTO hold_aggregation_assignments(hold_id,aggregation_id)
    VALUES (preserving_hold_id,child_id);
    IF NOT resource_state_changes_blocked('record',record_id) THEN
        RAISE EXCEPTION 'inherited enhanced state preservation was not derived';
    END IF;
    rejected:=false;
    BEGIN UPDATE records SET title='Changed while frozen' WHERE id=record_id;
    EXCEPTION WHEN SQLSTATE 'P0001' THEN
        rejected:=SQLERRM='effective_hold_prevents_metadata_change';
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'enhanced hold did not freeze record metadata'; END IF;

    rejected:=false;
    BEGIN DELETE FROM holds WHERE id=active_hold_id;
    EXCEPTION WHEN SQLSTATE 'P0001' THEN rejected:=SQLERRM='hold_not_empty';
    END;
    IF NOT rejected THEN RAISE EXCEPTION 'non-empty hold deletion was not restricted'; END IF;

    IF NOT EXISTS(SELECT 1 FROM event_history WHERE entity_type='hold' AND operation='CREATE')
       OR NOT EXISTS(SELECT 1 FROM event_history WHERE entity_type='hold_aggregation_assignment'
                     AND operation='CREATE' AND reason='Apply test hold'
                     AND metadata#>>'{reference_snapshots,hold,code}'='ACTIVE')
       OR NOT EXISTS(SELECT 1 FROM event_history WHERE entity_type='hold'
                     AND operation='RESOURCE_ADDED_TO_HOLD' AND entity_id=active_hold_id)
       OR NOT EXISTS(SELECT 1 FROM event_history WHERE entity_type='aggregation'
                     AND operation='RESOURCE_ADDED_TO_HOLD' AND entity_id=root_id) THEN
        RAISE EXCEPTION 'hold row history was not recorded with its reason';
    END IF;
END;
$$;

ROLLBACK;
