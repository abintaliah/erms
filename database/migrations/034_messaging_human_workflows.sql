BEGIN;

CREATE OR REPLACE FUNCTION messaging_validate_envelope() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE e message_envelopes; parent message_envelopes;
BEGIN
 SELECT * INTO e FROM message_envelopes WHERE id=NEW.id;
 IF NOT FOUND THEN RETURN NULL; END IF;
 IF NOT EXISTS(SELECT 1 FROM message_recipient_selectors WHERE envelope_id=e.id AND recipient_type='to')
 OR NOT EXISTS(SELECT 1 FROM message_addressees WHERE envelope_id=e.id AND recipient_type='to')
 OR EXISTS(SELECT 1 FROM message_addressees a LEFT JOIN message_deliveries d
       ON d.envelope_id=a.envelope_id AND d.recipient_user_id=a.user_id
       WHERE a.envelope_id=e.id AND (d.id IS NULL OR a.user_id=e.sender_user_id))
 OR NOT EXISTS(SELECT 1 FROM message_request_receipts WHERE result_envelope_id=e.id) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_incomplete_fanout';
 END IF;
 IF e.sender_kind='system' AND e.security_level_id<>(SELECT id FROM security_levels ORDER BY level_number LIMIT 1) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_system_level';
 END IF;
 IF e.action_due_date IS NOT NULL AND
   (NOT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=e.action_due_timezone)
    OR e.action_due_at IS DISTINCT FROM ((e.action_due_date+1)::timestamp AT TIME ZONE e.action_due_timezone)) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_due_boundary';
 END IF;
 IF e.related_delivery_id IS NOT NULL THEN
  SELECT original.* INTO parent FROM message_envelopes original
  JOIN message_deliveries d ON d.envelope_id=original.id
  WHERE d.id=e.related_delivery_id AND d.recipient_user_id=e.sender_user_id;
 ELSIF e.related_envelope_id IS NOT NULL THEN
  SELECT * INTO parent FROM message_envelopes WHERE id=e.related_envelope_id AND sender_user_id=e.sender_user_id;
 END IF;
 IF e.relationship_kind IS NOT NULL AND (parent.id IS NULL OR parent.message_kind='action_amendment_notice'
 OR parent.is_test OR (SELECT level_number FROM security_levels WHERE id=parent.security_level_id)>
 (SELECT level_number FROM security_levels WHERE id=e.security_level_id)) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_relationship_invalid';
 END IF;
 RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION messaging_validate_completion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM message_deliveries d JOIN message_envelopes original ON original.id=d.envelope_id
 JOIN message_envelopes reply ON reply.id=NEW.reply_envelope_id
 WHERE d.id=NEW.original_delivery_id AND d.recipient_user_id=NEW.completed_by_user_id
 AND reply.sender_user_id=NEW.completed_by_user_id AND reply.relationship_kind='reply'
 AND reply.related_delivery_id=d.id AND NEW.completed_by_user_id=current_user_id()
 AND EXISTS(SELECT 1 FROM message_addressees a WHERE a.envelope_id=reply.id AND a.user_id=original.sender_user_id AND a.recipient_type='to')
 AND original.action_required AND original.message_kind='user_message'
 AND NOT EXISTS(SELECT 1 FROM message_action_amendments a WHERE a.original_envelope_id=original.id AND NOT a.new_action_required)) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_completion_invalid';
 END IF;
 RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION messaging_validate_amendment() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original message_envelopes; previous message_action_amendments;
BEGIN
 SELECT * INTO original FROM message_envelopes WHERE id=NEW.original_envelope_id FOR UPDATE;
 SELECT * INTO previous FROM message_action_amendments WHERE original_envelope_id=NEW.original_envelope_id
 AND sequence<NEW.sequence ORDER BY sequence DESC LIMIT 1;
 IF original.message_kind<>'user_message' OR NOT original.action_required OR original.sender_user_id<>NEW.created_by_user_id
 OR original.is_test OR original.sender_deleted_at IS NOT NULL OR original.expires_at<=clock_timestamp()
 OR NEW.created_by_user_id<>current_user_id()
 OR (NEW.new_due_at IS NOT NULL AND NEW.new_due_at<=clock_timestamp())
 OR NEW.sequence<>COALESCE(previous.sequence,0)+1
 OR ROW(NEW.previous_action_required,NEW.previous_due_date,NEW.previous_due_timezone,NEW.previous_due_at)
 IS DISTINCT FROM ROW(COALESCE(previous.new_action_required,original.action_required),
 CASE WHEN previous.id IS NULL THEN original.action_due_date ELSE previous.new_due_date END,
 CASE WHEN previous.id IS NULL THEN original.action_due_timezone ELSE previous.new_due_timezone END,
 CASE WHEN previous.id IS NULL THEN original.action_due_at ELSE previous.new_due_at END)
 OR NOT EXISTS(SELECT 1 FROM message_envelopes WHERE action_amendment_id=NEW.id AND sender_user_id=NEW.created_by_user_id)
 THEN RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_amendment_invalid'; END IF;
 RETURN NULL;
END $$;

INSERT INTO schema_migrations(version) VALUES ('034_messaging_human_workflows') ON CONFLICT(version) DO NOTHING;
COMMIT;
