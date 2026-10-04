BEGIN;
DO $$
DECLARE t text; constraint_name text;
BEGIN
 FOREACH t IN ARRAY ARRAY['message_recipient_selectors','message_draft_recipient_selectors'] LOOP
  FOR constraint_name IN SELECT conname FROM pg_constraint
   WHERE conrelid=t::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%selector_kind%'
  LOOP EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I',t,constraint_name); END LOOP;
  EXECUTE format($ddl$ALTER TABLE %I ADD CHECK(
   (selector_kind='user' AND user_id IS NOT NULL AND role_id IS NULL AND org_unit_id IS NULL)
   OR (selector_kind='role' AND role_id IS NOT NULL AND user_id IS NULL AND org_unit_id IS NULL)
   OR (selector_kind='org_unit' AND org_unit_id IS NOT NULL AND user_id IS NULL AND role_id IS NULL)
   OR (selector_kind='everyone' AND user_id IS NULL AND role_id IS NULL AND org_unit_id IS NULL))$ddl$,t);
 END LOOP;
END $$;
CREATE UNIQUE INDEX message_recipient_selectors_everyone_unique ON message_recipient_selectors(envelope_id,recipient_type) WHERE selector_kind='everyone';
CREATE UNIQUE INDEX message_draft_recipient_selectors_everyone_unique ON message_draft_recipient_selectors(draft_id,recipient_type) WHERE selector_kind='everyone';
INSERT INTO schema_migrations(version) VALUES ('042_messaging_everyone');
COMMIT;
