INSERT INTO classification_schemes (code, title, date_published)
VALUES ('SEG-MIG', 'Segment migration fixture', CURRENT_TIMESTAMP);
INSERT INTO classifications (classification_scheme_id, code, title, is_terminal)
SELECT id, 'SEG-MIG-01', 'Segment migration fixture', false
FROM classification_schemes WHERE code = 'SEG-MIG';
INSERT INTO classification_retention_rules (
    classification_id, current_period_years, intermediate_period_years, final_disposition
)
SELECT id, 1, 0, 'destruction' FROM classifications WHERE code = 'SEG-MIG-01';
UPDATE classifications SET is_terminal = true WHERE code = 'SEG-MIG-01';
INSERT INTO aggregations (aggregation_number, title, classification_id)
SELECT 'SEG-MIG-AGG', 'Segment migration fixture', id
FROM classifications WHERE code = 'SEG-MIG-01';
INSERT INTO records (aggregation_id, record_number, title)
SELECT id, 'SEG-MIG-REC', 'Segment migration fixture'
FROM aggregations WHERE aggregation_number = 'SEG-MIG-AGG';
INSERT INTO digital_components (
    record_id, component_order, file_name, mime_type, size_in_bytes,
    checksum_algo, checksum_value, content_status
)
SELECT id, 1, 'legacy.bin', 'application/octet-stream', 14,
       'sha256', 'legacy-checksum', 'available'
FROM records WHERE record_number = 'SEG-MIG-REC';
INSERT INTO digital_component_blobs (digital_component_id, content)
SELECT id, convert_to('legacy-content', 'UTF8')
FROM digital_components WHERE file_name = 'legacy.bin';
