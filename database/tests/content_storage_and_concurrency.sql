BEGIN;

INSERT INTO classification_schemes (code, title, date_published)
VALUES ('CONTENT-TEST', 'Content test scheme', CURRENT_TIMESTAMP)
RETURNING id AS content_scheme_id \gset
INSERT INTO classifications (classification_scheme_id, code, title, is_terminal)
VALUES (:content_scheme_id, 'CONTENT-01', 'Content test classification', true)
RETURNING id AS content_classification_id \gset
INSERT INTO classification_retention_rules
    (classification_id, current_period_years, intermediate_period_years, final_disposition)
VALUES (:content_classification_id, 5, 0, 'destruction');

INSERT INTO aggregations (aggregation_number, title, classification_id)
VALUES ('VERSION-TEST', 'Before', :content_classification_id)
RETURNING id, version \gset version_aggregation_

SELECT 1 / CASE WHEN :'version_aggregation_version'::bigint = 1 THEN 1 ELSE 0 END;

UPDATE aggregations SET title = 'After' WHERE id = :'version_aggregation_id';

SELECT 1 / CASE WHEN (SELECT version FROM aggregations
    WHERE id = :'version_aggregation_id') = 2 THEN 1 ELSE 0 END;

INSERT INTO records (aggregation_id, record_number, title)
VALUES (:'version_aggregation_id', 'BLOB-RECORD', 'Blob record')
RETURNING id \gset version_record_

INSERT INTO digital_components (
    record_id, component_order, file_name, mime_type,
    size_in_bytes, checksum_algo, checksum_value, content_status
)
VALUES (:'version_record_id', 1, 'hello.txt', 'text/plain', 5, 'sha256', 'test', 'available')
RETURNING id \gset version_component_

INSERT INTO digital_component_content_sets (
    digital_component_id, status, size_in_bytes, segment_count,
    checksum_algo, checksum_value, date_completed
)
VALUES (:'version_component_id', 'active', 5, 1, 'sha256', 'test', CURRENT_TIMESTAMP)
RETURNING id \gset version_content_set_

INSERT INTO digital_component_blobs (
    content_set_id, segment_no, segment_size, content
)
VALUES (:'version_content_set_id', 0, 5, convert_to('hello', 'UTF8'));

UPDATE digital_components
SET active_content_set_id = :'version_content_set_id'
WHERE id = :'version_component_id';

SELECT 1 / CASE WHEN (SELECT convert_from(content, 'UTF8')
    FROM digital_component_blobs
    WHERE content_set_id = :'version_content_set_id') = 'hello' THEN 1 ELSE 0 END;

SELECT append_domain_event(
    'digital_component', :'version_component_id', 'CONTENT_UPLOADED',
    '{"size_in_bytes": 5}'::jsonb
);

SELECT 1 / CASE WHEN EXISTS (
        SELECT 1 FROM event_history
        WHERE entity_type = 'digital_component'
          AND entity_id = :'version_component_id'
          AND operation = 'CONTENT_UPLOADED'
          AND before_state IS NULL
          AND after_state IS NULL
          AND metadata @> '{"size_in_bytes": 5}'::jsonb
          AND metadata #>> '{reference_snapshots,entity,name}' = 'hello.txt'
    ) THEN 1 ELSE 0 END;

ROLLBACK;
