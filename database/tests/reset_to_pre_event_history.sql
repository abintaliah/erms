-- Test-only fixture: turn the freshly bootstrapped database into the state that
-- existed immediately before migration 001.
DROP TRIGGER IF EXISTS aggregations_record_history ON aggregations;
DROP TRIGGER IF EXISTS records_record_history ON records;
DROP TRIGGER IF EXISTS digital_components_record_history ON digital_components;
DROP FUNCTION IF EXISTS record_entity_history();
DROP TABLE IF EXISTS event_history;
DROP FUNCTION IF EXISTS reject_event_history_mutation();
DELETE FROM schema_migrations WHERE version = '001_add_event_history';
