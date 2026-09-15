-- Enforce inherited aggregation closure across records, components and blobs.
CREATE TABLE IF NOT EXISTS schema_migrations (
    id         bigserial PRIMARY KEY,
    version    text NOT NULL UNIQUE,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT schema_migrations_version_not_blank CHECK (btrim(version) <> '')
);

CREATE OR REPLACE FUNCTION assert_aggregation_effectively_open(p_aggregation_id bigint)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    blocker record;
BEGIN
    IF p_aggregation_id IS NULL THEN
        RETURN;
    END IF;

    -- Lock every ancestor in a stable order. Closing or reparenting an ancestor
    -- must wait for in-flight content changes, and vice versa.
    PERFORM 1
    FROM aggregations AS locked
    WHERE locked.id IN (
        WITH RECURSIVE ancestors AS (
            SELECT id, parent_aggregation_id
            FROM aggregations
            WHERE id = p_aggregation_id
            UNION ALL
            SELECT parent.id, parent.parent_aggregation_id
            FROM aggregations AS parent
            JOIN ancestors ON parent.id = ancestors.parent_aggregation_id
        )
        SELECT id FROM ancestors
    )
    ORDER BY locked.id
    FOR SHARE;

    WITH RECURSIVE ancestors AS (
        SELECT id, parent_aggregation_id, aggregation_number, title, date_closed, 0 AS depth
        FROM aggregations
        WHERE id = p_aggregation_id
        UNION ALL
        SELECT parent.id, parent.parent_aggregation_id, parent.aggregation_number,
               parent.title, parent.date_closed, child.depth + 1
        FROM aggregations AS parent
        JOIN ancestors AS child ON parent.id = child.parent_aggregation_id
    )
    SELECT id, aggregation_number, title, date_closed
    INTO blocker
    FROM ancestors
    WHERE date_closed IS NOT NULL
    ORDER BY depth
    LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = format(
                'aggregation %s (%s) is closed by aggregation %s (%s); records and digital content in this subtree are immutable',
                p_aggregation_id,
                (SELECT aggregation_number FROM aggregations WHERE id = p_aggregation_id),
                blocker.id,
                blocker.aggregation_number
            );
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION validate_aggregation_closure_date()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.date_closed IS NOT NULL AND NEW.date_closed > CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'date_closed cannot be in the future';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION protect_closed_aggregation_hierarchy()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.parent_aggregation_id IS NOT NULL THEN
            PERFORM assert_aggregation_effectively_open(NEW.parent_aggregation_id);
        END IF;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM assert_aggregation_effectively_open(OLD.id);
        RETURN OLD;
    END IF;

    IF NEW.parent_aggregation_id IS DISTINCT FROM OLD.parent_aggregation_id THEN
        PERFORM assert_aggregation_effectively_open(OLD.id);
        IF NEW.parent_aggregation_id IS NOT NULL THEN
            PERFORM assert_aggregation_effectively_open(NEW.parent_aggregation_id);
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION protect_record_in_closed_aggregation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM assert_aggregation_effectively_open(NEW.aggregation_id);
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM assert_aggregation_effectively_open(OLD.aggregation_id);
        RETURN OLD;
    END IF;

    PERFORM assert_aggregation_effectively_open(OLD.aggregation_id);
    IF NEW.aggregation_id IS DISTINCT FROM OLD.aggregation_id THEN
        PERFORM assert_aggregation_effectively_open(NEW.aggregation_id);
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION assert_record_effectively_open(p_record_id bigint)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    aggregation_key bigint;
BEGIN
    SELECT aggregation_id
    INTO aggregation_key
    FROM records
    WHERE id = p_record_id
    FOR SHARE;

    IF aggregation_key IS NOT NULL THEN
        PERFORM assert_aggregation_effectively_open(aggregation_key);
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION protect_component_in_closed_aggregation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM assert_record_effectively_open(NEW.record_id);
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM assert_record_effectively_open(OLD.record_id);
        RETURN OLD;
    END IF;

    PERFORM assert_record_effectively_open(OLD.record_id);
    IF NEW.record_id IS DISTINCT FROM OLD.record_id THEN
        PERFORM assert_record_effectively_open(NEW.record_id);
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION protect_blob_in_closed_aggregation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM assert_record_effectively_open(
            (SELECT record_id FROM digital_components WHERE id = NEW.digital_component_id)
        );
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM assert_record_effectively_open(
            (SELECT record_id FROM digital_components WHERE id = OLD.digital_component_id)
        );
        RETURN OLD;
    END IF;

    PERFORM assert_record_effectively_open(
        (SELECT record_id FROM digital_components WHERE id = OLD.digital_component_id)
    );
    IF NEW.digital_component_id IS DISTINCT FROM OLD.digital_component_id THEN
        PERFORM assert_record_effectively_open(
            (SELECT record_id FROM digital_components WHERE id = NEW.digital_component_id)
        );
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS aggregations_validate_closure_date ON aggregations;
CREATE TRIGGER aggregations_validate_closure_date
BEFORE INSERT OR UPDATE OF date_closed ON aggregations
FOR EACH ROW EXECUTE FUNCTION validate_aggregation_closure_date();

DROP TRIGGER IF EXISTS aggregations_protect_closed_hierarchy ON aggregations;
CREATE TRIGGER aggregations_protect_closed_hierarchy
BEFORE INSERT OR UPDATE OF parent_aggregation_id OR DELETE ON aggregations
FOR EACH ROW EXECUTE FUNCTION protect_closed_aggregation_hierarchy();

DROP TRIGGER IF EXISTS records_protect_closed_aggregation ON records;
CREATE TRIGGER records_protect_closed_aggregation
BEFORE INSERT OR UPDATE OR DELETE ON records
FOR EACH ROW EXECUTE FUNCTION protect_record_in_closed_aggregation();

DROP TRIGGER IF EXISTS digital_components_protect_closed_aggregation ON digital_components;
CREATE TRIGGER digital_components_protect_closed_aggregation
BEFORE INSERT OR UPDATE OR DELETE ON digital_components
FOR EACH ROW EXECUTE FUNCTION protect_component_in_closed_aggregation();

DROP TRIGGER IF EXISTS digital_component_blobs_protect_closed_aggregation ON digital_component_blobs;
CREATE TRIGGER digital_component_blobs_protect_closed_aggregation
BEFORE INSERT OR UPDATE OR DELETE ON digital_component_blobs
FOR EACH ROW EXECUTE FUNCTION protect_blob_in_closed_aggregation();

INSERT INTO schema_migrations (version)
VALUES ('006_enforce_closed_aggregations')
ON CONFLICT (version) DO NOTHING;
