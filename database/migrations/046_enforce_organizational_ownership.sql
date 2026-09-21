BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Database migration 046', true),
       set_config('app.event_source', 'migration', true),
       set_config('app.change_reason', 'Enforce organizational ownership invariants and move propagation', true),
       set_config('app.event_metadata', '{"migration":"046_enforce_organizational_ownership"}', true);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM organizational_ownership_diagnostics) THEN
        RAISE EXCEPTION 'cannot enforce organizational ownership while diagnostics remain';
    END IF;
END;
$$;

ALTER TABLE aggregations ALTER COLUMN owning_org_unit_id SET NOT NULL;
ALTER TABLE records ALTER COLUMN owning_org_unit_id SET NOT NULL;

CREATE FUNCTION enforce_aggregation_ownership()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parent_owner bigint;
    target_owner bigint;
    confirmed boolean := COALESCE(NULLIF(current_setting('app.ownership_move_confirmed', true), '')::boolean, false);
    propagating boolean := current_setting('app.ownership_propagation', true) = 'authorized';
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

CREATE FUNCTION propagate_aggregation_ownership()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE previous_context text;
BEGIN
    IF NEW.owning_org_unit_id IS NOT DISTINCT FROM OLD.owning_org_unit_id
       OR current_setting('app.ownership_propagation', true) = 'authorized' THEN
        RETURN NEW;
    END IF;
    previous_context := current_setting('app.ownership_propagation', true);
    PERFORM set_config('app.ownership_propagation', 'authorized', true);

    WITH RECURSIVE descendants(id) AS (
        SELECT child.id FROM aggregations child WHERE child.parent_aggregation_id = NEW.id
        UNION ALL
        SELECT child.id FROM descendants parent
        JOIN aggregations child ON child.parent_aggregation_id = parent.id
    )
    UPDATE aggregations child SET owning_org_unit_id = NEW.owning_org_unit_id
    FROM descendants WHERE child.id = descendants.id
      AND child.owning_org_unit_id IS DISTINCT FROM NEW.owning_org_unit_id;

    WITH RECURSIVE subtree(id) AS (
        SELECT NEW.id
        UNION ALL
        SELECT child.id FROM subtree parent
        JOIN aggregations child ON child.parent_aggregation_id = parent.id
    )
    UPDATE records record SET owning_org_unit_id = NEW.owning_org_unit_id
    FROM subtree WHERE record.aggregation_id = subtree.id
      AND record.owning_org_unit_id IS DISTINCT FROM NEW.owning_org_unit_id;

    PERFORM set_config('app.ownership_propagation', COALESCE(previous_context, ''), true);
    RETURN NEW;
END;
$$;

CREATE FUNCTION enforce_record_ownership()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    target_owner bigint;
    confirmed boolean := COALESCE(NULLIF(current_setting('app.ownership_move_confirmed', true), '')::boolean, false);
    propagating boolean := current_setting('app.ownership_propagation', true) = 'authorized';
BEGIN
    IF TG_OP = 'UPDATE' AND propagating THEN RETURN NEW; END IF;

    IF NEW.aggregation_id IS NULL THEN RETURN NEW; END IF;

    SELECT owning_org_unit_id INTO STRICT target_owner
    FROM aggregations WHERE id = NEW.aggregation_id FOR UPDATE;

    IF TG_OP = 'INSERT' THEN
        NEW.owning_org_unit_id := target_owner;
        RETURN NEW;
    END IF;

    IF NEW.aggregation_id IS NOT DISTINCT FROM OLD.aggregation_id THEN
        IF NEW.owning_org_unit_id IS DISTINCT FROM OLD.owning_org_unit_id THEN
            RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='owning_org_unit_id cannot be changed directly';
        END IF;
        RETURN NEW;
    END IF;

    IF target_owner IS DISTINCT FROM OLD.owning_org_unit_id AND (
        NOT confirmed OR NULLIF(btrim(current_setting('app.change_reason', true)), '') IS NULL
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001',
            MESSAGE='ownership-changing record moves require a reason and explicit confirmation';
    END IF;
    NEW.owning_org_unit_id := target_owner;
    RETURN NEW;
END;
$$;

CREATE TRIGGER aggregations_enforce_ownership
BEFORE INSERT OR UPDATE OF parent_aggregation_id, owning_org_unit_id ON aggregations
FOR EACH ROW EXECUTE FUNCTION enforce_aggregation_ownership();
CREATE TRIGGER aggregations_propagate_ownership
AFTER UPDATE OF parent_aggregation_id, owning_org_unit_id ON aggregations
FOR EACH ROW EXECUTE FUNCTION propagate_aggregation_ownership();
CREATE TRIGGER records_enforce_ownership
BEFORE INSERT OR UPDATE OF aggregation_id, owning_org_unit_id ON records
FOR EACH ROW EXECUTE FUNCTION enforce_record_ownership();

INSERT INTO schema_migrations(version) VALUES ('046_enforce_organizational_ownership');

COMMIT;
