-- Test-only fixture: turn the freshly bootstrapped database into the state that
-- existed immediately before migration 001.
DROP TRIGGER IF EXISTS aggregations_record_classification_selection ON aggregations;
DROP TRIGGER IF EXISTS aggregations_record_classification_scheme_first_use ON aggregations;
DROP TRIGGER IF EXISTS aggregations_record_classification_governance_first_use ON aggregations;
DROP TRIGGER IF EXISTS aggregations_validate_local_rule_root ON aggregations;
DROP TRIGGER IF EXISTS aggregations_validate_classification ON aggregations;
DROP TABLE IF EXISTS user_classification_selections;
DROP TABLE IF EXISTS aggregation_retention_rules;
DROP TABLE IF EXISTS classification_retention_rules;
ALTER TABLE aggregations
    DROP CONSTRAINT IF EXISTS aggregations_root_classification_consistent,
    DROP COLUMN IF EXISTS classification_id;
DROP TABLE IF EXISTS classifications;
DROP TABLE IF EXISTS classification_schemes;
DROP FUNCTION IF EXISTS record_classification_selection();
DROP FUNCTION IF EXISTS record_classification_scheme_first_use();
DROP FUNCTION IF EXISTS record_classification_governance_first_use();
DROP FUNCTION IF EXISTS protect_classification_deletion();
DROP FUNCTION IF EXISTS validate_classification_dates();
DROP FUNCTION IF EXISTS classification_is_effectively_active(bigint);
DROP FUNCTION IF EXISTS delete_unused_classification_scheme();
DROP FUNCTION IF EXISTS aggregation_effective_retention_rule(bigint);
DROP FUNCTION IF EXISTS validate_root_aggregation_retention_rules();
DROP FUNCTION IF EXISTS validate_aggregation_classification();
DROP FUNCTION IF EXISTS validate_terminal_classification_rules();
DROP FUNCTION IF EXISTS effective_classification_retention_rule(bigint);
DROP FUNCTION IF EXISTS validate_classification_structure();
DROP FUNCTION IF EXISTS classification_scheme_is_eligible(bigint);
DROP FUNCTION IF EXISTS validate_classification_scheme_dates();
DROP FUNCTION IF EXISTS touch_classification_date_updated();
DELETE FROM schema_migrations WHERE version = '019_add_classification_schemes';
DELETE FROM schema_migrations WHERE version IN (
    '022_govern_classification_scheme_deletion',
    '023_govern_classification_lifecycle'
);
DROP TRIGGER IF EXISTS digital_component_blobs_protect_closed_aggregation ON digital_component_blobs;
DROP TRIGGER IF EXISTS digital_components_protect_closed_aggregation ON digital_components;
DROP TRIGGER IF EXISTS records_protect_closed_aggregation ON records;
DROP TRIGGER IF EXISTS aggregations_protect_closed_hierarchy ON aggregations;
DROP TRIGGER IF EXISTS aggregations_validate_closure_date ON aggregations;
DROP FUNCTION IF EXISTS protect_blob_in_closed_aggregation();
DROP FUNCTION IF EXISTS protect_component_in_closed_aggregation();
DROP FUNCTION IF EXISTS assert_record_effectively_open(bigint);
DROP FUNCTION IF EXISTS protect_record_in_closed_aggregation();
DROP FUNCTION IF EXISTS protect_closed_aggregation_hierarchy();
DROP FUNCTION IF EXISTS validate_aggregation_closure_date();
DROP FUNCTION IF EXISTS assert_aggregation_effectively_open(bigint);
DELETE FROM schema_migrations WHERE version IN (
    '006_enforce_closed_aggregations', '007_freeze_closed_aggregation_metadata',
    '008_cascade_record_digital_components', '009_user_management_lifecycle',
    '010_rename_org_unit_deactivation_date',
    '011_normalize_org_unit_event_history',
    '012_backfill_anonymous_event_actor',
    '013_snapshot_event_actor_identity',
    '014_backfill_webui_event_source',
    '015_reclassify_lifecycle_normalization_events',
    '016_snapshot_role_assignment_parties',
    '017_rename_system_accounts_to_service',
    '018_rename_system_actor_to_automated_process'
);
DROP TRIGGER IF EXISTS event_history_populate_relationship_snapshot ON event_history;
DROP FUNCTION IF EXISTS populate_event_relationship_snapshot();
DROP TRIGGER IF EXISTS event_history_populate_actor_snapshot ON event_history;
DROP FUNCTION IF EXISTS populate_event_actor_snapshot();
DROP TRIGGER IF EXISTS user_role_assignments_validate_active ON user_role_assignments;
DROP TRIGGER IF EXISTS roles_normalize_lifecycle ON roles;
DROP TRIGGER IF EXISTS users_normalize_lifecycle ON users;
DROP TRIGGER IF EXISTS org_units_normalize_lifecycle ON org_units;
DROP FUNCTION IF EXISTS validate_active_role_assignment();
DROP FUNCTION IF EXISTS role_effectively_active(bigint);
DROP FUNCTION IF EXISTS org_unit_effectively_active(bigint);
DROP FUNCTION IF EXISTS normalize_user_management_lifecycle();
ALTER TABLE digital_components
    DROP CONSTRAINT IF EXISTS digital_components_record_id_fkey,
    ADD CONSTRAINT digital_components_record_id_fkey
        FOREIGN KEY (record_id) REFERENCES records (id) ON DELETE RESTRICT;
DROP TABLE IF EXISTS record_draft_components;
DROP TABLE IF EXISTS record_drafts;
DROP TABLE IF EXISTS login_sessions;
DROP TABLE IF EXISTS user_credentials;
ALTER TABLE users DROP COLUMN IF EXISTS account_type;
DELETE FROM schema_migrations WHERE version IN ('004_add_record_drafts', '005_add_authentication');
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
