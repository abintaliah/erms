BEGIN;

DO $$
DECLARE
    gcs_scheme_id bigint;
    target_classification_id bigint;
    other_terminal_count integer;
BEGIN
    SELECT id INTO gcs_scheme_id
    FROM classification_schemes
    WHERE lower(code) = lower('GCS');

    IF gcs_scheme_id IS NULL THEN
        RAISE EXCEPTION 'classification scheme GCS does not exist';
    END IF;

    SELECT id INTO target_classification_id
    FROM classifications
    WHERE classification_scheme_id = gcs_scheme_id
      AND lower(code) = lower('GCS-01.01.01')
      AND is_terminal;

    IF target_classification_id IS NULL THEN
        RAISE EXCEPTION
            'terminal classification GCS-01.01.01 does not exist in scheme GCS';
    END IF;

    SELECT count(*) INTO other_terminal_count
    FROM classifications
    WHERE classification_scheme_id = gcs_scheme_id
      AND is_terminal
      AND id <> target_classification_id
      AND date_deactivated IS NULL;

    IF other_terminal_count = 0 THEN
        RAISE EXCEPTION 'scheme GCS has no other active terminal classifications';
    END IF;

    IF EXISTS (
        SELECT 1 FROM aggregations
        WHERE aggregation_number LIKE 'GCS-SEED-%'
    ) OR EXISTS (
        SELECT 1 FROM records
        WHERE record_number LIKE 'GCS-SEED-%'
    ) THEN
        RAISE EXCEPTION
            'GCS seed data already exists; reserved GCS-SEED identifiers must be absent';
    END IF;

    PERFORM set_config('app.actor_type', 'automated_process', true),
            set_config('app.actor_name', 'GCS classification-tree seed', true),
            set_config('app.event_source', 'seeding', true),
            set_config(
                'app.change_reason',
                'Create deterministic realistic GCS aggregation and record data for classification-tree load testing',
                true
            ),
            set_config(
                'app.event_metadata',
                jsonb_build_object(
                    'seed', '001_seed_gcs_aggregation_tree_load_data',
                    'purpose', 'classification_tree_load_testing',
                    'distributed_aggregations', 100,
                    'distributed_records', 300,
                    'focused_classification', 'GCS-01.01.01',
                    'focused_aggregations', 75,
                    'focused_records', 100,
                    'deterministic', true
                )::text,
                true
            );

    CREATE TEMP TABLE seed_other_terminals ON COMMIT DROP AS
    SELECT id, code, title, description,
           row_number() OVER (ORDER BY code) AS sequence_no
    FROM classifications
    WHERE classification_scheme_id = gcs_scheme_id
      AND is_terminal
      AND id <> target_classification_id
      AND date_deactivated IS NULL
    ORDER BY code;

    CREATE TEMP TABLE seed_aggregations (
        seed_group text NOT NULL,
        sequence_no integer NOT NULL,
        classification_id bigint NOT NULL,
        aggregation_number text PRIMARY KEY,
        title text NOT NULL,
        description text NOT NULL,
        date_created timestamptz NOT NULL,
        date_opened timestamptz NOT NULL
    ) ON COMMIT DROP;

    INSERT INTO seed_aggregations (
        seed_group, sequence_no, classification_id, aggregation_number,
        title, description, date_created, date_opened
    )
    SELECT
        'distributed',
        generated.sequence_no,
        classification.id,
        format('GCS-SEED-D-%s', lpad(generated.sequence_no::text, 4, '0')),
        CASE generated.sequence_no % 8
            WHEN 0 THEN format('%s — Annual Programme %s', classification.title, 2021 + generated.sequence_no % 5)
            WHEN 1 THEN format('%s — Operational Case Series %s', classification.title, lpad(generated.sequence_no::text, 3, '0'))
            WHEN 2 THEN format('%s — Review and Approval Cycle %s', classification.title, 1 + generated.sequence_no % 12)
            WHEN 3 THEN format('%s — Governance and Assurance File %s', classification.title, 2023 + generated.sequence_no % 4)
            WHEN 4 THEN format('%s — Service Delivery Portfolio %s', classification.title, lpad(generated.sequence_no::text, 3, '0'))
            WHEN 5 THEN format('%s — Planning and Monitoring Series %s', classification.title, 2021 + generated.sequence_no % 5)
            WHEN 6 THEN format('%s — Compliance Evidence Set %s', classification.title, lpad(generated.sequence_no::text, 3, '0'))
            ELSE format('%s — Management Working File %s', classification.title, lpad(generated.sequence_no::text, 3, '0'))
        END,
        format(
            '%s This aggregation groups the authoritative plans, approvals, correspondence, evidence and outcomes for %s, maintained as a coherent business file for the %s cycle.',
            classification.description,
            lower(classification.title),
            2021 + generated.sequence_no % 5
        ),
        make_timestamptz(
            2021 + generated.sequence_no % 5,
            1 + generated.sequence_no % 12,
            1 + generated.sequence_no % 24,
            9 + generated.sequence_no % 8,
            (generated.sequence_no * 7) % 60,
            0,
            'Asia/Dubai'
        ),
        make_timestamptz(
            2021 + generated.sequence_no % 5,
            1 + generated.sequence_no % 12,
            1 + generated.sequence_no % 24,
            9 + generated.sequence_no % 8,
            (generated.sequence_no * 7) % 60,
            0,
            'Asia/Dubai'
        )
    FROM generate_series(1, 100) AS generated(sequence_no)
    JOIN seed_other_terminals classification
      ON classification.sequence_no =
         1 + ((generated.sequence_no * 17 + 5) % other_terminal_count);

    INSERT INTO seed_aggregations (
        seed_group, sequence_no, classification_id, aggregation_number,
        title, description, date_created, date_opened
    )
    SELECT
        'focused',
        generated.sequence_no,
        target.id,
        format('GCS-SEED-BOARD-%s', lpad(generated.sequence_no::text, 3, '0')),
        CASE generated.sequence_no % 6
            WHEN 0 THEN format('Governing Board Meeting Series — Session %s', lpad(generated.sequence_no::text, 3, '0'))
            WHEN 1 THEN format('Executive Committee Papers — Cycle %s', lpad(generated.sequence_no::text, 3, '0'))
            WHEN 2 THEN format('Board Resolutions and Decisions — Register %s', lpad(generated.sequence_no::text, 3, '0'))
            WHEN 3 THEN format('Audit and Risk Committee Proceedings — Series %s', lpad(generated.sequence_no::text, 3, '0'))
            WHEN 4 THEN format('Governance Committee Deliberations — Cycle %s', lpad(generated.sequence_no::text, 3, '0'))
            ELSE format('Board Strategy Workshop Papers — Session %s', lpad(generated.sequence_no::text, 3, '0'))
        END,
        format(
            'Authoritative governance file for %s. Contains controlled agendas, approved papers, declared interests, deliberations, resolutions, signed minutes and follow-up evidence for session series %s.',
            target.title,
            lpad(generated.sequence_no::text, 3, '0')
        ),
        make_timestamptz(
            2023 + generated.sequence_no % 3,
            1 + generated.sequence_no % 12,
            1 + generated.sequence_no % 24,
            8 + generated.sequence_no % 9,
            (generated.sequence_no * 11) % 60,
            0,
            'Asia/Dubai'
        ),
        make_timestamptz(
            2023 + generated.sequence_no % 3,
            1 + generated.sequence_no % 12,
            1 + generated.sequence_no % 24,
            8 + generated.sequence_no % 9,
            (generated.sequence_no * 11) % 60,
            0,
            'Asia/Dubai'
        )
    FROM generate_series(1, 75) AS generated(sequence_no)
    JOIN classifications target ON target.id = target_classification_id;

    CREATE TEMP TABLE seed_owner_roles ON COMMIT DROP AS
    SELECT role.org_unit_id,
           row_number() OVER (ORDER BY lower(unit.code), lower(role.code), role.id) AS stable_ordinal,
           count(*) OVER () AS role_count
    FROM roles role
    JOIN org_units unit ON unit.id=role.org_unit_id
    WHERE role.status='active' AND unit.status='active' AND lower(unit.code)<>'system';

    IF NOT EXISTS (SELECT 1 FROM seed_owner_roles) THEN
        RAISE EXCEPTION 'GCS aggregation seed requires at least one active non-system role';
    END IF;

    INSERT INTO aggregations (
        classification_id, aggregation_number, title, description,
        date_created, date_opened, owning_org_unit_id, medium, is_vital
    )
    SELECT classification_id, aggregation_number, title, description,
           date_created, date_opened, owner.org_unit_id, 'mixed', false
    FROM (
        SELECT seed.*,
               row_number() OVER (ORDER BY seed_group, sequence_no) AS stable_ordinal
        FROM seed_aggregations seed
    ) seed
    JOIN seed_owner_roles owner
      ON owner.stable_ordinal = 1 + ((seed.stable_ordinal - 1) % owner.role_count)
    ORDER BY seed_group, sequence_no;

    CREATE TEMP TABLE inserted_seed_aggregations ON COMMIT DROP AS
    SELECT aggregation.id, seed.seed_group, seed.sequence_no,
           seed.aggregation_number, seed.title,
           classification.code AS classification_code,
           classification.title AS classification_title
    FROM seed_aggregations seed
    JOIN aggregations aggregation
      ON aggregation.aggregation_number = seed.aggregation_number
    JOIN classifications classification
      ON classification.id = aggregation.classification_id;

    INSERT INTO records (
        aggregation_id, record_number, title, description,
        date_created, date_originated, medium, is_vital
    )
    SELECT
        aggregation.id,
        format('GCS-SEED-D-REC-%s', lpad(generated.sequence_no::text, 4, '0')),
        CASE generated.sequence_no % 7
            WHEN 0 THEN format('%s — Approved plan and authorization', aggregation.classification_title)
            WHEN 1 THEN format('%s — Review findings and management response', aggregation.classification_title)
            WHEN 2 THEN format('%s — Final report and supporting evidence', aggregation.classification_title)
            WHEN 3 THEN format('%s — Business correspondence and decisions', aggregation.classification_title)
            WHEN 4 THEN format('%s — Monitoring summary and action log', aggregation.classification_title)
            WHEN 5 THEN format('%s — Assessment, recommendations and approval', aggregation.classification_title)
            ELSE format('%s — Completion record and verified outcomes', aggregation.classification_title)
        END,
        format(
            'Business record maintained within %s. Documents the principal activity, review, decision and outcome associated with %s.',
            aggregation.title,
            lower(aggregation.classification_title)
        ),
        make_timestamptz(
            2021 + generated.sequence_no % 5,
            1 + generated.sequence_no % 12,
            1 + generated.sequence_no % 24,
            9 + generated.sequence_no % 8,
            (generated.sequence_no * 13) % 60,
            0,
            'Asia/Dubai'
        ),
        make_timestamptz(
            2021 + generated.sequence_no % 5,
            1 + generated.sequence_no % 12,
            1 + generated.sequence_no % 24,
            9 + generated.sequence_no % 8,
            (generated.sequence_no * 13) % 60,
            0,
            'Asia/Dubai'
        ),
        'mixed',
        false
    FROM generate_series(1, 300) AS generated(sequence_no)
    JOIN inserted_seed_aggregations aggregation
      ON aggregation.seed_group = 'distributed'
     AND aggregation.sequence_no = 1 + ((generated.sequence_no * 37 + 9) % 100);

    INSERT INTO records (
        aggregation_id, record_number, title, description,
        date_created, date_originated, medium, is_vital
    )
    SELECT
        aggregation.id,
        format('GCS-SEED-BOARD-REC-%s', lpad(generated.sequence_no::text, 3, '0')),
        CASE generated.sequence_no % 6
            WHEN 0 THEN format('Signed minutes — %s', aggregation.title)
            WHEN 1 THEN format('Approved agenda and meeting notice — %s', aggregation.title)
            WHEN 2 THEN format('Board paper and executive recommendation — %s', aggregation.title)
            WHEN 3 THEN format('Resolution and delegated action record — %s', aggregation.title)
            WHEN 4 THEN format('Declaration of interests and attendance — %s', aggregation.title)
            ELSE format('Decision follow-up and closure report — %s', aggregation.title)
        END,
        format(
            'Controlled governance record from %s, documenting formal consideration, decision, accountability and follow-up by the governing body or executive committee.',
            aggregation.title
        ),
        make_timestamptz(
            2023 + generated.sequence_no % 3,
            1 + generated.sequence_no % 12,
            1 + generated.sequence_no % 24,
            8 + generated.sequence_no % 9,
            (generated.sequence_no * 17) % 60,
            0,
            'Asia/Dubai'
        ),
        make_timestamptz(
            2023 + generated.sequence_no % 3,
            1 + generated.sequence_no % 12,
            1 + generated.sequence_no % 24,
            8 + generated.sequence_no % 9,
            (generated.sequence_no * 17) % 60,
            0,
            'Asia/Dubai'
        ),
        'mixed',
        false
    FROM generate_series(1, 100) AS generated(sequence_no)
    JOIN inserted_seed_aggregations aggregation
      ON aggregation.seed_group = 'focused'
     AND aggregation.sequence_no = 1 + ((generated.sequence_no * 29 + 3) % 75);

    IF (SELECT count(*) FROM seed_aggregations WHERE seed_group = 'distributed') <> 100
       OR (SELECT count(*) FROM seed_aggregations WHERE seed_group = 'focused') <> 75
       OR (SELECT count(*) FROM records WHERE record_number LIKE 'GCS-SEED-D-REC-%') <> 300
       OR (SELECT count(*) FROM records WHERE record_number LIKE 'GCS-SEED-BOARD-REC-%') <> 100 THEN
        RAISE EXCEPTION 'GCS seed verification failed; transaction will be rolled back';
    END IF;
END;
$$;

COMMIT;
