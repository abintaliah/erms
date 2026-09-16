-- Preserve the human-readable user and role identities on assignment audit
-- events so the audit trail never needs to render opaque foreign keys or rely
-- on the current user/role rows.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE FUNCTION populate_event_relationship_snapshot()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    assignment_state jsonb;
    user_snapshot     jsonb;
    role_snapshot     jsonb;
BEGIN
    IF NEW.entity_type <> 'user_role_assignment' THEN
        RETURN NEW;
    END IF;

    assignment_state := COALESCE(NEW.after_state, NEW.before_state);
    SELECT jsonb_build_object('id', id, 'name', name, 'email', email)
    INTO user_snapshot
    FROM users
    WHERE id = (assignment_state ->> 'user_id')::bigint;

    SELECT jsonb_build_object('id', id, 'code', code, 'name', name)
    INTO role_snapshot
    FROM roles
    WHERE id = (assignment_state ->> 'role_id')::bigint;

    NEW.metadata := NEW.metadata || jsonb_build_object(
        'assignment_parties',
        jsonb_build_object('user', user_snapshot, 'role', role_snapshot)
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS event_history_populate_relationship_snapshot ON event_history;
CREATE TRIGGER event_history_populate_relationship_snapshot
BEFORE INSERT ON event_history
FOR EACH ROW EXECUTE FUNCTION populate_event_relationship_snapshot();

DROP TRIGGER IF EXISTS event_history_reject_update_delete ON event_history;

UPDATE event_history AS event
SET metadata = event.metadata || jsonb_build_object(
        'assignment_parties',
        jsonb_build_object(
            'user', jsonb_build_object(
                'id', assigned_user.id,
                'name', assigned_user.name,
                'email', assigned_user.email
            ),
            'role', jsonb_build_object(
                'id', assigned_role.id,
                'code', assigned_role.code,
                'name', assigned_role.name
            )
        )
    )
FROM users AS assigned_user, roles AS assigned_role
WHERE event.entity_type = 'user_role_assignment'
  AND assigned_user.id = (
      COALESCE(event.after_state, event.before_state) ->> 'user_id'
  )::bigint
  AND assigned_role.id = (
      COALESCE(event.after_state, event.before_state) ->> 'role_id'
  )::bigint;

CREATE TRIGGER event_history_reject_update_delete
BEFORE UPDATE OR DELETE ON event_history
FOR EACH ROW EXECUTE FUNCTION reject_event_history_mutation();

INSERT INTO schema_migrations(version)
VALUES ('016_snapshot_role_assignment_parties')
ON CONFLICT(version) DO NOTHING;
