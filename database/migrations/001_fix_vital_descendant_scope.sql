BEGIN;

CREATE OR REPLACE FUNCTION aggregation_has_vital_descendants(p_id bigint)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    WITH RECURSIVE subtree AS (
        SELECT p_id AS id
        UNION ALL
        SELECT child.id
          FROM aggregations child
          JOIN subtree parent ON child.parent_aggregation_id = parent.id
    )
    SELECT EXISTS (
               SELECT 1
                 FROM aggregations
                WHERE id IN (SELECT id FROM subtree)
                  AND id <> p_id
                  AND is_vital
           )
        OR EXISTS (
               SELECT 1
                 FROM records
                WHERE aggregation_id IN (SELECT id FROM subtree)
                  AND is_vital
           )
$$;

CREATE OR REPLACE FUNCTION protect_vital_resource_deletion()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    vital_count integer;
BEGIN
    IF TG_TABLE_NAME = 'records' THEN
        IF OLD.is_vital THEN
            RAISE EXCEPTION USING
                ERRCODE = 'P0001',
                MESSAGE = 'vital_resource_deletion_blocked';
        END IF;
        RETURN OLD;
    END IF;

    PERFORM 1 FROM aggregations WHERE id = OLD.id FOR UPDATE;
    IF OLD.is_vital THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'vital_resource_deletion_blocked';
    END IF;

    WITH RECURSIVE subtree AS (
        SELECT OLD.id AS id
        UNION ALL
        SELECT child.id
          FROM aggregations child
          JOIN subtree parent ON child.parent_aggregation_id = parent.id
    )
    SELECT count(*)
      INTO vital_count
      FROM (
          SELECT id
            FROM aggregations
           WHERE id IN (SELECT id FROM subtree)
             AND id <> OLD.id
             AND is_vital
          UNION ALL
          SELECT id
            FROM records
           WHERE aggregation_id IN (SELECT id FROM subtree)
             AND is_vital
      ) vital;

    IF vital_count > 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001',
            MESSAGE = 'vital_descendant_deletion_blocked';
    END IF;
    RETURN OLD;
END;
$$;

INSERT INTO schema_migrations (version)
VALUES ('001_fix_vital_descendant_scope')
ON CONFLICT (version) DO NOTHING;

COMMIT;
