-- Classification schemes, classification hierarchy, inheritable rules, and
-- root-aggregation-local retention overrides.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE classification_schemes (
    id               bigserial PRIMARY KEY,
    code             text NOT NULL,
    title            text NOT NULL,
    description      text,
    authority        text,
    scope_note       text,
    edition          text,
    date_created     timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated     timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_published   timestamptz,
    date_deactivated timestamptz,
    version          bigint NOT NULL DEFAULT 1,
    CONSTRAINT classification_schemes_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT classification_schemes_title_not_blank CHECK (btrim(title) <> ''),
    CONSTRAINT classification_schemes_dates_in_order CHECK (
        date_deactivated IS NULL OR date_deactivated >= date_created
    ),
    CONSTRAINT classification_schemes_version_positive CHECK (version > 0)
);
CREATE UNIQUE INDEX classification_schemes_code_ci_unique
    ON classification_schemes (lower(code));

CREATE TABLE classifications (
    id                       bigserial PRIMARY KEY,
    classification_scheme_id bigint NOT NULL
        REFERENCES classification_schemes(id) ON DELETE RESTRICT,
    parent_classification_id bigint REFERENCES classifications(id) ON DELETE RESTRICT,
    code                     text NOT NULL,
    title                    text NOT NULL,
    description              text,
    authority                text,
    scope_note               text,
    keywords                 text,
    is_terminal              boolean NOT NULL DEFAULT false,
    date_created             timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated             timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version                  bigint NOT NULL DEFAULT 1,
    CONSTRAINT classifications_code_not_blank CHECK (btrim(code) <> ''),
    CONSTRAINT classifications_title_not_blank CHECK (btrim(title) <> ''),
    CONSTRAINT classifications_not_own_parent CHECK (
        parent_classification_id IS NULL OR parent_classification_id <> id
    ),
    CONSTRAINT classifications_version_positive CHECK (version > 0)
);
CREATE UNIQUE INDEX classifications_scheme_code_ci_unique
    ON classifications (classification_scheme_id, lower(code));
CREATE INDEX classifications_scheme_parent_idx
    ON classifications (classification_scheme_id, parent_classification_id);

CREATE TABLE classification_retention_rules (
    id                        bigserial PRIMARY KEY,
    classification_id         bigint NOT NULL UNIQUE
        REFERENCES classifications(id) ON DELETE CASCADE,
    current_period_years       integer NOT NULL CHECK (current_period_years >= 0),
    intermediate_period_years  integer NOT NULL CHECK (intermediate_period_years >= 0),
    final_disposition          text NOT NULL CHECK (final_disposition IN (
        'destruction', 'transfer_to_external_archive',
        'selective_preservation', 'retain_as_local_archives'
    )),
    instructions               text,
    date_created               timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated               timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version                    bigint NOT NULL DEFAULT 1 CHECK (version > 0)
);

ALTER TABLE aggregations
    ADD COLUMN classification_id bigint
        REFERENCES classifications(id) ON DELETE RESTRICT;
CREATE INDEX aggregations_classification_id_idx
    ON aggregations (classification_id);
ALTER TABLE aggregations
    ADD CONSTRAINT aggregations_root_classification_consistent
    CHECK (
        (parent_aggregation_id IS NULL AND classification_id IS NOT NULL)
        OR
        (parent_aggregation_id IS NOT NULL AND classification_id IS NULL)
    ) NOT VALID;

CREATE TABLE aggregation_retention_rules (
    id                        bigserial PRIMARY KEY,
    aggregation_id            bigint NOT NULL UNIQUE
        REFERENCES aggregations(id) ON DELETE CASCADE,
    current_period_years       integer NOT NULL CHECK (current_period_years >= 0),
    intermediate_period_years  integer NOT NULL CHECK (intermediate_period_years >= 0),
    final_disposition          text NOT NULL CHECK (final_disposition IN (
        'destruction', 'transfer_to_external_archive',
        'selective_preservation', 'retain_as_local_archives'
    )),
    instructions               text,
    justification              text NOT NULL CHECK (btrim(justification) <> ''),
    date_created               timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated               timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version                    bigint NOT NULL DEFAULT 1 CHECK (version > 0)
);

CREATE TABLE user_classification_selections (
    user_id           bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    classification_id bigint NOT NULL REFERENCES classifications(id) ON DELETE CASCADE,
    last_selected_at  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    selection_count   bigint NOT NULL DEFAULT 1 CHECK (selection_count > 0),
    PRIMARY KEY (user_id, classification_id)
);
CREATE INDEX user_classification_selections_recent_idx
    ON user_classification_selections (user_id, last_selected_at DESC);

CREATE OR REPLACE FUNCTION touch_classification_date_updated()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.date_updated := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validate_classification_scheme_dates()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.date_deactivated IS NOT NULL AND NEW.date_deactivated > CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION 'classification scheme date_deactivated cannot be in the future';
    END IF;
    IF NEW.date_deactivated IS NOT NULL AND NEW.date_deactivated < NEW.date_created THEN
        RAISE EXCEPTION 'classification scheme date_deactivated cannot precede date_created';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION classification_scheme_is_eligible(p_scheme_id bigint)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT COALESCE(
        date_deactivated IS NULL
        AND date_published IS NOT NULL
        AND date_published <= CURRENT_TIMESTAMP,
        false
    )
    FROM classification_schemes
    WHERE id = p_scheme_id;
$$;

CREATE OR REPLACE FUNCTION validate_classification_structure()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parent_scheme bigint;
    parent_terminal boolean;
BEGIN
    IF TG_OP = 'UPDATE'
       AND NEW.classification_scheme_id IS DISTINCT FROM OLD.classification_scheme_id THEN
        RAISE EXCEPTION 'a classification cannot be moved to another scheme';
    END IF;

    IF NEW.parent_classification_id IS NOT NULL THEN
        SELECT classification_scheme_id, is_terminal
        INTO parent_scheme, parent_terminal
        FROM classifications
        WHERE id = NEW.parent_classification_id;
        IF parent_scheme IS NULL THEN
            RAISE EXCEPTION 'parent classification does not exist';
        END IF;
        IF parent_scheme <> NEW.classification_scheme_id THEN
            RAISE EXCEPTION 'parent classification must belong to the same scheme';
        END IF;
        IF parent_terminal THEN
            RAISE EXCEPTION 'terminal classifications cannot contain child classifications';
        END IF;
        IF EXISTS (
            WITH RECURSIVE descendants AS (
                SELECT id FROM classifications WHERE parent_classification_id = NEW.id
                UNION ALL
                SELECT child.id
                FROM classifications AS child
                JOIN descendants AS parent ON child.parent_classification_id = parent.id
            )
            SELECT 1 FROM descendants WHERE id = NEW.parent_classification_id
        ) THEN
            RAISE EXCEPTION 'classification hierarchy cannot contain a cycle';
        END IF;
    END IF;

    IF NEW.is_terminal AND EXISTS (
        SELECT 1 FROM classifications WHERE parent_classification_id = NEW.id
    ) THEN
        RAISE EXCEPTION 'a classification with children cannot be terminal';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.is_terminal AND NOT NEW.is_terminal
       AND EXISTS (SELECT 1 FROM aggregations WHERE classification_id = NEW.id) THEN
        RAISE EXCEPTION 'an assigned terminal classification cannot become a branch';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION effective_classification_retention_rule(p_classification_id bigint)
RETURNS TABLE (
    rule_id bigint,
    defined_by_classification_id bigint,
    inheritance_depth integer,
    current_period_years integer,
    intermediate_period_years integer,
    final_disposition text,
    instructions text
)
LANGUAGE sql STABLE AS $$
    WITH RECURSIVE ancestors AS (
        SELECT c.id, c.parent_classification_id, 0 AS depth
        FROM classifications AS c
        WHERE c.id = p_classification_id
        UNION ALL
        SELECT parent.id, parent.parent_classification_id, child.depth + 1
        FROM classifications AS parent
        JOIN ancestors AS child ON parent.id = child.parent_classification_id
    )
    SELECT rule.id, rule.classification_id, ancestors.depth,
           rule.current_period_years, rule.intermediate_period_years,
           rule.final_disposition, rule.instructions
    FROM ancestors
    JOIN classification_retention_rules AS rule
      ON rule.classification_id = ancestors.id
    ORDER BY ancestors.depth
    LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION validate_terminal_classification_rules()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE missing_code text;
BEGIN
    SELECT c.code INTO missing_code
    FROM classifications AS c
    WHERE c.is_terminal
      AND NOT EXISTS (
          SELECT 1 FROM effective_classification_retention_rule(c.id)
      )
    ORDER BY c.id LIMIT 1;
    IF missing_code IS NOT NULL THEN
        RAISE EXCEPTION 'terminal classification % has no effective retention rule', missing_code;
    END IF;
    RETURN NULL;
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
        END IF;
    ELSIF NEW.classification_id IS NOT NULL THEN
        RAISE EXCEPTION 'child aggregations cannot have a classification';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION validate_root_aggregation_retention_rules()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE invalid_number text;
BEGIN
    SELECT a.aggregation_number INTO invalid_number
    FROM aggregation_retention_rules AS rule
    JOIN aggregations AS a ON a.id = rule.aggregation_id
    WHERE a.parent_aggregation_id IS NOT NULL
    ORDER BY a.id LIMIT 1;
    IF invalid_number IS NOT NULL THEN
        RAISE EXCEPTION 'child aggregation % cannot have a local retention rule', invalid_number;
    END IF;
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION aggregation_effective_retention_rule(p_aggregation_id bigint)
RETURNS TABLE (
    governing_root_aggregation_id bigint,
    classification_id bigint,
    rule_source text,
    rule_id bigint,
    defined_by_classification_id bigint,
    inheritance_depth integer,
    current_period_years integer,
    intermediate_period_years integer,
    final_disposition text,
    instructions text,
    justification text
)
LANGUAGE plpgsql STABLE AS $$
DECLARE root_row aggregations%ROWTYPE;
BEGIN
    WITH RECURSIVE lineage AS (
        SELECT a.*, 0 AS depth FROM aggregations AS a WHERE a.id = p_aggregation_id
        UNION ALL
        SELECT parent.*, child.depth + 1
        FROM aggregations AS parent
        JOIN lineage AS child ON parent.id = child.parent_aggregation_id
    )
    SELECT lineage.id, lineage.parent_aggregation_id, lineage.aggregation_number,
           lineage.title, lineage.description, lineage.date_created,
           lineage.date_opened, lineage.date_closed, lineage.version,
           lineage.classification_id
    INTO root_row
    FROM lineage WHERE lineage.parent_aggregation_id IS NULL LIMIT 1;

    IF root_row.id IS NULL THEN
        RETURN;
    END IF;
    IF EXISTS (
        SELECT 1 FROM aggregation_retention_rules WHERE aggregation_id = root_row.id
    ) THEN
        RETURN QUERY
        SELECT root_row.id, root_row.classification_id, 'aggregation'::text,
               r.id, NULL::bigint, 0,
               r.current_period_years, r.intermediate_period_years,
               r.final_disposition, r.instructions, r.justification
        FROM aggregation_retention_rules AS r
        WHERE r.aggregation_id = root_row.id;
        RETURN;
    END IF;
    RETURN QUERY
    SELECT root_row.id, root_row.classification_id, 'classification'::text,
           r.rule_id, r.defined_by_classification_id, r.inheritance_depth,
           r.current_period_years, r.intermediate_period_years,
           r.final_disposition, r.instructions, NULL::text
    FROM effective_classification_retention_rule(root_row.classification_id) AS r;
END;
$$;

CREATE OR REPLACE FUNCTION record_classification_selection()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE context_user_id text;
BEGIN
    context_user_id := NULLIF(current_setting('app.user_id', true), '');
    IF context_user_id IS NOT NULL
       AND NEW.parent_aggregation_id IS NULL
       AND NEW.classification_id IS NOT NULL
       AND (TG_OP = 'INSERT' OR NEW.classification_id IS DISTINCT FROM OLD.classification_id) THEN
        INSERT INTO user_classification_selections (
            user_id, classification_id, last_selected_at, selection_count
        ) VALUES (context_user_id::bigint, NEW.classification_id, CURRENT_TIMESTAMP, 1)
        ON CONFLICT (user_id, classification_id) DO UPDATE
        SET last_selected_at = EXCLUDED.last_selected_at,
            selection_count = user_classification_selections.selection_count + 1;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER classification_schemes_validate_dates
BEFORE INSERT OR UPDATE OF date_created, date_deactivated ON classification_schemes
FOR EACH ROW EXECUTE FUNCTION validate_classification_scheme_dates();
CREATE TRIGGER classification_schemes_touch
BEFORE UPDATE ON classification_schemes
FOR EACH ROW EXECUTE FUNCTION touch_classification_date_updated();
CREATE TRIGGER classifications_touch
BEFORE UPDATE ON classifications
FOR EACH ROW EXECUTE FUNCTION touch_classification_date_updated();
CREATE TRIGGER classification_retention_rules_touch
BEFORE UPDATE ON classification_retention_rules
FOR EACH ROW EXECUTE FUNCTION touch_classification_date_updated();
CREATE TRIGGER aggregation_retention_rules_touch
BEFORE UPDATE ON aggregation_retention_rules
FOR EACH ROW EXECUTE FUNCTION touch_classification_date_updated();

CREATE TRIGGER classifications_validate_structure
BEFORE INSERT OR UPDATE OF classification_scheme_id, parent_classification_id, is_terminal
ON classifications FOR EACH ROW EXECUTE FUNCTION validate_classification_structure();

CREATE CONSTRAINT TRIGGER classifications_validate_effective_rule
AFTER INSERT OR UPDATE ON classifications
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_terminal_classification_rules();
CREATE CONSTRAINT TRIGGER classification_rules_validate_effective_rule
AFTER INSERT OR UPDATE OR DELETE ON classification_retention_rules
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_terminal_classification_rules();

CREATE TRIGGER aggregations_validate_classification
BEFORE INSERT OR UPDATE OF parent_aggregation_id, classification_id ON aggregations
FOR EACH ROW EXECUTE FUNCTION validate_aggregation_classification();
CREATE CONSTRAINT TRIGGER aggregation_rules_validate_root
AFTER INSERT OR UPDATE ON aggregation_retention_rules
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_root_aggregation_retention_rules();
CREATE CONSTRAINT TRIGGER aggregations_validate_local_rule_root
AFTER UPDATE ON aggregations
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_root_aggregation_retention_rules();
CREATE TRIGGER aggregations_record_classification_selection
AFTER INSERT OR UPDATE OF classification_id ON aggregations
FOR EACH ROW EXECUTE FUNCTION record_classification_selection();

CREATE TRIGGER classification_schemes_bump_version
BEFORE UPDATE ON classification_schemes
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();
CREATE TRIGGER classifications_bump_version
BEFORE UPDATE ON classifications
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();
CREATE TRIGGER classification_retention_rules_bump_version
BEFORE UPDATE ON classification_retention_rules
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();
CREATE TRIGGER aggregation_retention_rules_bump_version
BEFORE UPDATE ON aggregation_retention_rules
FOR EACH ROW EXECUTE FUNCTION bump_entity_version();

CREATE TRIGGER classification_schemes_record_history
AFTER INSERT OR UPDATE OR DELETE ON classification_schemes
FOR EACH ROW EXECUTE FUNCTION record_entity_history('classification_scheme');
CREATE TRIGGER classifications_record_history
AFTER INSERT OR UPDATE OR DELETE ON classifications
FOR EACH ROW EXECUTE FUNCTION record_entity_history('classification');
CREATE TRIGGER classification_retention_rules_record_history
AFTER INSERT OR UPDATE OR DELETE ON classification_retention_rules
FOR EACH ROW EXECUTE FUNCTION record_entity_history('classification_retention_rule');
CREATE TRIGGER aggregation_retention_rules_record_history
AFTER INSERT OR UPDATE OR DELETE ON aggregation_retention_rules
FOR EACH ROW EXECUTE FUNCTION record_entity_history('aggregation_retention_rule');

INSERT INTO schema_migrations(version)
VALUES ('019_add_classification_schemes')
ON CONFLICT(version) DO NOTHING;
