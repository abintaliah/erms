BEGIN;
ALTER TABLE system_notification_producers ADD COLUMN name text CHECK(name IS NULL OR btrim(name)<>'');
ALTER TABLE system_notification_producers ADD COLUMN translations jsonb CHECK(translations IS NULL OR jsonb_typeof(translations)='object');
CREATE TRIGGER system_notification_producers_validate_translations BEFORE INSERT OR UPDATE OF translations ON system_notification_producers FOR EACH ROW EXECUTE FUNCTION validate_multilingual_entity_translations();
INSERT INTO schema_migrations(version) VALUES ('039_localized_notification_producer_names');
COMMIT;
