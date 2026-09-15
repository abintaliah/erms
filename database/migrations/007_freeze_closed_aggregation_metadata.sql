-- Freeze aggregation metadata while allowing an explicit direct reopen.
CREATE TABLE IF NOT EXISTS schema_migrations (
    id         bigserial PRIMARY KEY,
    version    text NOT NULL UNIQUE,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT schema_migrations_version_not_blank CHECK (btrim(version) <> '')
);

CREATE OR REPLACE FUNCTION protect_closed_aggregation_hierarchy()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    closure_source_id bigint;
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

    -- Lock the current ancestor chain in stable order before deciding whether
    -- this row is directly or inheritably closed.
    PERFORM 1
    FROM aggregations AS locked
    WHERE locked.id IN (
        WITH RECURSIVE ancestors AS (
            SELECT id, parent_aggregation_id FROM aggregations WHERE id = OLD.id
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
        SELECT id, parent_aggregation_id, date_closed, 0 AS depth
        FROM aggregations WHERE id = OLD.id
        UNION ALL
        SELECT parent.id, parent.parent_aggregation_id, parent.date_closed, child.depth + 1
        FROM aggregations AS parent
        JOIN ancestors AS child ON parent.id = child.parent_aggregation_id
    )
    SELECT id INTO closure_source_id
    FROM ancestors
    WHERE date_closed IS NOT NULL
    ORDER BY depth
    LIMIT 1;

    IF closure_source_id IS NOT NULL THEN
        -- The only permitted mutation is clearing this aggregation's own
        -- closure date without changing any other stored metadata.
        IF closure_source_id = OLD.id
           AND OLD.date_closed IS NOT NULL
           AND NEW.date_closed IS NULL
           AND NEW.parent_aggregation_id IS NOT DISTINCT FROM OLD.parent_aggregation_id
           AND NEW.aggregation_number IS NOT DISTINCT FROM OLD.aggregation_number
           AND NEW.title IS NOT DISTINCT FROM OLD.title
           AND NEW.description IS NOT DISTINCT FROM OLD.description
           AND NEW.date_created IS NOT DISTINCT FROM OLD.date_created
           AND NEW.date_opened IS NOT DISTINCT FROM OLD.date_opened THEN
            RETURN NEW;
        END IF;

        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = format(
                'aggregation %s is closed by aggregation %s; closed aggregation metadata is immutable and only a direct closure may be cleared',
                OLD.id, closure_source_id
            );
    END IF;

    IF NEW.parent_aggregation_id IS DISTINCT FROM OLD.parent_aggregation_id THEN
        IF NEW.parent_aggregation_id IS NOT NULL THEN
            PERFORM assert_aggregation_effectively_open(NEW.parent_aggregation_id);
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS aggregations_protect_closed_hierarchy ON aggregations;
CREATE TRIGGER aggregations_protect_closed_hierarchy
BEFORE INSERT OR UPDATE OR DELETE ON aggregations
FOR EACH ROW EXECUTE FUNCTION protect_closed_aggregation_hierarchy();

INSERT INTO schema_migrations (version)
VALUES ('007_freeze_closed_aggregation_metadata')
ON CONFLICT (version) DO NOTHING;
