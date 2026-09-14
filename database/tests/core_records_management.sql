\set ON_ERROR_STOP on

BEGIN;

INSERT INTO aggregations (aggregation_number, title, description, date_opened)
VALUES ('AGG-001', 'Root aggregation', 'Top-level test aggregation', NULL)
RETURNING id AS root_aggregation_id \gset

INSERT INTO aggregations (
    parent_aggregation_id,
    aggregation_number,
    title
)
VALUES (
    :root_aggregation_id,
    'AGG-002',
    'Child aggregation'
)
RETURNING id AS child_aggregation_id \gset

INSERT INTO records (
    aggregation_id,
    record_number,
    title,
    date_originated
)
VALUES (
    :child_aggregation_id,
    'REC-001',
    'Test record',
    NULL
)
RETURNING id AS record_id \gset

INSERT INTO digital_components (
    record_id,
    component_order,
    file_name,
    date_originated,
    mime_type,
    size_in_bytes,
    checksum_algo,
    checksum_value
)
VALUES (
    :record_id,
    1,
    'example.pdf',
    NULL,
    'application/pdf',
    1024,
    'SHA-256',
    repeat('a', 64)
);

INSERT INTO digital_components (
    record_id,
    component_order,
    file_name,
    mime_type,
    size_in_bytes,
    checksum_algo,
    checksum_value
)
VALUES (
    :record_id,
    2,
    'example-signature.p7s',
    'application/pkcs7-signature',
    512,
    'SHA-256',
    repeat('b', 64)
);

DO $$
DECLARE
    opened_matches boolean;
    originated_matches boolean;
    component_originated_matches boolean;
BEGIN
    SELECT date_opened = date_created
    INTO opened_matches
    FROM aggregations
    WHERE aggregation_number = 'AGG-001';

    SELECT date_originated = date_created
    INTO originated_matches
    FROM records
    WHERE record_number = 'REC-001';

    SELECT date_originated = date_created
    INTO component_originated_matches
    FROM digital_components
    WHERE file_name = 'example.pdf';

    IF NOT opened_matches OR NOT originated_matches OR NOT component_originated_matches THEN
        RAISE EXCEPTION 'default date behavior is incorrect';
    END IF;
END;
$$;

DO $$
BEGIN
    BEGIN
        INSERT INTO records (record_number, title, aggregation_id)
        VALUES ('REC-UNFILED-001', 'Unfiled record', NULL);
        RAISE EXCEPTION 'record without an aggregation was accepted';
    EXCEPTION
        WHEN not_null_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO records (aggregation_id, record_number, title)
        VALUES (
            (SELECT id FROM aggregations WHERE aggregation_number = 'AGG-002'),
            'REC-001',
            'Duplicate record number'
        );
        RAISE EXCEPTION 'duplicate record number was accepted';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    BEGIN
        UPDATE aggregations
        SET parent_aggregation_id = (
            SELECT id FROM aggregations WHERE aggregation_number = 'AGG-002'
        )
        WHERE aggregation_number = 'AGG-001';
        RAISE EXCEPTION 'aggregation cycle was accepted';
    EXCEPTION
        WHEN raise_exception THEN
            IF SQLERRM <> 'aggregation hierarchy cannot contain a cycle' THEN
                RAISE;
            END IF;
    END;

    BEGIN
        INSERT INTO digital_components (
            record_id,
            component_order,
            file_name,
            mime_type,
            size_in_bytes,
            checksum_algo,
            checksum_value
        )
        VALUES (999999, 1, 'orphan.txt', 'text/plain', 1, 'SHA-256', 'abc');
        RAISE EXCEPTION 'orphaned digital component was accepted';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO digital_components (
            record_id,
            component_order,
            file_name,
            mime_type,
            size_in_bytes,
            checksum_algo,
            checksum_value
        )
        VALUES (
            (SELECT id FROM records WHERE record_number = 'REC-001'),
            2,
            'duplicate-order.txt',
            'text/plain',
            1,
            'SHA-256',
            'abc'
        );
        RAISE EXCEPTION 'duplicate component order was accepted';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;
END;
$$;

ROLLBACK;
