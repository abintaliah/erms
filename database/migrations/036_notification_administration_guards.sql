BEGIN;

-- A technical serialization row makes concurrent language/configuration writes
-- visible to repeatable-read/serializable snapshots as well as read committed.
CREATE TABLE messaging_notification_configuration_guard (
 singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
 revision bigint NOT NULL
);

-- Coordinate language enablement and activation, preserving complete coverage.
CREATE FUNCTION messaging_guard_notification_coverage() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE active_id uuid;
BEGIN
 INSERT INTO messaging_notification_configuration_guard(singleton,revision) VALUES (true,1)
 ON CONFLICT(singleton) DO UPDATE SET revision=messaging_notification_configuration_guard.revision+1;
 IF TG_TABLE_NAME='system_notification_producers' THEN
  active_id := NEW.active_configuration_version_id;
  IF active_id IS NULL THEN
   RETURN NEW;
  END IF;
  IF NEW.required_for_business_commit AND NOT EXISTS (
   SELECT 1 FROM system_notification_configuration_versions WHERE id=active_id AND enabled
  ) THEN
   RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='notification_required_cannot_disable';
  END IF;
  IF EXISTS (
   SELECT 1 FROM supported_languages l WHERE (l.is_enabled OR l.language_tag='en')
   AND NOT EXISTS (SELECT 1 FROM system_notification_configuration_translations t
    WHERE t.configuration_version_id=active_id AND t.language_tag=l.language_tag
    AND t.review_status='published' AND t.reviewed_by_user_id IS NOT NULL AND t.reviewed_at IS NOT NULL
    AND btrim(t.subject_template)<>'' AND btrim(t.body_template_rich_text)<>'')
  ) THEN
   RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='notification_language_coverage_required';
  END IF;
 ELSIF NEW.is_enabled AND EXISTS (
  SELECT 1 FROM system_notification_producers p WHERE p.active_configuration_version_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM system_notification_configuration_translations t
   WHERE t.configuration_version_id=p.active_configuration_version_id AND t.language_tag=NEW.language_tag
   AND t.review_status='published' AND t.reviewed_by_user_id IS NOT NULL AND t.reviewed_at IS NOT NULL)
 ) THEN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='notification_language_coverage_required';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER notification_active_coverage BEFORE INSERT OR UPDATE ON system_notification_producers
 FOR EACH ROW EXECUTE FUNCTION messaging_guard_notification_coverage();
CREATE TRIGGER notification_language_coverage BEFORE INSERT OR UPDATE OF is_enabled ON supported_languages
 FOR EACH ROW EXECUTE FUNCTION messaging_guard_notification_coverage();
CREATE INDEX notification_test_history_idx ON event_history ((metadata->>'producer_code'),id DESC)
 WHERE entity_type='system_notification' AND operation IN ('NOTIFICATION_TEST_SENT','NOTIFICATION_TEST_FAILED');
CREATE INDEX notification_test_rate_idx ON event_history (actor_user_id,occurred_at)
 WHERE operation='NOTIFICATION_TEST_SENT';

INSERT INTO schema_migrations(version) VALUES ('036_notification_administration_guards');
COMMIT;
