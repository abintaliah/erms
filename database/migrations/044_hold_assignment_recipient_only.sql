BEGIN;
-- Revised approval: governors receive expiry reminders, not assignment events.
-- Preserve administrator configurations, wording and existing deliveries.
UPDATE system_notification_producers SET contract_version=3
WHERE producer_code='holds.responsibility_assigned' AND contract_version IN (1,2);
INSERT INTO schema_migrations(version) VALUES ('044_hold_assignment_recipient_only');
COMMIT;
