BEGIN;
-- Transactional wake-up hints; PostgreSQL releases NOTIFY only after commit.
CREATE OR REPLACE FUNCTION messaging_notify_delivery() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('wathiq_messages', json_build_object(
        'delivery_id', NEW.id,
        'recipient_user_id', NEW.recipient_user_id,
        'mailbox_sequence', NEW.mailbox_sequence
    )::text);
    RETURN NEW;
END;
$$;
CREATE TRIGGER message_delivery_notify AFTER INSERT ON message_deliveries
FOR EACH ROW EXECUTE FUNCTION messaging_notify_delivery();
INSERT INTO schema_migrations(version) VALUES ('035_messaging_live_signals') ON CONFLICT DO NOTHING;
COMMIT;
