BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    id         bigserial PRIMARY KEY,
    version    text NOT NULL UNIQUE,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT schema_migrations_version_not_blank CHECK (btrim(version) <> '')
);

CREATE TABLE IF NOT EXISTS security_levels (
    id                   bigserial PRIMARY KEY,
    code                 text NOT NULL,
    name                 text NOT NULL,
    level_number         integer NOT NULL,
    prevents_disposition boolean NOT NULL DEFAULT false,
    date_created         timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated         timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version              integer NOT NULL DEFAULT 1,
    CONSTRAINT security_levels_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT security_levels_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT security_levels_number_nonnegative CHECK (level_number >= 0),
    CONSTRAINT security_levels_version_positive CHECK (version > 0),
    CONSTRAINT security_levels_level_number_unique UNIQUE (level_number)
);

CREATE UNIQUE INDEX IF NOT EXISTS security_levels_code_ci_unique
    ON security_levels (lower(code));
CREATE UNIQUE INDEX IF NOT EXISTS security_levels_name_ci_unique
    ON security_levels (lower(name));

INSERT INTO security_levels (code, name, level_number, prevents_disposition)
VALUES
    ('G', 'General', 0, false),
    ('R', 'Restricted', 50, false),
    ('S', 'Secret', 75, false),
    ('TS', 'Top Secret', 100, true)
ON CONFLICT (level_number) DO NOTHING;

ALTER TABLE roles ADD COLUMN IF NOT EXISTS security_level_id bigint;
ALTER TABLE aggregations ADD COLUMN IF NOT EXISTS security_level_id bigint;
ALTER TABLE records ADD COLUMN IF NOT EXISTS security_level_id bigint;
ALTER TABLE record_drafts ADD COLUMN IF NOT EXISTS security_level_id bigint REFERENCES security_levels(id) ON DELETE RESTRICT;

UPDATE roles
SET security_level_id = (SELECT id FROM security_levels ORDER BY level_number, id LIMIT 1)
WHERE security_level_id IS NULL;
UPDATE aggregations
SET security_level_id = (SELECT id FROM security_levels ORDER BY level_number, id LIMIT 1)
WHERE security_level_id IS NULL;
UPDATE records
SET security_level_id = (SELECT id FROM security_levels ORDER BY level_number, id LIMIT 1)
WHERE security_level_id IS NULL;

-- Populated databases can have deferred constraint-trigger events queued by
-- the audited backfill updates. Flush them before altering the same tables.
SET CONSTRAINTS ALL IMMEDIATE;

ALTER TABLE roles ALTER COLUMN security_level_id SET NOT NULL;
ALTER TABLE aggregations ALTER COLUMN security_level_id SET NOT NULL;
ALTER TABLE records ALTER COLUMN security_level_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='roles_security_level_fk') THEN
        ALTER TABLE roles ADD CONSTRAINT roles_security_level_fk
            FOREIGN KEY (security_level_id) REFERENCES security_levels(id) ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='aggregations_security_level_fk') THEN
        ALTER TABLE aggregations ADD CONSTRAINT aggregations_security_level_fk
            FOREIGN KEY (security_level_id) REFERENCES security_levels(id) ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='records_security_level_fk') THEN
        ALTER TABLE records ADD CONSTRAINT records_security_level_fk
            FOREIGN KEY (security_level_id) REFERENCES security_levels(id) ON DELETE RESTRICT;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS roles_security_level_id_idx ON roles (security_level_id);
CREATE INDEX IF NOT EXISTS aggregations_security_level_id_idx ON aggregations (security_level_id);
CREATE INDEX IF NOT EXISTS records_security_level_id_idx ON records (security_level_id);
CREATE INDEX IF NOT EXISTS record_drafts_security_level_id_idx ON record_drafts (security_level_id);

CREATE OR REPLACE FUNCTION lowest_security_level_id()
RETURNS bigint
LANGUAGE sql
STABLE
AS $$
    SELECT id FROM security_levels ORDER BY level_number, id LIMIT 1
$$;

CREATE OR REPLACE FUNCTION default_entity_security_level()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.security_level_id IS NOT NULL THEN
        RETURN NEW;
    END IF;
    IF TG_TABLE_NAME = 'aggregations'
       AND NULLIF(to_jsonb(NEW)->>'parent_aggregation_id', '') IS NOT NULL THEN
        SELECT security_level_id INTO NEW.security_level_id
        FROM aggregations
        WHERE id = (to_jsonb(NEW)->>'parent_aggregation_id')::bigint;
    END IF;
    NEW.security_level_id := COALESCE(NEW.security_level_id, lowest_security_level_id());
    IF NEW.security_level_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='no security level is configured';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS roles_default_security_level ON roles;
CREATE TRIGGER roles_default_security_level
BEFORE INSERT ON roles FOR EACH ROW EXECUTE FUNCTION default_entity_security_level();
DROP TRIGGER IF EXISTS aggregations_default_security_level ON aggregations;
CREATE TRIGGER aggregations_default_security_level
BEFORE INSERT ON aggregations FOR EACH ROW EXECUTE FUNCTION default_entity_security_level();
DROP TRIGGER IF EXISTS records_default_security_level ON records;
CREATE TRIGGER records_default_security_level
BEFORE INSERT ON records FOR EACH ROW EXECUTE FUNCTION default_entity_security_level();

CREATE OR REPLACE FUNCTION enforce_resource_security_hierarchy()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    resource_level integer;
    parent_level integer;
    child_max integer;
BEGIN
    SELECT level_number INTO STRICT resource_level
    FROM security_levels WHERE id = NEW.security_level_id;

    IF TG_TABLE_NAME = 'records' THEN
        IF NEW.aggregation_id IS NULL THEN RETURN NEW; END IF;
        SELECT level.level_number INTO parent_level
        FROM aggregations parent
        JOIN security_levels level ON level.id = parent.security_level_id
        WHERE parent.id = NEW.aggregation_id;
        IF parent_level IS NULL THEN RETURN NEW; END IF;
        IF parent_level < resource_level THEN
            RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='security_hierarchy_violation',
                DETAIL=format('record level %s exceeds parent aggregation level %s', resource_level, parent_level);
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.parent_aggregation_id IS NOT NULL THEN
        SELECT level.level_number INTO parent_level
        FROM aggregations parent
        JOIN security_levels level ON level.id = parent.security_level_id
        WHERE parent.id = NEW.parent_aggregation_id;
        IF parent_level IS NULL THEN RETURN NEW; END IF;
        IF parent_level < resource_level THEN
            RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='security_hierarchy_violation',
                DETAIL=format('aggregation level %s exceeds parent aggregation level %s', resource_level, parent_level);
        END IF;
    END IF;

    SELECT max(level_number) INTO child_max
    FROM (
        SELECT level.level_number
        FROM aggregations child JOIN security_levels level ON level.id=child.security_level_id
        WHERE child.parent_aggregation_id=NEW.id
        UNION ALL
        SELECT level.level_number
        FROM records child JOIN security_levels level ON level.id=child.security_level_id
        WHERE child.aggregation_id=NEW.id
    ) children;
    IF child_max IS NOT NULL AND resource_level < child_max THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='security_hierarchy_violation',
            DETAIL=format('aggregation level %s is below contained resource level %s', resource_level, child_max);
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS aggregations_enforce_security_hierarchy ON aggregations;
CREATE TRIGGER aggregations_enforce_security_hierarchy
BEFORE INSERT OR UPDATE OF parent_aggregation_id, security_level_id ON aggregations
FOR EACH ROW EXECUTE FUNCTION enforce_resource_security_hierarchy();
DROP TRIGGER IF EXISTS records_enforce_security_hierarchy ON records;
CREATE TRIGGER records_enforce_security_hierarchy
BEFORE INSERT OR UPDATE OF aggregation_id, security_level_id ON records
FOR EACH ROW EXECUTE FUNCTION enforce_resource_security_hierarchy();

CREATE OR REPLACE FUNCTION enforce_security_level_catalogue_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.level_number IS DISTINCT FROM OLD.level_number AND EXISTS (
        SELECT 1 FROM aggregations child
        JOIN aggregations parent ON parent.id=child.parent_aggregation_id
        JOIN security_levels child_level ON child_level.id=child.security_level_id
        JOIN security_levels parent_level ON parent_level.id=parent.security_level_id
        WHERE (CASE WHEN parent_level.id=NEW.id THEN NEW.level_number ELSE parent_level.level_number END)
            < (CASE WHEN child_level.id=NEW.id THEN NEW.level_number ELSE child_level.level_number END)
        UNION ALL
        SELECT 1 FROM records child
        JOIN aggregations parent ON parent.id=child.aggregation_id
        JOIN security_levels child_level ON child_level.id=child.security_level_id
        JOIN security_levels parent_level ON parent_level.id=parent.security_level_id
        WHERE (CASE WHEN parent_level.id=NEW.id THEN NEW.level_number ELSE parent_level.level_number END)
            < (CASE WHEN child_level.id=NEW.id THEN NEW.level_number ELSE child_level.level_number END)
    ) THEN
        RAISE EXCEPTION USING ERRCODE='P0001', MESSAGE='security_hierarchy_violation',
            DETAIL='changing this catalogue number would invalidate a resource hierarchy';
    END IF;
    NEW.date_updated := CURRENT_TIMESTAMP;
    NEW.version := OLD.version + 1;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS security_levels_validate_update ON security_levels;
CREATE TRIGGER security_levels_validate_update
BEFORE UPDATE ON security_levels FOR EACH ROW EXECUTE FUNCTION enforce_security_level_catalogue_change();

DROP TRIGGER IF EXISTS security_levels_record_history ON security_levels;
CREATE TRIGGER security_levels_record_history
AFTER INSERT OR UPDATE OR DELETE ON security_levels
FOR EACH ROW EXECUTE FUNCTION record_entity_history('security_level');

-- Keep retention resolution independent of the physical order of aggregation
-- columns now that security metadata extends that table.
CREATE OR REPLACE FUNCTION aggregation_effective_retention_rule(p_aggregation_id bigint)
RETURNS TABLE (
    governing_root_aggregation_id bigint, classification_id bigint,
    rule_source text, rule_id bigint, defined_by_classification_id bigint,
    inheritance_depth integer, current_period_years integer,
    intermediate_period_years integer, final_disposition text,
    instructions text, justification text
)
LANGUAGE plpgsql STABLE AS $$
DECLARE root_row record;
BEGIN
    WITH RECURSIVE lineage AS (
        SELECT a.*, 0 AS depth FROM aggregations a WHERE a.id=p_aggregation_id
        UNION ALL
        SELECT parent.*, child.depth + 1
        FROM aggregations parent JOIN lineage child ON parent.id=child.parent_aggregation_id
    )
    SELECT lineage.* INTO root_row
    FROM lineage WHERE lineage.parent_aggregation_id IS NULL LIMIT 1;
    IF root_row.id IS NULL THEN RETURN; END IF;
    IF EXISTS (SELECT 1 FROM aggregation_retention_rules WHERE aggregation_id=root_row.id) THEN
        RETURN QUERY
        SELECT root_row.id, root_row.classification_id, 'aggregation'::text,
               r.id, NULL::bigint, 0, r.current_period_years,
               r.intermediate_period_years, r.final_disposition,
               r.instructions, r.justification
        FROM aggregation_retention_rules r WHERE r.aggregation_id=root_row.id;
        RETURN;
    END IF;
    RETURN QUERY
    SELECT root_row.id, root_row.classification_id, 'classification'::text,
           r.rule_id, r.defined_by_classification_id, r.inheritance_depth,
           r.current_period_years, r.intermediate_period_years,
           r.final_disposition, r.instructions, NULL::text
    FROM effective_classification_retention_rule(root_row.classification_id) r;
END;
$$;

INSERT INTO schema_migrations (version)
VALUES ('032_add_security_levels')
ON CONFLICT (version) DO NOTHING;

COMMIT;
