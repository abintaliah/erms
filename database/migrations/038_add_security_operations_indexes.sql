BEGIN;

SELECT set_config('app.actor_type','automated_process',true),
       set_config('app.actor_name','Database migration 038',true),
       set_config('app.event_source','migration',true),
       set_config('app.change_reason','Index Phase 11 security monitoring workloads',true),
       set_config('app.event_metadata','{"migration":"038_add_security_operations_indexes"}',true);

CREATE INDEX IF NOT EXISTS event_history_security_operation_timeline_idx
    ON event_history (operation, occurred_at DESC)
    WHERE operation IN (
        'AUTHORIZATION_DENIED','AUTHENTICATION_FAILED','ACCOUNT_LOCKED',
        'INFORMATION_GOVERNANCE_BYPASS_USED','ACCESS_EXPLANATION_VIEWED',
        'SECURITY_LEVEL_CHANGED','SECURITY_LEVEL_UPGRADED','SECURITY_LEVEL_DOWNGRADED',
        'ACL_REPLACED','DEFAULT_CHILD_AGGREGATION_ACL_REPLACED',
        'DEFAULT_CHILD_RECORD_ACL_REPLACED','PROFILE_PRIVILEGES_REPLACED',
        'PROFILE_ASSIGNED','GOVERNANCE_ROLE_CHANGED'
    );

INSERT INTO schema_migrations(version)
VALUES ('038_add_security_operations_indexes')
ON CONFLICT (version) DO NOTHING;

COMMIT;
