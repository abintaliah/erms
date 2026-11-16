BEGIN;
-- Sent-message lifecycle and atomic connected-group cleanup.
CREATE FUNCTION messaging_mailbox_envelope_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW)-ARRAY['sender_deleted_at','sender_purge_after']) IS DISTINCT FROM
    (to_jsonb(OLD)-ARRAY['sender_deleted_at','sender_purge_after'])
 OR (OLD.sender_purge_after IS NOT NULL AND NEW.sender_purge_after IS DISTINCT FROM OLD.sender_purge_after AND NOT (NEW.sender_purge_after IS NULL AND NEW.sender_deleted_at IS NULL AND OLD.expires_at>CURRENT_TIMESTAMP))
 OR (NEW.sender_deleted_at IS NOT NULL AND NEW.sender_purge_after IS NULL) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_immutable';
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER message_envelopes_immutable ON message_envelopes;
CREATE TRIGGER message_envelopes_immutable BEFORE UPDATE ON message_envelopes FOR EACH ROW EXECUTE FUNCTION messaging_mailbox_envelope_update();
CREATE TRIGGER message_envelopes_no_delete BEFORE DELETE ON message_envelopes FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE OR REPLACE FUNCTION messaging_delivery_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (to_jsonb(NEW)-ARRAY['read_at','deleted_at','purge_after','deletion_reason']) IS DISTINCT FROM
    (to_jsonb(OLD)-ARRAY['read_at','deleted_at','purge_after','deletion_reason'])
 OR (OLD.read_at IS NOT NULL AND NEW.read_at IS DISTINCT FROM OLD.read_at)
 OR (OLD.purge_after IS NOT NULL AND NEW.purge_after IS DISTINCT FROM OLD.purge_after AND NOT (NEW.purge_after IS NULL AND NEW.deleted_at IS NULL AND EXISTS(SELECT 1 FROM message_envelopes WHERE id=OLD.envelope_id AND expires_at>CURRENT_TIMESTAMP)))
 OR (NEW.deleted_at IS NOT NULL AND NEW.purge_after IS NULL) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_delivery_immutable';
 END IF;
 RETURN NEW;
END $$;
-- Only members of the transaction-local, fully rechecked purge set may be deleted.
CREATE OR REPLACE FUNCTION messaging_reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE envelope uuid; allowed boolean;
BEGIN
 IF TG_OP='DELETE' AND TG_TABLE_NAME=ANY(ARRAY['message_envelopes','message_envelope_localizations',
 'message_recipient_selectors','message_addressees','message_deliveries','message_resource_links',
 'message_action_completions','message_action_amendments']) AND to_regclass('pg_temp.messaging_purge_members') IS NOT NULL THEN
  envelope:=CASE TG_TABLE_NAME WHEN 'message_envelopes' THEN (to_jsonb(OLD)->>'id')::uuid
   WHEN 'message_action_amendments' THEN (to_jsonb(OLD)->>'original_envelope_id')::uuid
   WHEN 'message_action_completions' THEN (to_jsonb(OLD)->>'reply_envelope_id')::uuid
   ELSE (to_jsonb(OLD)->>'envelope_id')::uuid END;
  EXECUTE 'SELECT EXISTS(SELECT 1 FROM pg_temp.messaging_purge_members WHERE id=$1)' INTO allowed USING envelope;
  IF allowed THEN RETURN OLD; END IF;
 END IF;
 RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_immutable';
END $$;
CREATE FUNCTION messaging_receipt_purge_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF to_regclass('pg_temp.messaging_purge_members') IS NULL
 OR (to_jsonb(NEW)-'result_purged_at') IS DISTINCT FROM (to_jsonb(OLD)-'result_purged_at')
 OR OLD.result_purged_at IS NOT NULL OR NEW.result_purged_at IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_receipt_immutable';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_temp.messaging_purge_members WHERE id=OLD.result_envelope_id) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_receipt_immutable';
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER message_request_receipts_immutable ON message_request_receipts;
CREATE TRIGGER message_request_receipts_immutable BEFORE UPDATE ON message_request_receipts FOR EACH ROW EXECUTE FUNCTION messaging_receipt_purge_update();
CREATE TRIGGER message_request_receipts_no_delete BEFORE DELETE ON message_request_receipts FOR EACH ROW EXECUTE FUNCTION messaging_reject_mutation();
CREATE INDEX message_delivery_cleanup_idx ON message_deliveries(purge_after,envelope_id);
CREATE INDEX message_draft_cleanup_idx ON message_drafts(expires_at,purge_after,id);

-- Store the expiry restoration policy with each message; restart settings only
-- affect new messages, never an existing message's restoration deadline.
ALTER TABLE message_envelopes ADD COLUMN expiry_restoration_days integer NOT NULL DEFAULT 30 CHECK(expiry_restoration_days BETWEEN 1 AND 36500);
CREATE TABLE message_capture_drafts (
 draft_id bigint PRIMARY KEY REFERENCES record_drafts(id) ON DELETE CASCADE,
 capture_id uuid NOT NULL UNIQUE,
 selected_envelope_id uuid NOT NULL,
 root_envelope_id uuid NOT NULL,
 language_tag text NOT NULL,
 direction text NOT NULL CHECK(direction IN('ltr','rtl'))
);
-- Draft source identifiers are historical references, not retention edges.

CREATE TABLE messaging_operational_metrics (
 metric text NOT NULL, instance_id text NOT NULL DEFAULT '', producer_code text NOT NULL DEFAULT '',
 value double precision NOT NULL DEFAULT 0, observations bigint NOT NULL DEFAULT 0,
 last_observed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
 unresolved_since timestamptz,
 PRIMARY KEY(metric,instance_id,producer_code)
);
CREATE TABLE messaging_gateway_health (
 instance_id uuid PRIMARY KEY, observed_at timestamptz NOT NULL,
 listener_connected boolean NOT NULL, listener_generation bigint NOT NULL,
 notifications_received bigint NOT NULL, last_notification_at timestamptz,
 active_connections integer NOT NULL, slow_disconnects bigint NOT NULL
);
CREATE FUNCTION messaging_count_delivery() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO messaging_operational_metrics(metric,value,observations)
 VALUES('notifications_emitted',1,1) ON CONFLICT(metric,instance_id,producer_code)
 DO UPDATE SET value=messaging_operational_metrics.value+1,observations=messaging_operational_metrics.observations+1,last_observed_at=CURRENT_TIMESTAMP;
 IF NOT (SELECT is_test FROM message_envelopes WHERE id=NEW.envelope_id) THEN
  INSERT INTO messaging_operational_metrics(metric,value,observations) VALUES('fanout_count',1,1)
  ON CONFLICT(metric,instance_id,producer_code) DO UPDATE SET value=messaging_operational_metrics.value+1,observations=messaging_operational_metrics.observations+1,last_observed_at=CURRENT_TIMESTAMP;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER message_delivery_metric AFTER INSERT ON message_deliveries FOR EACH ROW EXECUTE FUNCTION messaging_count_delivery();

CREATE TABLE messaging_cleanup_groups (
 group_key uuid PRIMARY KEY,
 member_count bigint NOT NULL,
 expired_count bigint NOT NULL,
 eligible_at timestamptz NOT NULL,
 observed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
 failure_count bigint NOT NULL DEFAULT 0,
 oldest_failure_at timestamptz
);

ALTER TABLE message_drafts ADD COLUMN expiry_restoration_days integer NOT NULL DEFAULT 30 CHECK(expiry_restoration_days BETWEEN 1 AND 36500);

INSERT INTO schema_migrations(version) VALUES ('037_messaging_retention') ON CONFLICT DO NOTHING;
COMMIT;
