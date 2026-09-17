DO $$
DECLARE
    migrated_content text;
    migrated_count integer;
    migrated_status text;
BEGIN
    SELECT convert_from(blob.content, 'UTF8'), content_set.segment_count, content_set.status
      INTO STRICT migrated_content, migrated_count, migrated_status
      FROM digital_components component
      JOIN digital_component_content_sets content_set
        ON content_set.id = component.active_content_set_id
      JOIN digital_component_blobs blob ON blob.content_set_id = content_set.id
     WHERE component.file_name = 'legacy.bin' AND blob.segment_no = 0;
    IF migrated_content <> 'legacy-content'
       OR migrated_count <> 1 OR migrated_status <> 'active' THEN
        RAISE EXCEPTION 'legacy content was not preserved by segmented storage migration';
    END IF;
END;
$$;

-- Keep the migration fixture isolated from the behavioral test scripts that
-- follow and intentionally assume an otherwise empty records subsystem.
DELETE FROM records WHERE record_number = 'SEG-MIG-REC';
DELETE FROM aggregations WHERE aggregation_number = 'SEG-MIG-AGG';
ALTER TABLE event_history DISABLE TRIGGER USER;
TRUNCATE event_history RESTART IDENTITY;
ALTER TABLE event_history ENABLE TRIGGER USER;
