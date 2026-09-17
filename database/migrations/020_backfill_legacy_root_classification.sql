-- Backfill development-only root aggregations which predate the classification
-- subsystem. The user explicitly selected the existing "General"
-- classification in "Test Classification Scheme" as the remediation target.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DO $$
DECLARE
    migration_name constant text := '020_backfill_legacy_root_classification';
    target_scheme classification_schemes%ROWTYPE;
    target_classification classifications%ROWTYPE;
    matching_schemes integer;
    matching_classifications integer;
    updated_roots integer;
BEGIN
    IF EXISTS (SELECT 1 FROM schema_migrations WHERE version = migration_name) THEN
        RETURN;
    END IF;

    SELECT count(*) INTO matching_schemes
    FROM classification_schemes
    WHERE lower(title) = lower('Test Classification Scheme');

    IF matching_schemes <> 1 THEN
        RAISE EXCEPTION
            'migration % requires exactly one scheme titled Test Classification Scheme; found %',
            migration_name, matching_schemes;
    END IF;

    SELECT * INTO STRICT target_scheme
    FROM classification_schemes
    WHERE lower(title) = lower('Test Classification Scheme');

    SELECT count(*) INTO matching_classifications
    FROM classifications
    WHERE classification_scheme_id = target_scheme.id
      AND lower(title) = lower('General');

    IF matching_classifications <> 1 THEN
        RAISE EXCEPTION
            'migration % requires exactly one General classification in scheme %; found %',
            migration_name, target_scheme.code, matching_classifications;
    END IF;

    SELECT * INTO STRICT target_classification
    FROM classifications
    WHERE classification_scheme_id = target_scheme.id
      AND lower(title) = lower('General');

    IF NOT target_classification.is_terminal THEN
        RAISE EXCEPTION 'classification % — % must be terminal',
            target_classification.code, target_classification.title;
    END IF;

    IF NOT classification_scheme_is_eligible(target_scheme.id) THEN
        RAISE EXCEPTION 'classification scheme % — % must be active and currently published',
            target_scheme.code, target_scheme.title;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM effective_classification_retention_rule(target_classification.id)
    ) THEN
        RAISE EXCEPTION 'classification % — % must have an effective retention rule',
            target_classification.code, target_classification.title;
    END IF;

    PERFORM set_config('app.actor_type', 'automated_process', true),
            set_config('app.event_source', 'migration', true),
            set_config(
                'app.change_reason',
                'Backfill legacy unclassified root aggregation to General classification',
                true
            ),
            set_config(
                'app.event_metadata',
                jsonb_build_object(
                    'migration', migration_name,
                    'operation', 'legacy_root_classification_backfill',
                    'basis', 'greenfield remediation explicitly authorized by the user',
                    'target_scheme', jsonb_build_object(
                        'id', target_scheme.id,
                        'code', target_scheme.code,
                        'title', target_scheme.title
                    ),
                    'target_classification', jsonb_build_object(
                        'id', target_classification.id,
                        'code', target_classification.code,
                        'title', target_classification.title
                    )
                )::text,
                true
            );

    UPDATE aggregations
    SET classification_id = target_classification.id
    WHERE parent_aggregation_id IS NULL
      AND classification_id IS NULL;

    GET DIAGNOSTICS updated_roots = ROW_COUNT;

    IF EXISTS (
        SELECT 1
        FROM aggregations
        WHERE parent_aggregation_id IS NULL
          AND classification_id IS NULL
    ) THEN
        RAISE EXCEPTION 'migration % left unclassified root aggregations', migration_name;
    END IF;

    SET CONSTRAINTS ALL IMMEDIATE;

    ALTER TABLE aggregations
        VALIDATE CONSTRAINT aggregations_root_classification_consistent;

    INSERT INTO schema_migrations(version) VALUES (migration_name);

    RAISE NOTICE 'classified % legacy root aggregation(s) as % — %',
        updated_roots, target_classification.code, target_classification.title;
END;
$$;
