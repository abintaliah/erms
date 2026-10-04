BEGIN;

-- Actions belong to To recipients; Cc copies are informational.
CREATE OR REPLACE FUNCTION messaging_validate_completion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM message_deliveries d JOIN message_envelopes original ON original.id=d.envelope_id
 JOIN message_envelopes reply ON reply.id=NEW.reply_envelope_id
 WHERE d.id=NEW.original_delivery_id AND d.recipient_user_id=NEW.completed_by_user_id
 AND d.recipient_type='to'
 AND reply.sender_user_id=NEW.completed_by_user_id AND reply.relationship_kind='reply'
 AND reply.related_delivery_id=d.id AND NEW.completed_by_user_id=current_user_id()
 AND EXISTS(SELECT 1 FROM message_addressees a WHERE a.envelope_id=reply.id AND a.user_id=original.sender_user_id AND a.recipient_type='to')
 AND original.action_required AND original.message_kind='user_message'
 AND NOT EXISTS(SELECT 1 FROM message_action_amendments a WHERE a.original_envelope_id=original.id AND NOT a.new_action_required)) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='message_completion_invalid';
 END IF;
 RETURN NULL;
END $$;

INSERT INTO schema_migrations(version) VALUES ('041_to_recipient_action_completion');

COMMIT;
