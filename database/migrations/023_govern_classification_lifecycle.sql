BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true);
SELECT set_config('app.actor_name', 'Database migration 023', true);
SELECT set_config('app.source', 'migration', true);
SELECT set_config(
    'app.change_reason',
    'Introduce classification lifecycle controls and preserve historical classification governance',
    true
);

ALTER TABLE classifications
    ADD COLUMN IF NOT EXISTS date_deactivated timestamptz,
    ADD COLUMN IF NOT EXISTS date_first_used timestamptz;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'classifications_dates_in_order'
    ) THEN
        ALTER TABLE classifications ADD CONSTRAINT classifications_dates_in_order
            CHECK (date_deactivated IS NULL OR date_deactivated >= date_created);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'classifications_first_use_in_order'
    ) THEN
        ALTER TABLE classifications ADD CONSTRAINT classifications_first_use_in_order
            CHECK (date_first_used IS NULL OR date_first_used >= date_created);
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION classification_is_effectively_active(p_classification_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    WITH RECURSIVE lineage AS (
        SELECT id, parent_classification_id, date_deactivated
        FROM classifications WHERE id = p_classification_id
        UNION ALL
        SELECT parent.id, parent.parent_classification_id, parent.date_deactivated
        FROM classifications AS parent
        JOIN lineage AS child ON parent.id = child.parent_classification_id
    )
    SELECT EXISTS (SELECT 1 FROM lineage)
       AND NOT EXISTS (SELECT 1 FROM lineage WHERE date_deactivated IS NOT NULL);
$$;

CREATE OR REPLACE FUNCTION validate_classification_dates()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.date_deactivated IS NOT NULL AND NEW.date_deactivated > CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION 'classification date_deactivated cannot be in the future';
    END IF;
    IF NEW.date_deactivated IS NOT NULL AND NEW.date_deactivated < NEW.date_created THEN
        RAISE EXCEPTION 'classification date_deactivated cannot precede date_created';
    END IF;
    IF TG_OP = 'UPDATE'
       AND OLD.date_first_used IS NOT NULL
       AND NEW.date_first_used IS DISTINCT FROM OLD.date_first_used THEN
        RAISE EXCEPTION 'classification date_first_used is immutable once set';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION record_classification_governance_first_use()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    scheme_id bigint;
    used_at timestamptz := CURRENT_TIMESTAMP;
BEGIN
    IF NEW.classification_id IS NULL
       OR (TG_OP = 'UPDATE' AND NEW.classification_id IS NOT DISTINCT FROM OLD.classification_id) THEN
        RETURN NEW;
    END IF;

    SELECT classification_scheme_id INTO scheme_id
    FROM classifications WHERE id = NEW.classification_id;

    WITH RECURSIVE lineage AS (
        SELECT id, parent_classification_id
        FROM classifications WHERE id = NEW.classification_id
        UNION ALL
        SELECT parent.id, parent.parent_classification_id
        FROM classifications AS parent
        JOIN lineage AS child ON parent.id = child.parent_classification_id
    )
    UPDATE classifications
       SET date_first_used = used_at
     WHERE id IN (SELECT id FROM lineage) AND date_first_used IS NULL;

    UPDATE classification_schemes
       SET date_first_used = used_at
     WHERE id = scheme_id AND date_first_used IS NULL;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION protect_classification_deletion()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    scheme_row classification_schemes%ROWTYPE;
BEGIN
    SELECT * INTO scheme_row FROM classification_schemes WHERE id = OLD.classification_scheme_id;
    IF scheme_row.date_deactivated IS NOT NULL THEN
        RAISE EXCEPTION 'classifications cannot be deleted while their scheme is deactivated';
    END IF;
    IF scheme_row.date_published IS NOT NULL THEN
        RAISE EXCEPTION 'classification scheme must be unpublished before deleting classifications';
    END IF;
    IF OLD.date_first_used IS NOT NULL THEN
        RAISE EXCEPTION 'a classification that has governed an aggregation cannot be deleted; deactivate it instead';
    END IF;
    IF EXISTS (SELECT 1 FROM classifications WHERE parent_classification_id = OLD.id) THEN
        RAISE EXCEPTION 'classification has children; delete its child classifications first';
    END IF;
    IF EXISTS (SELECT 1 FROM aggregations WHERE classification_id = OLD.id) THEN
        RAISE EXCEPTION 'classification is assigned to an aggregation and cannot be deleted';
    END IF;
    IF NULLIF(current_setting('app.change_reason', true), '') IS NULL THEN
        RAISE EXCEPTION 'deleting a classification requires a change reason';
    END IF;
    RETURN OLD;
END;
$$;

CREATE OR REPLACE FUNCTION validate_aggregation_classification()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    classification_terminal boolean;
    scheme_id bigint;
BEGIN
    IF NEW.parent_aggregation_id IS NULL THEN
        IF NEW.classification_id IS NULL THEN
            RAISE EXCEPTION 'root aggregations must have a classification';
        END IF;
        SELECT is_terminal, classification_scheme_id
          INTO classification_terminal, scheme_id
          FROM classifications WHERE id = NEW.classification_id;
        IF NOT COALESCE(classification_terminal, false) THEN
            RAISE EXCEPTION 'root aggregations must use a terminal classification';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM effective_classification_retention_rule(NEW.classification_id)
        ) THEN
            RAISE EXCEPTION 'selected classification has no effective retention rule';
        END IF;
        IF TG_OP = 'INSERT'
           OR NEW.classification_id IS DISTINCT FROM OLD.classification_id
           OR NEW.parent_aggregation_id IS DISTINCT FROM OLD.parent_aggregation_id THEN
            IF NOT classification_scheme_is_eligible(scheme_id) THEN
                RAISE EXCEPTION 'selected classification scheme is not active and published';
            END IF;
            IF NOT classification_is_effectively_active(NEW.classification_id) THEN
                RAISE EXCEPTION 'selected classification or one of its ancestors is deactivated';
            END IF;
        END IF;
    ELSIF NEW.classification_id IS NOT NULL THEN
        RAISE EXCEPTION 'child aggregations cannot have a classification';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS classifications_validate_dates ON classifications;
CREATE TRIGGER classifications_validate_dates
BEFORE INSERT OR UPDATE OF date_created, date_deactivated, date_first_used ON classifications
FOR EACH ROW EXECUTE FUNCTION validate_classification_dates();

DROP TRIGGER IF EXISTS aggregations_record_classification_scheme_first_use ON aggregations;
DROP TRIGGER IF EXISTS aggregations_record_classification_governance_first_use ON aggregations;
CREATE TRIGGER aggregations_record_classification_governance_first_use
AFTER INSERT OR UPDATE OF classification_id ON aggregations
FOR EACH ROW EXECUTE FUNCTION record_classification_governance_first_use();
DROP FUNCTION IF EXISTS record_classification_scheme_first_use();

DROP TRIGGER IF EXISTS classifications_protect_deletion ON classifications;
CREATE TRIGGER classifications_protect_deletion
BEFORE DELETE ON classifications
FOR EACH ROW EXECUTE FUNCTION protect_classification_deletion();

WITH RECURSIVE used_paths AS (
    SELECT c.id, c.parent_classification_id, a.date_created AS used_at
    FROM aggregations AS a
    JOIN classifications AS c ON c.id = a.classification_id
    WHERE a.classification_id IS NOT NULL
    UNION ALL
    SELECT parent.id, parent.parent_classification_id, used_paths.used_at
    FROM classifications AS parent
    JOIN used_paths ON parent.id = used_paths.parent_classification_id
), first_uses AS (
    SELECT id, min(used_at) AS used_at FROM used_paths GROUP BY id
)
UPDATE classifications AS c
   SET date_first_used = GREATEST(first_uses.used_at, c.date_created)
  FROM first_uses
 WHERE c.id = first_uses.id AND c.date_first_used IS NULL;

INSERT INTO schema_migrations(version)
VALUES ('023_govern_classification_lifecycle')
ON CONFLICT(version) DO NOTHING;

COMMIT;
