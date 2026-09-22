-- Legal holds: persistence and non-bypassable policy enforcement.
BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 005',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Install legal holds persistence and enforcement',true),
       set_config('app.event_metadata','{"migration":"005_add_legal_holds_foundation"}',true);

CREATE TABLE holds (
    id                      bigserial PRIMARY KEY,
    code                    text NOT NULL,
    name                    text NOT NULL,
    description             text,
    valid_from              timestamptz NOT NULL,
    valid_to                timestamptz,
    owner_user_id           bigint NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    preserve_resource_state boolean NOT NULL DEFAULT false,
    date_created            timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated            timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version                 bigint NOT NULL DEFAULT 1,
    CONSTRAINT holds_code_valid CHECK (code=btrim(code) AND code<>'' AND char_length(code)<=100),
    CONSTRAINT holds_name_valid CHECK (name=btrim(name) AND name<>'' AND char_length(name)<=300),
    CONSTRAINT holds_description_length CHECK (description IS NULL OR char_length(description)<=4000),
    CONSTRAINT holds_dates_in_order CHECK (valid_to IS NULL OR valid_to>valid_from),
    CONSTRAINT holds_version_positive CHECK (version>0)
);
CREATE UNIQUE INDEX holds_code_ci_unique ON holds(lower(code));
CREATE INDEX holds_effective_period_idx ON holds(valid_from,valid_to,id);
CREATE INDEX holds_owner_idx ON holds(owner_user_id,id);

CREATE TABLE hold_contributors (
    id           bigserial PRIMARY KEY,
    hold_id      bigint NOT NULL REFERENCES holds(id) ON DELETE CASCADE,
    user_id      bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date_created timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version      bigint NOT NULL DEFAULT 1 CHECK (version>0),
    CONSTRAINT hold_contributors_unique UNIQUE(hold_id,user_id)
);
CREATE INDEX hold_contributors_user_idx ON hold_contributors(user_id,hold_id);

CREATE TABLE hold_aggregation_assignments (
    id                  bigserial PRIMARY KEY,
    hold_id             bigint NOT NULL REFERENCES holds(id) ON DELETE RESTRICT,
    aggregation_id      bigint NOT NULL REFERENCES aggregations(id) ON DELETE CASCADE,
    assigned_at         timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by_user_id bigint REFERENCES users(id) ON DELETE SET NULL,
    version             bigint NOT NULL DEFAULT 1 CHECK (version>0),
    CONSTRAINT hold_aggregation_assignments_unique UNIQUE(hold_id,aggregation_id)
);
CREATE INDEX hold_aggregation_assignments_resource_idx
    ON hold_aggregation_assignments(aggregation_id,hold_id);

CREATE TABLE hold_record_assignments (
    id                  bigserial PRIMARY KEY,
    hold_id             bigint NOT NULL REFERENCES holds(id) ON DELETE RESTRICT,
    record_id           bigint NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    assigned_at         timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by_user_id bigint REFERENCES users(id) ON DELETE SET NULL,
    version             bigint NOT NULL DEFAULT 1 CHECK (version>0),
    CONSTRAINT hold_record_assignments_unique UNIQUE(hold_id,record_id)
);
CREATE INDEX hold_record_assignments_resource_idx
    ON hold_record_assignments(record_id,hold_id);

INSERT INTO privileges(code,name,description,category,is_reserved)
VALUES ('holds.administer','Administer Legal Holds',
        'Create, update, and delete legal holds and manage their owners and contributors.',
        'administration',false)
ON CONFLICT DO NOTHING;
INSERT INTO profile_privileges(profile_id,privilege_id)
SELECT profile.id,privilege.id
FROM profiles profile CROSS JOIN privileges privilege
WHERE profile.code='ALL_PRIVS'
  AND privilege.code='holds.administer'
ON CONFLICT DO NOTHING;

CREATE FUNCTION hold_is_effective(p_hold_id bigint,p_at_time timestamptz DEFAULT statement_timestamp())
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT COALESCE(
        (hold.valid_from<=p_at_time AND (hold.valid_to IS NULL OR p_at_time<hold.valid_to)),
        false
    ) FROM holds hold WHERE hold.id=p_hold_id
$$;

CREATE FUNCTION effective_holds_for_aggregation(
    p_aggregation_id bigint,p_at_time timestamptz DEFAULT statement_timestamp()
) RETURNS TABLE(
    hold_id bigint,code text,name text,preserve_resource_state boolean,
    is_direct boolean,is_inherited boolean,nearest_assigned_aggregation_id bigint
) LANGUAGE sql STABLE AS $$
    WITH RECURSIVE ancestry AS (
        SELECT aggregation.id,aggregation.parent_aggregation_id,0 AS depth
        FROM aggregations aggregation WHERE aggregation.id=p_aggregation_id
        UNION ALL
        SELECT parent.id,parent.parent_aggregation_id,child.depth+1
        FROM aggregations parent JOIN ancestry child ON child.parent_aggregation_id=parent.id
    ), matched AS (
        SELECT assignment.hold_id,ancestry.id AS assigned_aggregation_id,ancestry.depth
        FROM ancestry
        JOIN hold_aggregation_assignments assignment ON assignment.aggregation_id=ancestry.id
    )
    SELECT hold.id,hold.code,hold.name,hold.preserve_resource_state,
           bool_or(matched.depth=0),bool_or(matched.depth>0),
           (array_agg(matched.assigned_aggregation_id ORDER BY matched.depth))[1]
    FROM matched JOIN holds hold ON hold.id=matched.hold_id
    WHERE hold.valid_from<=p_at_time AND (hold.valid_to IS NULL OR p_at_time<hold.valid_to)
    GROUP BY hold.id,hold.code,hold.name,hold.preserve_resource_state
$$;

CREATE FUNCTION effective_holds_for_record(
    p_record_id bigint,p_at_time timestamptz DEFAULT statement_timestamp()
) RETURNS TABLE(
    hold_id bigint,code text,name text,preserve_resource_state boolean,
    is_direct boolean,is_inherited boolean,nearest_assigned_aggregation_id bigint
) LANGUAGE sql STABLE AS $$
    WITH RECURSIVE record_row AS (
        SELECT id,aggregation_id FROM records WHERE id=p_record_id
    ), ancestry AS (
        SELECT aggregation.id,aggregation.parent_aggregation_id,0 AS depth
        FROM aggregations aggregation JOIN record_row ON record_row.aggregation_id=aggregation.id
        UNION ALL
        SELECT parent.id,parent.parent_aggregation_id,child.depth+1
        FROM aggregations parent JOIN ancestry child ON child.parent_aggregation_id=parent.id
    ), matched AS (
        SELECT assignment.hold_id,true AS direct,false AS inherited,
               NULL::bigint AS assigned_aggregation_id,NULL::integer AS depth
        FROM record_row JOIN hold_record_assignments assignment ON assignment.record_id=record_row.id
        UNION ALL
        SELECT assignment.hold_id,false,true,ancestry.id,ancestry.depth
        FROM ancestry
        JOIN hold_aggregation_assignments assignment ON assignment.aggregation_id=ancestry.id
    )
    SELECT hold.id,hold.code,hold.name,hold.preserve_resource_state,
           bool_or(matched.direct),bool_or(matched.inherited),
           (array_agg(matched.assigned_aggregation_id ORDER BY matched.depth NULLS LAST)
             FILTER (WHERE matched.assigned_aggregation_id IS NOT NULL))[1]
    FROM matched JOIN holds hold ON hold.id=matched.hold_id
    WHERE hold.valid_from<=p_at_time AND (hold.valid_to IS NULL OR p_at_time<hold.valid_to)
    GROUP BY hold.id,hold.code,hold.name,hold.preserve_resource_state
$$;

CREATE FUNCTION resource_has_effective_hold(
    p_resource_type text,p_resource_id bigint,p_at_time timestamptz DEFAULT statement_timestamp()
) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
BEGIN
    IF p_resource_type='aggregation' THEN
        RETURN EXISTS(SELECT 1 FROM effective_holds_for_aggregation(p_resource_id,p_at_time));
    ELSIF p_resource_type='record' THEN
        RETURN EXISTS(SELECT 1 FROM effective_holds_for_record(p_resource_id,p_at_time));
    END IF;
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='unknown hold resource type';
END;
$$;

CREATE FUNCTION resource_state_changes_blocked(
    p_resource_type text,p_resource_id bigint,p_at_time timestamptz DEFAULT statement_timestamp()
) RETURNS boolean LANGUAGE plpgsql STABLE AS $$
BEGIN
    IF p_resource_type='aggregation' THEN
        RETURN EXISTS(SELECT 1 FROM effective_holds_for_aggregation(p_resource_id,p_at_time)
                      WHERE preserve_resource_state);
    ELSIF p_resource_type='record' THEN
        RETURN EXISTS(SELECT 1 FROM effective_holds_for_record(p_resource_id,p_at_time)
                      WHERE preserve_resource_state);
    END IF;
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='unknown hold resource type';
END;
$$;

CREATE FUNCTION current_hold_actor_is_manager(p_hold_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS(
        SELECT 1 FROM holds hold JOIN users actor ON actor.id=NULLIF(current_setting('app.user_id',true),'')::bigint
        WHERE hold.id=p_hold_id AND actor.account_type='person'
          AND actor.date_deactivated IS NULL AND actor.date_suspended IS NULL
          AND (hold.owner_user_id=actor.id OR EXISTS(
              SELECT 1 FROM hold_contributors contributor
              WHERE contributor.hold_id=hold.id AND contributor.user_id=actor.id))
    )
$$;

CREATE FUNCTION lock_hold_policy_shared() RETURNS void LANGUAGE plpgsql AS $$
BEGIN PERFORM pg_advisory_xact_lock_shared(7246,1); END;
$$;
CREATE FUNCTION lock_hold_policy_exclusive() RETURNS void LANGUAGE plpgsql AS $$
BEGIN PERFORM pg_advisory_xact_lock(7246,1); END;
$$;

CREATE FUNCTION validate_hold_person_reference() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE selected_user_id bigint;
BEGIN
    IF TG_TABLE_NAME='holds' THEN
        selected_user_id:=NEW.owner_user_id;
    ELSE
        selected_user_id:=NEW.user_id;
    END IF;
    IF NOT EXISTS(SELECT 1 FROM users WHERE id=selected_user_id AND account_type='person'
                  AND date_deactivated IS NULL AND date_suspended IS NULL) THEN
        RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='hold_owner_or_contributor_must_be_active_person';
    END IF;
    IF TG_TABLE_NAME='hold_contributors' THEN
        IF EXISTS(SELECT 1 FROM holds WHERE id=NEW.hold_id AND owner_user_id=NEW.user_id) THEN
            RAISE EXCEPTION USING ERRCODE='23514',MESSAGE='hold_owner_cannot_be_contributor';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER holds_validate_owner BEFORE INSERT OR UPDATE OF owner_user_id ON holds
FOR EACH ROW EXECUTE FUNCTION validate_hold_person_reference();
CREATE TRIGGER hold_contributors_validate_user BEFORE INSERT OR UPDATE OF hold_id,user_id ON hold_contributors
FOR EACH ROW EXECUTE FUNCTION validate_hold_person_reference();

CREATE FUNCTION enforce_hold_change_reason() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE hold_created_in_transaction boolean:=false;
BEGIN
    PERFORM lock_hold_policy_exclusive();
    IF TG_TABLE_NAME='hold_contributors' AND TG_OP='DELETE' AND pg_trigger_depth()>1 THEN
        RETURN OLD;
    END IF;
    IF TG_TABLE_NAME='hold_contributors' AND TG_OP='INSERT' THEN
        SELECT xmin::text=pg_current_xact_id()::text INTO hold_created_in_transaction
        FROM holds WHERE id=NEW.hold_id;
    END IF;
    IF NOT hold_created_in_transaction
       AND NULLIF(btrim(current_setting('app.change_reason',true)),'') IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_change_reason_required';
    END IF;
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER holds_require_change_reason
BEFORE UPDATE OR DELETE ON holds FOR EACH ROW EXECUTE FUNCTION enforce_hold_change_reason();
CREATE TRIGGER hold_contributors_require_change_reason
BEFORE INSERT OR UPDATE OR DELETE ON hold_contributors FOR EACH ROW EXECUTE FUNCTION enforce_hold_change_reason();

CREATE FUNCTION enforce_hold_assignment_policy() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_hold_id bigint:=CASE WHEN TG_OP='DELETE' THEN OLD.hold_id ELSE NEW.hold_id END;
BEGIN
    PERFORM lock_hold_policy_exclusive();
    IF NULLIF(btrim(current_setting('app.change_reason',true)),'') IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_change_reason_required';
    END IF;
    IF NOT current_hold_actor_is_manager(target_hold_id) THEN
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_owner_or_contributor_required';
    END IF;
    IF TG_OP='INSERT' AND NEW.assigned_by_user_id IS NULL THEN
        NEW.assigned_by_user_id:=NULLIF(current_setting('app.user_id',true),'')::bigint;
    END IF;
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER hold_aggregation_assignments_policy
BEFORE INSERT OR UPDATE OR DELETE ON hold_aggregation_assignments
FOR EACH ROW EXECUTE FUNCTION enforce_hold_assignment_policy();
CREATE TRIGGER hold_record_assignments_policy
BEFORE INSERT OR UPDATE OR DELETE ON hold_record_assignments
FOR EACH ROW EXECUTE FUNCTION enforce_hold_assignment_policy();

CREATE FUNCTION protect_held_resource() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE blocked boolean;
DECLARE allowed_old jsonb;
DECLARE allowed_new jsonb;
BEGIN
    PERFORM lock_hold_policy_shared();
    IF TG_OP='DELETE' THEN
        IF TG_TABLE_NAME='aggregations' THEN
            WITH RECURSIVE subtree AS (
                SELECT OLD.id AS id UNION ALL
                SELECT child.id FROM aggregations child JOIN subtree parent ON child.parent_aggregation_id=parent.id
            )
            SELECT EXISTS(
                SELECT 1 FROM subtree WHERE resource_has_effective_hold('aggregation',subtree.id)
                UNION ALL
                SELECT 1 FROM records record JOIN subtree ON subtree.id=record.aggregation_id
                WHERE resource_has_effective_hold('record',record.id)
            ) INTO blocked;
        ELSE
            blocked:=resource_has_effective_hold('record',OLD.id);
        END IF;
        IF blocked THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='effective_hold_prevents_deletion'; END IF;
        RETURN OLD;
    END IF;

    IF TG_TABLE_NAME='aggregations' THEN
        blocked:=resource_state_changes_blocked('aggregation',OLD.id);
        IF NEW.parent_aggregation_id IS DISTINCT FROM OLD.parent_aggregation_id THEN
            IF blocked OR (NEW.parent_aggregation_id IS NOT NULL AND EXISTS(
                SELECT 1 FROM effective_holds_for_aggregation(NEW.parent_aggregation_id) WHERE preserve_resource_state
            )) THEN
                RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='effective_hold_prevents_metadata_change';
            END IF;
            IF EXISTS(
                WITH old_holds AS (SELECT hold_id FROM effective_holds_for_aggregation(OLD.id)),
                     new_ancestor_holds AS (
                         SELECT hold_id FROM effective_holds_for_aggregation(NEW.parent_aggregation_id)
                         UNION SELECT hold_id FROM hold_aggregation_assignments WHERE aggregation_id=OLD.id AND hold_is_effective(hold_id)
                     ), changed AS ((SELECT * FROM old_holds EXCEPT SELECT * FROM new_ancestor_holds)
                                    UNION (SELECT * FROM new_ancestor_holds EXCEPT SELECT * FROM old_holds))
                SELECT 1 FROM changed WHERE NOT current_hold_actor_is_manager(changed.hold_id)
            ) THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_membership_required_for_held_move'; END IF;
        END IF;
        IF blocked THEN
            allowed_old:=to_jsonb(OLD)-ARRAY['security_level_id','owning_org_unit_id','assigned_location','current_location',
                'inherit_acl_from_parent','resource_acl_version','child_aggregation_acl_version','child_record_acl_version','version'];
            allowed_new:=to_jsonb(NEW)-ARRAY['security_level_id','owning_org_unit_id','assigned_location','current_location',
                'inherit_acl_from_parent','resource_acl_version','child_aggregation_acl_version','child_record_acl_version','version'];
            IF allowed_old IS DISTINCT FROM allowed_new THEN
                RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='effective_hold_prevents_metadata_change';
            END IF;
        END IF;
    ELSE
        blocked:=resource_state_changes_blocked('record',OLD.id);
        IF NEW.aggregation_id IS DISTINCT FROM OLD.aggregation_id THEN
            IF blocked OR EXISTS(SELECT 1 FROM effective_holds_for_aggregation(NEW.aggregation_id)
                                 WHERE preserve_resource_state) THEN
                RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='effective_hold_prevents_metadata_change';
            END IF;
            IF EXISTS(
                WITH old_holds AS (SELECT hold_id FROM effective_holds_for_record(OLD.id)),
                     new_holds AS (
                         SELECT hold_id FROM effective_holds_for_aggregation(NEW.aggregation_id)
                         UNION SELECT hold_id FROM hold_record_assignments WHERE record_id=OLD.id AND hold_is_effective(hold_id)
                     ), changed AS ((SELECT * FROM old_holds EXCEPT SELECT * FROM new_holds)
                                    UNION (SELECT * FROM new_holds EXCEPT SELECT * FROM old_holds))
                SELECT 1 FROM changed WHERE NOT current_hold_actor_is_manager(changed.hold_id)
            ) THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_membership_required_for_held_move'; END IF;
        END IF;
        IF blocked THEN
            allowed_old:=to_jsonb(OLD)-ARRAY['security_level_id','owning_org_unit_id','inherit_acl_from_parent',
                'resource_acl_version','version'];
            allowed_new:=to_jsonb(NEW)-ARRAY['security_level_id','owning_org_unit_id','inherit_acl_from_parent',
                'resource_acl_version','version'];
            IF allowed_old IS DISTINCT FROM allowed_new THEN
                RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='effective_hold_prevents_metadata_change';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER aggregations_protect_effective_holds
BEFORE UPDATE OR DELETE ON aggregations FOR EACH ROW EXECUTE FUNCTION protect_held_resource();
CREATE TRIGGER records_protect_effective_holds
BEFORE UPDATE OR DELETE ON records FOR EACH ROW EXECUTE FUNCTION protect_held_resource();

CREATE FUNCTION protect_held_component_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE component_id bigint;
DECLARE held_record_id bigint;
DECLARE failure_code text;
BEGIN
    PERFORM lock_hold_policy_shared();
    IF TG_TABLE_NAME='digital_components' THEN
        held_record_id:=CASE WHEN TG_OP='DELETE' THEN OLD.record_id ELSE NEW.record_id END;
    ELSIF TG_TABLE_NAME='digital_component_content_sets' THEN
        component_id:=CASE WHEN TG_OP='DELETE' THEN OLD.digital_component_id ELSE NEW.digital_component_id END;
        SELECT record_id INTO held_record_id FROM digital_components WHERE id=component_id;
    ELSIF TG_TABLE_NAME='digital_component_blobs' THEN
        SELECT component.digital_component_id INTO component_id
        FROM digital_component_content_sets component
        WHERE component.id=CASE WHEN TG_OP='DELETE' THEN OLD.content_set_id ELSE NEW.content_set_id END;
        SELECT record_id INTO held_record_id FROM digital_components WHERE id=component_id;
    ELSE
        component_id:=CASE WHEN TG_OP='DELETE' THEN OLD.digital_component_id ELSE NEW.digital_component_id END;
        IF component_id IS NOT NULL THEN SELECT record_id INTO held_record_id FROM digital_components WHERE id=component_id; END IF;
    END IF;
    IF held_record_id IS NOT NULL AND resource_has_effective_hold('record',held_record_id) THEN
        failure_code:=CASE TG_OP WHEN 'INSERT' THEN 'effective_hold_prevents_component_addition'
          WHEN 'DELETE' THEN 'effective_hold_prevents_component_deletion'
          ELSE 'effective_hold_prevents_component_replacement' END;
        IF TG_TABLE_NAME='digital_components' AND TG_OP='UPDATE'
           AND NEW.component_order IS DISTINCT FROM OLD.component_order THEN
            failure_code:='effective_hold_prevents_component_reordering';
        END IF;
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE=failure_code;
    END IF;
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER digital_components_protect_effective_holds
BEFORE INSERT OR UPDATE OR DELETE ON digital_components FOR EACH ROW EXECUTE FUNCTION protect_held_component_mutation();
CREATE TRIGGER digital_component_content_sets_protect_effective_holds
BEFORE INSERT OR UPDATE OR DELETE ON digital_component_content_sets FOR EACH ROW EXECUTE FUNCTION protect_held_component_mutation();
CREATE TRIGGER digital_component_blobs_protect_effective_holds
BEFORE INSERT OR UPDATE OR DELETE ON digital_component_blobs FOR EACH ROW EXECUTE FUNCTION protect_held_component_mutation();
CREATE TRIGGER content_upload_sessions_protect_effective_holds
BEFORE INSERT OR UPDATE OR DELETE ON content_upload_sessions FOR EACH ROW EXECUTE FUNCTION protect_held_component_mutation();

CREATE FUNCTION prevent_nonempty_hold_deletion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM hold_aggregation_assignments WHERE hold_id=OLD.id)
       OR EXISTS (SELECT 1 FROM hold_record_assignments WHERE hold_id=OLD.id) THEN
        RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='hold_not_empty';
    END IF;
    RETURN OLD;
END;
$$;
CREATE TRIGGER holds_prevent_nonempty_deletion
BEFORE DELETE ON holds FOR EACH ROW EXECUTE FUNCTION prevent_nonempty_hold_deletion();

CREATE FUNCTION touch_hold() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.version:=OLD.version+1; NEW.date_updated:=CURRENT_TIMESTAMP; RETURN NEW; END;
$$;
CREATE TRIGGER holds_bump_version BEFORE UPDATE ON holds
FOR EACH ROW EXECUTE FUNCTION touch_hold();
CREATE TRIGGER hold_contributors_bump_version BEFORE UPDATE ON hold_contributors
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();
CREATE TRIGGER hold_aggregation_assignments_bump_version BEFORE UPDATE ON hold_aggregation_assignments
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();
CREATE TRIGGER hold_record_assignments_bump_version BEFORE UPDATE ON hold_record_assignments
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();

CREATE TRIGGER holds_record_history AFTER INSERT OR UPDATE OR DELETE ON holds
FOR EACH ROW EXECUTE FUNCTION record_entity_history('hold');
CREATE TRIGGER hold_contributors_record_history AFTER INSERT OR UPDATE OR DELETE ON hold_contributors
FOR EACH ROW EXECUTE FUNCTION record_entity_history('hold_contributor');
CREATE TRIGGER hold_aggregation_assignments_record_history AFTER INSERT OR UPDATE OR DELETE ON hold_aggregation_assignments
FOR EACH ROW EXECUTE FUNCTION record_entity_history('hold_aggregation_assignment');
CREATE TRIGGER hold_record_assignments_record_history AFTER INSERT OR UPDATE OR DELETE ON hold_record_assignments
FOR EACH ROW EXECUTE FUNCTION record_entity_history('hold_record_assignment');

CREATE FUNCTION populate_hold_event_reference_snapshots() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE state jsonb:=COALESCE(NEW.after_state,NEW.before_state,'{}'::jsonb);
DECLARE snapshots jsonb:='{}'::jsonb;
DECLARE reference_id bigint;
DECLARE snapshot jsonb;
DECLARE existing_snapshots jsonb;
BEGIN
    IF NEW.entity_type='hold' THEN
        snapshots:=jsonb_build_object('hold',jsonb_strip_nulls(jsonb_build_object(
            'id',NEW.entity_id,'code',state->>'code','name',state->>'name')));
    ELSIF NEW.entity_type IN ('hold_contributor','hold_aggregation_assignment','hold_record_assignment') THEN
        reference_id:=NULLIF(state->>'hold_id','')::bigint;
        SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot
        FROM holds WHERE id=reference_id;
        IF snapshot IS NOT NULL THEN snapshots:=snapshots||jsonb_build_object('hold',snapshot); END IF;
        IF NEW.entity_type='hold_contributor' THEN
            reference_id:=NULLIF(state->>'user_id','')::bigint;
            SELECT jsonb_strip_nulls(jsonb_build_object('id',id,'name',name,'email',email)) INTO snapshot
            FROM users WHERE id=reference_id;
            IF snapshot IS NOT NULL THEN snapshots:=snapshots||jsonb_build_object('user',snapshot); END IF;
        ELSIF NEW.entity_type='hold_aggregation_assignment' THEN
            reference_id:=NULLIF(state->>'aggregation_id','')::bigint;
            SELECT jsonb_build_object('id',id,'number',aggregation_number,'title',title) INTO snapshot
            FROM aggregations WHERE id=reference_id;
            IF snapshot IS NOT NULL THEN snapshots:=snapshots||jsonb_build_object('aggregation',snapshot); END IF;
        ELSE
            reference_id:=NULLIF(state->>'record_id','')::bigint;
            SELECT jsonb_build_object('id',id,'number',record_number,'title',title) INTO snapshot
            FROM records WHERE id=reference_id;
            IF snapshot IS NOT NULL THEN snapshots:=snapshots||jsonb_build_object('record',snapshot); END IF;
        END IF;
    ELSE
        IF NEW.metadata ? 'hold_id' THEN
            reference_id:=NULLIF(NEW.metadata->>'hold_id','')::bigint;
            SELECT jsonb_build_object('id',id,'code',code,'name',name) INTO snapshot
            FROM holds WHERE id=reference_id;
            IF snapshot IS NOT NULL THEN snapshots:=snapshots||jsonb_build_object('hold',snapshot); END IF;
        ELSE
            RETURN NEW;
        END IF;
    END IF;
    IF snapshots<>'{}'::jsonb THEN
        existing_snapshots:=COALESCE(NEW.metadata->'reference_snapshots','{}'::jsonb);
        NEW.metadata:=NEW.metadata||jsonb_build_object(
            'reference_snapshots',existing_snapshots||snapshots);
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER event_history_z_hold_reference_snapshots
BEFORE INSERT ON event_history FOR EACH ROW EXECUTE FUNCTION populate_hold_event_reference_snapshots();

CREATE FUNCTION append_hold_definition_domain_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE entity_id bigint:=CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;
DECLARE operation_name text:=CASE TG_OP WHEN 'INSERT' THEN 'HOLD_CREATED' WHEN 'UPDATE' THEN 'HOLD_UPDATED' ELSE 'HOLD_DELETED' END;
DECLARE old_state jsonb:=CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) ELSE NULL END;
DECLARE new_state jsonb:=CASE WHEN TG_OP IN ('INSERT','UPDATE') THEN to_jsonb(NEW) ELSE NULL END;
BEGIN
    IF TG_OP='INSERT' THEN
        new_state:=new_state||jsonb_build_object(
            'contributor_user_ids',COALESCE(NULLIF(current_setting('app.hold_contributor_ids',true),'')::jsonb,'[]'::jsonb));
    END IF;
    PERFORM append_domain_event('hold',entity_id,operation_name,
        jsonb_strip_nulls(jsonb_build_object('before',old_state,'after',new_state)));
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER holds_domain_events AFTER INSERT OR UPDATE OR DELETE ON holds
FOR EACH ROW EXECUTE FUNCTION append_hold_definition_domain_event();

CREATE FUNCTION append_hold_assignment_domain_events() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE state record;
DECLARE operation_name text:=CASE WHEN TG_OP='INSERT' THEN 'RESOURCE_ADDED_TO_HOLD' ELSE 'RESOURCE_REMOVED_FROM_HOLD' END;
DECLARE resource_type text:=CASE WHEN TG_TABLE_NAME='hold_aggregation_assignments' THEN 'aggregation' ELSE 'record' END;
DECLARE resource_id bigint;
DECLARE metadata jsonb;
BEGIN
    IF TG_OP='UPDATE' THEN RETURN NEW; END IF;
    IF TG_OP='DELETE' THEN state:=OLD; ELSE state:=NEW; END IF;
    IF resource_type='aggregation' THEN resource_id:=state.aggregation_id; ELSE resource_id:=state.record_id; END IF;
    metadata:=jsonb_build_object('hold_id',state.hold_id,'resource_type',resource_type,
                                 'resource_id',resource_id,'assignment_id',state.id);
    IF TG_OP='DELETE' THEN
        IF resource_type='aggregation' THEN
            metadata:=metadata||jsonb_build_object('remaining_effective_hold_ids',
                COALESCE((SELECT jsonb_agg(hold_id ORDER BY hold_id) FROM effective_holds_for_aggregation(resource_id)),'[]'::jsonb));
        ELSE
            metadata:=metadata||jsonb_build_object('remaining_effective_hold_ids',
                COALESCE((SELECT jsonb_agg(hold_id ORDER BY hold_id) FROM effective_holds_for_record(resource_id)),'[]'::jsonb));
        END IF;
    END IF;
    PERFORM append_domain_event('hold',state.hold_id,operation_name,metadata);
    PERFORM append_domain_event(resource_type,resource_id,operation_name,metadata);
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
CREATE TRIGGER hold_aggregation_assignments_domain_events
AFTER INSERT OR DELETE ON hold_aggregation_assignments
FOR EACH ROW EXECUTE FUNCTION append_hold_assignment_domain_events();
CREATE TRIGGER hold_record_assignments_domain_events
AFTER INSERT OR DELETE ON hold_record_assignments
FOR EACH ROW EXECUTE FUNCTION append_hold_assignment_domain_events();

CREATE OR REPLACE VIEW authorized_aggregations_for_search AS
SELECT resource.id,
       CASE WHEN resource.parent_aggregation_id IS NULL OR current_user_can_view_aggregation(resource.parent_aggregation_id)
            THEN resource.parent_aggregation_id END AS parent_aggregation_id,
       resource.classification_id,resource.aggregation_number,resource.title,resource.description,
       resource.date_created,resource.date_opened,resource.date_closed,resource.security_level_id,
       resource.inherit_acl_from_parent,resource.default_child_aggregation_acl_mode,
       resource.resource_acl_version,resource.child_aggregation_acl_version,resource.child_record_acl_version,
       resource.version,resource.owning_org_unit_id,resource.medium,resource.is_vital,
       resource.date_of_next_review,resource.assigned_location,resource.current_location,
       aggregation_effective_assigned_location(resource.id) AS effective_assigned_location,
       aggregation_effective_current_location(resource.id) AS effective_current_location,
       CASE WHEN current_user_can_view_aggregation(aggregation_effective_assigned_location_source_id(resource.id))
            THEN aggregation_effective_assigned_location_source_id(resource.id) END AS effective_assigned_location_source_aggregation_id,
       CASE WHEN current_user_can_view_aggregation(aggregation_effective_current_location_source_id(resource.id))
            THEN aggregation_effective_current_location_source_id(resource.id) END AS effective_current_location_source_aggregation_id,
       hold_state.effective_hold_count > 0 AS on_effective_hold,
       hold_state.resource_state_changes_blocked,
       hold_state.effective_hold_ids
FROM aggregations resource
CROSS JOIN LATERAL (
    SELECT count(*)::integer effective_hold_count,
           COALESCE(bool_or(effective.preserve_resource_state),false) resource_state_changes_blocked,
           COALESCE(array_agg(effective.hold_id ORDER BY effective.hold_id),'{}'::bigint[]) effective_hold_ids
    FROM effective_holds_for_aggregation(resource.id) effective
) hold_state;

CREATE OR REPLACE VIEW authorized_records_for_search AS
SELECT resource.id,
       CASE WHEN current_user_can_view_aggregation(resource.aggregation_id) THEN resource.aggregation_id END AS aggregation_id,
       resource.record_number,resource.title,resource.description,resource.date_created,resource.date_originated,
       resource.security_level_id,resource.inherit_acl_from_parent,resource.resource_acl_version,resource.version,
       resource.owning_org_unit_id,resource.medium,resource.is_vital,resource.date_of_next_review,
       aggregation_effective_assigned_location(resource.aggregation_id) AS effective_assigned_location,
       aggregation_effective_current_location(resource.aggregation_id) AS effective_current_location,
       CASE WHEN current_user_can_view_aggregation(aggregation_effective_assigned_location_source_id(resource.aggregation_id))
            THEN aggregation_effective_assigned_location_source_id(resource.aggregation_id) END AS effective_assigned_location_source_aggregation_id,
       CASE WHEN current_user_can_view_aggregation(aggregation_effective_current_location_source_id(resource.aggregation_id))
            THEN aggregation_effective_current_location_source_id(resource.aggregation_id) END AS effective_current_location_source_aggregation_id,
       hold_state.effective_hold_count > 0 AS on_effective_hold,
       hold_state.resource_state_changes_blocked,
       hold_state.effective_hold_ids
FROM records resource
CROSS JOIN LATERAL (
    SELECT count(*)::integer effective_hold_count,
           COALESCE(bool_or(effective.preserve_resource_state),false) resource_state_changes_blocked,
           COALESCE(array_agg(effective.hold_id ORDER BY effective.hold_id),'{}'::bigint[]) effective_hold_ids
    FROM effective_holds_for_record(resource.id) effective
) hold_state;

INSERT INTO schema_migrations(version)
VALUES ('005_add_legal_holds_foundation')
ON CONFLICT (version) DO NOTHING;

COMMIT;
