-- Test-only fixture: turn the freshly bootstrapped database into the state that
-- existed immediately before migration 001.
DROP TABLE IF EXISTS record_draft_components;
DROP TABLE IF EXISTS record_drafts;
DROP TABLE IF EXISTS digital_component_blobs;
DROP TRIGGER IF EXISTS aggregations_bump_version ON aggregations;
DROP TRIGGER IF EXISTS records_bump_version ON records;
DROP TRIGGER IF EXISTS digital_components_bump_version ON digital_components;
DROP TRIGGER IF EXISTS org_units_bump_version ON org_units;
DROP TRIGGER IF EXISTS users_bump_version ON users;
DROP TRIGGER IF EXISTS roles_bump_version ON roles;
DROP TRIGGER IF EXISTS user_role_assignments_bump_version ON user_role_assignments;
DROP FUNCTION IF EXISTS bump_entity_version();
DROP TRIGGER IF EXISTS event_history_remove_internal_fields ON event_history;
DROP FUNCTION IF EXISTS remove_internal_audit_fields();
DROP FUNCTION IF EXISTS append_domain_event(text, bigint, text, jsonb, text);
ALTER TABLE aggregations DROP COLUMN IF EXISTS version;
ALTER TABLE records DROP COLUMN IF EXISTS version;
ALTER TABLE digital_components
    DROP COLUMN IF EXISTS version,
    DROP COLUMN IF EXISTS storage_backend,
    DROP COLUMN IF EXISTS storage_key,
    DROP COLUMN IF EXISTS content_status;
DELETE FROM schema_migrations WHERE version = '003_add_content_storage_and_entity_versions';

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
