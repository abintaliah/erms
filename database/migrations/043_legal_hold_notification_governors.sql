BEGIN;
-- Approved 4 October 2026: both legal-hold audiences include effective governors.
-- Preserve all administrator configuration and wording.
UPDATE system_notification_producers SET contract_version=2
WHERE producer_code IN ('holds.responsibility_assigned','holds.approaching_end')
AND contract_version=1;
INSERT INTO schema_migrations(version) VALUES ('043_legal_hold_notification_governors');
COMMIT;
