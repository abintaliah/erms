BEGIN;
-- Approved legal-hold expiry reminder checkpoints. No message content is retained here.
CREATE TABLE hold_notification_reminders (
    hold_id bigint NOT NULL REFERENCES holds(id) ON DELETE CASCADE,
    end_at timestamptz NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (hold_id, end_at)
);
CREATE INDEX holds_notification_due_idx ON holds(valid_to,id) WHERE valid_to IS NOT NULL;
INSERT INTO schema_migrations(version) VALUES ('038_legal_hold_notifications');
COMMIT;
