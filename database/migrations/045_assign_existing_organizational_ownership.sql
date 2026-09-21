BEGIN;

SELECT set_config('app.actor_type', 'automated_process', true),
       set_config('app.actor_name', 'Database migration 045', true),
       set_config('app.event_source', 'migration', true),
       set_config('app.change_reason', 'Assign deterministic organizational owners to existing holdings', true),
       set_config('app.event_metadata', '{"migration":"045_assign_existing_organizational_ownership"}', true);

CREATE TABLE organizational_ownership_assignment_runs (
    id                    bigserial PRIMARY KEY,
    migration_version     text NOT NULL UNIQUE,
    started_at            timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at          timestamptz,
    root_count            bigint NOT NULL,
    aggregation_count     bigint NOT NULL,
    record_count          bigint NOT NULL,
    before_counts_by_unit jsonb NOT NULL,
    after_counts_by_unit  jsonb,
    CONSTRAINT ownership_assignment_run_version_not_blank
        CHECK (btrim(migration_version) <> ''),
    CONSTRAINT ownership_assignment_run_counts_nonnegative
        CHECK (root_count >= 0 AND aggregation_count >= 0 AND record_count >= 0),
    CONSTRAINT ownership_assignment_run_before_counts_object
        CHECK (jsonb_typeof(before_counts_by_unit) = 'object'),
    CONSTRAINT ownership_assignment_run_after_counts_object
        CHECK (after_counts_by_unit IS NULL OR jsonb_typeof(after_counts_by_unit) = 'object')
);

CREATE TABLE organizational_ownership_root_assignments (
    root_aggregation_id bigint PRIMARY KEY,
    run_id              bigint NOT NULL REFERENCES organizational_ownership_assignment_runs(id) ON DELETE RESTRICT,
    selected_role_id    bigint NOT NULL,
    selected_role_code  text NOT NULL,
    selected_role_name  text NOT NULL,
    owning_org_unit_id  bigint NOT NULL,
    owning_org_unit_code text NOT NULL,
    owning_org_unit_name text NOT NULL,
    match_score         integer NOT NULL CHECK (match_score >= 0),
    assignment_method   text NOT NULL CHECK (assignment_method IN (
        'text_match', 'score_tie_stable_distribution', 'no_text_match_stable_distribution'
    )),
    root_title          text NOT NULL,
    root_description    text,
    assigned_at         timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX organizational_ownership_root_assignments_role_idx
    ON organizational_ownership_root_assignments(selected_role_id, root_aggregation_id);
CREATE INDEX organizational_ownership_root_assignments_unit_idx
    ON organizational_ownership_root_assignments(owning_org_unit_id, root_aggregation_id);

DO $$
DECLARE
    assignment_run_id bigint;
    root_total bigint;
    aggregation_total bigint;
    record_total bigint;
    eligible_role_total bigint;
    reached_total bigint;
    before_counts jsonb;
    after_counts jsonb;
BEGIN
    SELECT count(*) FILTER (WHERE parent_aggregation_id IS NULL), count(*)
      INTO root_total, aggregation_total
      FROM aggregations;
    SELECT count(*) INTO record_total FROM records;

    IF EXISTS (
        WITH RECURSIVE walk(id, path, cycle) AS (
            SELECT id, ARRAY[id], false
              FROM aggregations
             WHERE parent_aggregation_id IS NULL
            UNION ALL
            SELECT child.id, walk.path || child.id, child.id = ANY(walk.path)
              FROM walk
              JOIN aggregations child ON child.parent_aggregation_id = walk.id
             WHERE NOT walk.cycle
        )
        SELECT 1 FROM walk WHERE cycle
    ) THEN
        RAISE EXCEPTION 'cannot assign organizational ownership: aggregation hierarchy contains a cycle';
    END IF;

    WITH RECURSIVE walk(id) AS (
        SELECT id FROM aggregations WHERE parent_aggregation_id IS NULL
        UNION ALL
        SELECT child.id FROM walk JOIN aggregations child ON child.parent_aggregation_id = walk.id
    )
    SELECT count(DISTINCT id) INTO reached_total FROM walk;
    IF reached_total <> aggregation_total THEN
        RAISE EXCEPTION 'cannot assign organizational ownership: % of % aggregations are reachable from roots',
            reached_total, aggregation_total;
    END IF;

    IF EXISTS (
        SELECT 1 FROM records record
        LEFT JOIN aggregations parent ON parent.id = record.aggregation_id
        WHERE parent.id IS NULL
    ) THEN
        RAISE EXCEPTION 'cannot assign organizational ownership: orphan records exist';
    END IF;

    CREATE TEMP TABLE eligible_ownership_roles ON COMMIT DROP AS
    SELECT
        role.id AS role_id,
        role.org_unit_id,
        role.code AS role_code,
        role.name AS role_name,
        unit.code AS org_unit_code,
        unit.name AS org_unit_name,
        row_number() OVER (ORDER BY lower(unit.code), lower(role.code), role.id) AS stable_ordinal,
        lower(concat_ws(' ', role.code, role.name, role.description,
                              unit.code, unit.name, unit.description)) AS searchable_text
    FROM roles role
    JOIN org_units unit ON unit.id = role.org_unit_id
    WHERE role.status = 'active'
      AND unit.status = 'active'
      AND lower(unit.code) <> 'system';

    SELECT count(*) INTO eligible_role_total FROM eligible_ownership_roles;
    IF root_total > 0 AND eligible_role_total = 0 THEN
        RAISE EXCEPTION 'cannot assign organizational ownership: no eligible active non-system role exists';
    END IF;

    WITH unit_keys AS (
        SELECT owning_org_unit_id FROM aggregations
        UNION
        SELECT owning_org_unit_id FROM records
    ), counts AS (
        SELECT
            COALESCE(key.owning_org_unit_id::text, 'unassigned') AS unit_key,
            (SELECT count(*) FROM aggregations a
              WHERE a.owning_org_unit_id IS NOT DISTINCT FROM key.owning_org_unit_id) AS aggregations,
            (SELECT count(*) FROM records r
              WHERE r.owning_org_unit_id IS NOT DISTINCT FROM key.owning_org_unit_id) AS records
        FROM unit_keys key
    )
    SELECT COALESCE(jsonb_object_agg(unit_key, jsonb_build_object(
               'aggregations', aggregations, 'records', records)), '{}'::jsonb)
      INTO before_counts FROM counts;

    INSERT INTO organizational_ownership_assignment_runs(
        migration_version, root_count, aggregation_count, record_count, before_counts_by_unit
    ) VALUES (
        '045_assign_existing_organizational_ownership', root_total,
        aggregation_total, record_total, before_counts
    ) RETURNING id INTO assignment_run_id;

    CREATE TEMP TABLE ownership_candidates ON COMMIT DROP AS
    WITH roots AS (
        SELECT id, title, description,
               row_number() OVER (ORDER BY lower(aggregation_number), id) AS root_ordinal,
               lower(concat_ws(' ', title, description)) AS searchable_text
        FROM aggregations
        WHERE parent_aggregation_id IS NULL
    ), scores AS (
        SELECT root.id AS root_id, root.title, root.description, root.root_ordinal,
               role.role_id, role.role_code, role.role_name,
               role.org_unit_id, role.org_unit_code, role.org_unit_name,
               role.stable_ordinal,
               COALESCE((
                   SELECT count(DISTINCT token)::integer
                   FROM regexp_split_to_table(role.searchable_text, '[^[:alnum:]]+') token
                   WHERE char_length(token) >= 3
                     AND position(token IN root.searchable_text) > 0
               ), 0) AS score
        FROM roots root CROSS JOIN eligible_ownership_roles role
    ), ranked AS (
        SELECT scores.*,
               max(score) OVER (PARTITION BY root_id) AS best_score
        FROM scores
    ), best AS (
        SELECT ranked.*,
               row_number() OVER (PARTITION BY root_id ORDER BY stable_ordinal) AS tied_ordinal,
               count(*) OVER (PARTITION BY root_id) AS tie_count
        FROM ranked
        WHERE score = best_score
    )
    SELECT * FROM best
    WHERE tied_ordinal = 1 + ((root_ordinal - 1) % tie_count);

    INSERT INTO organizational_ownership_root_assignments(
        root_aggregation_id, run_id, selected_role_id, selected_role_code,
        selected_role_name, owning_org_unit_id, owning_org_unit_code,
        owning_org_unit_name,
        match_score, assignment_method, root_title, root_description
    )
    SELECT root_id, assignment_run_id, role_id, role_code, role_name,
           org_unit_id, org_unit_code, org_unit_name, score,
           CASE
               WHEN score = 0 THEN 'no_text_match_stable_distribution'
               WHEN tie_count > 1 THEN 'score_tie_stable_distribution'
               ELSE 'text_match'
           END,
           title, description
    FROM ownership_candidates;

    WITH RECURSIVE assigned(id, owning_org_unit_id) AS (
        SELECT root_aggregation_id, owning_org_unit_id
        FROM organizational_ownership_root_assignments
        WHERE run_id = assignment_run_id
        UNION ALL
        SELECT child.id, assigned.owning_org_unit_id
        FROM assigned
        JOIN aggregations child ON child.parent_aggregation_id = assigned.id
    )
    UPDATE aggregations target
       SET owning_org_unit_id = assigned.owning_org_unit_id
      FROM assigned
     WHERE target.id = assigned.id
       AND target.owning_org_unit_id IS DISTINCT FROM assigned.owning_org_unit_id;

    UPDATE records record
       SET owning_org_unit_id = parent.owning_org_unit_id
      FROM aggregations parent
     WHERE parent.id = record.aggregation_id
       AND record.owning_org_unit_id IS DISTINCT FROM parent.owning_org_unit_id;

    IF EXISTS (SELECT 1 FROM organizational_ownership_diagnostics) THEN
        RAISE EXCEPTION 'organizational ownership assignment left missing or inconsistent owners';
    END IF;
    IF (SELECT count(*) FROM organizational_ownership_root_assignments WHERE run_id = assignment_run_id) <> root_total THEN
        RAISE EXCEPTION 'organizational ownership root assignment count does not reconcile';
    END IF;
    IF (SELECT count(*) FROM aggregations WHERE owning_org_unit_id IS NOT NULL) <> aggregation_total
       OR (SELECT count(*) FROM records WHERE owning_org_unit_id IS NOT NULL) <> record_total THEN
        RAISE EXCEPTION 'organizational ownership assigned totals do not reconcile';
    END IF;

    WITH units AS (
        SELECT owning_org_unit_id FROM aggregations
        UNION
        SELECT owning_org_unit_id FROM records
    ), counts AS (
        SELECT
            unit.owning_org_unit_id::text AS unit_key,
            (SELECT count(*) FROM aggregations a WHERE a.owning_org_unit_id = unit.owning_org_unit_id) AS aggregations,
            (SELECT count(*) FROM records r WHERE r.owning_org_unit_id = unit.owning_org_unit_id) AS records
        FROM units unit
        WHERE unit.owning_org_unit_id IS NOT NULL
    )
    SELECT COALESCE(jsonb_object_agg(unit_key, jsonb_build_object(
               'aggregations', aggregations, 'records', records)), '{}'::jsonb)
      INTO after_counts FROM counts;

    UPDATE organizational_ownership_assignment_runs
       SET completed_at = clock_timestamp(), after_counts_by_unit = after_counts
     WHERE id = assignment_run_id;
END;
$$;

INSERT INTO schema_migrations(version)
VALUES ('045_assign_existing_organizational_ownership');

COMMIT;
