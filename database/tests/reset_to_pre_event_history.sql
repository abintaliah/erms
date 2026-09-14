-- Test-only fixture: turn the freshly bootstrapped database into the state that
-- existed immediately before migration 001.
DROP TABLE IF EXISTS user_role_assignments;
DROP TABLE IF EXISTS roles;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS org_units;
DROP FUNCTION IF EXISTS set_assignment_default_dates();
DROP FUNCTION IF EXISTS set_user_management_default_dates();
DROP FUNCTION IF EXISTS prevent_role_supervision_cycle();
DROP FUNCTION IF EXISTS prevent_org_unit_cycle();
DELETE FROM schema_migrations WHERE version = '002_add_user_management';

DROP TRIGGER IF EXISTS aggregations_record_history ON aggregations;
DROP TRIGGER IF EXISTS records_record_history ON records;
DROP TRIGGER IF EXISTS digital_components_record_history ON digital_components;
DROP FUNCTION IF EXISTS record_entity_history();
DROP TABLE IF EXISTS event_history;
DROP FUNCTION IF EXISTS reject_event_history_mutation();
DELETE FROM schema_migrations WHERE version = '001_add_event_history';
