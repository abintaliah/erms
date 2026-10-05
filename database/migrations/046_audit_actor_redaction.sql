BEGIN;
-- Filter only actor snapshots the viewer is authorized to see.
CREATE OR REPLACE VIEW authorized_event_history AS
SELECT event.id,event.occurred_at,event.transaction_id,event.entity_type,event.entity_id,
       event.operation,
       CASE WHEN visible.allowed THEN event.actor_user_id END AS actor_user_id,
       CASE WHEN visible.allowed THEN event.actor_name END AS actor_name,
       CASE WHEN visible.allowed THEN event.actor_email END AS actor_email,
       event.actor_type,
       event.source,event.request_id,event.correlation_id,
       CASE WHEN visible.allowed THEN event.before_state ELSE NULL END AS before_state,
       CASE WHEN visible.allowed THEN event.after_state ELSE NULL END AS after_state,
       CASE WHEN visible.allowed THEN event.changed_fields ELSE ARRAY[]::text[] END AS changed_fields,
       CASE WHEN visible.allowed THEN event.reason ELSE NULL END AS reason,
       CASE WHEN visible.allowed THEN event.metadata
            ELSE jsonb_build_object('redacted',true,'reason','resource_access_denied') END AS metadata
FROM event_history event
CROSS JOIN LATERAL (
  SELECT current_user_can_view_event_resource(
    event.entity_type,event.entity_id,event.before_state,event.after_state
  ) AS allowed
) visible;

INSERT INTO schema_migrations(version) VALUES ('046_audit_actor_redaction');
COMMIT;
