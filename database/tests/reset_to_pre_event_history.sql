-- Test-only fixture: turn the freshly bootstrapped database into the state that
-- existed immediately before migration 001.
DROP TRIGGER IF EXISTS aggregations_enforce_ownership ON aggregations;
DROP TRIGGER IF EXISTS aggregations_propagate_ownership ON aggregations;
DROP TRIGGER IF EXISTS records_enforce_ownership ON records;
DROP FUNCTION IF EXISTS enforce_aggregation_ownership();
DROP FUNCTION IF EXISTS propagate_aggregation_ownership();
DROP FUNCTION IF EXISTS enforce_record_ownership();
DROP VIEW IF EXISTS authorized_records_for_search;
DROP VIEW IF EXISTS authorized_aggregations_for_search;
DROP INDEX IF EXISTS aggregation_acl_org_unit_members_grant_unique;
DROP INDEX IF EXISTS child_aggregation_acl_org_unit_members_grant_unique;
DROP INDEX IF EXISTS child_record_acl_org_unit_members_grant_unique;
DROP INDEX IF EXISTS record_acl_org_unit_members_grant_unique;
ALTER TABLE roles
    DROP CONSTRAINT IF EXISTS roles_org_unit_members_code_reserved,
    DROP CONSTRAINT IF EXISTS roles_org_unit_members_name_reserved;
DELETE FROM schema_migrations
WHERE version = '048_add_org_unit_members_acl_principal';
DELETE FROM schema_migrations
WHERE version = '049_initialize_organizational_acl_defaults';
DELETE FROM schema_migrations
WHERE version = '050_add_root_ownership_correction';
DELETE FROM schema_migrations
WHERE version = '047_expose_organizational_ownership_in_search';
ALTER TABLE records ALTER COLUMN owning_org_unit_id DROP NOT NULL;
ALTER TABLE aggregations ALTER COLUMN owning_org_unit_id DROP NOT NULL;
DELETE FROM schema_migrations
WHERE version = '046_enforce_organizational_ownership';
DROP TABLE IF EXISTS organizational_ownership_root_assignments;
DROP TABLE IF EXISTS organizational_ownership_assignment_runs;
DELETE FROM schema_migrations
WHERE version = '045_assign_existing_organizational_ownership';
DROP VIEW IF EXISTS organizational_ownership_diagnostics;
ALTER TABLE records
    DROP CONSTRAINT IF EXISTS records_owning_org_unit_fk,
    DROP COLUMN IF EXISTS owning_org_unit_id;
ALTER TABLE aggregations
    DROP CONSTRAINT IF EXISTS aggregations_owning_org_unit_fk,
    DROP COLUMN IF EXISTS owning_org_unit_id;
DELETE FROM schema_migrations
WHERE version = '044_add_organizational_ownership_foundation';
DROP FUNCTION IF EXISTS current_user_can_record_operation(bigint,text,text);
DROP FUNCTION IF EXISTS current_user_can_aggregation_operation(bigint,text,text);
DROP FUNCTION IF EXISTS user_can_record_operation(bigint,bigint,text,text);
DROP FUNCTION IF EXISTS user_can_aggregation_operation(bigint,bigint,text,text);
DROP FUNCTION IF EXISTS user_has_governance_clearance(bigint,bigint);
DROP VIEW IF EXISTS authorized_event_history;
DROP VIEW IF EXISTS authorized_records_for_search;
DROP VIEW IF EXISTS authorized_aggregations_for_search;
DROP FUNCTION IF EXISTS current_user_can_view_event_resource(text,bigint,jsonb,jsonb);
DROP FUNCTION IF EXISTS current_user_can_list_record_components(bigint);
DROP FUNCTION IF EXISTS current_user_can_view_record(bigint);
DROP FUNCTION IF EXISTS current_user_can_view_aggregation(bigint);
DROP FUNCTION IF EXISTS current_user_id();
DROP FUNCTION IF EXISTS user_can_view_record(bigint,bigint);
DROP FUNCTION IF EXISTS user_has_record_permission(bigint,bigint,text);
DROP FUNCTION IF EXISTS user_can_view_aggregation(bigint,bigint);
DROP FUNCTION IF EXISTS user_has_aggregation_permission(bigint,bigint,text);
DROP FUNCTION IF EXISTS user_has_global_privilege(bigint,text);
DROP TABLE IF EXISTS record_acl_grants;
DROP TABLE IF EXISTS aggregation_child_record_acl_defaults;
DROP TABLE IF EXISTS aggregation_child_aggregation_acl_defaults;
DROP TABLE IF EXISTS aggregation_acl_grants;
DROP TABLE IF EXISTS permission_dependencies;
DROP TABLE IF EXISTS permissions;
DROP TRIGGER IF EXISTS aggregations_initialize_acls ON aggregations;
DROP TRIGGER IF EXISTS records_initialize_acls ON records;
DROP TRIGGER IF EXISTS aggregations_normalize_acl_inheritance ON aggregations;
DROP FUNCTION IF EXISTS initialize_resource_acls();
DROP FUNCTION IF EXISTS normalize_aggregation_acl_inheritance();
DROP FUNCTION IF EXISTS validate_acl_dependencies();
DROP FUNCTION IF EXISTS validate_acl_permission_type();
DROP FUNCTION IF EXISTS validate_acl_role_clearance();
ALTER TABLE aggregations
    DROP CONSTRAINT IF EXISTS aggregations_root_acl_inheritance_valid,
    DROP CONSTRAINT IF EXISTS aggregations_acl_versions_positive,
    DROP CONSTRAINT IF EXISTS aggregations_child_acl_mode_valid,
    DROP COLUMN IF EXISTS inherit_acl_from_parent,
    DROP COLUMN IF EXISTS default_child_aggregation_acl_mode,
    DROP COLUMN IF EXISTS resource_acl_version,
    DROP COLUMN IF EXISTS child_aggregation_acl_version,
    DROP COLUMN IF EXISTS child_record_acl_version;
ALTER TABLE records
    DROP COLUMN IF EXISTS inherit_acl_from_parent,
    DROP COLUMN IF EXISTS resource_acl_version;
ALTER TABLE roles
    DROP CONSTRAINT IF EXISTS roles_everyone_code_reserved,
    DROP CONSTRAINT IF EXISTS roles_everyone_name_reserved;
DELETE FROM schema_migrations WHERE version='035_enforce_resource_read_authorization';
DELETE FROM schema_migrations WHERE version='036_enforce_resource_mutation_authorization';
DELETE FROM schema_migrations WHERE version='037_enforce_draft_component_authorization';
DELETE FROM schema_migrations WHERE version='034_add_resource_acl_inheritance';
DROP TABLE IF EXISTS user_favourite_records;
DROP TABLE IF EXISTS user_favourite_aggregations;
DELETE FROM schema_migrations WHERE version IN (
    '028_add_user_favourites',
    '030_remove_assignment_attribution_and_prepare_user_deletion'
);
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
    '018_rename_system_actor_to_automated_process',
    '043_add_event_reference_snapshots'
);
DROP TRIGGER IF EXISTS event_history_populate_relationship_snapshot ON event_history;
DROP TRIGGER IF EXISTS event_history_populate_reference_snapshots ON event_history;
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
DROP TABLE IF EXISTS content_upload_sessions;
DROP TABLE IF EXISTS record_draft_component_blobs;
DROP TABLE IF EXISTS record_draft_components;
DROP TABLE IF EXISTS record_drafts;
DROP TABLE IF EXISTS login_sessions;
DROP TABLE IF EXISTS user_credentials;
ALTER TABLE users DROP COLUMN IF EXISTS account_type;
DELETE FROM schema_migrations WHERE version IN ('004_add_record_drafts', '005_add_authentication');
DROP TABLE IF EXISTS digital_component_blobs;
ALTER TABLE digital_components DROP CONSTRAINT IF EXISTS digital_components_active_content_set_fk;
ALTER TABLE digital_components
    DROP COLUMN IF EXISTS active_content_set_id,
    DROP COLUMN IF EXISTS upload_completed_at;
DROP TABLE IF EXISTS digital_component_content_sets;
DROP TRIGGER IF EXISTS aggregations_bump_version ON aggregations;
DROP TRIGGER IF EXISTS records_bump_version ON records;
DROP TRIGGER IF EXISTS digital_components_bump_version ON digital_components;
DROP TRIGGER IF EXISTS org_units_bump_version ON org_units;
DROP TRIGGER IF EXISTS users_bump_version ON users;
DROP TRIGGER IF EXISTS roles_bump_version ON roles;
DROP TRIGGER IF EXISTS user_role_assignments_bump_version ON user_role_assignments;
DROP FUNCTION IF EXISTS bump_entity_version();
DROP FUNCTION IF EXISTS bump_digital_component_version();
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
DROP TABLE IF EXISTS profile_privileges;
DROP TABLE IF EXISTS privilege_dependencies;
ALTER TABLE IF EXISTS roles DROP CONSTRAINT IF EXISTS roles_profile_fk;
ALTER TABLE IF EXISTS roles DROP COLUMN IF EXISTS profile_id;
ALTER TABLE IF EXISTS roles DROP COLUMN IF EXISTS is_information_governance;
DROP TABLE IF EXISTS profiles;
DROP TABLE IF EXISTS privileges;
DROP FUNCTION IF EXISTS touch_authorization_catalogue();
DELETE FROM schema_migrations WHERE version='033_add_privileges_profiles_and_role_authorization';
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
DROP TRIGGER IF EXISTS security_levels_record_history ON security_levels;
DROP FUNCTION IF EXISTS record_entity_history();
DROP TABLE IF EXISTS event_history;
DROP FUNCTION IF EXISTS reject_event_history_mutation();
DROP FUNCTION IF EXISTS populate_event_reference_snapshots();
DROP FUNCTION IF EXISTS event_entity_identity_snapshot(text, bigint);
DROP FUNCTION IF EXISTS event_state_reference_snapshots(jsonb);
DROP FUNCTION IF EXISTS event_reference_identity(text, bigint);
DELETE FROM schema_migrations WHERE version = '001_add_event_history';
DROP FUNCTION IF EXISTS current_user_owns_open_draft(bigint);
DROP FUNCTION IF EXISTS current_user_can_record_component_operation(bigint,text,text);
DROP FUNCTION IF EXISTS user_has_destination_record_permission(bigint,bigint,text);
