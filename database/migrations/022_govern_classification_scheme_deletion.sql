-- Govern unpublishing and deletion of classification schemes. Accidental
-- publication remains reversible until a classification is first assigned to
-- an aggregation; actual use is remembered permanently.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM schema_migrations
        WHERE version = '022_govern_classification_scheme_deletion'
    ) THEN
        RETURN;
    END IF;

    ALTER TABLE classification_schemes
        ADD COLUMN IF NOT EXISTS date_first_used timestamptz;

    UPDATE classification_schemes AS scheme
    SET date_first_used = CURRENT_TIMESTAMP
    WHERE date_first_used IS NULL
      AND EXISTS (
          SELECT 1
          FROM classifications AS classification
          JOIN aggregations AS aggregation
            ON aggregation.classification_id = classification.id
          WHERE classification.classification_scheme_id = scheme.id
      );

    INSERT INTO schema_migrations(version)
    VALUES ('022_govern_classification_scheme_deletion');
END;
$$;

ALTER TABLE classification_schemes
    DROP CONSTRAINT IF EXISTS classification_schemes_first_use_in_order;
ALTER TABLE classification_schemes
    ADD CONSTRAINT classification_schemes_first_use_in_order CHECK (
        date_first_used IS NULL OR date_first_used >= date_created
    );

CREATE OR REPLACE FUNCTION validate_classification_scheme_dates()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.date_deactivated IS NOT NULL AND NEW.date_deactivated > CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION 'classification scheme date_deactivated cannot be in the future';
    END IF;
    IF NEW.date_deactivated IS NOT NULL AND NEW.date_deactivated < NEW.date_created THEN
        RAISE EXCEPTION 'classification scheme date_deactivated cannot precede date_created';
    END IF;
    IF TG_OP = 'UPDATE'
       AND OLD.date_first_used IS NOT NULL
       AND NEW.date_first_used IS DISTINCT FROM OLD.date_first_used THEN
        RAISE EXCEPTION 'classification scheme date_first_used is immutable once set';
    END IF;
    IF TG_OP = 'UPDATE'
       AND OLD.date_published IS NOT NULL
       AND NEW.date_published IS NULL THEN
        IF OLD.date_first_used IS NOT NULL THEN
            RAISE EXCEPTION 'a classification scheme that has governed an aggregation cannot be unpublished';
        END IF;
        IF NULLIF(current_setting('app.change_reason', true), '') IS NULL THEN
            RAISE EXCEPTION 'unpublishing a classification scheme requires a change reason';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS classification_schemes_validate_dates ON classification_schemes;
CREATE TRIGGER classification_schemes_validate_dates
BEFORE INSERT OR UPDATE OF date_created, date_published, date_deactivated, date_first_used
ON classification_schemes
FOR EACH ROW EXECUTE FUNCTION validate_classification_scheme_dates();

CREATE OR REPLACE FUNCTION record_classification_scheme_first_use()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    scheme_id bigint;
BEGIN
    IF NEW.classification_id IS NULL
       OR (TG_OP = 'UPDATE' AND NEW.classification_id IS NOT DISTINCT FROM OLD.classification_id) THEN
        RETURN NEW;
    END IF;

    SELECT classification_scheme_id INTO scheme_id
    FROM classifications
    WHERE id = NEW.classification_id;

    UPDATE classification_schemes
    SET date_first_used = CURRENT_TIMESTAMP
    WHERE id = scheme_id AND date_first_used IS NULL;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION delete_unused_classification_scheme()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    deleted_count integer;
BEGIN
    IF OLD.date_published IS NOT NULL THEN
        RAISE EXCEPTION 'published classification schemes must be unpublished before deletion';
    END IF;
    IF OLD.date_first_used IS NOT NULL THEN
        RAISE EXCEPTION 'a classification scheme that has governed an aggregation cannot be deleted';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM aggregations AS a
        JOIN classifications AS c ON c.id = a.classification_id
        WHERE c.classification_scheme_id = OLD.id
    ) THEN
        RAISE EXCEPTION 'classification scheme has classifications assigned to aggregations';
    END IF;

    LOOP
        DELETE FROM classifications AS candidate
        WHERE candidate.classification_scheme_id = OLD.id
          AND NOT EXISTS (
              SELECT 1 FROM classifications AS child
              WHERE child.parent_classification_id = candidate.id
          );
        GET DIAGNOSTICS deleted_count = ROW_COUNT;
        EXIT WHEN deleted_count = 0;
    END LOOP;

    IF EXISTS (SELECT 1 FROM classifications WHERE classification_scheme_id = OLD.id) THEN
        RAISE EXCEPTION 'classification scheme hierarchy could not be deleted safely';
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS aggregations_record_classification_scheme_first_use ON aggregations;
CREATE TRIGGER aggregations_record_classification_scheme_first_use
AFTER INSERT OR UPDATE OF classification_id ON aggregations
FOR EACH ROW EXECUTE FUNCTION record_classification_scheme_first_use();

DROP TRIGGER IF EXISTS classification_schemes_delete_unused ON classification_schemes;
CREATE TRIGGER classification_schemes_delete_unused
BEFORE DELETE ON classification_schemes
FOR EACH ROW EXECUTE FUNCTION delete_unused_classification_scheme();
